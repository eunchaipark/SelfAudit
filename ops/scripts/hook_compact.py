"""SessionStart 훅 (matcher: compact): 대화가 자동 요약된 직후에 교대 절차를 알려 준다.
이 훅이 출력한 글은 Claude의 문맥에 들어간다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import append_hook_log, use_utf8_output  # noqa: E402


def find_lane(cwd: Path) -> dict | None:
    for folder in [cwd, *cwd.parents]:
        fence = folder / ".lane.json"
        if fence.exists():
            try:
                return json.loads(fence.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {"레인": "?"}
        if (folder / ".git").exists():
            break
    return None


def message(cwd: Path) -> str:
    lane = find_lane(cwd)
    head = "[교대 신호] 방금 대화가 자동 요약되었습니다. 앞의 세부 내용이 빠졌을 수 있으니 새로 큰 일을 시작하지 마세요."
    if lane:
        task = lane.get("태스크", "<태스크>")
        return "\n".join([
            head,
            f"레인 '{lane.get('레인', '?')}' 세션의 할 일:",
            "1. 지금 하위 작업을 멈출 수 있는 지점까지만 마무리하고 커밋한다 (안 끝났으면 [WIP] 커밋).",
            f"2. ops/양식/인계서.md 양식으로 ops/인계/T{task}-<MMDD>.md를 쓰고 커밋한다.",
            "3. git switch --detach 로 브랜치를 놓아준다 (다음 세션이 그 브랜치를 이어받게).",
            f"4. 마지막 메시지 첫 줄: [T{task}] 교대 | ops/인계/T{task}-<MMDD>.md | 문맥 약 n만",
        ])
    return "\n".join([
        head,
        "역할 카드(ops/역할/)와 ops/보드.md를 다시 읽고, 지금 일을 마무리한 뒤 인계서(ops/양식/인계서.md)를 남겨 교대를 준비하세요.",
    ])


def main() -> int:
    use_utf8_output()
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = next((p for p in [cwd, *cwd.parents] if (p / ".git").exists()), cwd)
    append_hook_log(root, f"compact source={payload.get('source', '?')}")
    print(message(cwd))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
