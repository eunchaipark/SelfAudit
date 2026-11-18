"""로컬 API 보호와 보안 헤더 (NFR-08, D-022, 보안규칙 3장).

- Host가 127.0.0.1:<포트>·localhost:<포트>가 아니면 거부 (DNS 리바인딩)
- 상태를 바꾸는 요청은 Origin 검사 + 사용자 정의 머리말 요구 (CSRF). CORS는 열지 않는다
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.core.config import Settings
from app.core.errors import error_response

STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CLIENT_HEADER = "x-selfaudit-client"
CLIENT_HEADER_VALUE = "1"
MSG_BAD_HOST = "허용되지 않은 주소로 들어온 요청입니다"
MSG_BAD_ORIGIN = "다른 사이트에서 보낸 요청은 받지 않습니다"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

CallNext = Callable[[Request], Awaitable[Response]]


def install_security(app: FastAPI, settings: Settings) -> None:
    hosts = settings.allowed_hosts
    origins = settings.allowed_origins

    @app.middleware("http")
    async def _guard(request: Request, call_next: CallNext) -> Response:
        if request.headers.get("host", "") not in hosts:
            response: Response = error_response(400, "BAD_HOST", MSG_BAD_HOST)
        elif request.method in STATE_CHANGING and not _same_site(request, origins):
            response = error_response(403, "BAD_ORIGIN", MSG_BAD_ORIGIN)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _same_site(request: Request, origins: frozenset[str]) -> bool:
    origin = request.headers.get("origin")
    if origin is not None and origin not in origins:
        return False
    # 사용자 정의 머리말은 다른 출처에서 보내려면 사전 요청이 필요하고, CORS를 열지 않으므로 막힌다
    return request.headers.get(CLIENT_HEADER) == CLIENT_HEADER_VALUE
