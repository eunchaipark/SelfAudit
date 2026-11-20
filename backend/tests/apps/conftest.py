"""앱 영역 테스트 도우미: 점검 기록을 DB에 바로 넣는다 (점검 흐름은 다른 레인이 만든다)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.limits import CONSENT_VERSION
from app.db.models import App, Scan

AddApp = Callable[..., int]
AddScan = Callable[..., int]
REGISTERED_AT = datetime(2026, 11, 15, 1, 0, tzinfo=UTC)  # 가상 시각


@pytest.fixture
def db(client: TestClient) -> sessionmaker[Session]:
    factory: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def add_app(db: sessionmaker[Session]) -> AddApp:
    def _add(name: str, kind: str = "mine") -> int:
        with db() as session:
            app = App(
                name=name,
                name_key=name.casefold(),
                kind=kind,
                source_url="https://example.com/app" if kind == "practice" else None,
                consent_version=CONSENT_VERSION,
                created_at=REGISTERED_AT,
            )
            session.add(app)
            session.commit()
            return app.id

    return _add


@pytest.fixture
def add_scan(db: sessionmaker[Session]) -> AddScan:
    def _add(
        app_id: int,
        started_at: datetime,
        status: str = "done",
        score: int | None = None,
        counts: tuple[int, int, int] = (0, 0, 0),
        input_name: str = "dist.zip",
    ) -> int:
        high, medium, low = counts
        with db() as session:
            scan = Scan(
                app_id=app_id,
                status=status,
                started_at=started_at,
                input_name=input_name,
                score=score,
                high=high,
                medium=medium,
                low=low,
            )
            session.add(scan)
            session.commit()
            return scan.id

    return _add
