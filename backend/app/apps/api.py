"""앱 API (F-P01~P03). 입력 검증과 응답만. 계산·DB 접근은 service로."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter
from pydantic import BeforeValidator

from app.apps import service
from app.apps.engine import ScanRecord
from app.contracts.schemas import (
    AppIn,
    AppKind,
    AppListItemOut,
    AppOut,
    DeletedOut,
    ErrorOut,
    ScanListItemOut,
    ScanStatusOut,
)
from app.core.deps import ClockDep, IdPath, SessionDep, SettingsDep
from app.db.models import App

router = APIRouter(prefix="/api/v1", tags=["apps"])
ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorOut},
    404: {"model": ErrorOut},
    409: {"model": ErrorOut},
}
CONFIRM_TEXT = "true"


def parse_confirm(value: object) -> object:
    # 쿼리 문자열은 글이라 Literal[True]가 "true"를 받지 못한다. 정확히 "true"만 참으로 읽고
    # 나머지("false", "1", 빈 값)는 그대로 넘겨 Literal 검증이 거부하게 한다 (F-P03 1)
    return True if value == CONFIRM_TEXT else value


# 계약(openapi)은 그대로 `const: true, type: boolean`이다
Confirm = Annotated[Literal[True], BeforeValidator(parse_confirm)]


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


def to_list_item(app: App, latest: ScanRecord | None) -> AppListItemOut:
    return AppListItemOut(
        id=app.id,
        name=app.name,
        kind=cast(AppKind, app.kind),
        latest_score=latest.score if latest else None,
        latest_scan_at=latest.started_at if latest else None,
    )


def to_scan_item(record: ScanRecord) -> ScanListItemOut:
    return ScanListItemOut(
        id=record.id,
        started_at=record.started_at,
        input_name=record.input_name,
        status=cast(ScanStatusOut, record.status),
        score=record.score,
        high=record.high,
        medium=record.medium,
        low=record.low,
    )


@router.get("/apps", responses=ERRORS)
def list_apps(session: SessionDep) -> list[AppListItemOut]:
    """F-P02 4 앱 목록 (이름순, 최근 완료 점검의 점수와 시각)."""
    return [to_list_item(app, latest) for app, latest in service.list_apps(session)]


@router.get("/apps/{app_id}", responses=ERRORS)
def get_app(app_id: IdPath, session: SessionDep) -> AppOut:
    """SCR-03 머리줄용 앱 하나."""
    return to_out(service.get_app(session, app_id))


@router.get("/apps/{app_id}/scans", responses=ERRORS)
def list_scans(app_id: IdPath, session: SessionDep) -> list[ScanListItemOut]:
    """F-P02 점검 기록."""
    return [to_scan_item(record) for record in service.list_scans(session, app_id)]


@router.delete("/apps/{app_id}", responses=ERRORS)
def delete_app(
    app_id: IdPath, confirm: Confirm, session: SessionDep, settings: SettingsDep
) -> DeletedOut:
    """F-P03 앱 지우기. confirm=true일 때만."""
    deleted = service.delete_app(session, settings.data.work, app_id)
    return DeletedOut(deleted_scans=deleted)
