"""F-G01 결과 읽기 (R5) 시험. 기능명세 F-G01 예시를 옮겼다(값은 가상).

실행 폴더는 시험이 tmp_path 아래에 만든다(진짜 `bench/results/`를 쓰지 않는다).
정답지는 `fixtures/g01_g02/answers_ga.json`(F-G02 정답지 ㉮, 대상 `easy-1`).
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from score import read as sr

FIXTURES = Path(__file__).parent / "fixtures" / "g01_g02"
SHA = "3f2a" * 16  # answers_ga.json의 번들 지문
OTHER_SHA = "9c1e" * 16
KEY = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
LINEAR_RATIO_LIMIT = 8.0  # 선형이면 4배 입력에 약 4배, 제곱이면 약 16배 — 그 가운데


def answers() -> dict[str, Json]:
    return read_contract("answers", FIXTURES / "answers_ga.json")


def run_record(
    status: str = "ok", *, condition: str = "A", repeat: int = 1, target: str = "easy-1"
) -> dict[str, Json]:
    """계약 `run`에 맞는 가상 실행 한 번(실험구조 2.4 꼴)."""
    return {
        "schema": "selfaudit-bench/run@1",
        "run_kind": "target",
        "run_id": f"{target}-{condition.lower()}-{repeat}-3f2a9c10",
        "batch_id": "20261126-0100-first",
        "target_id": target,
        "target_kind": "planted",
        "bundle_manifest_sha256": SHA,
        "condition": condition,
        "repeat_index": repeat,
        "started_at": "2026-11-26T01:00:00+09:00",
        "ended_at": "2026-11-26T01:10:00+09:00",
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
            "timeout_s": 600,
            "max_budget_usd": 1.5,
            "tools": ["Read", "Grep", "Glob"],
            "allowed_tools": ["Read", "Grep", "Glob"],
            "rea_tools": [],
            "order_seed": 7,
            "firewall_rule": "absent",
            "deny_rule_forms": ["//C:/"],
        },
        "outcome": {"status": status, "exit_code": 0, "init_check": "passed", "detail": ""},
        "metrics": {
            "wall_s": 600.0,
            "duration_ms": 600000,
            "duration_api_ms": 500000,
            "num_turns": 12,
            "total_cost_usd": 0.75,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_read_input_tokens": 40,
            },
            "tool_calls": {"Read": 5},
        },
        "network": {
            "netguard_blocked": 0,
            "netguard_local": 0,
            "netstat_endpoints": 0,
            "guarded_processes": 0,
            "rea_processes": 0,
        },
        "transcript": {"stored": "results", "bytes": 100, "sha256": SHA},
    }


def finding(i: int, **over: Json) -> dict[str, Json]:
    item: dict[str, Json] = {
        "category": "secret",
        "file": "assets/index-3f2a.js",
        "line": 12,
        "evidence": f'k{i}: "{KEY}"',
        "reason": "평문 키",
        "confidence": "high",
    }
    item.update(over)
    return item


def findings_doc(count: int, **over: Json) -> dict[str, Json]:
    return {"findings": [finding(i, **over) for i in range(count)], "notes": ""}


def make_run(
    root: Path,
    name: str,
    record: dict[str, Json] | None,
    found: dict[str, Json] | None = None,
    *,
    raw_findings: bytes | None = None,
) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    if record is not None:
        (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    if found is not None:
        (run_dir / "findings.json").write_text(
            json.dumps(found, ensure_ascii=False), encoding="utf-8"
        )
    if raw_findings is not None:
        (run_dir / "findings.json").write_bytes(raw_findings)
    return run_dir


# --- 예시 ------------------------------------------------------------------------------------


def test_F_G01_계약맞음_통과(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record(), findings_doc(12))
    read = sr.read_run(run_dir, answers())
    assert read.status == "ok"
    assert read.findings is not None
    assert len(read.findings) == 12
    first = read.findings[0]
    assert (first.index, first.category, first.line) == (0, "secret", 12)
    assert read.scored
    assert read.run_id == "easy-1-a-1-3f2a9c10"


def test_F_G01_줄이_12점0이어도_정수로(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record(), findings_doc(1, line=12.0))
    read = sr.read_run(run_dir, answers())
    assert read.findings is not None
    assert read.findings[0].line == 12
    assert isinstance(read.findings[0].line, int)


@pytest.mark.parametrize(
    "over",
    [
        {"evidence": "x" * 301},  # evidence 300자 넘음
        {"category": "xss"},  # 범주 밖
        {"line": 10_000_001},  # 줄 번호 상한
        {"line": 0},
        {"reason": "y" * 501},
    ],
)
def test_F_G01_계약틀림_format_failure(tmp_path: Path, over: dict[str, Json]) -> None:
    run_dir = make_run(tmp_path, "r", run_record(), findings_doc(1, **over))
    read = sr.read_run(run_dir, answers())
    assert read.status == "format_failure"
    assert read.findings is None
    assert read.problems  # 값 없는 까닭
    assert all("x" * 10 not in str(p) and "y" * 10 not in str(p) for p in read.problems)


def test_F_G01_결과101개_format_failure(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record(), findings_doc(101))
    assert sr.read_run(run_dir, answers()).status == "format_failure"
    exactly = make_run(tmp_path, "r100", run_record(), findings_doc(100))
    assert sr.read_run(exactly, answers()).status == "ok"


def test_F_G01_findings없음_format_failure(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record())
    read = sr.read_run(run_dir, answers())
    assert read.status == "format_failure"
    assert read.findings is None


def test_F_G01_findings깨짐_format_failure(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record(), raw_findings=b'{"findings": [')
    assert sr.read_run(run_dir, answers()).status == "format_failure"


@pytest.mark.parametrize("status", ["timeout", "budget_exceeded", "format_failure"])
def test_F_G01_timeout_결과없이_상태만(tmp_path: Path, status: str) -> None:
    # findings.json이 있어도 읽지 않는다(결과 없이 채점, 재현율 0은 F-G03)
    run_dir = make_run(tmp_path, "r", run_record(status), findings_doc(3))
    read = sr.read_run(run_dir, answers())
    assert read.status == status
    assert read.findings is None
    assert read.scored


def test_F_G01_condition_mismatch_다시돌릴실행(tmp_path: Path) -> None:
    dirs = [
        make_run(tmp_path, "a1", run_record("condition_mismatch")),
        make_run(tmp_path, "a2", run_record("error", repeat=2)),
        make_run(tmp_path, "a3", run_record("ok", repeat=3), findings_doc(2)),
    ]
    summary = sr.read_runs(dirs, {"easy-1": answers()})
    assert [r.run_id for r in summary.rerun] == ["easy-1-a-1-3f2a9c10", "easy-1-a-2-3f2a9c10"]
    assert [r.status for r in summary.runs] == ["ok"]
    assert not summary.rerun[0].scored


def test_F_G01_runjson없음·계약실패_읽지못함(tmp_path: Path) -> None:
    broken = run_record()
    broken["condition"] = "D"
    dirs = [
        make_run(tmp_path, "none", None, findings_doc(1)),
        make_run(tmp_path, "bad", broken, findings_doc(1)),
        make_run(tmp_path, "good", run_record(), findings_doc(1)),
    ]
    summary = sr.read_runs(dirs, {"easy-1": answers()})
    assert [u.run_dir.name for u in summary.unreadable] == ["none", "bad"]
    assert len(summary.runs) == 1
    with pytest.raises(sr.RunUnreadableError):
        sr.read_run(dirs[0], answers())


def test_F_G01_지문다르면_그대상_채점멈춤(tmp_path: Path) -> None:
    other = run_record(target="easy-2")
    other_answers = answers()
    other_answers["bundle_id"] = "easy-2"
    changed = run_record(repeat=2)
    changed["bundle_manifest_sha256"] = OTHER_SHA
    dirs = [
        make_run(tmp_path, "e1-1", run_record(), findings_doc(1)),
        make_run(tmp_path, "e1-2", changed, findings_doc(1)),
        make_run(tmp_path, "e2-1", other, findings_doc(1)),
    ]
    summary = sr.read_runs(dirs, {"easy-1": answers(), "easy-2": other_answers})
    assert summary.stopped_targets == ("easy-1",)
    assert [r.target_id for r in summary.runs] == ["easy-2"]
    assert ("A", "easy-1") not in summary.counts
    with pytest.raises(sr.ManifestMismatchError):
        sr.read_run(dirs[1], answers())


def test_F_G01_다른대상의정답지_멈춤(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, "r", run_record(target="easy-2"), findings_doc(1))
    with pytest.raises(sr.ScoreError):
        sr.read_run(run_dir, answers())
    with pytest.raises(sr.ScoreError):
        sr.read_runs([run_dir], {"easy-1": answers()})  # easy-2 정답지를 받지 못함


def test_F_G01_정답지없는대상은_지문을대지않음(tmp_path: Path) -> None:
    record = run_record(target="mine-app")
    record["target_kind"] = "mine"
    record["run_id"] = "mine-app-a-1-3f2a9c10"
    run_dir = make_run(tmp_path, "r", record, findings_doc(2))
    summary = sr.read_runs([run_dir], {"mine-app": None})
    assert [r.status for r in summary.runs] == ["ok"]


def test_F_G01_상태별수_조건·대상마다(tmp_path: Path) -> None:
    dirs = [
        make_run(tmp_path, "a1", run_record("ok"), findings_doc(1)),
        make_run(tmp_path, "a2", run_record("timeout", repeat=2)),
        make_run(tmp_path, "a3", run_record("ok", repeat=3)),  # findings 없음 → format_failure
        make_run(tmp_path, "b1", run_record("ok", condition="B"), findings_doc(1)),
        make_run(tmp_path, "b2", run_record("condition_mismatch", condition="B", repeat=2)),
    ]
    summary = sr.read_runs(dirs, {"easy-1": answers()})
    assert summary.counts == {
        ("A", "easy-1"): {"format_failure": 1, "ok": 1, "timeout": 1},
        ("B", "easy-1"): {"condition_mismatch": 1, "ok": 1},
    }


# --- 처리량 (보안규칙 5장) -------------------------------------------------------------------


def test_F_G01_처리량_결과파일_4배에_4배쯤(tmp_path: Path) -> None:
    """계약 상한(100개)을 넘는 큰 결과 파일도 형식 실패로 읽는다 — 원문이 모두 다른 한글 결과."""

    def doc(count: int) -> dict[str, Json]:
        out = findings_doc(0)
        out["findings"] = [
            finding(i, evidence=f"한글 근거 {i:06d} — 값 {KEY}", reason=f"이유 {i}")
            for i in range(count)
        ]
        return out

    small = make_run(tmp_path, "s", run_record(), doc(2_500))
    large = make_run(tmp_path, "l", run_record(), doc(10_000))
    start = time.perf_counter()
    assert sr.read_run(small, answers()).status == "format_failure"
    t_small = time.perf_counter() - start
    start = time.perf_counter()
    assert sr.read_run(large, answers()).status == "format_failure"
    t_large = time.perf_counter() - start
    assert t_large / max(t_small, 1e-3) < LINEAR_RATIO_LIMIT


def test_F_G01_run기록은_그대로_넘김(tmp_path: Path) -> None:
    record = run_record()
    run_dir = make_run(tmp_path, "r", copy.deepcopy(record), findings_doc(1))
    assert sr.read_run(run_dir, answers()).record == record
