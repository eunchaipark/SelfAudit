"""문서 담당용 영향 찾기. 기능 ID가 문서·태스크·테스트·코드·커밋 어디에 걸려 있는지 한 번에 보여 준다.
범위 표기(F-A01~A05, F-PRJ-06~11)와 이어 쓰기(PRJ-03·05·07~11)도 알아본다. 아무것도 고치지 않는다.

사용 (저장소 맨 위에서):
  python ops/scripts/impact.py F-A16              # ID 하나
  python ops/scripts/impact.py F-A16 SCR-05       # 여러 개
  python ops/scripts/impact.py --next F-A         # 새 기능에 쓸 다음 번호 (지운 번호도 건너뜀)
  python ops/scripts/impact.py --next CR- --width 3   # 변경 요청·결정 번호는 세 자리
  python ops/scripts/impact.py F-A16 --json       # 기계용 출력
  옵션: --docs docs  --tasks .taskmaster/tasks/tasks.json  --root .
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import load_raw_tasks, use_utf8_output  # noqa: E402

SKIP_DIRS = {  # 어느 깊이에 있든 건너뛴다
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".ops-logs", ".mypy_cache",
    ".ruff_cache", ".pytest_cache", "coverage",
}
TOP_SKIP = {".claude", ".taskmaster", "backups", "ops"}  # 저장소 맨 위에 있을 때만 건너뛴다 (태스크는 따로 읽음)
TEXT_EXT = {
    ".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".yaml", ".yml", ".toml",
    ".html", ".css", ".scss", ".sql", ".txt", ".sh", ".ps1",
}
MAX_RANGE = 50  # 이보다 넓은 범위(FR-101~509 같은 개요)는 영향으로 세지 않는다
SKIP_MARK = "<!-- impact: 건너뜀 -->"  # 규칙·양식 문서처럼 예시 ID만 있는 문서의 맨 위에 둔다


def skipped_doc(text: str) -> bool:
    return SKIP_MARK in "\n".join(text.splitlines()[:5])
MAX_BYTES = 2_000_000
TEST_NAME = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.)")


class IdMatcher:
    """'F-A16' 같은 ID 하나가 한 줄에 직접 또는 범위로 들어 있는지 본다."""

    def __init__(self, ident: str):
        m = re.match(r"^(?P<prefix>.*?)(?P<num>\d+)$", ident.strip())
        if not m or not m.group("prefix"):
            raise ValueError(f"ID 형식이 아닙니다(끝이 숫자여야 함): {ident}")
        self.ident = ident.strip()
        self.prefix = m.group("prefix")
        self.num = int(m.group("num"))
        p = re.escape(self.prefix)
        tail = self.prefix.rsplit("-", 1)[-1] if "-" in self.prefix else ""
        num = rf"(?:{re.escape(tail)})?\d+" if tail else r"\d+"
        item = rf"{num}(?:\s*~\s*(?:{p})?{num})?"
        self.list_re = re.compile(rf"(?<![A-Za-z0-9-]){p}(?P<body>{item}(?:\s*·\s*{item})*)")
        self.under_re = re.compile(rf"(?<![A-Za-z0-9]){re.escape(self.ident.replace('-', '_'))}(?!\d)")
        self.def_cell_re = re.compile(rf"^\|\s*{p}0*{self.num}\s*\|")  # 표의 첫 칸이 이 ID
        self.def_head_re = re.compile(rf"^#+\s*{p}0*{self.num}(?!\d)")  # 제목이 이 ID로 시작

    def numbers(self, body: str) -> tuple[set[int], set[int]]:
        """(범위까지 포함한 번호들, 직접 적힌 번호들)"""
        covered: set[int] = set()
        written: set[int] = set()
        for item in body.split("·"):
            nums = [int(x) for x in re.findall(r"\d+", item.replace(self.prefix, ""))]
            if "~" in item and len(nums) == 2:
                a, b = nums
                written.update((a, b))
                if 0 <= b - a <= MAX_RANGE:
                    covered.update(range(a, b + 1))
            elif nums:
                written.add(nums[0])
                covered.add(nums[0])
        return covered, written

    def kind(self, line: str) -> str | None:
        """'직접' | '범위' | None"""
        found = None
        for m in self.list_re.finditer(line):
            covered, written = self.numbers(m.group("body"))
            if self.num in written:
                return "직접"
            if self.num in covered:
                found = "범위"
        return found

    def is_definition(self, line: str) -> bool:
        s = line.strip()
        return bool(self.def_head_re.match(s) or self.def_cell_re.match(s))


def walk_files(root: Path, top_skip: set[str]):
    """건너뛸 폴더는 아예 들어가지 않는다(node_modules 같은 큰 폴더 때문에)."""
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        at_top = here == root
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not (at_top and d in top_skip))
        for name in sorted(filenames):
            path = here / name
            if path.suffix.lower() not in TEXT_EXT:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            yield path.relative_to(root), text


def is_test_file(rel: Path) -> bool:
    return any(p in ("tests", "test", "__tests__") for p in rel.parts[:-1]) or bool(TEST_NAME.search(rel.name))


def short(text: str, n: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def scan_docs(matcher: IdMatcher, root: Path, docs: Path) -> list[dict]:
    out: list[dict] = []
    base = root / docs
    if not base.exists():
        return out
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        if skipped_doc(text):
            continue
        heading = ""
        seen: dict[tuple[str, str], dict] = {}
        for no, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                heading = line.strip().lstrip("#").strip()
            kind = matcher.kind(line)
            if not kind:
                continue
            if matcher.is_definition(line):
                kind = "정의"
            key = (kind, heading)
            if key in seen and kind != "정의":
                seen[key]["횟수"] += 1
                continue
            row = {"종류": kind, "파일": rel.as_posix(), "줄": no, "절": heading, "글": short(line), "횟수": 1}
            seen[key] = row
            out.append(row)
    order = {"정의": 0, "직접": 1, "범위": 2}
    return sorted(out, key=lambda r: (order[r["종류"]], r["파일"], r["줄"]))


def scan_tasks(matcher: IdMatcher, tasks_path: Path) -> list[dict]:
    if not tasks_path.exists():
        return []
    raw, _ = load_raw_tasks(tasks_path)
    out = []
    for t in raw:
        texts = [t.get("title", ""), t.get("description", ""), t.get("details", ""), t.get("testStrategy", "")]
        for s in t.get("subtasks", []) or []:
            texts += [s.get("title", ""), s.get("details", "")]
        kinds = {matcher.kind(line) for text in texts for line in str(text or "").splitlines()}
        kinds.discard(None)
        if kinds:
            out.append({"태스크": str(t["id"]), "상태": t.get("status", ""), "제목": t.get("title", ""),
                        "종류": "직접" if "직접" in kinds else "범위"})
    return out


def scan_code(matcher: IdMatcher, root: Path, docs: Path) -> tuple[list[dict], list[dict]]:
    tests, code = [], {}
    for rel, text in walk_files(root, TOP_SKIP | {docs.parts[0]}):
        test_file = is_test_file(rel)
        for no, line in enumerate(text.splitlines(), 1):
            hit = matcher.kind(line) or (matcher.under_re.search(line) and "직접")
            if not hit:
                continue
            if test_file:
                tests.append({"파일": rel.as_posix(), "줄": no, "글": short(line)})
            else:
                code[rel.as_posix()] = code.get(rel.as_posix(), 0) + 1
    return tests, [{"파일": f, "횟수": n} for f, n in sorted(code.items())]


def scan_commits(ident: str, root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(root), "log", "--oneline", "-F", f"--grep={ident}", "-n", "200"],
                             capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [ln for ln in out.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def impact(ident: str, root: Path, docs: Path, tasks_path: Path) -> dict:
    m = IdMatcher(ident)
    tests, code = scan_code(m, root, docs)
    return {"ID": m.ident, "문서": scan_docs(m, root, docs), "태스크": scan_tasks(m, tasks_path),
            "테스트": tests, "코드": code, "커밋": scan_commits(m.ident, root)}


def next_id(prefix: str, root: Path, docs: Path, tasks_path: Path, width: int | None = None) -> tuple[str, int]:
    """다음 빈 번호. 자릿수는 width를 주면 그것, 아니면 이미 쓴 번호의 자릿수(없으면 2)."""
    probe = IdMatcher(prefix + "0")
    texts = [p.read_text(encoding="utf-8") for p in sorted((root / docs).rglob("*.md"))] if (root / docs).exists() else []
    texts = [t for t in texts if not skipped_doc(t)]
    if tasks_path.exists():
        texts.append(tasks_path.read_text(encoding="utf-8"))
    best, width_seen = 0, 2
    for text in texts:
        for mt in probe.list_re.finditer(text):
            _, written = probe.numbers(mt.group("body"))
            if written:
                best = max(best, max(written))
            digits = re.findall(r"\d+", mt.group("body").replace(prefix, ""))
            if digits:
                width_seen = max(width_seen, len(digits[0]))
    return f"{prefix}{best + 1:0{width or width_seen}d}", best


def render(r: dict) -> str:
    counts = f"문서 {len(r['문서'])} · 태스크 {len(r['태스크'])} · 테스트 {len(r['테스트'])} · 코드 {len(r['코드'])} · 커밋 {len(r['커밋'])}"
    lines = [f"영향 — {r['ID']}  ({counts})"]

    def section(title: str, rows: list[str]) -> None:
        lines.append(title)
        lines.extend(rows if rows else ["  (없음)"])

    section("문서", [
        f"  {d['종류']}  {d['파일']}:{d['줄']}  § {short(d['절'], 40) or '(맨 위)'}" + (f"  ({d['횟수']}곳)" if d["횟수"] > 1 else "")
        for d in r["문서"]
    ])
    section("태스크", [f"  T{t['태스크']} [{t['상태']}] {t['제목']}" + (" (범위)" if t["종류"] == "범위" else "") for t in r["태스크"]])
    section("테스트", [f"  {t['파일']}:{t['줄']}  {t['글']}" for t in r["테스트"][:20]]
            + ([f"  … {len(r['테스트']) - 20}개 더"] if len(r["테스트"]) > 20 else []))
    section("코드 언급", [f"  {c['파일']} ({c['횟수']})" for c in r["코드"][:20]])
    section("커밋 (최근 3)", [f"  {c}" for c in r["커밋"][:3]])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(description="기능 ID 영향 찾기 (읽기 전용)")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--next", metavar="접두어", help="예: F-A → 다음 빈 번호")
    ap.add_argument("--width", type=int, default=None, help="--next의 자릿수 (CR-·D-는 3)")
    ap.add_argument("--root", default=".")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--tasks", default=".taskmaster/tasks/tasks.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    docs = Path(args.docs)
    tasks_path = Path(args.tasks) if Path(args.tasks).is_absolute() else root / args.tasks

    if args.next:
        ident, best = next_id(args.next, root, docs, tasks_path, args.width)
        print(json.dumps({"다음": ident, "지금까지 가장 큰 번호": best}, ensure_ascii=False) if args.json
              else f"다음 번호: {ident} (지금까지 가장 큰 번호 {best}, 문서·태스크 기준)")
        return 0
    if not args.ids:
        ap.print_usage(sys.stderr)
        return 2
    try:
        results = [impact(i, root, docs, tasks_path) for i in args.ids]
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(render(r) for r in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
