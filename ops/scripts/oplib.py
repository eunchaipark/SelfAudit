"""ops 스크립트 공통 함수. 표준 라이브러리만 쓴다 (설치할 것 없음)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_WILD = set("*?[{")


HOOK_LOG_MAX = 200_000  # 바이트. 넘으면 뒤쪽 절반만 남긴다


def append_hook_log(root: Path, line: str) -> None:
    """훅이 실제로 불렸는지 사람이 확인할 수 있게 `.ops-logs/hooks.log`에 한 줄 남긴다. 실패해도 조용히 넘어간다."""
    from datetime import datetime

    try:
        log = Path(root) / ".ops-logs" / "hooks.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > HOOK_LOG_MAX:
            data = log.read_bytes()
            log.write_bytes(data[len(data) // 2 :])
        with log.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except OSError:
        pass


def load_raw_tasks(path: Path, tag: str | None = None) -> tuple[list[dict], str]:
    """Taskmaster tasks.json에서 태스크 목록(원래 dict)과 쓴 태그를 읽는다. 태그 형식과 옛 형식 모두."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data.get("tasks"), list):  # 옛 형식 (태그 없음)
        return data["tasks"], "(태그 없음)"
    if not tag:
        state = Path(path).parent.parent / "state.json"
        if state.exists():
            tag = json.loads(state.read_text(encoding="utf-8")).get("currentTag")
    used = tag or "master"
    if used not in data:
        raise SystemExit(f"태그 '{used}'가 {path}에 없습니다. 있는 태그: {', '.join(data)}")
    return data[used].get("tasks", []), used


def use_utf8_output() -> None:
    """Windows에서 출력이 깨지지 않게 표준 출력·오류를 UTF-8로 맞춘다."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def norm_path(p: str) -> str:
    """경로를 비교용으로 맞춘다: 역슬래시 → 슬래시, 앞의 ./ 제거, 소문자."""
    p = p.strip().strip('"').strip("'").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lower()


def has_wildcard(pattern: str) -> bool:
    return any(ch in _WILD for ch in pattern)


def literal_prefix(pattern: str) -> str:
    """와일드카드가 나오기 전까지의 앞부분."""
    for i, ch in enumerate(pattern):
        if ch in _WILD:
            return pattern[:i]
    return pattern


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**`, `*`, `?`, `[abc]`, `{a,b}`를 지원하는 glob → 정규식."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern.startswith("**", i):
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                out.append("[" + pattern[i + 1 : j].replace("\\", "\\\\") + "]")
                i = j + 1
                continue
        elif c == "{":
            j = pattern.find("}", i + 1)
            if j == -1:
                out.append(re.escape(c))
            else:
                alts = pattern[i + 1 : j].split(",")
                out.append("(?:" + "|".join(re.escape(a) for a in alts) + ")")
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _as_dir_glob(pattern: str) -> str:
    return pattern + "**" if pattern.endswith("/") else pattern


def path_matches(path: str, pattern: str) -> bool:
    """파일 경로 하나가 패턴에 들어가는가. 와일드카드 없는 패턴은 그 파일 또는 그 폴더 아래 전부."""
    path, pattern = norm_path(path), _as_dir_glob(norm_path(pattern))
    if not has_wildcard(pattern):
        return path == pattern or path.startswith(pattern.rstrip("/") + "/")
    return glob_to_regex(pattern).match(path) is not None


def patterns_overlap(a: str, b: str) -> bool:
    """두 '고칠 파일' 항목이 같은 파일을 건드릴 수 있는가. 확실하지 않으면 겹친다고 본다(안전 쪽)."""
    a, b = _as_dir_glob(norm_path(a)), _as_dir_glob(norm_path(b))
    wa, wb = has_wildcard(a), has_wildcard(b)
    if not wa and not wb:
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")
    if not wa or not wb:
        lit, pat = (a, b) if not wa else (b, a)
        return path_matches(lit, pat) or literal_prefix(pat).startswith(lit.rstrip("/") + "/")
    pa, pb = literal_prefix(a), literal_prefix(b)
    return pa.startswith(pb) or pb.startswith(pa)
