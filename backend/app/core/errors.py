"""오류 응답은 한 가지 형식: {"code": "...", "message": "..."} (코드규칙 4.3, 보안규칙 6장).

스택·SQL·내부 경로·분석 대상 글·비밀값은 넣지 않는다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("selfaudit")

MSG_INVALID_INPUT = "입력 형식이 맞지 않습니다"
MSG_NOT_FOUND = "찾을 수 없습니다"
MSG_INTERNAL = "서버 오류가 났습니다"
MSG_NOT_IMPLEMENTED = "아직 만들지 않은 기능입니다"


class AppError(Exception):
    """도메인 오류의 공통 부모. message는 화면에 그대로 보여도 되는 문장만 넣는다."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ValidationFailed(AppError):
    code = "VALIDATION_FAILED"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = MSG_NOT_FOUND) -> None:
        super().__init__(message)


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class NotImplementedYet(AppError):
    """뼈대 단계의 빈 API. 레인이 기능을 만들면 없어진다."""

    status_code = 501
    code = "NOT_IMPLEMENTED"

    def __init__(self) -> None:
        super().__init__(MSG_NOT_IMPLEMENTED)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"code": code, "message": message},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, __: RequestValidationError) -> JSONResponse:
        # 검증 오류 원문에는 입력값이 들어 있어 응답에 넣지 않는다
        return error_response(400, ValidationFailed.code, MSG_INVALID_INPUT)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response(404, NotFound.code, MSG_NOT_FOUND)
        if exc.status_code == 400:
            # JSON 본문을 읽지 못한 경우 등. 원문은 돌려주지 않는다
            return error_response(400, ValidationFailed.code, MSG_INVALID_INPUT)
        return error_response(exc.status_code, "HTTP_ERROR", MSG_INVALID_INPUT)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 경로와 예외 종류만 남긴다. 메시지에는 분석 대상 글이 섞일 수 있다
        log.error(
            "처리하지 못한 오류: %s %s (%s)", request.method, request.url.path, type(exc).__name__
        )
        return error_response(500, "INTERNAL", MSG_INTERNAL)
