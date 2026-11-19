"""API 스키마 (설계). 화면 타입은 여기서 만든 OpenAPI로 생성한다 (frontend/src/api/schema.d.ts).

이름 규칙: 요청은 …In, 응답은 …Out. JSON 필드는 camelCase.
바꾸면 `uv run python -m app.contracts.export_openapi`로 contracts/openapi.json을 다시 만든다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

AppKind = Literal["mine", "practice"]
ScanStatusOut = Literal["running", "done", "no_target", "failed"]
SeverityOut = Literal["high", "medium", "low", "info"]
ReaStatusOut = Literal["used", "absent", "failed"]

URL_MAX = 2000
NAME_INPUT_MAX = 400  # 검사 전 길이 상한. 40자 판정은 F-P01 엔진이 한다
PATH_INPUT_MAX = 1000


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class ErrorOut(ApiModel):
    code: str
    message: str


# ---- 앱 (F-P01~P03) ----


class AppIn(ApiModel):
    name: str = Field(max_length=NAME_INPUT_MAX)
    kind: AppKind
    source_url: str | None = Field(default=None, max_length=URL_MAX)
    consent: bool


class AppOut(ApiModel):
    id: int
    name: str
    kind: AppKind
    source_url: str | None
    created_at: datetime
    consent_version: str


class AppListItemOut(ApiModel):
    id: int
    name: str
    kind: AppKind
    latest_score: int | None
    latest_scan_at: datetime | None


class DeletedOut(ApiModel):
    deleted_scans: int


# ---- 점검 (F-I01, F-S01~S06) ----


class FolderScanIn(ApiModel):
    path: str = Field(max_length=PATH_INPUT_MAX)


class ScanStartedOut(ApiModel):
    scan_id: int


class ScanListItemOut(ApiModel):
    id: int
    started_at: datetime
    input_name: str
    status: ScanStatusOut
    score: int | None
    high: int | None
    medium: int | None
    low: int | None


class FindingOut(ApiModel):
    rule_id: str
    severity: SeverityOut
    path: str
    location: str | None  # "3:15" 또는 null
    count: int
    value: str
    snippet: str
    fix: str
    detail: str | None


class SkippedOut(ApiModel):
    path: str
    reason: str


class ReaOut(ApiModel):
    status: ReaStatusOut
    version: str | None
    modules: int | None
    sourcemaps: int | None
    message: str | None


class ScanOut(ApiModel):
    id: int
    app_id: int
    app_name: str
    status: ScanStatusOut
    started_at: datetime
    input_name: str
    rules_version: str | None
    fail_reason: str | None
    total_files: int
    target_files: int
    score: int | None
    high: int
    medium: int
    low: int
    info: int
    findings: list[FindingOut]
    skipped: list[SkippedOut]
    notices: list[str]
    rea: ReaOut | None


# ---- 비교 (F-C01·C02) ----


class ComparedFindingOut(ApiModel):
    rule_id: str
    severity: SeverityOut
    path: str  # 정규화 경로
    value: str
    severity_changed: bool


class ComparisonOut(ApiModel):
    before_id: int
    after_id: int
    before_started_at: datetime
    after_started_at: datetime
    before_score: int
    after_score: int
    score_change: int
    fixed: list[ComparedFindingOut]
    remaining: list[ComparedFindingOut]
    new: list[ComparedFindingOut]
    rules_version_differs: bool
    # SCR-05 05-01 제목. 두 점검의 앱 이름(저장된 값, F-P01 1·2를 지난 40자 이하) 그대로.
    # `compare/api.py`가 아직 채우지 않아 None 기본값이다. 레인이 채우면 설계가 `str`로 바꾼다.
    app_name: str | None = None
