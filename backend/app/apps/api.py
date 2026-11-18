"""앱 API (F-P01~P03). 입력 검증과 응답만. 계산·DB 접근은 service로."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter

from app.apps import service
from app.contracts.schemas import (
    AppIn,
    AppKind,
    AppListItemOut,
    AppOut,
    DeletedOut,
    ErrorOut,
    ScanListItemOut,
)
from app.core.deps import ClockDep, SessionDep
from app.core.errors import NotImplementedYet
from app.db.models import App

router = APIRouter(prefix="/api/v1", tags=["apps"])
ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorOut},
    404: {"model": ErrorOut},
    409: {"model": ErrorOut},
}


def to_out(app: App) -> AppOut:
    return AppOut(
        id=app.id,
        name=app.name,
        kind=cast(AppKind, app.kind),
        source_url=app.source_url,
        created_at=app.created_at,
        consent_version=app.consent_version,
    )


@router.post("/apps", status_code=201, responses=ERRORS)
def create_app(body: AppIn, session: SessionDep, clock: ClockDep) -> AppOut:
    """F-P01 앱 등록."""
    return to_out(service.register_app(session, body, clock()))


@router.get("/apps", responses=ERRORS)
def list_apps(session: SessionDep) -> list[AppListItemOut]:
    """F-P02 4 앱 목록 (이름순, 최근 완료 점검의 점수와 시각)."""
    raise NotImplementedYet


@router.get("/apps/{app_id}", responses=ERRORS)
def get_app(app_id: int, session: SessionDep) -> AppOut:
    """SCR-03 머리줄용 앱 하나."""
    raise NotImplementedYet


@router.get("/apps/{app_id}/scans", responses=ERRORS)
def list_scans(app_id: int, session: SessionDep) -> list[ScanListItemOut]:
    """F-P02 점검 기록."""
    raise NotImplementedYet


@router.delete("/apps/{app_id}", responses=ERRORS)
def delete_app(app_id: int, confirm: Literal[True], session: SessionDep) -> DeletedOut:
    """F-P03 앱 지우기. confirm=true일 때만."""
    raise NotImplementedYet
