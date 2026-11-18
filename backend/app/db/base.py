"""SQLite 연결과 공통 타입. 쿼리는 ORM 또는 바인드 파라미터로만 (보안규칙 5장)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class AwareDateTime(TypeDecorator[datetime]):
    """시간대가 있는 시각만 받고, UTC로 저장해 UTC로 돌려준다 (SQLite는 시간대를 모른다)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("시간대가 없는 시각은 저장하지 않는다")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def make_engine(url: str) -> Engine:
    # 점검은 뒤쪽 스레드에서 돈다
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
