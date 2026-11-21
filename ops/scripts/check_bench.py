"""bench/ 실험 자료 검사 (check.py '실험자료', 설계, docs/설계/실험구조.md 4절).

막는 것: 내 실제 앱의 결과(비밀값 원문이 들어 있을 수 있음)가 공개 저장소에 들어가는 것,
GitHub 비밀 검사(push 막기)에 걸리는 서비스 꼴 키가 가짜 값으로라도 들어가는 것.

규칙 (㉠~㉢은 허용 꼴만 통과):
㉠ bench/results/ 아래 파일은 `bench/results/README.md` 또는
   `bench/results/<YYYY-MM-DD>/<실행 ID>/<허용 이름>`뿐이다.
㉡ 실행 폴더마다 run.json이 있고, run_id가 폴더 이름과 같고, target_kind가 planted·practice이며,
   target_id가 bench/targets.json에 같은 종류로 있다.
㉢ bench/targets.json의 대상 종류는 planted·practice뿐이다(내 앱 목록은 저장소 밖).
㉣ bench/ 아래 글 파일에 서비스 꼴 키(SECRET_SHAPES)가 없다. 이것만은 막을 꼴 목록이다 —
   GitHub 비밀 검사 자체가 서비스별 꼴로 찾으므로, 피해야 할 것도 그 꼴이다. 찾은 값은 찍지 않는다.
걸리면 `경로[:줄]: 이유`를 찍고 1로 끝난다. 끝 줄은 요약이다. bench/가 없으면 통과한다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "bench"
RESULTS = BENCH / "results"
TARGETS = BENCH / "targets.json"

SKIP_DIRS = {".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUN_FILES = {"run.json", "findings.json", "transcript.jsonl", "netguard.jsonl", "netstat.json"}
ALLOWED_KINDS = {"planted", "practice"}
DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{3,80}$")
# 글 파일로 읽을 크기 상한. 시험 번들·원자료 파일은 이보다 작다(transcript는 2MB 넘으면 저장소 밖, 실험구조 3.8)
MAX_TEXT_BYTES = 20 * 1024 * 1024
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".zip", ".gz", ".wasm"}

# 서비스 꼴 키 (GitHub 비밀 검사가 찾는 대표 꼴). 모두 되돌아가기가 없는 꼴이다
SECRET_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS 접근 키", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub 세부 토큰", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("Slack 토큰", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Stripe 실키", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI 키", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}T3BlbkFJ")),
    ("개인 키 머리", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def bench_files() -> list[Path]:
    if not BENCH.is_dir():
        return []
    return sorted(
        p for p in BENCH.rglob("*") if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(BENCH).parts)
    )


def load_targets(problems: list[str]) -> dict[str, str]:
    """{대상 ID: 종류}. ㉢: 종류는 허용 목록 안이어야 한다."""
    if not TARGETS.is_file():
        return {}
    try:
        data = json.loads(TARGETS.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"{rel(TARGETS)}: JSON으로 읽지 못함 ({type(exc).__name__})")
        return {}
    entries = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        problems.append(f"{rel(TARGETS)}: 'targets' 목록이 없음")
        return {}
    kinds: dict[str, str] = {}
    for entry in entries:
        tid = entry.get("id") if isinstance(entry, dict) else None
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if not isinstance(tid, str) or kind not in ALLOWED_KINDS:
            problems.append(f"{rel(TARGETS)}: 대상 {tid!r}의 종류 {kind!r}는 허용되지 않음 (planted·practice만)")
            continue
        kinds[tid] = kind
    return kinds


def check_results(files: list[Path], kinds: dict[str, str], problems: list[str]) -> None:
    """㉠·㉡."""
    run_dirs: set[Path] = set()
    for path in files:
        if RESULTS not in path.parents:
            continue
        parts = path.relative_to(RESULTS).parts
        if parts == ("README.md",):
            continue
        if len(parts) != 3 or not DATE_DIR.match(parts[0]) or not RUN_ID.match(parts[1]) or parts[2] not in RUN_FILES:
            problems.append(f"{rel(path)}: bench/results/<날짜>/<실행 ID>/<허용 이름> 꼴이 아님")
            continue
        run_dirs.add(path.parent)
    for run_dir in sorted(run_dirs):
        check_run(run_dir, kinds, problems)


def check_run(run_dir: Path, kinds: dict[str, str], problems: list[str]) -> None:
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        problems.append(f"{rel(run_dir)}: run.json 없음")
        return
    try:
        run = json.loads(run_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"{rel(run_json)}: JSON으로 읽지 못함 ({type(exc).__name__})")
        return
    if not isinstance(run, dict):
        problems.append(f"{rel(run_json)}: 객체가 아님")
        return
    kind, tid = run.get("target_kind"), run.get("target_id")
    if run.get("run_id") != run_dir.name:
        problems.append(f"{rel(run_json)}: run_id가 폴더 이름과 다름")
    if kind not in ALLOWED_KINDS:
        problems.append(f"{rel(run_json)}: target_kind {kind!r}는 저장소에 넣을 수 없음 (planted·practice만)")
    elif kinds.get(tid) != kind:
        problems.append(f"{rel(run_json)}: 대상 {tid!r}가 bench/targets.json에 {kind}로 없음")


def check_secret_shapes(files: list[Path], problems: list[str]) -> None:
    """㉣. 값은 찍지 않고 꼴 이름과 줄만 찍는다."""
    for path in files:
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                problems.append(f"{rel(path)}: {MAX_TEXT_BYTES}바이트보다 커서 읽지 않음(저장소 밖에 둔다)")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            problems.append(f"{rel(path)}: 읽지 못함 ({type(exc).__name__})")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SECRET_SHAPES:
                if pattern.search(line):
                    problems.append(f"{rel(path)}:{lineno}: 서비스 꼴 키({name}) — 가짜 값은 이 프로젝트만의 꼴로")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    problems: list[str] = []
    files = bench_files()
    kinds = load_targets(problems)
    check_results(files, kinds, problems)
    check_secret_shapes(files, problems)
    for line in problems:
        print(line)
    print(f"bench 파일 {len(files)}개, 문제 {len(problems)}곳")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
