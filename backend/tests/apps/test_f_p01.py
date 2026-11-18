"""F-P01 앱 등록 — 기능명세 예시를 그대로 옮긴다 (본보기 기능)."""

from __future__ import annotations

import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.apps import engine
from app.core.errors import ValidationFailed

URL = "/api/v1/apps"


def register(
    client: TestClient, name: str, kind: str = "mine", **extra: object
) -> dict[str, object]:
    body: dict[str, object] = {"name": name, "kind": kind, "consent": True, **extra}
    res = client.post(URL, json=body)
    return {"status": res.status_code, **res.json()}


# ---- 엔진 (순수) ----


def test_F_P01_엔진_앞뒤공백을_지우고_NFC() -> None:
    assert engine.normalize_name("  내 블로그 ") == "내 블로그"
    assert engine.normalize_name(unicodedata.normalize("NFD", "블로그")) == "블로그"


def test_F_P01_엔진_빈이름() -> None:
    with pytest.raises(ValidationFailed, match="앱 이름을 입력하세요"):
        engine.normalize_name("   ")


def test_F_P01_엔진_casefold_열쇠() -> None:
    assert engine.name_key("Juice Shop") == engine.name_key("juice shop")


# ---- API (예시 표) ----


def test_F_P01_예시_앞뒤공백_내블로그(client: TestClient) -> None:
    out = register(client, "  내 블로그 ")
    assert out["status"] == 201
    assert out["name"] == "내 블로그"
    assert out["consentVersion"] == "v1"
    assert out["createdAt"] == "2026-11-18T05:05:00Z"


def test_F_P01_예시_공개연습앱_https(client: TestClient) -> None:
    out = register(
        client,
        "Juice Shop",
        kind="practice",
        sourceUrl="https://github.com/juice-shop/juice-shop",
    )
    assert out["status"] == 201
    assert out["sourceUrl"] == "https://github.com/juice-shop/juice-shop"


def test_F_P01_예시_한글40자_저장(client: TestClient) -> None:
    assert register(client, "가" * 40)["status"] == 201


def test_F_P01_예시_41자_거부(client: TestClient) -> None:
    out = register(client, "a" * 41)
    assert out["status"] == 400
    assert out["message"] == "앱 이름은 40자까지입니다"


def test_F_P01_예시_대소문자만_다른_중복_거부(client: TestClient) -> None:
    register(
        client, "Juice Shop", kind="practice", sourceUrl="https://github.com/juice-shop/juice-shop"
    )
    out = register(client, "juice shop")
    assert out["status"] == 409
    assert out["message"] == "같은 이름의 앱이 있습니다"


def test_F_P01_예시_NFD_중복_거부(client: TestClient) -> None:
    register(client, "블로그")
    out = register(client, unicodedata.normalize("NFD", "블로그"))
    assert out["message"] == "같은 이름의 앱이 있습니다"


def test_F_P01_예시_http_출처_거부(client: TestClient) -> None:
    out = register(client, "연습", kind="practice", sourceUrl="http://example.com")
    assert out["status"] == 400
    assert out["message"] == "공개 연습앱은 출처 주소(https://…)가 필요합니다"


def test_F_P01_예시_확인거짓_거부(client: TestClient) -> None:
    res = client.post(URL, json={"name": "내 앱", "kind": "mine", "consent": False})
    assert res.status_code == 400
    assert res.json()["message"] == "직접 만든 앱이나 분석이 허용된 연습용 앱만 점검할 수 있습니다"
