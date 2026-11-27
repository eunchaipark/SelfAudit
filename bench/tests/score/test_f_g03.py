"""F-G03 지표 (R5) 시험. 기능명세 F-G03 예시를 옮겼다(값은 가상, 직접 계산).

이 파일의 만들기 함수(`answers_doc`·`record`·`hit`·`miss`·`write_run` 등)는 F-G04~G06 시험도 쓴다
(`tests/score`에는 `__init__.py`·`conftest.py`가 없어 — 허용 범위 밖 — 시험 파일끼리 가져다 쓴다).
정답지는 시험 안에서 만들고 계약 `answers`로 검증한다. 정답 k는 `assets/app.js`의 10(k+1)줄,
닻 없음(줄 맞춤) — 결과 `hit(k)`는 그 줄, `miss(j)`는 어느 정답에서도 5줄 떨어진 줄이다.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from common.contracts import Json, read_contract, validate_contract
from score import aggregate as sa
from score.match import Rules
from score.metrics import ItemInfo, RunMetrics, RunScore, fmt_percent, score_run
from score.read import Finding, RunRead, ScoreError
from score.recompute import score_results

FIXTURES_G01 = Path(__file__).parent / "fixtures" / "g01_g02"
SHA = "ab12" * 16
APP = "assets/app.js"
APP_LINES = 1000
GA_SHA = "3f2a" * 16  # g01_g02/answers_ga.json의 번들 지문


# --- 만들기 (F-G04~G06 시험도 쓴다) ----------------------------------------------------------


def item_line(k: int) -> int:
    return 10 * (k + 1)


def answers_doc(
    target: str,
    n: int,
    *,
    difficulty: str = "easy",
    item_difficulties: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
    origin: str = "planted",
    decoys: int = 0,
) -> dict[str, Json]:
    """정답 n개(차례 k: 10(k+1)줄)와 미끼 `decoys`개(차례 j: 10(j+1)+5줄)인 정답지."""
    practice = origin == "practice"
    prefix = target.upper()
    items: list[Json] = [
        {
            "id": f"{prefix}-{k + 1:02d}",
            "categories": [categories[k] if categories else "secret"],
            "difficulty": item_difficulties[k] if item_difficulties else difficulty,
            "hiding": "plain",
            "locations": [_loc(item_line(k))],
            "anchor": None,
            "decoded_anchor": None,
            "planted": "가상 정답(시험)",
            "why": "시험",
        }
        for k in range(n)
    ]
    decoy_list: list[Json] = [
        {
            "id": f"{prefix}-D{j + 1}",
            "locations": [_loc(item_line(j) + 5)],
            "anchor": None,
            "hiding": "comment",
            "why": "시험 미끼",
        }
        for j in range(decoys)
    ]
    doc: dict[str, Json] = {
        "schema": "selfaudit-bench/answers@1",
        "bundle_id": target,
        "origin": origin,
        "difficulty": "mixed" if practice else difficulty,
        "bundle_manifest_sha256": SHA,
        "complete": not practice,
        "items": items,
        "decoys": decoy_list,
    }
    errors = validate_contract("answers", doc)
    assert errors == [], errors
    return doc


def _loc(line: int) -> dict[str, Json]:
    return {"file": APP, "line_start": line, "line_end": line, "file_lines": APP_LINES}


def hit(k: int, category: str = "secret", *, offset: int = 0, evidence: str = "") -> Json:
    """정답 k의 줄(+offset)을 가리키는 결과."""
    return finding(category, item_line(k) + offset, evidence or f"value_{k}")


def miss(j: int, category: str = "secret", *, evidence: str = "") -> Json:
    """어느 정답에도 맞지 않는 결과(정답 줄에서 5줄, 미끼가 있으면 미끼 j의 줄)."""
    return finding(category, item_line(j) + 5, evidence or f"miss_{j}")


def finding(category: str, line: int | None, evidence: str, reason: str = "가상 까닭") -> Json:
    return {
        "category": category,
        "file": APP,
        "line": line,
        "evidence": evidence,
        "reason": reason,
        "confidence": "high",
    }


def record(
    target: str,
    condition: str,
    repeat: int,
    status: str = "ok",
    *,
    kind: str = "planted",
    run_kind: str = "target",
    cost: float | None = 0.75,
    wall_s: float = 600.0,
    stored: str = "results",
    transcript_sha: str = SHA,
    manifest: str = SHA,
) -> dict[str, Json]:
    """계약 `run`에 맞는 가상 실행 한 번(실험구조 2.4 꼴)."""
    rec: dict[str, Json] = {
        "schema": "selfaudit-bench/run@1",
        "run_kind": run_kind,
        "run_id": f"{target}-{condition.lower()}-{repeat}-{SHA[:8]}",
        "batch_id": "20261127-0100-first",
        "target_id": target,
        "target_kind": kind,
        "bundle_manifest_sha256": manifest,
        "condition": condition,
        "repeat_index": repeat,
        "started_at": "2026-11-27T01:00:00+09:00",
        "ended_at": "2026-11-27T01:10:00+09:00",
        "versions": {
            "claude_code": "2.1.119",
            "model": "claude-test-model",
            "rea": None,
            "node": None,
            "prompt_sha256": SHA,
            "findings_schema_sha256": SHA,
            "mcp_config_sha256": SHA,
            "plan_sha256": SHA,
        },
        "settings": {
            "effort": "high",
            "timeout_s": 780,
            "max_budget_usd": 2.52,
            "tools": ["Read", "Grep", "Glob"],
            "allowed_tools": ["Read", "Grep", "Glob"],
            "rea_tools": [],
            "order_seed": 7,
            "firewall_rule": "absent",
            "deny_rule_forms": ["//C:/"],
        },
        "outcome": {"status": status, "exit_code": 0, "init_check": "passed", "detail": ""},
        "metrics": {
            "wall_s": wall_s,
            "duration_ms": 600000,
            "duration_api_ms": 500000,
            "num_turns": 12,
            "total_cost_usd": cost,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_read_input_tokens": 40,
            },
            "tool_calls": {"Read": 5, "Grep": 2},
        },
        "network": {
            "netguard_blocked": 0,
            "netguard_local": 0,
            "netstat_endpoints": 0,
            "guarded_processes": 0,
            "rea_processes": 0,
        },
        "transcript": {"stored": stored, "bytes": 0, "sha256": transcript_sha},
    }
    assert validate_contract("run", rec) == []
    return rec


def run_read(rec: dict[str, Json], found: Sequence[Json] | None) -> RunRead:
    """F-G01을 거친 꼴(메모리 안). `found`가 `None`이면 결과 없는 상태."""
    findings = None
    if found is not None:
        findings = tuple(
            Finding(
                index=i,
                category=str(f["category"]),
                file=str(f["file"]),
                line=None if f["line"] is None else int(str(f["line"])),
                evidence=str(f["evidence"]),
            )
            for i, f in enumerate(found)
            if isinstance(f, dict)
        )
    status = rec["outcome"]["status"] if isinstance(rec["outcome"], dict) else "ok"
    assert isinstance(status, str)
    return RunRead(Path(str(rec["run_id"])), rec, status, findings)


def scored(
    answers: dict[str, Json] | None,
    target: str,
    condition: str,
    repeat: int,
    found: Sequence[Json] | None,
    status: str = "ok",
    **kw: Json,
) -> RunScore:
    rec = record(target, condition, repeat, status, **kw)  # type: ignore[arg-type]
    return score_run(run_read(rec, found), answers)


def fake_score(
    target: str,
    condition: str,
    repeat: int,
    n_items: int,
    matched: int,
    *,
    difficulty: str = "normal",
) -> RunScore:
    """짝짓기 없이 (정답 수, 짝 수)만 정한 실행 — 정답 1000개처럼 계약 상한보다 큰 묶음을 본다."""
    items = tuple(
        ItemInfo(f"{target.upper()}-{k}", difficulty, "secret", "plain") for k in range(n_items)
    )
    return RunScore(
        run_dir=Path(target),
        run_id=f"{target}-{condition.lower()}-{repeat}-{SHA[:8]}",
        run_kind="target",
        target_id=target,
        target_kind="planted",
        condition=condition,
        repeat=repeat,
        status="ok",
        answered=True,
        complete=True,
        target_difficulty=difficulty,
        items=items,
        findings=(),
        match=None,
        metrics=RunMetrics(Fraction(600), Fraction(3, 4), (1, 2, 3, 4), 7),
        transcript_stored="results",
        transcript_sha256=SHA,
        matched_ids=frozenset(i.id for i in items[:matched]),
    )


def write_run(
    root: Path,
    rec: dict[str, Json],
    found: Sequence[Json] | None,
    transcript: bytes = b"",
    name: str | None = None,
) -> Path:
    """실행 폴더 하나(run.json·findings.json·transcript.jsonl)를 쓴다. 대화 기록 지문은 맞춘다."""
    run_dir = root / (name or str(rec["run_id"]))
    run_dir.mkdir(parents=True)
    rec = json.loads(json.dumps(rec))  # 사본(부른 쪽 값을 바꾸지 않게)
    meta: Any = rec["transcript"]
    meta["bytes"] = len(transcript)
    if meta["stored"] == "results":
        meta["sha256"] = hashlib.sha256(transcript).hexdigest()
        (run_dir / "transcript.jsonl").write_bytes(transcript)
    (run_dir / "run.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    if found is not None:
        doc = {"findings": list(found), "notes": ""}
        (run_dir / "findings.json").write_text(json.dumps(doc, ensure_ascii=False), "utf-8")
    return run_dir


def pct(value: Fraction | None) -> str:
    return fmt_percent(value)


def spread_text(s: sa.Spread | None) -> tuple[str, str, str] | None:
    if s is None:
        return None
    return (pct(s.low), pct(s.mid), pct(s.high))


# --- 실행 하나 (규칙 1~3) --------------------------------------------------------------------


def test_F_G03_정답6_결과5_맞음4_재현율66_7_정밀도80_0() -> None:
    answers = answers_doc("easy-1", 6)
    s = scored(answers, "easy-1", "A", 1, [hit(0), hit(1), hit(2), hit(3), miss(4)])
    assert (s.matched, s.results) == (4, 5)
    assert (pct(s.recall), pct(s.precision)) == ("66.7%", "80.0%")


def test_F_G03_F_G02예시가_첫줄() -> None:
    answers = read_contract("answers", FIXTURES_G01 / "answers_ga.json")
    j, m = "assets/index-3f2a.js", "assets/index-3f2a.js.map"
    key = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
    rows = [
        ("secret", j, 13, f'payKey: "{key}"'),
        ("secret", m, None, key),
        ("internal_address", "./assets/index-3f2a.js", 40, 'base:"http://10.20.30.40:8080"'),
        ("admin_path", "assets\\index-3f2a.js", 60, 'fetch("/internal-admin/users")'),
        ("debug_flag", j, 83, "debug: true"),
        ("secret", j, 20, 'apiKey: "YOUR_API_KEY"'),
        ("other", j, 5, "eval(x)"),
        ("source_map", "assets/Index-3f2a.js.map", 1, '"sourcesContent"'),
    ]
    found: list[Json] = [finding(c, line, ev) for c, _, line, ev in rows]
    for item, (_, file, _, _) in zip(found, rows, strict=True):
        assert isinstance(item, dict)
        item["file"] = file
    s = scored(answers, "easy-1", "A", 1, found, manifest=GA_SHA)
    assert (pct(s.recall), pct(s.precision), pct(s.location_accuracy)) == (
        "50.0%",
        "42.9%",
        "33.3%",
    )
    assert (s.duplicates, s.decoy_misses, s.others) == (1, 1, 1)


def test_F_G03_other빼고_정밀도() -> None:
    answers = answers_doc("easy-1", 6)
    found = [hit(0), hit(1), hit(2), miss(3), miss(4, "other"), miss(5, "other")]
    s = scored(answers, "easy-1", "A", 1, found)
    assert (s.others, pct(s.precision)) == (2, "75.0%")  # 3 ÷ (6 − 2)


def test_F_G03_정밀도분모에_중복·미끼헛짚음·틀림이_모두듦() -> None:
    answers = answers_doc("easy-1", 6, decoys=1)
    # hit(0) 두 번(하나는 중복), 미끼 D1 자리(정답 0의 줄 + 5), 아무 데도 아닌 줄
    found = [hit(0), hit(0, offset=1), miss(0), finding("secret", 500, "zz")]
    s = scored(answers, "easy-1", "A", 1, found)
    assert (s.matched, s.duplicates, s.decoy_misses) == (1, 1, 1)
    assert pct(s.precision) == "25.0%"  # 1 ÷ 4 — 중복·헛짚음·틀림이 모두 분모


def test_F_G03_위치정확도_T없이() -> None:
    answers = answers_doc("easy-1", 6)
    s = scored(answers, "easy-1", "A", 1, [hit(0), hit(1, offset=2)])
    assert s.matched == 2
    assert pct(s.location_accuracy) == "50.0%"  # 2줄 밖은 짝이지만 위치까지는 아님


def test_F_G03_형식실패_재현율0_정밀도없음() -> None:
    answers = answers_doc("easy-1", 6)
    for status in ("format_failure", "timeout", "budget_exceeded"):
        s = scored(answers, "easy-1", "A", 1, None, status)
        assert (pct(s.recall), pct(s.precision), pct(s.location_accuracy)) == ("0.0%", "-", "-")
        assert s.results is None
    empty = scored(answers, "easy-1", "A", 1, [])
    assert (pct(empty.recall), pct(empty.precision), pct(empty.location_accuracy)) == (
        "0.0%",
        "-",
        "-",
    )


def test_F_G03_결과가모두_other면_정밀도없음() -> None:
    s = scored(answers_doc("easy-1", 6), "easy-1", "A", 1, [miss(0, "other")])
    assert (pct(s.recall), pct(s.precision)) == ("0.0%", "-")


def test_F_G03_condition_mismatch_빼고_다시돌릴목록(tmp_path: Path) -> None:
    answers = answers_doc("easy-1", 6)
    root = tmp_path / "2026-11-27"
    write_run(root, record("easy-1", "A", 1), [hit(0)])
    mismatch = record("easy-1", "B", 1, "condition_mismatch")
    write_run(root, mismatch, None)
    write_run(root, record("easy-1", "B", 2, "error"), None)
    write_run(root, record("easy-1", "B", 3), [hit(0), hit(1)])
    result = score_results([root], {"easy-1": answers})
    report = result.report
    assert [s.run_id for s in report.runs] == [
        "easy-1-a-1-ab12ab12",
        "easy-1-b-3-ab12ab12",
    ]
    assert [(r.run_id, r.status) for r in report.rerun] == [
        ("easy-1-b-1-ab12ab12", "condition_mismatch"),
        ("easy-1-b-2-ab12ab12", "error"),
    ]
    assert report.status_counts["B"]["condition_mismatch"] == 1
    assert report.status_counts["B"]["error"] == 1
    assert spread_text(report.overall["B"].recall_spread) == ("33.3%", "33.3%", "33.3%")


def test_F_G03_빈·문지기실행은_지표에서_뺌() -> None:
    answers = answers_doc("easy-1", 6)
    runs = [
        scored(answers, "easy-1", "A", r, [hit(0)], run_kind=kind)
        for r, kind in enumerate(["target"] * 3 + ["empty", "gate"], start=1)
    ]
    report = sa.build_report(runs, [])
    assert len(report.runs) == 3
    assert report.skipped_kinds == {"empty": 1, "gate": 1}


def test_F_G03_내앱은_재현율없이_결과수만() -> None:
    runs = [
        scored(None, "mine-app", "A", r, [miss(0)] * n, kind="mine")
        for r, n in enumerate((12, 9, 15), start=1)
    ]
    report = sa.build_report(runs, [])
    stats = report.by_target[("A", "mine-app")]
    assert (stats.recall, stats.precision) == (None, None)
    assert stats.results is not None
    assert [stats.results.low, stats.results.mid, stats.results.high] == [9, 12, 15]
    assert report.overall["A"].recall_spread is None  # 심은 번들 묶음과 섞지 않는다


def test_F_G03_같은조건대상차례_실행둘이면_멈춤() -> None:
    answers = answers_doc("easy-1", 6)
    one = scored(answers, "easy-1", "A", 1, [hit(0)])
    two = scored(answers, "easy-1", "A", 1, [hit(1)])
    two = dataclasses.replace(two, run_id="easy-1-a-1-cd34cd34")
    with pytest.raises(ScoreError, match="차례 1"):
        sa.build_report([one, two], [])


# --- 모으기 (규칙 4~6) -----------------------------------------------------------------------


def xy_runs(third: bool = False) -> list[RunScore]:
    """예시: 조건 B, x(정답 6)·y(정답 4). 차례 1 x 3·y 4 / 차례 2 x 6·y format_failure."""
    x, y = answers_doc("x-1", 6), answers_doc("y-1", 4)
    runs = [
        scored(x, "x-1", "B", 1, [hit(k) for k in range(3)]),
        scored(y, "y-1", "B", 1, [hit(k) for k in range(4)]),
        scored(x, "x-1", "B", 2, [hit(k) for k in range(6)]),
        scored(y, "y-1", "B", 2, None, "format_failure"),
    ]
    if third:
        runs += [
            scored(x, "x-1", "B", 3, [hit(k) for k in range(5)]),
            scored(y, "y-1", "B", 3, [hit(k) for k in range(2)]),
        ]
    return runs


def test_F_G03_조건전체_반복차례마다_짝합나누기정답합() -> None:
    report = sa.build_report(xy_runs(), [])
    pool = report.overall["B"]
    assert {r: pct(v) for r, v in pool.recall.items()} == {1: "70.0%", 2: "60.0%"}
    assert spread_text(pool.recall_spread) == ("60.0%", "65.0%", "70.0%")


def test_F_G03_조건전체_정밀도도_같은꼴() -> None:
    x, y = answers_doc("x-1", 6), answers_doc("y-1", 9)
    runs = [
        scored(x, "x-1", "B", 1, [hit(k) for k in range(3)] + [miss(k) for k in range(4)]),
        scored(y, "y-1", "B", 1, [hit(k) for k in range(7)] + [miss(k) for k in range(2)]),
        scored(x, "x-1", "B", 2, [hit(k) for k in range(6)] + [miss(k) for k in range(2)]),
        scored(y, "y-1", "B", 2, None, "format_failure"),
    ]
    pool = sa.build_report(runs, []).overall["B"]
    assert {r: pct(v) for r, v in pool.precision.items()} == {1: "62.5%", 2: "75.0%"}


def test_F_G03_N2_최소가운데최대() -> None:
    report = sa.build_report(xy_runs(), [])
    x, y = report.by_target[("B", "x-1")], report.by_target[("B", "y-1")]
    assert spread_text(x.recall) == ("50.0%", "75.0%", "100.0%")
    assert spread_text(y.recall) == ("0.0%", "50.0%", "100.0%")
    assert spread_text(y.precision) == ("100.0%", "100.0%", "100.0%")  # `-`는 빼고 센다


def test_F_G03_N3_셋째를_더하면() -> None:
    report = sa.build_report(xy_runs(third=True), [])
    assert spread_text(report.overall["B"].recall_spread) == ("60.0%", "70.0%", "70.0%")
    assert spread_text(report.by_target[("B", "x-1")].recall) == ("50.0%", "83.3%", "100.0%")
    assert spread_text(report.by_target[("B", "y-1")].recall) == ("0.0%", "50.0%", "100.0%")


def test_F_G03_가운데_계산안한값은_빼고() -> None:
    values = [Fraction(60, 100), None, Fraction(70, 100)]
    assert spread_text(sa.spread(values)) == ("60.0%", "65.0%", "70.0%")
    assert sa.spread([None, None]) is None


def test_F_G03_난이도별_범주별() -> None:
    answers = answers_doc(
        "easy-1",
        3,
        item_difficulties=["easy", "easy", "normal"],
        categories=["secret", "admin_path", "secret"],
    )
    found = [hit(0), hit(2), miss(1, "admin_path")]
    report = sa.build_report([scored(answers, "easy-1", "A", 1, found)], [])
    recall = {d: pct(report.by_difficulty[("A", d)].recall[1]) for d in ("easy", "normal")}
    assert recall == {"easy": "50.0%", "normal": "100.0%"}  # 정답의 난이도로
    assert report.by_difficulty[("A", "hard")].recall == {1: None}
    # 정밀도는 대상(정답지 맨 위)의 난이도로: 대상이 easy라 normal 묶음에는 정밀도가 없다
    assert pct(report.by_difficulty[("A", "easy")].precision[1]) == "66.7%"
    assert report.by_difficulty[("A", "normal")].precision == {}
    by_cat = report.by_category
    assert pct(by_cat[("A", "secret")].recall[1]) == "100.0%"  # 주 범주(첫째)로
    assert pct(by_cat[("A", "admin_path")].recall[1]) == "0.0%"
    assert pct(by_cat[("A", "secret")].precision[1]) == "100.0%"  # 결과의 범주로
    assert pct(by_cat[("A", "admin_path")].precision[1]) == "0.0%"
    assert by_cat[("A", "debug_flag")].recall == {1: None}  # 정답 0 → `-`


def test_F_G03_juice_정밀도_하한() -> None:
    juice = answers_doc("juice-shop", 10, origin="practice")
    found = [hit(0), hit(1), hit(2)] + [miss(k) for k in range(4)]
    s = scored(juice, "juice-shop", "A", 1, found, kind="practice")
    report = sa.build_report([s, *xy_runs()], [])
    assert pct(report.practice["A"].precision[1]) == "42.9%"
    assert report.overall["A"].recall_spread is None  # 심은 번들 묶음과 섞지 않는다
    assert spread_text(report.overall["B"].recall_spread) == ("60.0%", "65.0%", "70.0%")
    verdicts = [v for v in s.verdicts if v != "match"]
    assert len(verdicts) == 4  # 짝 안 된 결과 4개(요약.md 목록은 F-G04 시험)


def test_F_G03_상한에_걸린_실행수() -> None:
    answers = answers_doc("easy-1", 6)
    runs = [
        scored(answers, "easy-1", "A", 1, None, "timeout"),
        scored(answers, "easy-1", "A", 2, None, "budget_exceeded"),
        scored(answers, "easy-1", "A", 3, None, "format_failure"),
    ]
    report = sa.build_report(runs, [])
    assert (report.limited("A"), report.limited("B")) == (2, 0)


def test_F_G03_시간·비용_null은_빼고() -> None:
    answers = answers_doc("easy-1", 6)
    runs = [
        scored(answers, "easy-1", "A", 1, [], cost=0.5, wall_s=300.0),
        scored(answers, "easy-1", "A", 2, [], cost=None, wall_s=900.0),
        scored(answers, "easy-1", "A", 3, [], cost=0.75, wall_s=600.0),
    ]
    stats = sa.build_report(runs, []).by_target[("A", "easy-1")]
    assert stats.cost_usd is not None and stats.minutes is not None
    assert (stats.cost_usd.low, stats.cost_usd.mid, stats.cost_usd.n) == (
        Fraction(1, 2),
        Fraction(5, 8),
        2,
    )
    assert [stats.minutes.low, stats.minutes.mid, stats.minutes.high] == [5, 10, 15]


# --- 셋째를 더할지 (규칙 10, 설계 8.2) --------------------------------------------------------


def advice(*rows: tuple[str, str, int, int, int]) -> tuple[str, ...]:
    """(대상, 조건, 차례, 정답 수, 짝 수) → 권고 줄. 대상의 난이도는 이름 앞부분."""
    runs = [fake_score(t, c, r, n, k, difficulty=t.split("-")[0]) for t, c, r, n, k in rows]
    return sa.build_report(runs, []).advice


def two_bundles(
    condition: str, matched: Sequence[int], difficulty: str = "normal"
) -> list[tuple[str, str, int, int, int]]:
    """그 난이도 번들 둘(정답 9·9 = 합 18)에서 차례마다 짝 합이 `matched`가 되게."""
    rows = []
    for r, k in enumerate(matched, start=1):
        rows.append((f"{difficulty}-1", condition, r, 9, min(k, 9)))
        rows.append((f"{difficulty}-2", condition, r, 9, k - min(k, 9)))
    return rows


def test_F_G03_예시_normal_A가20넘으면_두조건모두셋째() -> None:
    lines = advice(*two_bundles("A", [5, 9]), *two_bundles("B", [10, 13]))
    assert lines == (
        "normal: 번들 normal-1·normal-2를 두 조건 모두 셋째 차례로 (20%p 넘음: A 22.2%p)",
    )


def test_F_G03_두차례차이20_1p면_셋째권고() -> None:
    rows = [("hard-1", "A", 1, 1000, 500), ("hard-1", "A", 2, 1000, 701)]
    rows += [("hard-1", "B", 1, 1000, 500), ("hard-1", "B", 2, 1000, 500)]
    assert advice(*rows) == ("hard: 번들 hard-1를 두 조건 모두 셋째 차례로 (20%p 넘음: A 20.1%p)",)


def test_F_G03_범위20p는_그대로() -> None:
    lines = advice(*two_bundles("A", [5, 7], "easy"), *two_bundles("B", [5, 7], "easy"))
    assert lines == ("easy: 범위가 두 값 (N = 2, 셋째 없음)",)
    # 반올림 전 값으로 댄다: 500/1000 → 700/1000은 꼭 20%p라 넘지 않는다
    rows = [("hard-1", c, r, 1000, k) for c in "AB" for r, k in ((1, 500), (2, 700))]
    assert advice(*rows) == ("hard: 범위가 두 값 (N = 2, 셋째 없음)",)


def test_F_G03_셋째뒤_겹치지않으면_줄없음() -> None:
    assert advice(*two_bundles("A", [5, 9, 8]), *two_bundles("B", [10, 13, 12])) == ()


def test_F_G03_셋째뒤_겹치면_차이를말할수없음() -> None:
    lines = advice(*two_bundles("A", [5, 9, 8]), *two_bundles("B", [8, 13, 12]))
    assert lines == ("normal: 차이를 말할 수 없음 (범위가 겹침: A 27.8~50.0%, B 44.4~72.2%)",)


def test_F_G03_조건마다_N이다르면_알림() -> None:
    lines = advice(*two_bundles("A", [5, 9, 8]), *two_bundles("B", [10, 13]))
    assert lines == ("normal: 조건마다 반복 수가 다름(A 3, B 2) — 같은 N으로 맞춘 뒤 보기",)


def test_F_G03_규칙에_T를바꿔_다시채점() -> None:
    answers = answers_doc("easy-1", 6)
    rec = record("easy-1", "A", 1)
    read = run_read(rec, [hit(0, offset=2)])
    assert score_run(read, answers).matched == 1
    assert score_run(read, answers, Rules(tolerance=0)).matched == 0
