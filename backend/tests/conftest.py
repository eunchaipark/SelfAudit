"""공통 픽스처: 임시 데이터 폴더, 고정 시각, 127.0.0.1 주소의 테스트 클라이언트."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clock import fixed_clock
from app.core.config import DataPaths, Settings
from app.core.security import CLIENT_HEADER, CLIENT_HEADER_VALUE
from app.main import create_app

FIXED_NOW = datetime(2026, 11, 18, 5, 5, tzinfo=UTC)  # 가상 시각 (KST 14:05)
BASE_URL = "http://127.0.0.1:8000"
TEST_KEY = b"selfaudit-test-key"  # 명세 '로컬 키'의 테스트 키 (가상)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data=DataPaths(tmp_path / "data"))


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, clock=fixed_clock(FIXED_NOW))
    headers = {CLIENT_HEADER: CLIENT_HEADER_VALUE}
    with TestClient(app, base_url=BASE_URL, headers=headers) as c:
        yield c
