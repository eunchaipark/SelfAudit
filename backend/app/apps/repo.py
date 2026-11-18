"""앱 저장소. 쿼리는 ORM으로만."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import App


def find_by_name_key(session: Session, key: str) -> App | None:
    return session.scalars(select(App).where(App.name_key == key)).first()
