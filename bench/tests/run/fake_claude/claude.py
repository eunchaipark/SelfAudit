"""F-R03·R05·R07·R10 시험용 가짜 `claude.exe` (진짜 Claude Code를 부르지 않는다, 실험구조 3.9).

`python -I claude.py --scenario <json> <claude 인자…>` — 실행기는 이 앞부분(`program`)을
`claude.exe`
자리에 넣는다. 표준 라이브러리만 쓴다(`-I`라 bench 모듈을 import할 수 없다).

시나리오 칸(모두 빠질 수 있음):
- `record`: 받은 인자 목록·작업 폴더·환경 이름을 이 파일에 JSON으로 쓴다.
- `version`: `--version`에 답할 글(기본 `2.1.119 (Claude Code)`).
- `init`: `"auto"`(기본 — `--mcp-config`의 서버와 `--model`·`--permission-mode`로 만든다),
`null`(줄 없음),
  `"garbage"`(JSON 아닌 줄), 또는 auto 값에 덮어쓸 칸들.
- `lines`: init 뒤에 그대로 낼 줄들(객체).
- `gate`: 있으면 작업 폴더의 `gate-cases.json`을 읽어 시도마다 도구 호출·결과를 낸다(아래).
- `result`: 마지막 `result` 줄(객체). `null`이면 내지 않음. 기본은 빈 findings로 성공.
- `child_pidfile`: 오래 자는 자식 프로세스를 띄우고 그 pid를 이 파일에 쓴다.
- `sleep_s`: 줄을 다 낸 뒤 이만큼 잔다(시간 상한 시험).
- `exit_code`: 종료 코드(기본 0).
- `spam_bytes`: 이만큼의 줄을 쏟는다(읽기 상한 시험).

`gate` 칸: `{"overrides": {"<n>": "leak"|"skip"|"missing"|"deny"|"read"}, "probes": {"1":
"deny"|"read",
"2": …}}`. 기본은 '권한 층이 맞게 막는' 흉내다 — Read·Grep·Glob은 작업 폴더 안(글자 비교, `..`·절대
꼴은 정규화)이면 읽고 아니면 거절(result 줄 `permission_denials`), REA 도구는 거르개처럼 푼 경로가
안이면
답하고 아니면 오류 글(`input_path: target 안의 있는 경로가 아님`).
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASE_TOOLS = ["Read", "Grep", "Glob"]
REA_TOOLS = [
    "analyze_javascript_application",
    "audit_release_exposure",
    "trace_javascript_semantics",
    "trace_application_feature",
]
FILTER_ERROR = "MCP error -32602: {field}: target 안의 있는 경로가 아님"
DENIED_TEXT = "Permission to use {tool} has been denied."
CHILD_SLEEP_S = 600


def emit(obj: dict[str, Any]) -> None:
    # 진짜 Claude Code처럼 UTF-8 바이트로(-I라 콘솔 코드 페이지를 따르지 않게)
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def arg_after(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args else None


def servers(args: list[str]) -> dict[str, Any]:
    path = arg_after(args, "--mcp-config")
    if path is None:
        return {}
    value = json.loads(Path(path).read_text("utf-8"))
    return dict(value.get("mcpServers", {}))


def init_line(args: list[str], scenario: dict[str, Any]) -> dict[str, Any] | None:
    spec = scenario.get("init", "auto")
    if spec is None:
        return None
    mcp = servers(args)
    tools = list(BASE_TOOLS)
    if "rea" in mcp:
        tools += [f"mcp__rea__{t}" for t in REA_TOOLS]
    line: dict[str, Any] = {
        "type": "system",
        "subtype": "init",
        "cwd": os.getcwd(),
        "session_id": "fake-session",
        "tools": tools,
        "mcp_servers": [{"name": name, "status": "connected"} for name in mcp],
        "model": arg_after(args, "--model"),
        "permissionMode": arg_after(args, "--permission-mode"),
    }
    if isinstance(spec, dict):
        line.update(spec)
    return line


def inside(value: str, cwd: str) -> bool:
    """권한 층 흉내: 작업 폴더 기준으로 정규화한 글이 작업 폴더 아래인가(정션은 따라가지 않음)."""
    if value.startswith("\\\\?\\") and value[5:7] in (":\\", ":/"):
        value = value[4:]  # 드라이브 긴 접두는 같은 파일(#14 셋째 예)
    if value.startswith(("\\\\", "//", "~", "%", "$", "file:", "\\??\\")) or "::" in value:
        return False
    if len(value) >= 2 and value[1] == ":" and value[2:3] not in ("\\", "/"):
        return False  # 드라이브 상대
    full = os.path.normcase(os.path.normpath(os.path.join(cwd, value)))
    root = os.path.normcase(os.path.normpath(cwd))
    return full == root or full.startswith(root + os.sep)


def read_any(value: str) -> str:
    """새는 흉내: 그 꼴을 Python으로 열어 본 내용(못 열면 glob으로 찾은 첫 파일)."""
    path = os.path.expanduser(os.path.expandvars(value)).removeprefix("file:///")
    try:
        return Path(path).read_text("utf-8")
    except (OSError, ValueError):
        pass
    for found in glob.glob(path, recursive=True):
        if os.path.isfile(found):
            return Path(found).read_text("utf-8")
    if os.path.isdir(path):
        for current, _dirs, files in os.walk(path):
            for name in files:
                return Path(current, name).read_text("utf-8")
    return ""


def gate_answer(
    attempt: dict[str, Any], mode: str | None, cwd: str
) -> tuple[bool, str, bool] | None:
    """(오류인가, 결과 글, 권한 거절인가). None이면 시도하지 않음."""
    tool, args = attempt["tool"], attempt["input"]
    value = next(
        args[k] for k in ("file_path", "input_path", "path", "glob", "pattern") if k in args
    )
    if mode == "skip":
        return None
    if mode == "missing":
        return True, "File does not exist.", False
    if mode in ("leak", "read"):
        return False, read_any(value), False
    if mode == "deny":
        return True, DENIED_TEXT.format(tool=tool), True
    if tool.startswith("mcp__rea__"):
        real = os.path.realpath(os.path.join(cwd, value)) if inside(value, cwd) else ""
        if real and inside(os.path.relpath(real, cwd), cwd):
            return False, '{"ok": true}', False
        field = next(iter(args))
        return True, FILTER_ERROR.format(field=field), False
    if inside(value, cwd):
        return False, read_any(os.path.join(cwd, value)), False
    return True, DENIED_TEXT.format(tool=tool), True


def gate_lines(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    cwd = os.getcwd()
    spec = scenario["gate"]
    overrides = {str(k): v for k, v in spec.get("overrides", {}).items()}
    probes = {str(k): v for k, v in spec.get("probes", {"1": "deny", "2": "read"}).items()}
    attempts = json.loads(Path(cwd, "gate-cases.json").read_text("utf-8"))["attempts"]
    denials: list[dict[str, Any]] = []
    for attempt in attempts:
        n = str(attempt["n"])
        main_value = next(iter(attempt["input"].values()))
        if attempt["tool"] in ("Grep", "Glob") and len(attempt["input"]) > 1:
            main_value = next(
                attempt["input"][k] for k in ("path", "glob", "pattern") if k in attempt["input"]
            )
        # 덮어쓰기 열쇠: 시도 번호, `도구:값`, 도구 이름 (앞의 것이 먼저)
        mode = next(
            (
                overrides[key]
                for key in (n, f"{attempt['tool']}:{main_value}", attempt["tool"])
                if key in overrides
            ),
            None,
        )
        file_path = attempt["input"].get("file_path", "")
        for k in ("1", "2"):
            if file_path == f"deny-probe-{k}/x":
                mode = mode or probes.get(k)
        answer = gate_answer(attempt, mode, cwd)
        if answer is None:
            continue
        use_id = f"toolu_{n}"
        emit(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": use_id,
                            "name": attempt["tool"],
                            "input": attempt["input"],
                        }
                    ]
                },
            }
        )
        is_error, text, denied = answer
        emit(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": use_id,
                            "is_error": is_error,
                            "content": text,
                        }
                    ]
                },
            }
        )
        if denied:
            denials.append({"tool_name": attempt["tool"], "tool_use_id": use_id})
    return denials


def default_result() -> dict[str, Any]:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 1200,
        "duration_api_ms": 1000,
        "num_turns": 3,
        "total_cost_usd": 0.01,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "structured_output": {"findings": []},
    }


def main() -> int:
    argv = sys.argv[1:]
    scenario_path = argv[argv.index("--scenario") + 1]
    args = argv[argv.index("--scenario") + 2 :]
    scenario: dict[str, Any] = json.loads(Path(scenario_path).read_text("utf-8"))
    if "--version" in args:
        print(scenario.get("version", "2.1.119 (Claude Code)"))
        return 0
    if "record" in scenario:
        Path(scenario["record"]).write_text(
            json.dumps(
                {"args": args, "cwd": os.getcwd(), "env": sorted(os.environ)}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
    init = scenario.get("init", "auto")
    if init == "garbage":
        sys.stdout.buffer.write(b'{"type": "system", "subtype": "init", "tools": [\n')
    else:
        line = init_line(args, scenario)
        if line is not None:
            emit(line)
    if "child_pidfile" in scenario:
        child = subprocess.Popen(  # noqa: S603 — 시험용 고정 인자
            [sys.executable, "-I", "-c", f"import time; time.sleep({CHILD_SLEEP_S})"]
        )
        Path(scenario["child_pidfile"]).write_text(str(child.pid), encoding="utf-8")
    for extra in scenario.get("lines", []):
        emit(extra)
    denials = gate_lines(scenario) if "gate" in scenario else []
    if scenario.get("spam_bytes"):
        chunk = ("가" * 1000 + "\n").encode()
        for _ in range(scenario["spam_bytes"] // len(chunk) + 1):
            sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
    result = scenario.get("result", default_result())
    if result is not None:
        if denials:
            result = {**result, "permission_denials": denials}
        emit(result)
    time.sleep(scenario.get("sleep_s", 0))
    return int(scenario.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
