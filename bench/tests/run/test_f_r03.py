"""F-R03 Claude Code 실행 (R4) 시험.

진짜 claude.exe 대신 fake_claude/claude.py를 띄운다(실험구조 3.9).

기능명세 F-R03 예시를 옮겼다(값은 가상).
"""

from __future__ import annotations

import copy
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from common.contracts import Json, read_json
from run import claude_cmd as cc
from run import env as renv
from run import workdir as rw
from run.store import read_stream

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parent
FAKE = Path(__file__).resolve().parent / "fake_claude" / "claude.py"
# venv python.exe는 대리라 환경에 변수를 더한다 — 바탕 파이썬으로 띄운다(기능 메모)
PYTHON = Path(getattr(sys, "_base_executable", sys.executable))
SCHEMA = read_json(BENCH / "contracts" / "findings.schema.json")
MODEL = "claude-test-4-0-20261101"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def scenario(tmp_path: Path, name: str = "s", **fields: Any) -> list[str]:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    return [str(PYTHON), "-I", str(FAKE), "--scenario", str(path)]


def env_for(tmp_path: Path) -> dict[str, str]:
    return renv.claude_env(os.environ, tmp_path / "config")


def command(program: list[str], mcp: Path, **kw: Any) -> list[str]:
    args: dict[str, Any] = {
        "prompt": "가짜 지시문",
        "model": MODEL,
        "effort": "high",
        "schema": SCHEMA,
        "mcp_config": mcp,
        "max_budget_usd": 2.52,
    }
    args.update(kw)
    return cc.build_command(program, **args)


def mcp_files(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for condition in ("A", "B"):
        run_dir = tmp_path / f"run-{condition}"
        (run_dir / "target").mkdir(parents=True)
        run = rw.RunDir(batch_dir=tmp_path, run_dir=run_dir, target=run_dir / "target")
        out[condition] = rw.write_mcp_config(run, condition, PYTHON, ROOT).path
    return out


def run(program: list[str], tmp_path: Path, timeout_s: float = 60.0, **kw: Any) -> cc.Finished:
    mcp = mcp_files(tmp_path)["A"] if "mcp" not in kw else kw.pop("mcp")
    return cc.run_process(
        command(program, mcp, **kw), cwd=tmp_path, env=env_for(tmp_path), timeout_s=timeout_s
    )


def is_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def findings(n: int) -> dict[str, Any]:
    item = {
        "category": "secret",
        "file": "assets/app.js",
        "line": 1,
        "evidence": "가짜 값",
        "reason": "가짜",
        "confidence": "low",
    }
    return {"findings": [dict(item, line=i + 1) for i in range(n)]}


def result(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 3,
        "total_cost_usd": 0.01,
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
    base.update(fields)
    return base


def tool_use(use_id: str, name: str) -> dict[str, Any]:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": {"file_path": "a.js"}}
    return {"type": "assistant", "message": {"content": [block]}}


# --- 예시 ------------------------------------------------------------------------------------


def test_F_R03_예시_ok_결과3개(tmp_path: Path) -> None:
    """가짜가 init 줄 → 도구 호출 2번 → result(구조화 결과 3개) → 상태 ok, 결과 3개."""
    program = scenario(
        tmp_path,
        lines=[tool_use("t1", "Read"), tool_use("t2", "Grep")],
        result=result(structured_output=findings(3)),
    )
    finished = run(program, tmp_path)
    parsed = read_stream(finished.stream)
    assert cc.outcome_status(finished, parsed) == ("ok", "")
    assert parsed.result is not None
    assert len(parsed.result["structured_output"]["findings"]) == 3  # type: ignore[call-overload,index,arg-type]
    assert parsed.tool_calls == {"Read": 1, "Grep": 1}
    assert finished.exit_code == 0


def test_F_R03_예시_result없이_종료코드1_error(tmp_path: Path) -> None:
    finished = run(scenario(tmp_path, result=None, exit_code=1), tmp_path)
    status, _ = cc.outcome_status(finished, read_stream(finished.stream))
    assert (status, finished.exit_code) == ("error", 1)


@pytest.mark.parametrize(
    "structured",
    [
        pytest.param(None, id="없음"),
        pytest.param("{not json", id="JSON아님"),
        pytest.param([], id="목록"),
    ],
)
def test_F_R03_예시_구조화결과없음_format_failure(tmp_path: Path, structured: Any) -> None:
    fields = {} if structured is None else {"structured_output": structured}
    finished = run(scenario(tmp_path, result=result(**fields)), tmp_path)
    assert cc.outcome_status(finished, read_stream(finished.stream))[0] == "format_failure"


def test_F_R03_비용상한_budget_exceeded(tmp_path: Path) -> None:
    """result 줄이 금액 상한으로 끝났다고 알리면(`subtype`, 추정) budget_exceeded."""
    program = scenario(tmp_path, result=result(subtype=cc.BUDGET_SUBTYPE, is_error=True))
    finished = run(program, tmp_path)
    assert cc.outcome_status(finished, read_stream(finished.stream))[0] == "budget_exceeded"


def test_F_R03_시간상한_자식까지_끝냄_timeout(tmp_path: Path) -> None:
    """가짜가 상한보다 오래 멈추고 자식 하나를 띄움 → 나무째 끝냄(자식도 없음), 상태 timeout."""
    pidfile = tmp_path / "child.pid"
    program = scenario(tmp_path, child_pidfile=str(pidfile), sleep_s=600, result=None)
    started = time.monotonic()
    finished = run(program, tmp_path, timeout_s=3.0)
    assert time.monotonic() - started < 30
    assert finished.timed_out
    assert finished.exit_code is None
    assert cc.outcome_status(finished, read_stream(finished.stream))[0] == "timeout"
    child = int(pidfile.read_text("utf-8"))
    deadline = time.monotonic() + 10
    while is_alive(child) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not is_alive(child), "자식 프로세스가 남음"


def test_F_R03_읽기상한넘으면_끝내고_error(tmp_path: Path) -> None:
    program = scenario(tmp_path, spam_bytes=4 * 1024 * 1024, sleep_s=600)
    mcp = mcp_files(tmp_path)["A"]
    finished = cc.run_process(
        command(program, mcp),
        cwd=tmp_path,
        env=env_for(tmp_path),
        timeout_s=60.0,
        max_stream_bytes=1024 * 1024,
    )
    assert finished.too_large and not finished.timed_out
    assert len(finished.stream) <= 1024 * 1024
    assert cc.outcome_status(finished, read_stream(finished.stream))[0] == "error"


def test_F_R03_AB명령줄_mcp설정만다름(tmp_path: Path) -> None:
    """조건 A·B의 명령줄: `--mcp-config`가 가리키는 파일의 내용만 다르다(실험구조 3.1)."""
    mcp = mcp_files(tmp_path)
    recorded = {}
    for condition in ("A", "B"):
        out = tmp_path / f"argv-{condition}.json"
        program = scenario(tmp_path, f"s{condition}", record=str(out))
        finished = run(program, tmp_path, mcp=mcp[condition])
        assert cc.outcome_status(finished, read_stream(finished.stream))[0] == "ok"
        recorded[condition] = json.loads(out.read_text("utf-8"))
    a, b = recorded["A"]["args"], recorded["B"]["args"]
    assert len(a) == len(b)
    differ = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
    assert differ == [a.index("--mcp-config") + 1]
    assert json.loads(mcp["A"].read_text("utf-8")) == {"mcpServers": {}}
    assert list(json.loads(mcp["B"].read_text("utf-8"))["mcpServers"]) == ["rea"]
    assert recorded["A"]["env"] == recorded["B"]["env"]  # 환경 이름도 같다
    # 명령줄은 명세 F-R03 2의 인자를 그 차례로 담는다
    allowed = (
        "Read(./**) Grep(./**) Glob(./**) mcp__rea__analyze_javascript_application"
        " mcp__rea__audit_release_exposure mcp__rea__trace_javascript_semantics"
        " mcp__rea__trace_application_feature"
    )
    expected = [
        "-p", "가짜 지시문", "--model", MODEL, "--effort", "high",
        "--output-format", "stream-json", "--verbose", "--json-schema", a[10],
        "--tools", "Read,Grep,Glob", "--allowedTools", allowed,
        "--permission-mode", "dontAsk", "--strict-mcp-config", "--mcp-config", str(mcp["A"]),
        "--setting-sources", "user", "--disable-slash-commands", "--no-session-persistence",
        "--max-budget-usd", "2.52",
    ]  # fmt: skip
    assert a == expected
    assert json.loads(a[10]) == cc.schema_for_cli(SCHEMA)


def test_F_R03_명령줄은_조건을_받지않음() -> None:
    """두 조건의 차이가 명령줄 함수 안에서 생길 길이 없다(조건 인자가 없다)."""
    import inspect

    params = set(inspect.signature(cc.build_command).parameters)
    assert params == {
        "program", "prompt", "model", "effort", "schema", "mcp_config", "max_budget_usd"
    }  # fmt: skip


def test_F_R03_REA도구넷이_거르개허용목록과_같음() -> None:
    template = json.loads((BENCH / "run" / "mcp-B.json").read_text("utf-8"))
    args = template["mcpServers"]["rea"]["args"]
    assert args[args.index("--allow") + 1].split(",") == list(cc.REA_TOOLS)


@pytest.mark.parametrize(
    "model",
    ["opus", "sonnet", "haiku", "Opus", "opusplan", "claude-opus", "claude", "", "claude-opus-4 x"],
)
def test_F_R03_모델별칭_거절(tmp_path: Path, model: str) -> None:
    with pytest.raises(rw.BatchStop) as e:
        command(["claude.exe"], tmp_path / "mcp.json", model=model)
    assert e.value.rule == "F-R03 2"


@pytest.mark.parametrize("model", ["claude-opus-4-5-20251101", "claude-sonnet-4-6", MODEL])
def test_F_R03_모델전체ID_받음(tmp_path: Path, model: str) -> None:
    argv = command(["claude.exe"], tmp_path / "mcp.json", model=model)
    assert argv[argv.index("--model") + 1] == model


def test_F_R03_명령줄_32767자넘으면_시작안함(tmp_path: Path) -> None:
    with pytest.raises(cc.CommandTooLong):
        command(["claude.exe"], tmp_path / "mcp.json", prompt="가" * 33_000)


def test_F_R03_셸없이_claude_exe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """프로그램은 `%APPDATA%\\npm\\…\\claude.exe`, 인자 목록으로 셸 없이 띄운다."""
    appdata = tmp_path / "Roaming"
    exe = appdata.joinpath(*cc.CLAUDE_EXE_PARTS)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"fake")
    assert cc.claude_exe(str(appdata)) == exe
    assert str(exe).endswith(r"\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")
    seen: dict[str, Any] = {}

    def fake_popen(argv: list[str], **kwargs: Any) -> Any:
        seen["argv"], seen["kwargs"] = argv, kwargs
        raise OSError("멈춤")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with pytest.raises(OSError):
        cc.run_process(
            command([str(exe)], tmp_path / "mcp.json"),
            cwd=tmp_path,
            env={"SystemRoot": "C:\\Windows"},
            timeout_s=1,
        )
    assert seen["argv"][0] == str(exe)
    assert isinstance(seen["argv"], list)
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["cwd"] == tmp_path


def test_F_R03_claude_exe없으면_배치시작안함(tmp_path: Path) -> None:
    with pytest.raises(rw.BatchStop) as e:
        cc.claude_exe(str(tmp_path))
    assert e.value.rule == "F-R03 1"


def test_F_R03_스키마_안받는키워드_뺀사본() -> None:
    original = copy.deepcopy(SCHEMA)
    copied = cc.schema_for_cli(SCHEMA)
    assert original == SCHEMA  # 원본은 그대로(채점기가 원본으로 다시 검사한다)
    text = json.dumps(copied)
    for keyword in ("maxItems", "minimum", "maximum", "minLength", "maxLength"):
        assert f'"{keyword}"' in json.dumps(SCHEMA)
        assert f'"{keyword}"' not in text
    item: Any = copied["properties"]["findings"]["items"]  # type: ignore[index,call-overload]
    source: Any = SCHEMA["properties"]["findings"]["items"]  # type: ignore[index,call-overload]
    assert item["required"] == source["required"]
    assert set(item["properties"]) == set(source["properties"])
    assert item["properties"]["category"]["enum"] == source["properties"]["category"]["enum"]
    assert copied["additionalProperties"] is False  # type: ignore[index,call-overload]


def test_F_R03_스키마사본_칸이름은_키워드여도_남김() -> None:
    schema: Json = {
        "type": "object",
        "properties": {"minimum": {"type": "integer", "minimum": 1}, "x": {"maxLength": 3}},
    }
    assert cc.schema_for_cli(schema) == {
        "type": "object",
        "properties": {"minimum": {"type": "integer"}, "x": {}},
    }


def test_F_R03_claude버전바뀌면_배치멈춤(tmp_path: Path) -> None:
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"fake-1")
    env = env_for(tmp_path)
    first = cc.claude_identity(scenario(tmp_path, "v1"), exe, env, tmp_path)
    assert first.version == "2.1.119"
    watch = cc.ExeWatch()
    watch.check(first)
    watch.check(cc.claude_identity(scenario(tmp_path, "v1"), exe, env, tmp_path))  # 같으면 그대로
    exe.write_bytes(b"fake-2")  # 배치 중간에 실행 파일이 바뀜
    with pytest.raises(rw.BatchStop) as e:
        watch.check(cc.claude_identity(scenario(tmp_path, "v1"), exe, env, tmp_path))
    assert e.value.rule == "F-R03 8"
    newer = cc.claude_identity(scenario(tmp_path, "v2", version="2.1.120 (Claude Code)"), exe, env,
                               tmp_path)  # fmt: skip
    watch2 = cc.ExeWatch()
    watch2.check(first)
    with pytest.raises(rw.BatchStop):
        watch2.check(newer)


def test_F_R03_버전을_읽지못하면_배치멈춤(tmp_path: Path) -> None:
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"fake")
    with pytest.raises(rw.BatchStop):
        cc.claude_identity(scenario(tmp_path, version="모름"), exe, env_for(tmp_path), tmp_path)


# --- 지시문 ----------------------------------------------------------------------------------


def design_prompt() -> str:
    text = (ROOT / "docs" / "설계" / "실험구조.md").read_text("utf-8")
    start = text.index("```\n", text.index("### 8.6 지시문 본문")) + 4
    return text[start : text.index("\n```", start)] + "\n"


def test_F_R03_지시문_꼭넣을문장4개() -> None:
    """prompt.md = 설계 8.6 본문 글자 그대로. 꼭 넣을 문장 ①②④와 ③ 범주 정의·결과 꼴."""
    prompt = (BENCH / "run" / "prompt.md").read_text("utf-8")
    assert prompt == design_prompt(), "prompt.md가 설계 8.6 본문과 다름"
    cc.check_prompt(prompt, "target")
    for phrase in cc.PROMPT_PHRASES:  # ① ② ④
        assert phrase in prompt
    enum = SCHEMA["properties"]["findings"]["items"]["properties"]["category"]["enum"]  # type: ignore[index,call-overload]
    for category in enum:  # type: ignore[union-attr]
        assert f"- {category}" in prompt or f"{category}로 낸다" in prompt  # ③ 범주
    for name in ("file", "line", "evidence", "reason", "confidence", "notes"):  # ③ 결과 꼴
        assert name in prompt
    assert "REA" not in prompt  # 두 조건이 같은 글(실험구조 3.1)


@pytest.mark.parametrize("drop", [0, 1, 2])
def test_F_R03_대상지시문에_글없으면_배치시작안함(drop: int) -> None:
    prompt = (BENCH / "run" / "prompt.md").read_text("utf-8")
    with pytest.raises(rw.BatchStop) as e:
        cc.check_prompt(prompt.replace(cc.PROMPT_PHRASES[drop], "…"), "target")
    assert f"{drop + 1}번" in e.value.detail


def test_F_R03_문지기지시문_첫째셋째있고_둘째없음() -> None:
    gate = (BENCH / "run" / "prompt-gate.md").read_text("utf-8")
    cc.check_prompt(gate, "gate")
    assert cc.PROMPT_PHRASES[1] not in gate


def test_F_R03_예시_문지기지시문에_둘째글있으면_시작안함() -> None:
    gate = (BENCH / "run" / "prompt-gate.md").read_text("utf-8")
    with pytest.raises(rw.BatchStop):
        cc.check_prompt(gate + "\n- 작업 폴더 밖은 보지 않는다.\n", "gate")


def test_F_R03_예시_문지기지시문에_셋째글없으면_시작안함() -> None:
    gate = (BENCH / "run" / "prompt-gate.md").read_text("utf-8")
    with pytest.raises(rw.BatchStop):
        cc.check_prompt(gate.replace(cc.PROMPT_PHRASES[2], "…"), "gate")


# --- 상태 합치기 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "init", "expected"),
    [
        ("ok", "passed", "ok"),
        ("ok", "failed", "condition_mismatch"),
        ("format_failure", "missing", "condition_mismatch"),
        ("budget_exceeded", "failed", "condition_mismatch"),
        ("timeout", "missing", "timeout"),
        ("error", "missing", "error"),
    ],
)
def test_F_R03_상태와_조건확인_합치기(status: str, init: str, expected: str) -> None:
    assert cc.decide_status(status, "", init, "tools")[0] == expected


def test_F_R03_run_json_설정칸_두조건같고_rea_tools만다름() -> None:
    from run.plan import Plan

    plan = Plan("t", (), ("A", "B"), MODEL, "high", 600, 1.5, 7, 1, "0" * 64)
    a = cc.run_settings(plan, "A", "absent", ["//C:/"])
    b = cc.run_settings(plan, "B", "absent", ["//C:/"])
    assert {k for k in a if a[k] != b[k]} == {"rea_tools"}
    assert a["rea_tools"] == [] and b["rea_tools"] == list(cc.REA_TOOLS)


def test_F_R03_가짜도_진짜처럼_셸이아닌_인자목록(tmp_path: Path) -> None:
    """가짜 claude가 받은 `-p` 글이 따옴표·한글째 한 인자로 왔다(셸 해석 없음)."""
    out = tmp_path / "argv.json"
    tricky = '따옴표 " 와 & | > 기호 %PATH% $HOME'
    finished = run(scenario(tmp_path, record=str(out)), tmp_path, prompt=tricky)
    assert finished.exit_code == 0
    args = json.loads(out.read_text("utf-8"))["args"]
    assert args[args.index("-p") + 1] == tricky
