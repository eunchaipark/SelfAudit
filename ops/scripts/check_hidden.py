"""docs·ops·.taskmaster 글 파일에서 보이지 않는 글자를 찾는다 (check.py '숨은글자').

찾는 것: 폭 없는 글자·방향 표시 U+200B~U+200F, 방향 문자 U+202A~U+202E·U+2066~U+2069,
탭·줄바꿈(\\t \\n \\r) 밖의 제어 문자(Cc: U+0000~U+001F, U+007F~U+009F).
그대로 두면 글이 거꾸로 보이거나 사라져, 사람과 검토 에이전트가 다른 글을 읽는다.
문서에 이 글자를 적어야 하면 `\\u202E`처럼 글로 쓴다. 이 파일도 글자를 chr()로만 만든다.
걸리면 `파일:줄: U+XXXX`를 찍고 1로 끝난다. 끝 줄은 요약이다.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ("docs", "ops", ".taskmaster")
SKIP_DIRS = {"node_modules", ".git", "__pycache__"}
ALLOWED_CC = {chr(0x09), chr(0x0A), chr(0x0D)}
HIDDEN = (
    {chr(c) for c in range(0x200B, 0x2010)}
    | {chr(c) for c in range(0x202A, 0x202F)}
    | {chr(c) for c in range(0x2066, 0x206A)}
)


def is_hidden(ch: str) -> bool:
    if ch in HIDDEN:
        return True
    return unicodedata.category(ch) == "Cc" and ch not in ALLOWED_CC


def files() -> list[Path]:
    out: list[Path] = []
    for folder in FOLDERS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
                out.append(path)
    return out


def scan(path: Path) -> list[str]:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return []  # 글 파일이 아니다
    rel = path.relative_to(ROOT).as_posix()
    hits = []
    for number, line in enumerate(text.split("\n"), 1):
        for ch in sorted({c for c in line if is_hidden(c)}):
            hits.append(f"{rel}:{number}: U+{ord(ch):04X}")
    return hits


def main() -> int:
    paths = files()
    hits = [hit for path in paths for hit in scan(path)]
    for hit in hits:
        print(hit)
    print(f"글 파일 {len(paths)}개, 보이지 않는 글자 {len(hits)}곳")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main())
