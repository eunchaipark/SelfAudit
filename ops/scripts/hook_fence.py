"""PreToolUse 훅: 레인 울타리.

작업 폴더(worktree) 맨 위에 .lane.json이 있으면, 그 '허용' 범위 밖 파일을 고치려는
Edit·Write·NotebookEdit 호출을 막는다(종료 코드 2, 이유는 stderr로 Claude에게 보임).
.lane.json이 없는 폴더(총괄·설계·관제·문서가 쓰는 main 폴더)에서는 막지 않는다.
불릴 때마다 `.ops-logs/hooks.log`에 한 줄 남긴다(훅이 실제로 도는지 확인용).

.lane.json 예:
  {"레인": "돈", "태스크": "12", "허용": ["backend/app/money/**", "frontend/src/features/money/**"]}

한계: 실수 방지용이다. Bash로 파일을 쓰는 것까지 막지는 못한다(보안 경계가 아님).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import append_hook_log, norm_path, path_matches, use_utf8_output  # noqa: E402

FENCE_FILE = ".lane.json"
ALWAYS_ALLOWED = [FENCE_FILE, "ops/보고/**", "ops/인계/**", "ops/회고/**"]


@dataclass
class Decision:
    code: int  # 0 허용, 2 막음
    message: str = ""
    root: Path | None = None
    rel: str = ""
    why: str = ""  # 기록용 짧은 이유


def git_root(start: Path) -> Path | None:
    probe = start
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = out.stdout.strip()
    return Path(top) if out.returncode == 0 and top else None


def evaluate(payload: dict) -> Decision:
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return Decision(0, why="경로 없음")
    cwd = Path(payload.get("cwd") or os.getcwd())
    file_path = Path(target) if Path(target).is_absolute() else cwd / target
    root = git_root(file_path.parent) or git_root(cwd)
    if root is None:
        return Decision(0, why="git 밖")
    try:
        rel = norm_path(os.path.relpath(os.path.normcase(str(file_path)), os.path.normcase(str(root))))
    except ValueError:
        return Decision(0, root=root, why="다른 드라이브")
    if rel.startswith("../") or rel == "..":
        return Decision(0, root=root, rel=rel, why="작업 폴더 밖")
    fence = root / FENCE_FILE
    if not fence.exists():
        return Decision(0, root=root, rel=rel, why="울타리 없음")
    if any(path_matches(rel, p) for p in ALWAYS_ALLOWED):
        return Decision(0, root=root, rel=rel, why="항상 허용")
    try:
        cfg = json.loads(fence.read_text(encoding="utf-8"))
        allowed = list(cfg.get("허용", []))
    except (OSError, ValueError) as e:
        return Decision(2, f"레인 울타리: {FENCE_FILE}를 읽을 수 없습니다({e}). 이 파일을 고치거나 지운 뒤 다시 하세요.",
                        root, rel, "울타리 파일 오류")
    if any(path_matches(rel, p) for p in allowed):
        return Decision(0, root=root, rel=rel, why="허용 범위")
    lane = cfg.get("레인", "?")
    return Decision(2, (
        f"레인 울타리: '{rel}'은(는) 레인 '{lane}'의 허용 범위 밖입니다. "
        f"허용: {', '.join(allowed) or '(없음)'}. "
        "꼭 필요하면 고치지 말고 보고서 '요청' 칸에 적어 총괄에게 알리세요."
    ), root, rel, f"범위 밖 (레인 {lane})")


def decide(payload: dict) -> tuple[int, str]:
    """(종료 코드, 메시지). 0 = 허용, 2 = 막음."""
    d = evaluate(payload)
    return d.code, d.message


def main() -> int:
    use_utf8_output()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return 0  # 입력을 못 읽으면 막지 않는다(작업을 멈추지 않게)
    d = evaluate(payload)
    if d.root is not None:
        append_hook_log(d.root, f"fence {'block' if d.code == 2 else 'allow'} {payload.get('tool_name', '?')} {d.rel} ({d.why})")
    if d.message:
        print(d.message, file=sys.stderr)
    return d.code


if __name__ == "__main__":
    raise SystemExit(main())
