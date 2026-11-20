"""앱 저장소. 쿼리는 ORM으로만."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, delete, exists, select
from sqlalchemy.orm import Session

from app.apps.engine import ScanRecord
from app.contracts.engine import ScanStatus
from app.db.models import App, Scan

# 점검 기록 한 줄에 필요한 칸만 읽는다 (발견·건너뜀은 읽지 않는다)
RECORD_COLUMNS = (
    Scan.id,
    Scan.app_id,
    Scan.started_at,
    Scan.input_name,
    Scan.status,
    Scan.score,
    Scan.high,
    Scan.medium,
    Scan.low,
)


def find_by_name_key(session: Session, key: str) -> App | None:
    return session.scalars(select(App).where(App.name_key == key)).first()


def get_app(session: Session, app_id: int) -> App | None:
    return session.get(App, app_id)


def list_apps(session: Session) -> list[App]:
    """이름순 (SCR-01 01-02). 열쇠는 casefold한 이름이라 대소문자로 갈리지 않는다."""
    return list(session.scalars(select(App).order_by(App.name_key, App.id)))


def scan_records(session: Session, app_id: int) -> list[ScanRecord]:
    rows = session.execute(select(*RECORD_COLUMNS).where(Scan.app_id == app_id))
    return [ScanRecord(*row) for row in rows]


def done_scan_records(session: Session) -> list[ScanRecord]:
    rows = session.execute(select(*RECORD_COLUMNS).where(Scan.status == ScanStatus.DONE))
    return [ScanRecord(*row) for row in rows]


def delete_app_if_idle(session: Session, app_id: int) -> bool:
    """앱을 지운다. 그 앱에 `진행 중` 점검이 있으면 지우지 않고 False.

    확인과 지우기를 한 문장으로 해서, 확인한 뒤 점검이 새로 시작돼도 진행 중 점검을 지우지 않는다.
    점검·발견·건너뜀·참고는 DB의 ON DELETE CASCADE가 함께 지운다.
    """
    running = exists().where(Scan.app_id == app_id, Scan.status == ScanStatus.RUNNING)
    stmt = delete(App).where(App.id == app_id, ~running)
    result = cast(
        CursorResult[Any], session.execute(stmt, execution_options={"synchronize_session": False})
    )
    return result.rowcount == 1
