"""점검 API (F-I01, F-S06, F-P03). 뼈대: 레인이 채운다.

zip은 multipart가 아니라 본문 그대로(application/zip) 받는다. multipart는 시스템 임시 폴더에
파일을 쓰는데, 서버는 데이터 폴더 밖에 쓰지 않기 때문이다 (용어 '데이터 폴더').
파일 이름은 X-File-Name 머리말(퍼센트 인코딩)로 받는다.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request

from app.contracts.schemas import DeletedOut, ErrorOut, FolderScanIn, ScanOut, ScanStartedOut
from app.core.deps import SessionDep
from app.core.errors import NotImplementedYet

router = APIRouter(prefix="/api/v1", tags=["scans"])
ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorOut},
    404: {"model": ErrorOut},
    409: {"model": ErrorOut},
}
FILE_NAME_HEADER = "x-file-name"
ZIP_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post("/apps/{app_id}/scans/zip", status_code=202, responses=ERRORS, openapi_extra=ZIP_BODY)
def start_zip_scan(app_id: int, request: Request, session: SessionDep) -> ScanStartedOut:
    """F-I01 zip 점검 시작. A의 거부는 점검을 만들기 전에 한다."""
    raise NotImplementedYet


@router.post("/apps/{app_id}/scans/folder", status_code=202, responses=ERRORS)
def start_folder_scan(app_id: int, body: FolderScanIn, session: SessionDep) -> ScanStartedOut:
    """F-I01 폴더 점검 시작."""
    raise NotImplementedYet


@router.get("/scans/{scan_id}", responses=ERRORS)
def get_scan(scan_id: int, session: SessionDep) -> ScanOut:
    """SCR-04 점검 결과 (진행 중이면 상태만 채워서)."""
    raise NotImplementedYet


@router.delete("/scans/{scan_id}", responses=ERRORS)
def delete_scan(scan_id: int, confirm: Literal[True], session: SessionDep) -> DeletedOut:
    """F-P03 점검 지우기."""
    raise NotImplementedYet
