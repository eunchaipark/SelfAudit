"""비교 API (F-C02). 입력 검증과 응답만. 계산·DB 접근은 service로."""

from __future__ import annotations

from fastapi import APIRouter

from app.compare import service
from app.compare.engine import ComparedFinding, Comparison
from app.contracts.schemas import ComparedFindingOut, ComparisonOut, ErrorOut
from app.core.deps import SessionDep

router = APIRouter(prefix="/api/v1", tags=["compare"])
ERRORS: dict[int | str, dict[str, object]] = {400: {"model": ErrorOut}, 404: {"model": ErrorOut}}


def _item_out(item: ComparedFinding) -> ComparedFindingOut:
    return ComparedFindingOut(
        rule_id=item.rule_id,
        severity=item.severity.value,
        path=item.path,
        value=item.value,
        severity_changed=item.severity_changed,
    )


def to_out(result: Comparison) -> ComparisonOut:
    return ComparisonOut(
        before_id=result.before.scan_id,
        after_id=result.after.scan_id,
        before_started_at=result.before.started_at,
        after_started_at=result.after.started_at,
        before_score=result.before.score,
        after_score=result.after.score,
        score_change=result.score_change,
        fixed=[_item_out(item) for item in result.fixed],
        remaining=[_item_out(item) for item in result.remaining],
        new=[_item_out(item) for item in result.new],
        rules_version_differs=result.rules_version_differs,
    )


@router.get("/compare", responses=ERRORS)
def compare(a: int, b: int, session: SessionDep) -> ComparisonOut:
    """F-C02 두 점검 비교. 고른 순서와 상관없이 시작 시각으로 전후를 정한다."""
    return to_out(service.compare(session, a, b))
