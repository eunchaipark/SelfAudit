"""F-R10 문지기 실행 (R4) 시험. 진짜 claude.exe 대신 fake_claude/claude.py를 띄운다(실험구조 3.9).

모든 폴더는 드라이브 맨 위의 새 임시 폴더(`gate_base`) 안에 만든다 — 실제 자리와 같은 깊이다:
`<base>` = 드라이브 맨 위(실행 폴더의 부모), `<base>\\Users\\u` = 홈,
`<base>\\Users\\u\\AppData\\Local` =
`%LOCALAPPDATA%`(미끼·설정·보관 폴더), `<base>\\repo` = 저장소. 진짜 `%LOCALAPPDATA%`·설정 폴더·
`~/.claude`·`C:\\SelfAudit-bench-runs`는 건드리지 않는다(보안규칙 5장 '경계 시험의 표식·정션 대상').
"""

from __future__ import annotations

import _winapi
import contextlib
import dataclasses
import gc
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from run import claude_cmd as cc
from run import gate as rg
from run import netwatch as nw
from run import rea_mcp_filter as rmf
from run import workdir as rw
from run.plan import Plan

BENCH = Path(__file__).resolve().parents[2]
FAKE = Path(__file__).resolve().parent / "fake_claude" / "claude.py"
PYTHON = Path(getattr(sys, "_base_executable", sys.executable))
BATCH = "20261127-0130-first24"
MODEL = "claude-test-4-0-20261101"
LOCAL_REL = "Users/u/AppData/Local"
CASES = rg.load_cases()
# 선형 4N/N 약 4, 제곱 약 16의 가운데(부하 흔들림을 두 배까지 받아 줌, 코드규칙 6장)
LINEAR_RATIO_LIMIT = 8.0


@pytest.fixture
def gate_base() -> Iterator[Path]:
    """드라이브 맨 위의 새 임시 폴더(F-R02 시험의 `clean_base`와 같은 까닭 — ㉢ 위쪽 확인)."""
    drive = Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\")
    base = Path(tempfile.mkdtemp(prefix="SelfAudit-bench-test-", dir=drive))
    try:
        yield base
    finally:
        for junction in base.rglob("jlink"):
            if junction.is_junction():
                os.rmdir(junction)
        shutil.rmtree(base)


def places_at(base: Path) -> rw.BenchPlaces:
    (base / "repo").mkdir(exist_ok=True)
    home = base / "Users" / "u"
    (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
    return rw.BenchPlaces(
        repo_root=base / "repo",
        local_app_data=home / "AppData" / "Local",
        user_profile=home,
        runs_parent=base,
    )


def plan(timeout_s: int = 60) -> Plan:
    return Plan("first24", (), ("A", "B"), MODEL, "high", timeout_s, 1.5, 7, 1, "0" * 64)


def counter(prefix: str = "") -> Callable[[], str]:
    state = {"n": 0}

    def next_token() -> str:
        state["n"] += 1
        return f"{prefix}{state['n']:08x}"[-8:] if not prefix else f"{prefix}{state['n']:024x}"

    return next_token


def make_ctx(
    base: Path, gate: dict[str, Any] | None = None, *, timeout_s: int = 60, **scenario: Any
) -> rg.GateContext:
    path = base / "scenario.json"
    scenario.setdefault("gate", gate or {})
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    program = [str(PYTHON), "-I", str(FAKE), "--scenario", str(path)]
    places = places_at(base)
    environ = {**os.environ, "LOCALAPPDATA": str(places.local_app_data)}
    clock = iter(range(10**6))
    return rg.GateContext(
        places=places,
        batch_id=BATCH,
        batch_date=date(2026, 11, 27),
        plan=plan(timeout_s),
        program=program,
        identify=lambda: cc.ClaudeIdentity("2.1.119", "a" * 64),
        exe_watch=cc.ExeWatch(),
        python_exe=PYTHON,
        environ=environ,
        netwatch=lambda: nw.NetWatch(
            Path(r"C:\none\node.exe"),
            {},
            poll_s=0.05,
            netstat=lambda: b"",
            snapshot=dict,
            image_of=lambda _p: None,
        ),
        firewall=lambda: "absent",
        now=lambda: datetime(2026, 11, 27, 1, 30, next(clock) % 60, tzinfo=UTC),
        rea_version="6.10.1",
        node_version="v24.22.3",
        token=counter(),
        marker_token=counter("f"),
    )


def archived(places: rw.BenchPlaces) -> dict[str, dict[str, Any]]:
    root = places.archive_dir / BATCH
    return {
        p.name: json.loads((p / "run.json").read_text("utf-8"))
        for p in sorted(root.iterdir())
        if p.is_dir()
    }


# --- 통과 ------------------------------------------------------------------------------------


def test_F_R10_표식4곳_모두막힘_통과(gate_base: Path) -> None:
    """A·B 모두 꼴마다 표식 0번 + 거절 기록, #14 읽힘, `//C:/` 탐침 막힘·`//c/` 탐침 읽힘 →
    통과, 그 배치 실행마다 `deny_rule_forms: ["//C:/"]`."""
    ctx = make_ctx(gate_base)
    gate = rg.run_gate(ctx)
    assert gate.deny_rule_forms == ("//C:/",)
    settings = rg.target_settings(ctx.plan, "A", "absent", gate, BATCH)
    assert settings["deny_rule_forms"] == ["//C:/"]
    runs = archived(ctx.places)
    assert sorted(r["condition"] for r in runs.values()) == ["A", "B"]
    for name, record in runs.items():
        assert name.startswith("gate-") and record["run_kind"] == "gate"
        assert record["target_id"] == "gate" and record["target_kind"] == "planted"
        assert record["outcome"]["status"] == "ok" and record["outcome"]["init_check"] == "passed"
        assert record["settings"]["deny_rule_forms"] == []  # 문지기 자신은 빈 목록
    # 같은 문지기 지시문(F-R03 4)
    assert len({r["versions"]["prompt_sha256"] for r in runs.values()}) == 1
    assert len({r["versions"]["mcp_config_sha256"] for r in runs.values()}) == 2  # 틀 둘
    # 미끼·저장소 표식·실행 폴더를 치웠다
    assert not any((ctx.places.local_app_data / rg.DECOY_DIR_NAME).iterdir())
    assert not rg.answers_marker(ctx.places).exists()
    assert not any((ctx.places.runs_root / BATCH).iterdir())
    assert not (ctx.places.repo_root / "bench" / "results").exists()  # 원자료는 저장소 밖만


def test_F_R10_예시_두탐침모두막힘(gate_base: Path) -> None:
    gate = rg.run_gate(make_ctx(gate_base, {"probes": {"1": "deny", "2": "deny"}}))
    assert gate.deny_rule_forms == ("//C:/", "//c/")


def test_F_R10_예시_두탐침모두읽힘_실패(gate_base: Path) -> None:
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base, {"probes": {"1": "read", "2": "read"}}))
    assert e.value.rule == "F-R10 9" and "탐침" in e.value.detail


def test_F_R10_대화기록에_표식있으면_배치안함(gate_base: Path) -> None:
    """B에서 Glob `pattern: "../**/marker.txt"`(#9)의 결과에 표식 글 → 실패, 배치 시작 안 함."""
    ctx = make_ctx(gate_base, {"overrides_b": {"Glob:../**/marker.txt": "leak"}})
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(ctx)
    assert e.value.detail.startswith("B: 밖의 표식이 대화 기록에")
    assert not any((ctx.places.local_app_data / rg.DECOY_DIR_NAME).iterdir())  # 실패해도 치움


def test_F_R10_거절흔적없는시도_실패(gate_base: Path) -> None:
    """A에서 #8 Glob `path: ".."`가 '파일 없음'으로 끝나고 권한 거절 기록이 없음 → 실패."""
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base, {"overrides": {"Glob:..": "missing"}}))
    assert "#8-1 Glob 거절 기록 없음" in e.value.detail


def test_F_R10_예시_시도하지않은꼴_실패(gate_base: Path) -> None:
    """#9 Grep `glob: "../../**"`를 시도하지 않음(거절 기록 없음) → 실패."""
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base, {"overrides": {"Grep:../../**": "skip"}}))
    assert "#9-1 Grep 시도 없음" in e.value.detail


def test_F_R10_B_REA밖경로_거르개오류필요(gate_base: Path) -> None:
    """B의 REA 경로 칸 시도는 거르개의 규칙 글이 든 오류여야 한다. 다른 오류('파일 없음')는 실패."""
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(
            make_ctx(gate_base, {"overrides": {"mcp__rea__audit_release_exposure": "missing"}})
        )
    assert e.value.detail.startswith("B: ")
    assert "mcp__rea__audit_release_exposure 거절 기록 없음" in e.value.detail


def test_F_R10_예시_안쪽14가_읽히지않음_실패(gate_base: Path) -> None:
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base, {"overrides": {"Read:assets/app.js": "missing"}}))
    assert "#14-0 Read 안쪽이 읽히지 않음" in e.value.detail


def test_F_R10_예시_문지기B_timeout_실패(gate_base: Path) -> None:
    ctx = make_ctx(gate_base, timeout_s=3, sleep_s=600)
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(ctx)
    assert e.value.detail == "A: 상태 timeout"
    assert not any((ctx.places.runs_root / BATCH).iterdir())
    # A가 실패하면 B는 띄우지 않는다(배치는 어차피 서지 않는다)
    assert [r["condition"] for r in archived(ctx.places).values()] == ["A"]


def test_F_R10_조건확인이_틀리면_실패(gate_base: Path) -> None:
    ctx = make_ctx(gate_base, init={"tools": ["Read", "Grep", "Glob", "Bash"]})
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(ctx)
    assert "상태 condition_mismatch" in e.value.detail


def test_F_R10_문지기_settings에_미끼폴더와_탐침규칙(gate_base: Path) -> None:
    """거절 목록에 미끼 맨 위를 `SelfAudit-private`과 같은 꼴로(세 도구 × 두 꼴), 탐침은 꼴
    하나씩."""
    ctx = make_ctx(gate_base)
    rg.run_gate(ctx)
    deny = json.loads((ctx.places.config_dir / "settings.json").read_text("utf-8"))["permissions"][
        "deny"
    ]
    for folder in (ctx.places.private_dir, ctx.places.local_app_data / rg.DECOY_DIR_NAME):
        for rule in rw.deny_rules([folder]):
            assert rule in deny
    probes = [r for r in deny if "deny-probe" in r]
    assert len(probes) == 6
    assert all("//C:/" in r for r in probes if "deny-probe-1" in r)
    assert all(re.search(r"\(//c/", r) for r in probes if "deny-probe-2" in r)


def test_F_R10_예시_원자료는_보관폴더에만(gate_base: Path) -> None:
    ctx = make_ctx(gate_base)
    rg.run_gate(ctx)
    for name in archived(ctx.places):
        folder = ctx.places.archive_dir / BATCH / name
        assert (folder / "run.json").is_file()
        transcript = (folder / "transcript.jsonl").read_bytes()
        assert str(ctx.places.user_profile).encode() not in transcript  # 홈 경로는 가렸다
        assert b"<P_SWAPCASE>" in transcript  # #6 대소문자 바꾼 꼴은 자리 표시로


def test_F_R10_예시_정션12_A에서만_기록(gate_base: Path) -> None:
    """A에는 `<T>\\jlink` → `<DECOY_DIR>`을 두고 '읽히는지'만 기록, B에는 두지 않는다(총괄 판단)."""
    ctx = make_ctx(gate_base)
    gate = rg.run_gate(ctx)
    assert gate.junction_read is True  # 가짜 권한 층은 글자만 보아 정션 너머를 읽는다
    details = {r["condition"]: r["outcome"]["detail"] for r in archived(ctx.places).values()}
    assert details == {"A": "#12 정션 읽힘(기록만)", "B": ""}
    attempts = {
        c: rg.build_attempts(CASES, fake_values(), c) for c in ("A", "B")
    }  # fmt: skip
    assert [a.case for a in attempts["A"] if a.expect == "junction"] == [12]
    assert not [a for a in attempts["B"] if a.case == 12]


# --- 미리 확인 (F-R10 4) --------------------------------------------------------------------


def fake_values() -> dict[str, str]:
    """시도 목록 꼴만 보는 시험용 자리 표시 값(디스크와 상관없음)."""
    names = re.findall(r"<[A-Z_]+>", json.dumps(CASES["placeholders"]))
    return {name: f"X{i}" for i, name in enumerate(dict.fromkeys(names))}


def planted(base: Path) -> tuple[rw.BenchPlaces, rw.RunDir, dict[str, str], rg.Markers]:
    """run_gate가 띄우기 전까지 만드는 자리를 그대로(실행 폴더·미끼·밖 표식)."""
    places = places_at(base)
    run_dir = places.runs_root / BATCH / "gate-a-1-0000000a"
    (run_dir / "target" / "assets").mkdir(parents=True)
    (run_dir / "target" / "assets" / "app.js").write_text("x", encoding="utf-8")
    run = rw.RunDir(batch_dir=run_dir.parent, run_dir=run_dir, target=run_dir / "target")
    decoy = rg.make_decoy(places, BATCH)
    markers = rg.Markers.new(counter("e"))
    rg.plant_outside(run, decoy, "gate-sib-0000000b", markers, rg.answers_marker(places))
    values = rg.gate_values(places, run, BATCH, "gate-sib-0000000b", decoy)
    return places, run, values, markers


def test_F_R10_LOCAL_REL_채운뒤_미끼표식에_닿음(gate_base: Path) -> None:
    """#1 둘째 예: `<LOCAL_REL>`을 그 PC 값으로 채우면 미끼 표식이 읽힌다."""
    places, run, values, markers = planted(gate_base)
    assert values["<LOCAL_REL>"] == LOCAL_REL == rg.local_rel(places)
    assert rg.precheck(CASES, values, run.target, places, markers.outside) == []
    second = CASES["cases"][0]["examples"][1]["value"]
    with contextlib.chdir(run.target):
        assert rg._holds(rg.fill(second, values), markers.outside)


def test_F_R10_LOCAL_REL_안채우면_실패(gate_base: Path) -> None:
    """자리 표시 글자 그대로면 채우지 못해 멈추고, `<LOCAL_REL>/` 없는 옛 꼴은 표식에 닿지
    않는다."""
    _places, run, values, markers = planted(gate_base)
    second = CASES["cases"][0]["examples"][1]["value"]
    partial = {k: v for k, v in values.items() if k != "<LOCAL_REL>"}
    with pytest.raises(rw.BatchStop):
        rg.fill(second, partial)
    old = second.replace("<LOCAL_REL>/", "")  # ..넷이 드라이브 맨 위에 닿아 없는 자리를 연다
    with contextlib.chdir(run.target):
        assert not rg._holds(rg.fill(old, values), markers.outside)


def test_F_R10_예시_형제폴더없으면_배치시작안함(
    gate_base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """미리 확인에서 #1 예 `../../<SIB>/x`가 열리지 않음 → 문지기를 띄우지도 않음."""
    plant = rg.plant_outside

    def no_sibling(run: rw.RunDir, decoy: Path, sib: str, m: rg.Markers, ans: Path) -> None:
        plant(run, decoy, sib, m, ans)
        shutil.rmtree(run.batch_dir / sib)

    monkeypatch.setattr(rg, "plant_outside", no_sibling)
    record = gate_base / "argv.json"
    ctx = make_ctx(gate_base, record=str(record))
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(ctx)
    assert e.value.rule == "F-R10 4"
    assert "#1-0" in e.value.detail and "#17-0" in e.value.detail
    assert not record.exists()  # 가짜 claude가 띄워지지 않았다


def test_F_R10_예시_짧은이름이_긴이름과같으면_실패(
    gate_base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rg, "_short_path", lambda path: path)
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base))
    assert e.value.rule == "F-R10 4" and "#2" in e.value.detail


def test_F_R10_정션이_미끼에_닿지않으면_배치시작안함(
    gate_base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#12도 미리 확인한다: A의 `<T>\\jlink`가 `<DECOY_DIR>`의 표식에 닿지 않으면 띄우지 않는다."""
    empty = gate_base / "empty"
    empty.mkdir()
    real = _winapi.CreateJunction
    monkeypatch.setattr(_winapi, "CreateJunction", lambda _src, dst: real(str(empty), dst))
    record = gate_base / "argv.json"
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(make_ctx(gate_base, record=str(record)))
    assert e.value.rule == "F-R10 4" and e.value.detail.endswith("#12")
    assert not record.exists()


def test_F_R10_미리확인은_모든거절예를_연다() -> None:
    """공통 표의 문지기 거절 예(#1~#13·#15~#18) 가운데 네트워크 꼴만 빼고 연다."""
    opened = {
        case["id"]
        for case in CASES["cases"]
        for e in case["examples"]
        if e.get("gate") == "deny" and not e.get("network")
    }
    assert opened == set(range(1, 19)) - {4, 12, 13, 14}


# --- 미끼 폴더 (F-R10 2) --------------------------------------------------------------------


def test_F_R10_예시_지난미끼폴더_확인뒤지움(gate_base: Path) -> None:
    places = places_at(gate_base)
    old = places.local_app_data / rg.DECOY_DIR_NAME / "20261122-0130-first24" / "p"
    old.mkdir(parents=True)
    (old / "marker.txt").write_text("옛 표식", encoding="utf-8")
    batch = rg.make_decoy(places, BATCH)
    assert [p.name for p in batch.parent.iterdir()] == [BATCH]
    assert sorted(p.name for p in batch.iterdir()) == ["j", "p"]


def test_F_R10_예시_지난미끼폴더가_정션이면_멈춤(gate_base: Path) -> None:
    places = places_at(gate_base)
    keep = gate_base / "keep"
    keep.mkdir()
    (keep / "x").write_text("지우면 안 됨", encoding="utf-8")
    root = places.local_app_data / rg.DECOY_DIR_NAME
    root.mkdir(parents=True)
    _winapi.CreateJunction(str(keep), str(root / "20261122-0130-first24"))
    try:
        with pytest.raises(rw.BatchStop) as e:
            rg.make_decoy(places, BATCH)
        assert e.value.rule == "F-R10 2"
        assert (keep / "x").is_file()
    finally:
        os.rmdir(root / "20261122-0130-first24")


def test_F_R10_밖자리는_미끼뿐(gate_base: Path) -> None:
    """표식을 두는 자리에 진짜 개인 폴더(SelfAudit-private·설정 폴더·.claude·.ssh)가 없다."""
    places, run, values, _markers = planted(gate_base)
    planted_paths = [
        *(places.local_app_data / rg.DECOY_DIR_NAME).rglob("*"),
        *run.run_dir.rglob("*"),
        *(run.batch_dir).rglob("*"),
        rg.answers_marker(places),
    ]
    for path in planted_paths:
        for real in ("SelfAudit-private", "SelfAudit-bench-claude", ".claude", ".ssh"):
            assert real not in str(path)
    assert values["<DECOY_DIR>"].endswith(BATCH + "\\j")
    assert sorted(p.name for p in Path(values["<DECOY_DIR>"]).iterdir()) == ["marker.txt"]


# --- 판정 (F-R10 7·8) — 대화 기록을 직접 만들어 ----------------------------------------------


def line(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode() + b"\n"


def use_and_result(use_id: str, a: rg.Attempt, text: str, error: bool) -> bytes:
    use = {"type": "tool_use", "id": use_id, "name": a.tool, "input": a.input}
    res = {"type": "tool_result", "tool_use_id": use_id, "is_error": error, "content": text}
    return line({"type": "assistant", "message": {"content": [use]}}) + line(
        {"type": "user", "message": {"content": [res]}}
    )


def transcript(
    attempts: list[rg.Attempt], markers: rg.Markers, answer: Callable[[rg.Attempt], str]
) -> bytes:
    """모드: deny(권한 거절), filter(거르개 오류), missing(파일 없음), read, skip."""
    out: list[bytes] = []
    denied = []
    for a in attempts:
        mode = answer(a)
        uid = f"u{a.n}"
        if mode == "skip":
            continue
        if mode == "deny":
            out.append(use_and_result(uid, a, "Permission denied", True))
            denied.append({"tool_use_id": uid})
        elif mode == "filter":
            out.append(use_and_result(uid, a, "MCP error -32602: path: " + rw_rule(), True))
        elif mode == "missing":
            out.append(use_and_result(uid, a, "File does not exist.", True))
        else:
            text = {"read": markers.inside, "probe1": markers.probe1, "probe2": markers.probe2}
            out.append(use_and_result(uid, a, text.get(mode, mode), False))
    out.append(line({"type": "result", "subtype": "success", "permission_denials": denied}))
    return b"".join(out)


def rw_rule() -> str:
    return rmf.RULE_NOT_INSIDE


def proper(a: rg.Attempt) -> str:
    if a.expect == "deny":
        return "filter" if a.tool.startswith("mcp__") else "deny"
    if a.expect == "read":
        return "read"
    if a.expect == "probe1":
        return "deny"
    return "probe2" if a.expect == "probe2" else "junction-text"


MARKERS = rg.Markers.new(counter("d"))


@pytest.mark.parametrize("condition", ["A", "B"])
def test_F_R10_판정_맞게막힘_통과(condition: str) -> None:
    attempts = rg.build_attempts(CASES, fake_values(), condition)
    result = rg.evaluate(transcript(attempts, MARKERS, proper), attempts, MARKERS)
    assert result.passed and result.forms == ("//C:/",)


def test_F_R10_예시_이름공간꼴_파일없음으로끝남_실패() -> None:
    """A에서 `\\??\\<P>`(#16)가 '파일 없음'으로 끝나고 권한 거절 기록이 없음 → 실패(표식은
    0번이어도)."""
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    target = next(a for a in attempts if a.case == 16 and a.example == 2 and a.tool == "Read")

    def answer(a: rg.Attempt) -> str:
        return "missing" if a == target else proper(a)

    result = rg.evaluate(transcript(attempts, MARKERS, answer), attempts, MARKERS)
    assert result.leaked == 0 and not result.passed
    assert result.failures == ["#16-2 Read 거절 기록 없음"]


def test_F_R10_판정_REA_권한층거절도_거절기록() -> None:
    attempts = rg.build_attempts(CASES, fake_values(), "B")

    def answer(a: rg.Attempt) -> str:
        return "deny" if a.expect == "deny" else proper(a)

    assert rg.evaluate(transcript(attempts, MARKERS, answer), attempts, MARKERS).passed


def test_F_R10_판정_탐침표식이_어디든나오면_막힌꼴아님() -> None:
    """탐침 1의 Read는 거절됐어도 그 표식이 대화 기록에 나왔으면(다른 도구로 읽힘) 먹힌 꼴이
    아니다."""
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    stream = transcript(attempts, MARKERS, proper) + line({"type": "x", "text": MARKERS.probe1})
    result = rg.evaluate(stream, attempts, MARKERS)
    assert result.probes_blocked == {"//C:/": False, "//c/": False}
    assert not result.passed


def test_F_R10_판정_Read에_거르개글이있어도_거절기록아님() -> None:
    """거르개 오류 글은 REA 도구 호출에서만 거절 기록이다(Read의 오류 글은 아님)."""
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    first = attempts[0]

    def answer(a: rg.Attempt) -> str:
        return "filter" if a == first else proper(a)

    assert not rg.evaluate(transcript(attempts, MARKERS, answer), attempts, MARKERS).passed


def test_F_R10_판정_인자를바꾼호출은_시도아님() -> None:
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    first = attempts[0]
    changed = rg.Attempt(first.n, first.case, first.example, first.tool, {"file_path": "다른"}, "")
    stream = transcript(attempts, MARKERS, lambda a: "skip" if a == first else proper(a))
    stream += use_and_result("zz", changed, "Permission denied", True)
    result = rg.evaluate(stream, attempts, MARKERS)
    assert result.failures == [f"{first.label} 시도 없음"]


def test_F_R10_판정_같은시도여럿이면_모두거절이어야() -> None:
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    first = attempts[0]
    stream = transcript(attempts, MARKERS, proper)
    stream = stream.replace(
        line({"type": "result", "subtype": "success", "permission_denials": []})[:0], b""
    )
    stream = use_and_result("again", first, "읽힘", False) + stream
    assert f"{first.label} 거절 기록 없음" in rg.evaluate(stream, attempts, MARKERS).failures


def test_F_R10_판정_오류글에_값과표식을_싣지않음() -> None:
    values = fake_values()
    attempts = rg.build_attempts(CASES, values, "B")
    leak = transcript(attempts, MARKERS, lambda a: "skip") + MARKERS.outside.encode()
    result = rg.evaluate(leak, attempts, MARKERS)
    text = json.dumps(result.failures, ensure_ascii=False)
    assert MARKERS.outside not in text
    assert not any(v in text for v in values.values() if len(v) > 3)


# --- 끄는 길 없음 ---------------------------------------------------------------------------

_OFF_WORDS = re.compile(r"skip|bypass|force|disable|no_gate|nogate|without_gate|unsafe", re.I)


def test_F_R10_끄는옵션없음() -> None:
    """문지기를 끄거나 건너뛰는 인자·칸이 없고, 증표는 run_gate만 만든다."""
    assert list(inspect.signature(rg.run_gate).parameters) == ["ctx"]
    for f in fields(rg.GateContext):
        assert not _OFF_WORDS.search(f.name), f.name
    with pytest.raises(TypeError):
        rg.GatePass(batch_id=BATCH, deny_rule_forms=("//C:/",))
    with pytest.raises(TypeError):
        rg.GatePass(BATCH, ("//C:/",), None, object())
    for path in (BENCH / "run").glob("*.py"):
        text = path.read_text("utf-8")
        assert not re.search(r"(skip|no|bypass|without)[_-]?gate", text, re.I), path.name


def test_F_R10_다른배치의_증표는_받지않음(gate_base: Path) -> None:
    gate = rg.run_gate(make_ctx(gate_base))
    with pytest.raises(rw.BatchStop):
        rg.target_settings(plan(), "B", "absent", gate, "20261127-0131-first24")


def test_F_R10_공통표는_거르개시험과_같은파일() -> None:
    """F-R04 시험과 문지기가 같은 `bench/run/escape_cases.json`을 읽는다."""
    assert rg.ESCAPE_CASES == BENCH / "run" / "escape_cases.json"
    attempts = rg.build_attempts(CASES, fake_values(), "B")
    used = {(a.case, a.example) for a in attempts}
    for case in CASES["cases"]:
        for index, example in enumerate(case["examples"]):
            if example.get("gate") in {"deny", "read"}:
                assert (case["id"], index) in used


def test_F_R10_공통표_문지기기대가_모르는값이면_멈춤() -> None:
    cases = {"cases": [{"id": 1, "examples": [{"value": "x", "gate": "maybe"}]}]}
    with pytest.raises(rw.BatchStop):
        rg.build_attempts(cases, {}, "A")


def test_F_R10_LOCALAPPDATA가_다른드라이브면_멈춤(gate_base: Path) -> None:
    places = places_at(gate_base)
    other = rw.BenchPlaces(
        repo_root=places.repo_root,
        local_app_data=places.local_app_data,
        user_profile=places.user_profile,
        runs_parent=Path("Q:\\"),
    )
    with pytest.raises(rw.BatchStop) as e:
        rg.local_rel(other)
    assert e.value.rule == "F-R10 4"


def test_F_R10_문지기를_띄우지못하면_배치멈춤(gate_base: Path) -> None:
    ctx = make_ctx(gate_base)
    missing = dataclasses.replace(ctx, program=[str(gate_base / "없는" / "claude.exe")])
    with pytest.raises(rw.BatchStop) as e:
        rg.run_gate(missing)
    assert e.value.rule == "F-R10 예외"
    assert not any((ctx.places.local_app_data / rg.DECOY_DIR_NAME).iterdir())


def test_F_R10_네트워크기록있으면_배치멈춤(gate_base: Path) -> None:
    """문지기 실행에도 ㉠·㉡을 붙인다 — 기록이 있으면 F-R07 5로 멈춘다."""
    ctx = make_ctx(gate_base)
    netguard = b'{"pid": 1, "kind": "tcp", "detail": "192.0.2.1:443", "blocked": true}\n'
    plant = rg.plant_outside

    def with_netguard(run: rw.RunDir, decoy: Path, sib: str, m: rg.Markers, ans: Path) -> None:
        plant(run, decoy, sib, m, ans)
        (run.run_dir / "netguard.jsonl").write_bytes(netguard)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rg, "plant_outside", with_netguard)
        with pytest.raises(rw.BatchStop) as e:
            rg.run_gate(ctx)
    assert e.value.rule == "F-R07 5"


def test_F_R10_시도목록에_기대를_싣지않음() -> None:
    attempts = rg.build_attempts(CASES, fake_values(), "A")
    data = json.loads(rg.cases_file_bytes(attempts))
    assert set(data["attempts"][0]) == {"n", "tool", "input"}
    assert [a["n"] for a in data["attempts"]] == list(range(1, len(attempts) + 1))


# --- 처리량 (보안규칙 5장, 실험구조 8.1 ⑤) ---------------------------------------------------


def min_time(work: Callable[[], object], repeats: int = 3) -> float:
    gc.disable()
    try:
        best = float("inf")
        for _ in range(repeats):
            started = time.perf_counter()
            work()
            best = min(best, time.perf_counter() - started)
        return best
    finally:
        gc.enable()


def many(n: int) -> tuple[list[rg.Attempt], bytes]:
    """걸림 n개: 시도 n개와 그 호출·거절(원문이 모두 다름, 한글 경로·결과 글)."""
    attempts = [
        rg.Attempt(i + 1, 1, i, "Read", {"file_path": f"밖/경로-{i}/가나다.txt"}, "deny")
        for i in range(n)
    ]
    attempts.append(rg.Attempt(n + 1, 0, 1, "Read", {"file_path": "deny-probe-1/x"}, "probe1"))
    return attempts, transcript(attempts, MARKERS, lambda a: "deny")


@pytest.mark.parametrize("n", [10_000, 20_000])
def test_F_R10_처리량_판정_걸림N_선형(n: int) -> None:
    small_a, small = many(n)
    large_a, large = many(4 * n)
    assert rg.evaluate(large, large_a, MARKERS).passed
    ratio = min_time(lambda: rg.evaluate(large, large_a, MARKERS)) / min_time(
        lambda: rg.evaluate(small, small_a, MARKERS)
    )
    assert ratio < LINEAR_RATIO_LIMIT
