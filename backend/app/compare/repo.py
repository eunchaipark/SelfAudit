"""비교 저장소: 점검과 그 발견을 읽기만 한다. 쿼리는 ORM으로만."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FindingRow, Scan


def get_scan(session: Session, scan_id: int) -> Scan | None:
    return session.get(Scan, scan_id)


def list_findings(session: Session, scan_id: int) -> Sequence[FindingRow]:
    """점검의 발견을 F-S06 정렬 순서(저장된 order)로."""
    query = (
        select(FindingRow)
        .where(FindingRow.scan_id == scan_id)
        .order_by(FindingRow.order, FindingRow.id)
    )
    return session.scalars(query).all()
