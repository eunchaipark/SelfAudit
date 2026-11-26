"""F-R05 조건 확인: stream-json의 첫 `system`/`init` 줄을 그 실행의 조건·계획과 맞춘다 (실험구조
3.4).

맞지 않으면 그 실행은 `condition_mismatch`로 버리고 채점하지 않는다(다시 돌린다) — 요구사항 3절 실패
①(조건이 같지 않음)을 실행 뒤가 아니라 실행마다 기계가 잡는다.

init 줄의 칸 이름(`tools`, `mcp_servers[].name`·`status`, `model`, `permissionMode`)은 **추정**이다.
확인 방법: 보정 첫 실행(F-R08 ㉮ 빈 실행 A·B)에서 총괄이 init 줄의 칸 이름만 읽어 이 모듈과 F-R05
예시를 맞춘다. 그때 B에 MCP 리소스 도구(`ListMcpResourcesTool` 등)가 더해지는지도 본다(실험구조
3.4).
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from common.contracts import Json
from run.claude_cmd import BASE_TOOLS, PERMISSION_MODE, REA_TOOL_PREFIX, REA_TOOLS

__all__ = ["EXPECTED_TOOLS", "InitCheck", "check_init", "find_init"]

EXPECTED_TOOLS: Final[Mapping[str, frozenset[str]]] = {
    "A": frozenset(BASE_TOOLS),
    "B": frozenset(BASE_TOOLS) | {REA_TOOL_PREFIX + tool for tool in REA_TOOLS},
}
REA_SERVER: Final = "rea"
CONNECTED: Final = "connected"
FIELDS: Final = ("tools", "mcp_servers", "model", "permissionMode")
MAX_DETAIL_CHARS: Final = 500  # run.schema.json outcome.detail


@dataclass(frozen=True)
class InitCheck:
    """`outcome.init_check`(passed·failed·missing)과 `outcome.detail`(다른 칸 이름, 값은 싣지
    않음)."""

    result: str
    detail: str


def find_init(stream: bytes) -> dict[str, Json] | None:
    """첫 `{"type": "system", "subtype": "init"}` 줄. JSON으로 읽을 수 없는 줄은 init 줄이 아니다.

    찾으면 거기서 멈춘다(대화 기록 끝까지 읽지 않는다).
    """
    for line in io.BytesIO(stream):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(obj, dict) and obj.get("type") == "system" and obj.get("subtype") == "init":
            return obj
    return None


def check_init(stream: bytes, condition: str, model: str) -> InitCheck:
    """F-R05 1~5. 조건 A·B 밖이면 `ValueError`(실행기가 틀린 것)."""
    if condition not in EXPECTED_TOOLS:
        raise ValueError("조건이 A·B 밖")
    init = find_init(stream)
    if init is None:
        return InitCheck("missing", "init 줄 없음")
    wrong = [
        name
        for name, ok in (
            ("tools", _tools_ok(init.get("tools"), condition)),
            ("mcp_servers", _servers_ok(init.get("mcp_servers"), condition)),
            ("model", init.get("model") == model),
            ("permissionMode", init.get("permissionMode") == PERMISSION_MODE),
        )
        if not ok
    ]
    if wrong:
        return InitCheck("failed", ",".join(wrong)[:MAX_DETAIL_CHARS])
    return InitCheck("passed", "")


def _tools_ok(value: Json, condition: str) -> bool:
    """1: 기대 목록과 **같은 모음**(더 있거나 빠지면 불일치). 같은 이름이 두 번이어도 불일치."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return False
    return len(value) == len(set(value)) and set(value) == EXPECTED_TOOLS[condition]


def _servers_ok(value: Json, condition: str) -> bool:
    """2: A는 서버 없음, B는 `rea` 하나가 연결됨."""
    if not isinstance(value, list):
        return False
    if condition == "A":
        return value == []
    if len(value) != 1 or not isinstance(value[0], dict):
        return False
    server = value[0]
    return server.get("name") == REA_SERVER and server.get("status") == CONNECTED
