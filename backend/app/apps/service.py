"""앱 흐름: 읽기 → 엔진 → 저장. 트랜잭션 경계는 여기."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps import engine, repo
from app.apps.engine import ScanRecord
from app.contracts.schemas import AppIn
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.limits import CONSENT_VERSION
from app.core.workdirs import remove_work_dirs
from app.db.models import App

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
