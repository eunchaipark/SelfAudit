"""문제와 개선 자동 정리. 보고서·인계서·검증 결과·역할별 회고 기록에서
`- 방법론: 문제 → 제안`, `- 프로젝트: 문제 → 제안` 줄을 모아 `docs/회고.md`를 다시 만든다.
`ops/측정.csv`가 있으면 모델·노력별 반려·교대도 모은다. 판단 없이 모으기만 한다(토큰 0).

사용 (저장소 맨 위에서):
  python ops/scripts/retro.py            # docs/회고.md 다시 만들기 + 요약 한 줄
  python ops/scripts/retro.py --print    # 파일을 쓰지 않고 화면에만
  옵션: --root .  --out docs/회고.md

줄 형식 (어느 파일에 있어도 된다. 첫 '→'(또는 '->')에서 문제와 제안을 나눈다):
  - 방법론: 인계서에 실행 중인 서버가 빠졌다 → 인계서 양식에 '실행 중인 것' 칸
  - 프로젝트: REA가 APK 리소스를 못 읽었다 → 대체 도구 검토
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import use_utf8_output  # noqa: E402

SOURCES = ["ops/보고/*.md", "ops/인계/*.md", "ops/검증/*.md", "ops/회고/*.md"]
ITEM_RE = re.compile(r"^\s*[-*]\s*(방법론|프로젝트)\s*[:：]\s*(.+?)\s*$")
ARROW_RE = re.compile(r"\s*(?:→|->)\s*")
EMPTY = {"없음", "없음.", "-", "해당 없음"}
KINDS = ("방법론", "프로젝트")


def collect(root: Path) -> tuple[list[dict], int]:
    items: list[dict] = []
    files = sorted({p for pattern in SOURCES for p in root.glob(pattern) if p.is_file()})
    for path in files:
        day = date.fromtimestamp(path.stat().st_mtime).isoformat()
        rel = path.relative_to(root).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            m = ITEM_RE.match(line)
            if not m:
                continue
            kind, text = m.group(1), m.group(2)
            if text in EMPTY or text.startswith("<"):
                continue
            problem, suggestion = split_item(text)
            items.append({"구분": kind, "문제": problem, "제안": suggestion, "출처": rel, "날짜": day})
    items.sort(key=lambda r: (r["날짜"], r["출처"]))
    return items, len(files)


def split_item(text: str) -> tuple[str, str]:
    """'문제 → 제안'을 (문제, 제안)으로. 화살표가 없으면 제안은 빈칸."""
    parts = ARROW_RE.split(text, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


def key_of(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower())


def repeats(items: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for it in items:
        groups[(it["구분"], key_of(it["문제"]))].append(it)
    out = [{"구분": g[0]["구분"], "문제": g[0]["문제"], "횟수": len(g), "출처": ", ".join(sorted({x["출처"] for x in g}))}
           for g in groups.values() if len(g) >= 2]
    return sorted(out, key=lambda r: (-r["횟수"], r["구분"]))


def metrics(root: Path) -> list[dict]:
    path = root / "ops" / "측정.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or not {"레인", "모델", "노력"} <= set(rows[0]):
        return []

    def num(v: str | None) -> int:
        try:
            return int(str(v).strip() or 0)
        except ValueError:
            return 0

    groups: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        k = (r.get("레인") or "?", r.get("모델") or "?", r.get("노력") or "?")
        g = groups.setdefault(k, {"레인": k[0], "모델": k[1], "노력": k[2], "태스크": 0, "반려": 0, "교대": 0})
        g["태스크"] += 1
        g["반려"] += num(r.get("반려"))
        g["교대"] += num(r.get("교대"))
    return sorted(groups.values(), key=lambda g: (g["레인"], g["모델"], g["노력"]))


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(items: list[dict], file_count: int, reps: list[dict], mets: list[dict], now: datetime) -> str:
    count = {k: sum(1 for it in items if it["구분"] == k) for k in KINDS}
    today = now.date().isoformat()
    new_today = sum(1 for it in items if it["날짜"] == today)
    out = [
        "# 회고 (자동 생성 — 손으로 고치지 않는다)",
        "",
        f"만든 때: {now.strftime('%Y-%m-%d %H:%M')} · 출처 파일 {file_count}개 · 방법론 {count['방법론']}건 · "
        f"프로젝트 {count['프로젝트']}건 · 오늘 새로 {new_today}건",
        "다시 만들기: `python ops/scripts/retro.py` (기록 단계마다). 항목은 보고서·인계서·검증 결과의 '문제와 개선' 칸과 "
        "`ops/회고/<역할>.md`에서 모은다.",
        "",
        "## 자주 나온 것 (2번 이상)",
        "",
    ]
    if reps:
        out += ["| 구분 | 문제 | 횟수 | 출처 |", "|---|---|---|---|"]
        out += [f"| {r['구분']} | {cell(r['문제'])} | {r['횟수']} | {cell(r['출처'])} |" for r in reps]
    else:
        out.append("(없음)")
    titles = {"방법론": "방법론 — 클로드로 일하는 방식 (SessionKit에 반영할 후보)", "프로젝트": "프로젝트 — 명세·코드·도구"}
    for kind in KINDS:
        rows = [it for it in items if it["구분"] == kind]
        out += ["", f"## {titles[kind]}", ""]
        if rows:
            out += ["| 날짜 | 출처 | 문제 | 제안 |", "|---|---|---|---|"]
            out += [f"| {r['날짜']} | {cell(r['출처'])} | {cell(r['문제'])} | {cell(r['제안'])} |" for r in rows]
        else:
            out.append("(없음)")
    out += ["", "## 모델·노력별 결과 (`ops/측정.csv`)", ""]
    if mets:
        out += ["| 레인 | 모델 | 노력 | 태스크 | 반려 | 교대 |", "|---|---|---|---|---|---|"]
        out += [f"| {cell(m['레인'])} | {cell(m['모델'])} | {cell(m['노력'])} | {m['태스크']} | {m['반려']} | {m['교대']} |"
                for m in mets]
        out.append("")
        out.append("반려·교대가 많은 조합은 `ops/모델표.md`를 다시 본다(노력을 올리거나 태스크를 더 작게).")
    else:
        out.append("(아직 없음)")
    out += [
        "",
        "## 회고 때 정할 것 (총괄이 사용자와)",
        "",
        "- 방법론 항목: SessionKit 키트(역할 카드·양식·스크립트)에 반영할지",
        "- 프로젝트 항목: 변경 요청 후보(문서)인지, 태스크(관제)인지",
        "- 모델·노력 표를 바꿀지",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(description="문제와 개선 자동 정리")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="docs/회고.md")
    ap.add_argument("--print", action="store_true", dest="print_only")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    items, file_count = collect(root)
    reps = repeats(items)
    text = render(items, file_count, reps, metrics(root), datetime.now())
    if args.print_only:
        print(text)
        return 0
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")  # Windows에서도 LF
    count = {k: sum(1 for it in items if it["구분"] == k) for k in KINDS}
    print(f"회고: 방법론 {count['방법론']} · 프로젝트 {count['프로젝트']} · 자주 나온 것 {len(reps)} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
