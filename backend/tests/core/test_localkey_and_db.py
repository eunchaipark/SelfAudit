"""로컬 키 (D-014)와 DB 뼈대."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.core import localkey
from app.core.config import Settings
from app.db.base import make_engine


def test_로컬키_처음에_32바이트로_만들고_다시_읽음(tmp_path: Path) -> None:
    path = tmp_path / "local.key"
    first = localkey.load_or_create(path)
    assert len(first) == localkey.KEY_BYTES
    assert localkey.load_or_create(path) == first
    assert [p.name for p in tmp_path.iterdir()] == ["local.key"]  # 임시 파일이 남지 않는다


def test_로컬키_이미_있으면_덮어쓰지_않음(tmp_path: Path) -> None:
    path = tmp_path / "local.key"
    path.write_bytes(b"k" * localkey.KEY_BYTES)
    localkey._create(path)  # 동시에 시작한 다른 프로세스가 늦게 만든 경우
    assert path.read_bytes() == b"k" * localkey.KEY_BYTES


def test_로컬키_길이가_틀리면_멈춤(tmp_path: Path) -> None:
    path = tmp_path / "local.key"
    path.write_bytes(b"short")
    with pytest.raises(localkey.LocalKeyError):
        localkey.load_or_create(path)


def test_로컬키는_응답에_나오지_않음(client: TestClient) -> None:
    key: bytes = client.app.state.local_key  # type: ignore[attr-defined]
    res = client.post("/api/v1/apps", json={"name": "가상", "kind": "mine", "consent": True})
    for text in (res.text, client.get("/api/v1/health").text):
        assert key.hex() not in text


def test_시작하면_데이터폴더와_마이그레이션(client: TestClient, settings: Settings) -> None:
    assert settings.data.work.is_dir()
    assert settings.data.uploads.is_dir()
    tables = set(inspect(make_engine(settings.db_url)).get_table_names())
    assert {"apps", "scans", "findings", "skipped", "rea_refs"} <= tables
