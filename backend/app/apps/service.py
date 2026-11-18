"""앱 흐름: 읽기 → 엔진 → 저장. 트랜잭션 경계는 여기."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps import engine, repo
from app.contracts.schemas import AppIn
from app.core.errors import Conflict
from app.core.limits import CONSENT_VERSION
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
