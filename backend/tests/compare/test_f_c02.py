"""F-C02 두 점검 비교 — 기능명세 예시를 그대로 옮긴다. 점검·발견 행은 모델로 직접 넣는다."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.compare import engine, fingerprint
from app.contracts.engine import Finding, Location, Severity
from app.db.models import App, FindingRow, Scan

URL = "/api/v1/compare"
BEFORE_AT = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)  # 가상 시각 (KST 11-16 09:00)
AFTER_AT = datetime(2026, 11, 18, 5, 5, tzinfo=UTC)  # 가상 시각 (KST 11-18 14:05)
VERSION_NONE = "r1+vulndb.none"
VERSION_HASH = "r1+vulndb.1a2b3c4d"
MSG_SAME = "서로 다른 점검 두 개를 고르세요"
MSG_OTHER_APP = "같은 앱의 점검끼리만 비교할 수 있습니다"
MSG_NOT_DONE = "완료된 점검만 비교할 수 있습니다"
LARGE_COUNT = 20_000  # 큰 점검에서도 시간이 늘지 않는지 본다
TIME_LIMIT_S = 2.0


@dataclass(frozen=True)
class F:
    """테스트용 발견 (가상 값)."""

    rule_id: str
    severity: str
    path: str
    key: str
    value: str = "****"
    line: int | None = None
    column: int | None = None


# 명세 F-C02 예시 1의 f1~f4 (경로·증거키는 가상)
F1 = F("S01-AWS", "high", "assets/index-BmR2x9Qa.js", "ce01f31bef88", "AKIA****LE")
F2 = F("S02-MAP-CONTENT", "high", "assets/index.js.map", "map-content")
F3 = F("S03-LOCAL", "low", "assets/index-BmR2x9Qa.js", "localhost-key")
F4 = F("S03-DEVHOST", "low", "assets/index-Cc77dd88.js", "devhost-key")
F2_AFTER_REBUILD = F("S02-MAP-CONTENT", "high", "assets/index.js.map", "map-content")


def factory(client: TestClient) -> sessionmaker[Session]:
    made: sessionmaker[Session] = client.app.state.session_factory  # type: ignore[attr-defined]
    return made


def add_app(client: TestClient, name: str = "Juice Shop") -> int:
    with factory(client)() as s:
        app = App(
            name=name,
            name_key=name.casefold(),
            kind="practice",
            source_url=None,
            consent_version="v1",
            created_at=BEFORE_AT,
        )
        s.add(app)
        s.commit()
        return app.id


def to_finding(f: F) -> Finding:
    location = None if f.line is None or f.column is None else Location(f.line, f.column)
    return Finding(
        rule_id=f.rule_id,
        severity=Severity(f.severity),
        path=f.path,
        location=location,
        count=1,
        value=f.value,
        snippet="",
        evidence_key=f.key,
        fix="",
    )


def add_scan(
    client: TestClient,
    app_id: int,
    started_at: datetime,
    score: int | None,
    findings: list[F],
    *,
    status: str = "done",
    rules_version: str = VERSION_NONE,
) -> int:
    with factory(client)() as s:
        scan = Scan(
            app_id=app_id,
            status=status,
            started_at=started_at,
            input_name="shop-dist.zip",
            rules_version=rules_version,
            score=score,
        )
        for order, f in enumerate(findings):
            scan.findings.append(
                FindingRow(
                    order=order,
                    rule_id=f.rule_id,
                    severity=f.severity,
                    path=f.path,
                    line=f.line,
                    column=f.column,
                    count=1,
                    value=f.value,
                    snippet="",
                    evidence_key=f.key,
                    fingerprint=fingerprint(to_finding(f)),
                    fix="",
                )
            )
        s.add(scan)
        s.commit()
        return scan.id


def compare(client: TestClient, a: int, b: int) -> dict[str, object]:
    res = client.get(URL, params={"a": a, "b": b})
    return {"status": res.status_code, **res.json()}


def rules(items: object) -> list[str]:
    assert isinstance(items, list)
    return [str(item["ruleId"]) for item in items]


def example_pair(client: TestClient) -> tuple[int, int]:
    app_id = add_app(client)
    before = add_scan(client, app_id, BEFORE_AT, 58, [F1, F2, F3])
    after = add_scan(client, app_id, AFTER_AT, 78, [F2_AFTER_REBUILD, F4])
    return before, after


# ---- 예시 표 ----


def test_F_C02_고쳐짐2_남음1_새로1_58에서78(client: TestClient) -> None:
    before, after = example_pair(client)
    out = compare(client, before, after)
    assert out["status"] == 200
    assert rules(out["fixed"]) == ["S01-AWS", "S03-LOCAL"]
    assert rules(out["remaining"]) == ["S02-MAP-CONTENT"]
    assert rules(out["new"]) == ["S03-DEVHOST"]
    assert (out["beforeScore"], out["afterScore"], out["scoreChange"]) == (58, 78, 20)
    assert (out["beforeId"], out["afterId"]) == (before, after)
    assert out["beforeStartedAt"] == "2026-11-16T00:00:00Z"
    assert out["afterStartedAt"] == "2026-11-18T05:05:00Z"
    assert out["rulesVersionDiffers"] is False


def test_F_C02_경로는_정규화경로_값은_가린값(client: TestClient) -> None:
    before, after = example_pair(client)
    out = compare(client, before, after)
    fixed = out["fixed"]
    assert isinstance(fixed, list)
    assert fixed[0] == {
        "ruleId": "S01-AWS",
        "severity": "high",
        "path": "assets/index.js",
        "value": "AKIA****LE",
        "severityChanged": False,
    }


def test_F_C02_같은번들_변화0(client: TestClient) -> None:
    app_id = add_app(client)
    a = add_scan(client, app_id, BEFORE_AT, 58, [F1, F2, F3])
    b = add_scan(client, app_id, AFTER_AT, 58, [F1, F2, F3])
    out = compare(client, a, b)
    assert out["fixed"] == []
    assert rules(out["remaining"]) == ["S01-AWS", "S02-MAP-CONTENT", "S03-LOCAL"]
    assert out["new"] == []
    assert out["scoreChange"] == 0


def test_F_C02_순서바꿔도_같다(client: TestClient) -> None:
    before, after = example_pair(client)
    assert compare(client, after, before) == compare(client, before, after)


def test_F_C02_시각같으면_ID작은쪽이_전(client: TestClient) -> None:
    app_id = add_app(client)
    first = add_scan(client, app_id, AFTER_AT, 58, [F1, F2, F3])
    second = add_scan(client, app_id, AFTER_AT, 78, [F2, F4])
    out = compare(client, second, first)
    assert (out["beforeId"], out["afterId"]) == (first, second)
    assert out["scoreChange"] == 20


def test_F_C02_전2개_후1개면_남음1_고쳐짐1(client: TestClient) -> None:
    app_id = add_app(client)
    before = add_scan(client, app_id, BEFORE_AT, 60, [F1, F1])
    after = add_scan(client, app_id, AFTER_AT, 80, [F1])
    out = compare(client, before, after)
    assert rules(out["remaining"]) == ["S01-AWS"]
    assert rules(out["fixed"]) == ["S01-AWS"]
    assert out["new"] == []


def test_F_C02_규칙버전다르면_알림(client: TestClient) -> None:
    app_id = add_app(client)
    before = add_scan(client, app_id, BEFORE_AT, 58, [F1, F2, F3], rules_version=VERSION_NONE)
    after = add_scan(client, app_id, AFTER_AT, 78, [F2, F4], rules_version=VERSION_HASH)
    out = compare(client, before, after)
    assert out["rulesVersionDiffers"] is True
    assert rules(out["fixed"]) == ["S01-AWS", "S03-LOCAL"]


def test_F_C02_전후_둘다_vulndb_none이면_알림없음(client: TestClient) -> None:
    # 전은 목록 없음, 후는 형식 오류 목록. 둘 다 S04를 돌리지 못해 none (CR-004)
    app_id = add_app(client)
    before = add_scan(client, app_id, BEFORE_AT, 58, [F1, F2, F3], rules_version=VERSION_NONE)
    after = add_scan(client, app_id, AFTER_AT, 78, [F2, F4], rules_version=VERSION_NONE)
    assert compare(client, before, after)["rulesVersionDiffers"] is False


def test_F_C02_남음인데_심각도바뀌면_후의심각도와_표시(client: TestClient) -> None:
    lib_before = F("S04-VULNLIB", "medium", "assets/vendor-Ab12Cd34.js", "jquery@3.4.1")
    lib_after = F("S04-VULNLIB", "high", "assets/vendor-Zz98Yy76.js", "jquery@3.4.1")
    app_id = add_app(client)
    before = add_scan(client, app_id, BEFORE_AT, 92, [lib_before])
    after = add_scan(client, app_id, AFTER_AT, 80, [lib_after])
    out = compare(client, before, after)
    assert out["remaining"] == [
        {
            "ruleId": "S04-VULNLIB",
            "severity": "high",
            "path": "assets/vendor.js",
            "value": "****",
            "severityChanged": True,
        }
    ]
    assert out["scoreChange"] == -12


def test_F_C02_묶음안은_F_S06_정렬(client: TestClient) -> None:
    info = F("S03-LOCAL", "info", "a.js", "k-info")
    low_b = F("S03-LOCAL", "low", "b.js", "k-low-b", line=2, column=1)
    low_a_late = F("S03-LOCAL", "low", "a.js", "k-low-a2", "9:1", line=9, column=1)
    low_a_none = F("S03-LOCAL", "low", "a.js", "k-low-a3", "-")
    low_a_early = F("S03-LOCAL", "low", "a.js", "k-low-a1", "1:5", line=1, column=5)
    high = F("S01-AWS", "high", "z.js", "k-high")
    medium_rule_b = F("S03-DEVHOST", "medium", "a.js", "k-med-b")
    medium_rule_a = F("S02-MAP-CONTENT", "medium", "z.js", "k-med-a")
    app_id = add_app(client)
    before = add_scan(
        client,
        app_id,
        BEFORE_AT,
        50,
        [info, low_b, low_a_late, low_a_none, low_a_early, high, medium_rule_b, medium_rule_a],
    )
    after = add_scan(client, app_id, AFTER_AT, 100, [])
    fixed = compare(client, before, after)["fixed"]
    assert isinstance(fixed, list)
    order = [(item["severity"], item["ruleId"], item["path"]) for item in fixed]
    assert order == [
        ("high", "S01-AWS", "z.js"),
        ("medium", "S02-MAP-CONTENT", "z.js"),
        ("medium", "S03-DEVHOST", "a.js"),
        ("low", "S03-LOCAL", "a.js"),
        ("low", "S03-LOCAL", "a.js"),
        ("low", "S03-LOCAL", "a.js"),
        ("low", "S03-LOCAL", "b.js"),
        ("info", "S03-LOCAL", "a.js"),
    ]
    # 같은 파일 안에서는 위치(줄, 열) 차례, 위치 없음(`-`)은 맨 뒤
    assert [item["value"] for item in fixed[3:6]] == ["1:5", "9:1", "-"]


# ---- 예외 ----


def test_F_C02_같은점검_두번_400(client: TestClient) -> None:
    before, _ = example_pair(client)
    out = compare(client, before, before)
    assert (out["status"], out["message"]) == (400, MSG_SAME)


def test_F_C02_다른앱_완료아님_400(client: TestClient) -> None:
    app_id = add_app(client)
    other_app = add_app(client, "내 블로그")
    done = add_scan(client, app_id, BEFORE_AT, 58, [F1])
    other = add_scan(client, other_app, AFTER_AT, 78, [F1])
    failed = add_scan(client, app_id, AFTER_AT, None, [], status="failed")
    running = add_scan(client, app_id, AFTER_AT, None, [], status="running")
    no_target = add_scan(client, app_id, AFTER_AT, None, [], status="no_target")

    out = compare(client, done, other)
    assert (out["status"], out["message"]) == (400, MSG_OTHER_APP)
    for not_done in (failed, running, no_target):
        out = compare(client, done, not_done)
        assert (out["status"], out["message"]) == (400, MSG_NOT_DONE)


def test_F_C02_다른앱이면서_완료아님은_다른앱_문구가_먼저(client: TestClient) -> None:
    app_id = add_app(client)
    other_app = add_app(client, "내 블로그")
    done = add_scan(client, app_id, BEFORE_AT, 58, [F1])
    other_failed = add_scan(client, other_app, AFTER_AT, None, [], status="failed")
    out = compare(client, done, other_failed)
    assert (out["status"], out["message"]) == (400, MSG_OTHER_APP)


def test_F_C02_없는점검_404(client: TestClient) -> None:
    before, _ = example_pair(client)
    out = compare(client, before, 9999)
    assert out["status"] == 404


def test_F_C02_ID가_숫자아님_400(client: TestClient) -> None:
    res = client.get(URL, params={"a": "x", "b": "1"})
    assert res.status_code == 400


# ---- 엔진 (순수) ----


def side(scan_id: int, at: datetime, findings: list[F]) -> engine.ScanSide:
    return engine.ScanSide(
        scan_id=scan_id,
        started_at=at,
        score=100,
        rules_version=VERSION_NONE,
        findings=tuple(to_finding(f) for f in findings),
    )


def test_F_C02_엔진_큰점검도_빠르다() -> None:
    many = [F("S03-LOCAL", "low", f"assets/c{i}-Ab12Cd34.js", f"k{i}") for i in range(LARGE_COUNT)]
    started = time.perf_counter()
    result = engine.compare_scans(side(1, BEFORE_AT, many), side(2, AFTER_AT, many[::-1]))
    assert time.perf_counter() - started < TIME_LIMIT_S
    assert len(result.remaining) == LARGE_COUNT
    assert result.fixed == () and result.new == ()
