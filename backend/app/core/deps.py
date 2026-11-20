"""API 계층이 받는 공통 의존성: DB 세션, 시각, 설정, 로컬 키, ID 인자, 지우기 확인."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import Depends, Path, Query, Request
from pydantic import BeforeValidator
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import Clock
from app.core.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_local_key(request: Request) -> bytes:
    key: bytes = request.app.state.local_key
    return key


SessionDep = Annotated[Session, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LocalKeyDep = Annotated[bytes, Depends(get_local_key)]

# 자원 ID 인자. SQLite INTEGER 범위 밖 값이 DB까지 가면 OverflowError(500)가 나서
# 경계에서 400으로 막는다
ID_MAX = 2**63 - 1
IdPath = Annotated[int, Path(ge=1, le=ID_MAX)]
IdQuery = Annotated[int, Query(ge=1, le=ID_MAX)]

# 지우기 확인 `?confirm=true` (F-P03 1, 점검 지우기도 같다). 쿼리 문자열은 글이라 Literal[True]가
# "true"를 받지 못한다. 정확히 "true"만 참으로 읽고 나머지("false", "1", 빈 값)는 그대로 넘겨
# Literal 검증이 400으로 거부하게 한다. 계약(openapi)은 `const: true, type: boolean`이다
CONFIRM_TEXT = "true"


def parse_confirm(value: object) -> object:
    return True if value == CONFIRM_TEXT else value


Confirm = Annotated[Literal[True], BeforeValidator(parse_confirm)]
