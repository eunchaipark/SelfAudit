"""F-R04 시험용 가짜 REA MCP 서버 (진짜 REA를 부르지 않는다, 실험구조 3.9).

`python -I server.py --record <jsonl> --env-out <json>`
- 띄워지자마자 받은 환경 변수와 작업 폴더를 `--env-out`에 쓴다(거르개가 만든 REA 환경을 보려고).
- 받은 줄을 하나도 빼지 않고 `--record`에 덧붙인다(거르개가 REA에 무엇을 보냈는지 보려고).
- 진짜 REA 6.10.1처럼 `tools`·`prompts`·`resources`·`logging` 능력과 도구 68개를 알린다.
- `ping`을 받으면 먼저 REA가 거는 요청(`sampling/createMessage`·`roots/list`)과
  `notifications/tools/list_changed`를 보낸 뒤 답한다.
- `tools/call`은 받은 인자를 그대로 글로 돌려준다. 허용 밖 메서드도 성공으로 답한다
  (거르개가 넘겼다면 시험이 알 수 있게).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ALLOWED = (
    "analyze_javascript_application",
    "audit_release_exposure",
    "trace_javascript_semantics",
    "trace_application_feature",
)
# REA환경.md 6절 '아니오' 줄의 이름들. 나머지는 채움 이름으로 68개를 맞춘다
DENIED_NAMED = (
    "list_electron_targets",
    "inspect_electron_page",
    "reconcile_javascript_runtime",
    "capture_electron_scenario",
    "inspect_electron_fuses",
    "extract_artifact",
    "export_web_scripts",
    "recover_javascript_sources",
    "trace_web_source_location",
    "trace_web_module_imports",
)
TOOL_COUNT = 68
# 멈춘 흉내의 길이: 거르개의 STOP_WAIT_S(5초)보다 훨씬 길어, 스스로 끝나기 전에 거르개가 끝내야 한다
HANG_S = 60


def tool_names() -> list[str]:
    names = [*ALLOWED, *DENIED_NAMED]
    names += [f"fake_other_tool_{i:02d}" for i in range(TOOL_COUNT - len(names))]
    return names


def tools() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": f"fake {name}", "inputSchema": {"type": "object"}}
        for name in tool_names()
    ]


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def result(msg_id: Any, value: dict[str, Any]) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "result": value})


def answer(message: dict[str, Any]) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        result(
            msg_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "prompts": {"listChanged": True},
                    "resources": {},
                    "logging": {},
                },
                "serverInfo": {"name": "fake-rea", "version": "0"},
                "instructions": "fake instructions",
            },
        )
    elif method == "tools/list":
        result(msg_id, {"tools": tools()})
    elif method == "tools/call":
        params = message.get("params") or {}
        text = json.dumps(params.get("arguments"))
        result(msg_id, {"content": [{"type": "text", "text": text}]})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": "rea-1", "method": "sampling/createMessage", "params": {}})
        send({"jsonrpc": "2.0", "id": "rea-2", "method": "roots/list"})
        send({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        result(msg_id, {})
    else:
        result(msg_id, {"forwarded": method})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True)
    parser.add_argument("--env-out", required=True)
    parser.add_argument(
        "--hang-with-child", help="자식 PID를 쓸 파일. 자식을 띄우고 입력이 끝나도 버틴다"
    )
    args = parser.parse_args()
    state = {"environ": dict(os.environ), "cwd": os.getcwd()}
    Path(args.env_out).write_text(json.dumps(state), encoding="utf-8")
    child = None
    if args.hang_with_child:
        # 분석 자식을 둔 채 멈춘 REA 흉내: 거르개가 프로세스 나무째 끝내는지 본다
        child = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({HANG_S})"])  # noqa: S603
        Path(args.hang_with_child).write_text(str(child.pid), encoding="utf-8")
    record = Path(args.record)
    for raw in sys.stdin.buffer:
        with record.open("ab") as out:
            out.write(raw)
        message = json.loads(raw)
        if "method" in message and "id" in message:
            answer(message)
    if child is not None:
        time.sleep(HANG_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
