"""앱 조립 (설계): 설정, DB, 로컬 키, 보안, 라우터, 화면 파일."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.apps.api import router as apps_router
from app.compare.api import router as compare_router
from app.core import localkey
from app.core.clock import Clock, system_clock
from app.core.config import Settings, load_settings
from app.core.errors import install_error_handlers
from app.core.security import install_security
from app.db import migrate
from app.db.base import make_engine, make_session_factory
from app.export.api import router as export_router
from app.scans.api import router as scans_router

VERSION = "0.1.0"


class SpaFiles(StaticFiles):
    """화면 빌드 결과. 없는 경로는 index.html로 돌려 화면 라우터가 받게 한다."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None, *, clock: Clock = system_clock) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data.ensure()
        migrate.upgrade(settings.db_url)
        engine = make_engine(settings.db_url)
        app.state.local_key = localkey.load_or_create(settings.data.key_file)
        app.state.session_factory = make_session_factory(engine)
        # TODO(F-I01): 12번 시작 정리(진행 중 → 실패, work/ 비우기)는 scans 레인이 여기에 붙인다
        yield
        engine.dispose()

    # 문서 화면(/docs)은 외부 CDN을 불러오므로 끈다 (NFR-01)
    app = FastAPI(
        title="SelfAudit",
        version=VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.clock = clock
    install_error_handlers(app)
    install_security(app, settings)

    @app.get("/api/v1/health", tags=["core"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (apps_router, scans_router, compare_router, export_router):
        app.include_router(router)
    if settings.static_dir is not None:
        app.mount("/", SpaFiles(directory=Path(settings.static_dir), html=True), name="spa")
    return app
