"""F-P03 앱 지우기 — 기능명세 예시를 그대로 옮긴다. 점검 하나 지우기는 점검 흐름 레인(T15)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.apps import engine
from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.db.models import App, FindingRow, ReaRow, Scan, SkippedRow
from tests.apps.conftest import AddApp, AddScan

APPS_URL = "/api/v1/apps"
NOV_16 = datetime(2026, 11, 16, 5, 0, tzinfo=UTC)  # 가상 시각
NOV_17 = datetime(2026, 11, 17, 5, 0, tzinfo=UTC)
MSG_RUNNING = "점검이 끝난 뒤 지울 수 있습니다"


def delete_url(app_id: int | str, confirm: str | None = "true") -> str:
    url = f"{APPS_URL}/{app_id}"
    return url if confirm is None else f"{url}?confirm={confirm}"


def count(db: sessionmaker[Session], model: type[object]) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def add_children(db: sessionmaker[Session], scan_id: int) -> None:
    """발견·건너뜀·참고를 하나씩 붙인다 (가상 값)."""
    with db() as session:
        session.add(
            FindingRow(
                scan_id=scan_id,
                order=1,
                rule_id="S01-AWS",
                severity="high",
                path="assets/index.js",
                line=1,
                column=1,
                count=1,
                value="AKIA****",
                snippet="AKIA****",
                evidence_key="k",
                fingerprint="f",
                fix="키를 서버로 옮긴다",
            )
        )
        session.add(SkippedRow(scan_id=scan_id, path="logo.png", reason="점검 안 하는 종류"))
        session.add(ReaRow(scan_id=scan_id, status="absent"))
        session.commit()


# ---- 엔진 (순수) ----


def test_F_P03_엔진_진행중이_하나라도_있으면_거부() -> None:
    engine.check_deletable(["done", "failed", "no_target"])
    try:
        engine.check_deletable(["done", "running"])
    except ValidationFailed as err:
        assert err.message == MSG_RUNNING
    else:
        raise AssertionError("진행 중 점검이 있는데 거부하지 않았다")


# ---- API (예시 표) ----


def test_F_P03_앱지우기_점검2개_지운수2(
    client: TestClient, add_app: AddApp, add_scan: AddScan, db: sessionmaker[Session]
) -> None:
    app_id = add_app("Juice Shop", "practice")
    keep = add_app("내 블로그")
    first = add_scan(app_id, NOV_16, "done", 58)
    add_scan(app_id, NOV_17, "failed")
    kept_scan = add_scan(keep, NOV_17, "done", 90)
    add_children(db, first)
    add_children(db, kept_scan)

    res = client.delete(delete_url(app_id))
    assert res.status_code == 200
    assert res.json() == {"deletedScans": 2}
    assert [a["name"] for a in client.get(APPS_URL).json()] == ["내 블로그"]
    assert client.get(f"{APPS_URL}/{app_id}/scans").status_code == 404
    # 그 앱의 점검과 발견·건너뜀·참고만 지워지고 다른 앱 것은 남는다 (F-P03 2·3)
    assert count(db, Scan) == 1
    assert (count(db, FindingRow), count(db, SkippedRow), count(db, ReaRow)) == (1, 1, 1)


def test_F_P03_앱지우기_점검0개_지운수0(client: TestClient, add_app: AddApp) -> None:
    app_id = add_app("내 블로그")
    res = client.delete(delete_url(app_id))
    assert res.status_code == 200
    assert res.json() == {"deletedScans": 0}
    assert client.get(APPS_URL).json() == []


def test_F_P03_진행중_점검있으면_거부(
    client: TestClient, add_app: AddApp, add_scan: AddScan, db: sessionmaker[Session]
) -> None:
    app_id = add_app("Juice Shop", "practice")
    add_scan(app_id, NOV_16, "done", 58)
    add_scan(app_id, NOV_17, "running")

    res = client.delete(delete_url(app_id))
    assert res.status_code == 400
    assert res.json() == {"code": "VALIDATION_FAILED", "message": MSG_RUNNING}
    assert count(db, App) == 1
    assert count(db, Scan) == 2


def test_F_P03_확인없으면_지우지않음(
    client: TestClient, add_app: AddApp, add_scan: AddScan, db: sessionmaker[Session]
) -> None:
    app_id = add_app("내 블로그")
    add_scan(app_id, NOV_16, "done", 58)

    for confirm in (None, "false", "0", "", "True"):
        res = client.delete(delete_url(app_id, confirm))
        assert res.status_code == 400 and res.json()["code"] == "VALIDATION_FAILED"
    assert count(db, App) == 1
    assert count(db, Scan) == 1


def test_F_P03_확인이_여러개면_지우지않음(
    client: TestClient, add_app: AddApp, add_scan: AddScan, db: sessionmaker[Session]
) -> None:
    # FastAPI는 마지막 값만 보므로, 앞에 false가 있어도 지워지던 꼴 (보안 낮음, 공용 Confirm)
    app_id = add_app("내 블로그")
    add_scan(app_id, NOV_16, "done", 58)

    for query in ("confirm=false&confirm=true", "confirm=true&confirm=true"):
        res = client.delete(f"{APPS_URL}/{app_id}?{query}")
        assert res.status_code == 400 and res.json()["code"] == "VALIDATION_FAILED"
    assert count(db, App) == 1
    assert count(db, Scan) == 1


def test_F_P03_없는앱_404(client: TestClient) -> None:
    res = client.delete(delete_url(999))
    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "찾을 수 없습니다"}


def test_F_P03_ID범위밖_400(client: TestClient) -> None:
    for bad in ("0", str(2**63)):
        res = client.delete(delete_url(bad))
        assert res.status_code == 400 and res.json()["code"] == "VALIDATION_FAILED"


def test_F_P03_격리폴더_남아있으면_지움(
    client: TestClient, add_app: AddApp, add_scan: AddScan, settings: Settings
) -> None:
    app_id = add_app("내 블로그")
    left = add_scan(app_id, NOV_16, "failed")
    other_app = add_app("Juice Shop", "practice")
    other_scan = add_scan(other_app, NOV_16, "done", 80)
    left_dir = settings.data.work / str(left)
    (left_dir / "assets").mkdir(parents=True)
    (left_dir / "assets" / "index.js").write_text("var a = 1;", encoding="utf-8")
    other_dir = settings.data.work / str(other_scan)
    other_dir.mkdir(parents=True)

    res = client.delete(delete_url(app_id))
    assert res.status_code == 200
    assert not left_dir.exists()
    assert other_dir.is_dir()
