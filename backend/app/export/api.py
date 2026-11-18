"""내보내기 API (F-E01·E02). 브라우저 내려받기로 준다 (D-023). 뼈대: 레인이 채운다.

파일 이름에 한글이 있으므로 Content-Disposition은 filename*=UTF-8''… 형식을 쓴다.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.contracts.schemas import ErrorOut
from app.core.deps import SessionDep
from app.core.errors import NotImplementedYet

router = APIRouter(prefix="/api/v1", tags=["export"])
ERRORS: dict[int | str, dict[str, object]] = {400: {"model": ErrorOut}, 404: {"model": ErrorOut}}


@router.get("/scans/{scan_id}/export.json", responses=ERRORS, response_class=Response)
def export_json(scan_id: int, session: SessionDep) -> Response:
    """F-E01 JSON 내보내기."""
    raise NotImplementedYet


@router.get("/scans/{scan_id}/export.md", responses=ERRORS, response_class=Response)
def export_markdown(scan_id: int, session: SessionDep) -> Response:
    """F-E02 Markdown 내보내기."""
    raise NotImplementedYet
