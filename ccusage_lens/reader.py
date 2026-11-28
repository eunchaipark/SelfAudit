"""Claude Code 대화 기록(*.jsonl)에서 사용량 숫자만 읽는다.

읽는 칸: type, timestamp, message.id, message.usage(네 토큰), isSidechain, sessionId,
agentId, 그리고 Task/Agent 도구 호출 입력의 subagent_type. 본문(메시지 내용·도구 결과)은
꺼내 쓰지 않고, 이 모듈이 돌려주는 값에도 넣지 않는다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
AGENT_TOOLS = {"Task", "Agent"}
MAIN_AGENT = "main"
UNKNOWN_AGENT = "subagent(unknown)"
# Task/Agent 호출에 subagent_type이 없으면 Claude Code는 general-purpose로 띄운다.
DEFAULT_SUBAGENT = "general-purpose"


@dataclass
class Record:
    """assistant 응답 하나의 사용량. 숫자와 이름·시각만 든다."""

    project: str
    session: str
    day: str  # 로컬 날짜 YYYY-MM-DD, 시각이 없으면 "unknown"
    agent: str
    tokens: tuple[int, int, int, int]


@dataclass
class Stats:
    files: int = 0
    lines: int = 0
    broken_lines: int = 0
    assistant_lines: int = 0
    duplicate_lines: int = 0  # 이미 센 message.id라 건너뛴 줄


@dataclass
class _Pending:
    project: str
    session: str
    day: str
    agent_id: str | None  # 하위 에이전트 파일이면 그 agentId
    tokens: tuple[int, int, int, int]


@dataclass
class ScanResult:
    records: list[Record] = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)


def default_root() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def local_day(ts: object) -> str:
    if not isinstance(ts, str) or not ts:
        return "unknown"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return "unknown"
    if dt.tzinfo is None:  # 기록 시각은 UTC로 적힌다
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date().isoformat()


def _int(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _project_of(path: Path, root: Path) -> str:
    rel = path.relative_to(root).parts
    return rel[0] if len(rel) > 1 else root.name


def _subagent_id(path: Path) -> str | None:
    if path.parent.name == "subagents" and path.name.startswith("agent-"):
        return path.stem[len("agent-") :]
    return None


def find_files(root: Path, project: str | None = None) -> list[Path]:
    files = []
    for p in sorted(root.rglob("*.jsonl")):
        if project and project.lower() not in _project_of(p, root).lower():
            continue
        files.append(p)
    return files


def scan(
    root: Path,
    since: date | None = None,
    until: date | None = None,
    project: str | None = None,
) -> ScanResult:
    result = ScanResult()
    stats = result.stats
    seen_ids: set[str] = set()
    pending: list[_Pending] = []
    tool_type: dict[str, str] = {}  # Task/Agent tool_use id -> subagent_type
    agent_tool: dict[str, str] = {}  # agentId -> 띄운 tool_use id
    meta_type: dict[str, str] = {}  # agentId -> meta.json의 agentType (보조)

    for path in find_files(root, project):
        stats.files += 1
        proj = _project_of(path, root)
        sub_id = _subagent_id(path)
        if sub_id:
            _read_meta(path.with_suffix(".meta.json"), sub_id, agent_tool, meta_type)
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                stats.lines += 1
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    stats.broken_lines += 1
                    continue
                if not isinstance(obj, dict):
                    stats.broken_lines += 1
                    continue
                kind = obj.get("type")
                msg = obj.get("message")
                msg = msg if isinstance(msg, dict) else {}
                if kind == "assistant":
                    stats.assistant_lines += 1
                    _collect_agent_calls(msg, tool_type)
                    mid = msg.get("id")
                    if isinstance(mid, str) and mid:
                        if mid in seen_ids:
                            stats.duplicate_lines += 1
                            continue
                        seen_ids.add(mid)
                    usage = msg.get("usage")
                    usage = usage if isinstance(usage, dict) else {}
                    tokens = tuple(_int(usage.get(k)) for k in TOKEN_FIELDS)
                    agent_id = sub_id
                    if agent_id is None and obj.get("isSidechain") is True:
                        aid = obj.get("agentId")
                        agent_id = aid if isinstance(aid, str) else ""
                    pending.append(
                        _Pending(
                            project=proj,
                            session=str(obj.get("sessionId") or path.stem),
                            day=local_day(obj.get("timestamp")),
                            agent_id=agent_id,
                            tokens=tokens,  # type: ignore[arg-type]
                        )
                    )
                elif kind == "user":
                    _collect_agent_result(obj, msg, agent_tool)

    for p in pending:
        if since or until:
            if p.day == "unknown":
                continue
            d = date.fromisoformat(p.day)
            if (since and d < since) or (until and d > until):
                continue
        result.records.append(
            Record(
                project=p.project,
                session=p.session,
                day=p.day,
                agent=_agent_label(p.agent_id, tool_type, agent_tool, meta_type),
                tokens=p.tokens,
            )
        )
    return result


def _agent_label(
    agent_id: str | None,
    tool_type: dict[str, str],
    agent_tool: dict[str, str],
    meta_type: dict[str, str],
) -> str:
    if agent_id is None:
        return MAIN_AGENT
    tid = agent_tool.get(agent_id)
    if tid and tid in tool_type:
        return tool_type[tid]
    return meta_type.get(agent_id) or UNKNOWN_AGENT


def _collect_agent_calls(msg: dict, tool_type: dict[str, str]) -> None:
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for c in content:
        if (
            isinstance(c, dict)
            and c.get("type") == "tool_use"
            and c.get("name") in AGENT_TOOLS
            and isinstance(c.get("id"), str)
        ):
            inp = c.get("input")
            st = inp.get("subagent_type") if isinstance(inp, dict) else None
            tool_type[c["id"]] = st if isinstance(st, str) and st else DEFAULT_SUBAGENT


def _collect_agent_result(obj: dict, msg: dict, agent_tool: dict[str, str]) -> None:
    """Task/Agent 결과 줄에서 agentId ↔ tool_use id만 잇는다(결과 본문은 보지 않는다)."""
    tur = obj.get("toolUseResult")
    if not isinstance(tur, dict) or not isinstance(tur.get("agentId"), str):
        return
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for c in content:
        if isinstance(c, dict) and c.get("type") == "tool_result":
            tid = c.get("tool_use_id")
            if isinstance(tid, str):
                agent_tool.setdefault(tur["agentId"], tid)
                return


def _read_meta(
    path: Path, agent_id: str, agent_tool: dict[str, str], meta_type: dict[str, str]
) -> None:
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(meta, dict):
        return
    if isinstance(meta.get("toolUseId"), str):
        agent_tool.setdefault(agent_id, meta["toolUseId"])
    if isinstance(meta.get("agentType"), str) and meta["agentType"]:
        meta_type[agent_id] = meta["agentType"]
