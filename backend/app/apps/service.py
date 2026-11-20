"""앱 흐름: 읽기 → 엔진 → 저장. 트랜잭션 경계는 여기."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps import engine, repo
from app.apps.engine import ScanRecord
from app.contracts.schemas import AppIn
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.limits import CONSENT_VERSION
from app.db.models import App

log = logging.getLogger("selfaudit")
DUPLICATE_CODE = "DUPLICATE_NAME"


def register_app(session: Session, data: AppIn, now: datetime) -> App:
    """F-P01 앱 등록 (FR-01). 예외 문구의 차례는 명세 예외 칸의 차례를 따른다."""
    name = engine.normalize_name(data.name)
    key = engine.name_key(name)
    if repo.find_by_name_key(session, key) is not None:
        raise Conflict(engine.MSG_DUPLICATE, code=DUPLICATE_CODE)
    source_url = engine.check_source_and_consent(data.kind, data.source_url, data.consent)
    app = App(
        name=name,
        name_key=key,
        kind=data.kind,
        source_url=source_url,
        consent_version=CONSENT_VERSION,
        created_at=now,
    )
    session.add(app)
    try:
        session.commit()
    except IntegrityError:
        # 같은 이름을 동시에 등록한 경우. unique 제약이 마지막으로 막는다
        session.rollback()
        raise Conflict(engine.MSG_DUPLICATE, code=DUPLICATE_CODE) from None
    return app


def get_app(session: Session, app_id: int) -> App:
    """SCR-03 머리줄의 앱 하나. 없으면 404."""
    app = repo.get_app(session, app_id)
    if app is None:
        raise NotFound()
    return app


def list_apps(session: Session) -> list[tuple[App, ScanRecord | None]]:
    """F-P02 4 앱 목록(이름순)과 앱마다 가장 최근 `완료` 점검."""
    latest = engine.latest_done_by_app(repo.done_scan_records(session))
    return [(app, latest.get(app.id)) for app in repo.list_apps(session)]


def list_scans(session: Session, app_id: int) -> list[ScanRecord]:
    """F-P02 1~3 그 앱의 점검 기록 (최신순, 완료가 아니면 점수·개수 없음)."""
    get_app(session, app_id)
    records = engine.newest_first(repo.scan_records(session, app_id))
    return [engine.shown(record) for record in records]


def delete_app(session: Session, work_dir: Path, app_id: int) -> int:
    """F-P03 1·3·4 앱과 그 점검을 모두 지우고 지운 점검 수를 돌려준다.

    확인(1)은 API가 `confirm=true`로만 받는다. 예외 차례: 없는 앱(404) → 진행 중(400).
    """
    get_app(session, app_id)
    records = repo.scan_records(session, app_id)
    engine.check_deletable(record.status for record in records)
    if not repo.delete_app_if_idle(session, app_id):
        # 확인한 뒤 점검이 시작됐다
        session.rollback()
        raise ValidationFailed(engine.MSG_RUNNING)
    session.commit()
    remove_work_dirs(work_dir, [record.id for record in records])
    return len(records)


def remove_work_dirs(work_dir: Path, scan_ids: list[int]) -> None:
    """F-P03 2 남아 있는 격리 폴더 `work/<점검ID>/`를 지운다.

    보통은 점검이 끝날 때(F-I01 11) 이미 지워져 있다. 여기서 못 지운 폴더는 서버가 다음에
    시작할 때 지운다(F-I01 12). DB는 이미 지웠으므로 오류로 돌려주지 않고 로그만 남긴다.
    """
    for scan_id in scan_ids:
        folder = work_dir / str(scan_id)
        if not folder.is_dir():
            continue
        try:
            shutil.rmtree(folder)
        except OSError as err:
            log.warning("격리 폴더를 지우지 못했습니다: 점검 %d (%s)", scan_id, type(err).__name__)
