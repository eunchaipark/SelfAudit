"""F-P02 점검 기록 보기 — 기능명세 예시를 그대로 옮긴다."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.apps import engine
from tests.apps.conftest import AddApp, AddScan

APPS_URL = "/api/v1/apps"
NOV_16 = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)  # 가상 시각
NOV_17 = datetime(2026, 11, 17, 5, 0, tzinfo=UTC)
NOV_18 = datetime(2026, 11, 18, 5, 5, tzinfo=UTC)  # KST 14:05


def scans_url(app_id: int | str) -> str:
    return f"{APPS_URL}/{app_id}/scans"


def record(scan_id: int, started_at: datetime, status: str = "done") -> engine.ScanRecord:
    return engine.ScanRecord(
        id=scan_id,
        app_id=1,
        started_at=started_at,
        input_name="dist.zip",
        status=status,
        score=50,
        high=1,
        medium=2,
        low=3,
    )


# ---- 엔진 (순수) ----


def test_F_P02_엔진_최신순_같은시각은_ID큰것이_위() -> None:
    rows = [record(1, NOV_16), record(3, NOV_17), record(2, NOV_17)]
    assert [r.id for r in engine.newest_first(rows)] == [3, 2, 1]


def test_F_P02_엔진_완료아니면_점수와_개수가_없다() -> None:
    for status in ("running", "no_target", "failed"):
        shown = engine.shown(record(1, NOV_16, status))
        assert (shown.score, shown.high, shown.medium, shown.low) == (None, None, None, None)
    done = engine.shown(record(1, NOV_16))
    assert (done.score, done.high, done.medium, done.low) == (50, 1, 2, 3)


def test_F_P02_엔진_앱마다_가장최근_완료점검() -> None:
    rows = [record(1, NOV_16), record(2, NOV_18, "failed"), record(3, NOV_17)]
    latest = engine.latest_done_by_app(rows)
    assert latest[1].id == 3


# ---- API (예시 표) ----


def test_F_P02_점검3개_최신순_점수_78(
    client: TestClient, add_app: AddApp, add_scan: AddScan
) -> None:
    app_id = add_app("Juice Shop", "practice")
    add_scan(app_id, NOV_16, "done", 58, (1, 2, 3))
    add_scan(app_id, NOV_17, "failed")
    add_scan(app_id, NOV_18, "done", 78, (0, 1, 2))

    res = client.get(scans_url(app_id))
    assert res.status_code == 200
    rows = res.json()
    assert [r["startedAt"] for r in rows] == [
        "2026-11-18T05:05:00Z",
        "2026-11-17T05:00:00Z",
        "2026-11-16T05:00:00Z",
    ]
    assert [r["score"] for r in rows] == [78, None, 58]
    assert [r["status"] for r in rows] == ["done", "failed", "done"]
    assert rows[0]["inputName"] == "dist.zip"
    assert (rows[0]["high"], rows[0]["medium"], rows[0]["low"]) == (0, 1, 2)

    apps = client.get(APPS_URL).json()
    assert apps == [
        {
            "id": app_id,
            "name": "Juice Shop",
            "kind": "practice",
            "latestScore": 78,
            "latestScanAt": "2026-11-18T05:05:00Z",
        }
    ]


def test_F_P02_같은시각이면_점검ID큰것이_위(
    client: TestClient, add_app: AddApp, add_scan: AddScan
) -> None:
    app_id = add_app("내 블로그")
    first = add_scan(app_id, NOV_17, "done", 60)
    second = add_scan(app_id, NOV_17, "done", 70)

    rows = client.get(scans_url(app_id)).json()
    assert [r["id"] for r in rows] == [second, first]
    assert client.get(APPS_URL).json()[0]["latestScore"] == 70


def test_F_P02_완료아님은_점수_대시(client: TestClient, add_app: AddApp, add_scan: AddScan) -> None:
    app_id = add_app("내 블로그")
    # 저장된 값이 있어도 완료가 아니면 내지 않는다 (F-P02 3)
    for status in ("running", "no_target", "failed"):
        add_scan(app_id, NOV_17, status, 40, (1, 1, 1))

    rows = client.get(scans_url(app_id)).json()
    assert len(rows) == 3
    for row in rows:
        assert (row["score"], row["high"], row["medium"], row["low"]) == (None, None, None, None)
    app = client.get(APPS_URL).json()[0]
    assert (app["latestScore"], app["latestScanAt"]) == (None, None)


def test_F_P02_점검0개_빈목록_최근점수_대시(client: TestClient, add_app: AddApp) -> None:
    app_id = add_app("내 블로그")
    res = client.get(scans_url(app_id))
    assert res.status_code == 200
    assert res.json() == []
    app = client.get(APPS_URL).json()[0]
    assert (app["latestScore"], app["latestScanAt"]) == (None, None)


def test_F_P02_없는앱_404(client: TestClient) -> None:
    res = client.get(scans_url(999))
    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "찾을 수 없습니다"}


def test_F_P02_ID범위밖_400(client: TestClient) -> None:
    for bad in ("0", str(2**63), "abc"):
        res = client.get(scans_url(bad))
        assert res.status_code == 400 and res.json()["code"] == "VALIDATION_FAILED"


def test_F_P02_다른앱의_점검은_섞이지_않는다(
    client: TestClient, add_app: AddApp, add_scan: AddScan
) -> None:
    mine = add_app("내 블로그")
    other = add_app("Juice Shop", "practice")
    add_scan(other, NOV_18, "done", 90)

    assert client.get(scans_url(mine)).json() == []
    apps = {a["name"]: a["latestScore"] for a in client.get(APPS_URL).json()}
    assert apps == {"내 블로그": None, "Juice Shop": 90}


def test_F_P02_앱목록_이름순(client: TestClient, add_app: AddApp) -> None:
    for name in ("내 블로그", "Juice Shop", "alpha"):
        add_app(name)
    assert [a["name"] for a in client.get(APPS_URL).json()] == ["alpha", "Juice Shop", "내 블로그"]


def test_F_P02_앱0개_빈목록(client: TestClient) -> None:
    res = client.get(APPS_URL)
    assert res.status_code == 200
    assert res.json() == []


def test_F_P02_앱하나_읽기(client: TestClient, add_app: AddApp) -> None:
    app_id = add_app("Juice Shop", "practice")
    res = client.get(f"{APPS_URL}/{app_id}")
    assert res.status_code == 200
    assert res.json()["name"] == "Juice Shop"
    assert client.get(f"{APPS_URL}/999").status_code == 404
