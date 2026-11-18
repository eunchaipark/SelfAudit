"""비교 API (F-C02). 뼈대: 레인이 채운다."""

from __future__ import annotations

from fastapi import APIRouter

from app.contracts.schemas import ComparisonOut, ErrorOut
from app.core.deps import SessionDep
from app.core.errors import NotImplementedYet

router = APIRouter(prefix="/api/v1", tags=["compare"])
ERRORS: dict[int | str, dict[str, object]] = {400: {"model": ErrorOut}, 404: {"model": ErrorOut}}


@router.get("/compare", responses=ERRORS)
def compare(a: int, b: int, session: SessionDep) -> ComparisonOut:
    """F-C02 두 점검 비교. 고른 순서와 상관없이 시작 시각으로 전후를 정한다."""
    raise NotImplementedYet
