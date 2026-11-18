"""보안 기본 테스트 (NFR-08, D-022, 보안규칙 3·6장). 뼈대에서 만들고 유지한다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import CLIENT_HEADER
from app.main import create_app
from tests.conftest import BASE_URL

NEW_APP = {"name": "가상 앱", "kind": "mine", "consent": True}


def test_NFR_08_다른_Host는_거부(client: TestClient) -> None:
    res = client.get("/api/v1/health", headers={"host": "evil.example:8000"})
    assert res.status_code == 400
    assert res.json() == {"code": "BAD_HOST", "message": "허용되지 않은 주소로 들어온 요청입니다"}


def test_NFR_08_localhost_Host는_받음(client: TestClient) -> None:
    assert client.get("/api/v1/health", headers={"host": "localhost:8000"}).status_code == 200


def test_NFR_08_다른_Origin의_POST는_거부(client: TestClient) -> None:
    res = client.post("/api/v1/apps", json=NEW_APP, headers={"origin": "https://evil.example"})
    assert res.status_code == 403
    assert res.json()["code"] == "BAD_ORIGIN"


def test_NFR_08_전용_머리말_없는_POST는_거부(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app, base_url=BASE_URL) as c:
        res = c.post("/api/v1/apps", json=NEW_APP)
    assert res.status_code == 403


def test_NFR_08_같은_출처_POST는_받음(client: TestClient) -> None:
    res = client.post("/api/v1/apps", json=NEW_APP, headers={"origin": BASE_URL})
    assert res.status_code == 201


def test_NFR_08_CORS를_열지_않음(client: TestClient) -> None:
    res = client.options(
        "/api/v1/apps",
        headers={"origin": "https://evil.example", "access-control-request-method": "POST"},
    )
    assert "access-control-allow-origin" not in res.headers


def test_보안헤더와_no_store(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.headers["content-security-policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["referrer-policy"] == "no-referrer"
    assert res.headers["cache-control"] == "no-store"


def test_오류응답_모양_검증실패는_입력값을_되돌리지_않음(client: TestClient) -> None:
    res = client.post("/api/v1/apps", json={"name": "비밀-값-1234", "kind": "x", "consent": True})
    assert res.status_code == 400
    assert res.json() == {"code": "VALIDATION_FAILED", "message": "입력 형식이 맞지 않습니다"}
    assert "비밀-값-1234" not in res.text


def test_오류응답_모양_없는_경로(client: TestClient) -> None:
    res = client.get("/api/v1/없는-경로")
    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "찾을 수 없습니다"}


def test_오류응답_모양_처리못한_오류는_스택을_숨김(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("내부 경로 C:\\secret\\x 와 원문")

    with TestClient(app, base_url=BASE_URL, raise_server_exceptions=False) as c:
        res = c.get("/api/v1/boom")
    assert res.status_code == 500
    assert res.json() == {"code": "INTERNAL", "message": "서버 오류가 났습니다"}
    assert "secret" not in res.text
    assert "Traceback" not in res.text


def test_빈_API는_501_한가지_형식(client: TestClient) -> None:
    res = client.get("/api/v1/apps")
    assert res.status_code == 501
    assert res.json() == {"code": "NOT_IMPLEMENTED", "message": "아직 만들지 않은 기능입니다"}


def test_문서화면과_스키마는_내놓지_않음(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_전용_머리말_이름(client: TestClient) -> None:
    assert CLIENT_HEADER == "x-selfaudit-client"
