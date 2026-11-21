"""bench/ 실험 자료 검사 (check.py '실험자료', 설계, docs/설계/실험구조.md 4절).

막는 것: 내 실제 앱의 결과(비밀값 원문이 들어 있을 수 있음)가 공개 저장소에 들어가는 것,
GitHub 비밀 검사(push 막기)에 걸리는 서비스 꼴 키가 가짜 값으로라도 들어가는 것.

보는 파일: 작업 폴더의 bench/ 아래 파일 + git 색인(staged 포함)의 bench/ 아래 파일과 그 내용.
작업 폴더에서 지웠지만 색인에 남은 것, 고친 뒤 색인에만 올린 내용도 본다.

규칙 (㉠~㉢은 허용 꼴만 통과):
㉠ bench/results/ 아래 파일은 `bench/results/README.md` 또는
   `bench/results/<YYYY-MM-DD>/<실행 ID>/<허용 이름>`뿐이다.
㉡ 실행 폴더마다 run.json이 있고, run_id가 폴더 이름과 같고, target_kind가 planted·practice이며,
   target_id가 bench/targets.json에 같은 종류로 있고, bundle_manifest_sha256이 그 대상의 정답지
   (bench/answers/<target_id>.json) 지문과 같다 — run.json의 종류 글만 믿지 않고 대상 자체가 같은지 본다.
㉢ bench/targets.json의 대상 종류는 planted·practice뿐이다(내 앱 목록은 저장소 밖).
㉣ bench/ 아래 글 파일에 서비스 꼴 키(SECRET_SHAPES, openai_shape)가 없다. 이것만은 막을 꼴 목록이다 —
   GitHub 비밀 검사 자체가 서비스별 꼴로 찾으므로, 피해야 할 것도 그 꼴이다. 찾은 값은 찍지 않는다.
걸리면 `경로[:줄]: 이유`를 찍고 1로 끝난다. 끝 줄은 요약이다. bench/가 없으면 통과한다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "bench"
TARGETS_REL = "bench/targets.json"
RESULTS_PREFIX = "bench/results/"
ANSWERS_PREFIX = "bench/answers/"

SKIP_DIRS = {".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
RUN_FILES = {"run.json", "findings.json", "transcript.jsonl", "netguard.jsonl", "netstat.json"}
ALLOWED_KINDS = {"planted", "practice"}
DATE_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{3,80}$")
TARGET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
# 글 파일로 읽을 크기 상한. 시험 번들·원자료 파일은 이보다 작다(transcript는 2MB 넘으면 저장소 밖, 실험구조 3.8)
MAX_TEXT_BYTES = 20 * 1024 * 1024
GIT_TIMEOUT_S = 60
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".zip", ".gz", ".wasm"}

# 서비스 꼴 키 (GitHub 비밀 검사가 찾는 대표 꼴). 모두 뒤에 붙는 글자 조건이 없거나 길이가 정해져 있어,
# 실패할 때 되돌아가며 다시 훑지 않는다(입력 길이에 선형, 1MB 줄 시험 — 실험구조 4절)
SECRET_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("AWS 접근 키", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub 세부 토큰", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("Slack 토큰", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("Stripe 실키", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}")),
    ("Google API 키", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("개인 키 머리", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
)

# OpenAI 키 꼴 `\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}T3BlbkFJ`은 정규식으로 쓰면 뒤 글자(T3BlbkFJ) 때문에
# `sk-`가 많은 줄에서 제곱으로 느려진다(반려 2: 12만 자 6.6초). 그래서 키 글자 덩어리를 한 번씩만 보고
# 덩어리 안에서 '경계 뒤 sk-'와 그보다 23자 이상 뒤의 T3BlbkFJ가 있는지만 본다(선형).
KEY_RUN = re.compile(r"[A-Za-z0-9_\-]+")
OPENAI_MARK = "T3BlbkFJ"
OPENAI_MIN_GAP = len("sk-") + 20


def openai_shape(line: str) -> bool:
    for m in KEY_RUN.finditer(line):
        run = m.group()
        mark = run.rfind(OPENAI_MARK)
        if mark < OPENAI_MIN_GAP:
            continue
        pos = run.find("sk-")
        while 0 <= pos <= mark - OPENAI_MIN_GAP:
            before = run[pos - 1] if pos > 0 else (line[m.start() - 1] if m.start() > 0 else " ")
            if not (before.isalnum() or before == "_"):
                return True
            pos = run.find("sk-", pos + 1)
    return False


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def worktree_files() -> dict[str, Path]:
    if not BENCH.is_dir():
        return {}
    return {
        rel(p): p
        for p in sorted(BENCH.rglob("*"))
        if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(BENCH).parts)
    }


def git(*args: str, data: bytes | None = None) -> bytes | None:
    try:
        done = subprocess.run(  # noqa: S603
            ["git", "-C", str(ROOT), *args], input=data, capture_output=True, timeout=GIT_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def index_files() -> dict[str, bytes]:
    """git 색인(staged 포함)의 bench/ 아래 파일 {경로: 색인 내용}. git이 없거나 저장소가 아니면 빈 것."""
    listed = git("ls-files", "-z", "--cached", "--", "bench")
    if not listed:
        return {}
    paths = [p for p in listed.decode("utf-8").split("\0") if p]
    batch = git("cat-file", "--batch", data="".join(f":{p}\n" for p in paths).encode("utf-8"))
    if batch is None:
        return {}
    out: dict[str, bytes] = {}
    pos = 0
    for path in paths:
        end = batch.index(b"\n", pos)
        head = batch[pos:end].split()
        pos = end + 1
        if len(head) < 3 or head[1] != b"blob":
            continue
        size = int(head[2])
        out[path] = batch[pos : pos + size]
        pos += size + 1
    return out


class Files:
    """작업 폴더와 색인을 합친 보기."""

    def __init__(self) -> None:
        self.work = worktree_files()
        self.index = index_files()

    def paths(self) -> list[str]:
        return sorted(set(self.work) | set(self.index))

    def versions(self, path: str) -> Iterator[bytes]:
        """작업 폴더 내용, 그리고 색인 내용이 다르면 그것도."""
        seen: bytes | None = None
        if path in self.work:
            try:
                seen = self.work[path].read_bytes()[: MAX_TEXT_BYTES + 1]
            except OSError:
                seen = None
            if seen is not None:
                yield seen
        staged = self.index.get(path)
        if staged is not None and staged[: MAX_TEXT_BYTES + 1] != seen:
            yield staged[: MAX_TEXT_BYTES + 1]

    def json(self, path: str) -> object:
        for raw in self.versions(path):
            return json.loads(raw.decode("utf-8"))
        raise FileNotFoundError(path)


def load_targets(files: Files, problems: list[str]) -> dict[str, str]:
    """{대상 ID: 종류}. ㉢: 종류는 허용 목록 안이어야 한다."""
    if TARGETS_REL not in files.paths():
        return {}
    try:
        data = files.json(TARGETS_REL)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"{TARGETS_REL}: JSON으로 읽지 못함 ({type(exc).__name__})")
        return {}
    entries = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        problems.append(f"{TARGETS_REL}: 'targets' 목록이 없음")
        return {}
    kinds: dict[str, str] = {}
    for entry in entries:
        tid = entry.get("id") if isinstance(entry, dict) else None
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if not isinstance(tid, str) or not TARGET_ID.match(tid) or kind not in ALLOWED_KINDS:
            problems.append(f"{TARGETS_REL}: 대상 {tid!r}의 종류 {kind!r}는 허용되지 않음 (planted·practice만)")
            continue
        kinds[tid] = kind
    return kinds


def check_results(files: Files, kinds: dict[str, str], problems: list[str]) -> None:
    """㉠·㉡."""
    run_dirs: set[str] = set()
    for path in files.paths():
        if not path.startswith(RESULTS_PREFIX):
            continue
        parts = path[len(RESULTS_PREFIX) :].split("/")
        if parts == ["README.md"]:
            continue
        if len(parts) != 3 or not DATE_DIR.match(parts[0]) or not RUN_ID.match(parts[1]) or parts[2] not in RUN_FILES:
            problems.append(f"{path}: bench/results/<날짜>/<실행 ID>/<허용 이름> 꼴이 아님")
            continue
        run_dirs.add(f"{RESULTS_PREFIX}{parts[0]}/{parts[1]}")
    for run_dir in sorted(run_dirs):
        check_run(files, run_dir, kinds, problems)


def check_run(files: Files, run_dir: str, kinds: dict[str, str], problems: list[str]) -> None:
    run_path = f"{run_dir}/run.json"
    if run_path not in files.paths():
        problems.append(f"{run_dir}: run.json 없음")
        return
    try:
        run = files.json(run_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"{run_path}: JSON으로 읽지 못함 ({type(exc).__name__})")
        return
    if not isinstance(run, dict):
        problems.append(f"{run_path}: 객체가 아님")
        return
    kind, tid = run.get("target_kind"), run.get("target_id")
    if run.get("run_id") != run_dir.rsplit("/", 1)[1]:
        problems.append(f"{run_path}: run_id가 폴더 이름과 다름")
    if kind not in ALLOWED_KINDS:
        problems.append(f"{run_path}: target_kind {kind!r}는 저장소에 넣을 수 없음 (planted·practice만)")
        return
    if not isinstance(tid, str) or kinds.get(tid) != kind:
        problems.append(f"{run_path}: 대상 {tid!r}가 bench/targets.json에 {kind}로 없음")
        return
    answers_path = f"{ANSWERS_PREFIX}{tid}.json"
    try:
        answers = files.json(answers_path)
    except FileNotFoundError:
        problems.append(f"{run_path}: 대상의 정답지 {answers_path}가 없어 지문을 맞출 수 없음")
        return
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        problems.append(f"{answers_path}: JSON으로 읽지 못함 ({type(exc).__name__})")
        return
    expected = answers.get("bundle_manifest_sha256") if isinstance(answers, dict) else None
    if not isinstance(expected, str) or run.get("bundle_manifest_sha256") != expected:
        problems.append(f"{run_path}: bundle_manifest_sha256이 정답지 지문과 다름 — 이 대상의 번들이 아님")


def check_secret_shapes(files: Files, problems: list[str]) -> None:
    """㉣. 값은 찍지 않고 꼴 이름과 줄만 찍는다."""
    found: set[str] = set()
    for path in files.paths():
        if Path(path).suffix.lower() in BINARY_SUFFIXES:
            continue
        for raw in files.versions(path):
            if len(raw) > MAX_TEXT_BYTES:
                found.add(f"{path}: {MAX_TEXT_BYTES}바이트보다 커서 읽지 않음(저장소 밖에 둔다)")
                continue
            for lineno, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
                names = [name for name, pattern in SECRET_SHAPES if pattern.search(line)]
                if openai_shape(line):
                    names.append("OpenAI 키")
                for name in names:
                    found.add(f"{path}:{lineno}: 서비스 꼴 키({name}) — 가짜 값은 이 프로젝트만의 꼴로")
    problems.extend(sorted(found))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    problems: list[str] = []
    files = Files()
    kinds = load_targets(files, problems)
    check_results(files, kinds, problems)
    check_secret_shapes(files, problems)
    for line in problems:
        print(line)
    print(f"bench 파일 {len(files.paths())}개(색인 {len(files.index)}개), 문제 {len(problems)}곳")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
