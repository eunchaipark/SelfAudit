"""명령줄: 사용량을 묶어 표나 JSON으로 낸다."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from .reader import TOKEN_FIELDS, Record, ScanResult, default_root, scan

GROUPS = ("project", "session", "day", "agent")
SHORT = ("input", "output", "cache_write", "cache_read")


def group(records: list[Record], by: str) -> list[dict]:
    sums: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        key = getattr(r, by)
        acc = sums[key]
        for i, v in enumerate(r.tokens):
            acc[i] += v
        counts[key] += 1
    rows = [
        {"key": k, "messages": counts[k], **dict(zip(TOKEN_FIELDS, v)), "total": sum(v)}
        for k, v in sums.items()
    ]
    # 날짜는 시간 순서가 읽기 쉽고, 나머지는 큰 것부터
    if by == "day":
        rows.sort(key=lambda r: r["key"])
    else:
        rows.sort(key=lambda r: (-r["total"], r["key"]))
    return rows


def totals(rows: list[dict]) -> dict:
    t = {k: sum(r[k] for r in rows) for k in ("messages", *TOKEN_FIELDS, "total")}
    return t


def to_json(result: ScanResult, by: str, rows: list[dict], top: int) -> str:
    s = result.stats
    return json.dumps(
        {
            "by": by,
            "rows": rows[:top] if top else rows,
            "other_rows": max(0, len(rows) - top) if top else 0,
            "total": totals(rows),
            "stats": {
                "files": s.files,
                "lines": s.lines,
                "broken_lines": s.broken_lines,
                "assistant_lines": s.assistant_lines,
                "duplicate_lines": s.duplicate_lines,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def to_table(result: ScanResult, by: str, rows: list[dict], top: int) -> str:
    shown = rows[:top] if top else rows
    rest = rows[len(shown) :]
    total = totals(rows)
    head = [by, "msgs", *SHORT, "total", "%"]
    body: list[list[str]] = []

    def line(key: str, r: dict) -> list[str]:
        pct = f"{100 * r['total'] / total['total']:.1f}" if total["total"] else "-"
        return [key, f"{r['messages']:,}", *(f"{r[k]:,}" for k in TOKEN_FIELDS), f"{r['total']:,}", pct]

    for r in shown:
        body.append(line(r["key"], r))
    if rest:
        body.append(line(f"(other {len(rest)})", totals(rest)))
    foot = line("TOTAL", total)
    widths = [max(len(c[i]) for c in [head, *body, foot]) for i in range(len(head))]

    def fmt(cells: list[str]) -> str:
        return "  ".join(
            c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths))
        )

    sep = "  ".join("-" * w for w in widths)
    out = [fmt(head), sep, *(fmt(b) for b in body), sep, fmt(foot)]
    s = result.stats
    out.append(
        f"\nfiles {s.files}, lines {s.lines:,}, broken lines skipped {s.broken_lines}, "
        f"duplicate message.id skipped {s.duplicate_lines:,}"
    )
    if not rows:
        out.append("no usage found")
    return "\n".join(out)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="ccusage_lens",
        description="Claude Code usage by project / session / day / agent (numbers only).",
    )
    p.add_argument("--root", type=Path, default=None, help="folder with *.jsonl (default ~/.claude/projects)")
    p.add_argument("--since", type=date.fromisoformat, help="first local day, YYYY-MM-DD")
    p.add_argument("--until", type=date.fromisoformat, help="last local day, YYYY-MM-DD")
    p.add_argument("--project", help="only project folders whose name contains this")
    p.add_argument("--by", choices=GROUPS, default="project")
    p.add_argument("--top", type=int, default=20, help="rows to show, 0 = all (default 20)")
    p.add_argument("--json", action="store_true", help="print numbers-only JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root or default_root()
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    result = scan(root, since=args.since, until=args.until, project=args.project)
    rows = group(result.records, args.by)
    top = max(0, args.top)
    print(to_json(result, args.by, rows, top) if args.json else to_table(result, args.by, rows, top))
    return 0
