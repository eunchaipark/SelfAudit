"""관제용 병렬 판단. Taskmaster의 tasks.json을 읽기만 하고(고치지 않음),
지금 시작할 수 있는 태스크, 레인별 대기열, 이번 배치안을 짧게 보여 준다.

사용 (저장소 맨 위에서):
  python ops/scripts/tm_parallel.py              # 기본: .taskmaster/tasks/tasks.json, 현재 태그
  python ops/scripts/tm_parallel.py --max 2      # 배치에 넣을 레인 수 (기본 3)
  python ops/scripts/tm_parallel.py --json       # 기계용 출력
  python ops/scripts/tm_parallel.py --tasks 경로 --tag master

관제가 태스크 details 맨 위에 적는 머리줄 (이 스크립트가 읽는다):
  영역: 돈
  목적: 월급날 무엇을 몇 주 살지 바로 알 수 있게
  읽을 문서: 기능명세 F-A16, 화면정의 SCR-05
  고칠 파일: backend/app/money/**, frontend/src/features/money/**
  계약: GET /assets/insight          (선택)
  명세 기준: 3fa9c1d                 (관제가 in-progress로 바꿀 때, 이 스크립트는 읽지 않음)
  변경: CR-007                       (변경 요청으로 생긴 태스크, 이 스크립트는 읽지 않음)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import load_raw_tasks, patterns_overlap, use_utf8_output  # noqa: E402

HEADER_KEYS = {"영역": "lane", "목적": "purpose", "읽을 문서": "docs", "고칠 파일": "files", "계약": "contract"}
HEADER_RE = re.compile(r"^\s*(영역|목적|읽을 문서|고칠 파일|계약)\s*[:：]\s*(.*?)\s*$")
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
ACTIVE = ("in-progress", "review")


@dataclass
class Task:
    id: str
    title: str
    status: str
    priority: str
    deps: list[str]
    lane: str = ""
    purpose: str = ""
    docs: str = ""
    files: list[str] = field(default_factory=list)
    contract: str = ""
    test_strategy: str = ""

    @property
    def sort_key(self) -> tuple[int, int, str]:
        num = int(self.id) if self.id.isdigit() else 10**9
        return (PRIORITY_RANK.get(self.priority, 1), num, self.id)


def parse_header(details: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in (details or "").splitlines():
        m = HEADER_RE.match(line)
        if m and HEADER_KEYS[m.group(1)] not in found:
            found[HEADER_KEYS[m.group(1)]] = m.group(2)
    return found


def split_files(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,，]", value or "") if p.strip()]


def dep_id(d: object) -> str:
    return str(d).strip().split(".")[0]


def load_tasks(path: Path, tag: str | None) -> tuple[list[Task], str]:
    raw, used = load_raw_tasks(path, tag)
    tasks = []
    for t in raw:
        h = parse_header(t.get("details", ""))
        tasks.append(
            Task(
                id=str(t["id"]),
                title=str(t.get("title", "")),
                status=str(t.get("status", "pending")),
                priority=str(t.get("priority", "medium")),
                deps=[dep_id(d) for d in t.get("dependencies", [])],
                lane=h.get("lane", ""),
                purpose=h.get("purpose", ""),
                docs=h.get("docs", ""),
                files=split_files(h.get("files", "")),
                contract=h.get("contract", ""),
                test_strategy=str(t.get("testStrategy", "") or "").strip(),
            )
        )
    return tasks, used


def missing_ready_items(t: Task) -> list[str]:
    miss = []
    if not t.lane:
        miss.append("영역")
    if not t.purpose:
        miss.append("목적")
    if not t.docs:
        miss.append("읽을 문서")
    if not t.files:
        miss.append("고칠 파일")
    if not t.test_strategy:
        miss.append("testStrategy")
    return miss


def first_overlap(files: list[str], others: list[tuple[str, Task]]) -> tuple[str, str, Task] | None:
    for f in files:
        for g, owner in others:
            if patterns_overlap(f, g):
                return f, g, owner
    return None


def analyze(tasks: list[Task], max_lanes: int = 3) -> dict:
    by_id = {t.id: t for t in tasks}
    active = [t for t in tasks if t.status in ACTIVE]
    occupied = [(f, t) for t in active for f in t.files]
    busy_lanes = {t.lane: t for t in tasks if t.status == "in-progress" and t.lane}

    held: list[dict] = []
    candidates: list[Task] = []
    for t in sorted((t for t in tasks if t.status == "pending"), key=lambda x: x.sort_key):
        unknown = [d for d in t.deps if d not in by_id]
        unmet = [d for d in t.deps if d in by_id and by_id[d].status != "done"]
        if unknown or unmet:
            why = []
            if unmet:
                why.append("선행 태스크 미완료: " + ", ".join(unmet))
            if unknown:
                why.append("없는 태스크를 선행으로 둠: " + ", ".join(unknown))
            held.append({"태스크": t.id, "제목": t.title, "이유": " / ".join(why), "종류": "선행 대기"})
            continue
        miss = missing_ready_items(t)
        if miss:
            held.append({"태스크": t.id, "제목": t.title, "이유": "착수 조건 부족: " + ", ".join(miss), "종류": "착수 조건"})
            continue
        # 같은 레인의 진행·검증 중 태스크와 겹치는 것은 막지 않는다: 그 레인 세션이 차례로 이어서 한다
        hit = first_overlap(t.files, [(f, o) for f, o in occupied if o.lane != t.lane])
        if hit:
            f, g, owner = hit
            held.append(
                {"태스크": t.id, "제목": t.title, "이유": f"파일 사용 중: {f} ↔ {g} (T{owner.id} {owner.status})", "종류": "파일 사용 중"}
            )
            continue
        candidates.append(t)

    queues: dict[str, list[str]] = {}
    for t in candidates:
        queues.setdefault(t.lane, []).append(t.id)

    batch: list[Task] = []
    stacked_on: dict[str, str] = {}  # 태스크 → 이어 붙일 앞 태스크(같은 레인, 검증 대기, 파일 겹침)
    continue_in_lane: list[dict] = []
    later: list[dict] = []
    seen_lanes: set[str] = set()
    for t in candidates:
        if t.lane in seen_lanes:
            continue  # 한 레인은 한 번에 하나씩, 나머지는 대기열
        seen_lanes.add(t.lane)
        if t.lane in busy_lanes:
            continue_in_lane.append({"레인": t.lane, "태스크": t.id, "진행 중": busy_lanes[t.lane].id})
            continue
        hit = first_overlap(t.files, [(f, b) for b in batch for f in b.files])
        if hit:
            later.append({"태스크": t.id, "제목": t.title, "이유": f"이번 배치 T{hit[2].id}와 파일 겹침: {hit[0]} ↔ {hit[1]}"})
            continue
        if len(batch) >= max_lanes:
            later.append({"태스크": t.id, "제목": t.title, "이유": f"배치 레인 수 한도({max_lanes})"})
            continue
        base = first_overlap(t.files, [(f, o) for f, o in occupied if o.lane == t.lane and o.status == "review"])
        if base:
            stacked_on[t.id] = base[2].id
        batch.append(t)

    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1

    return {
        "개수": counts,
        "진행 중": [{"태스크": t.id, "제목": t.title, "레인": t.lane, "상태": t.status} for t in active],
        "배치": [
            {"태스크": t.id, "제목": t.title, "레인": t.lane, "파일 수": len(t.files), "계약": t.contract, "기반": stacked_on.get(t.id, "")}
            for t in batch
        ],
        "이어서": continue_in_lane,
        "다음 배치로": later,
        "대기열": queues,
        "보류": held,
        "멈춤": [{"태스크": t.id, "제목": t.title, "상태": t.status} for t in tasks if t.status in ("blocked", "deferred")],
    }


def render(result: dict, source: str, tag: str) -> str:
    c = result["개수"]
    order = ["done", "in-progress", "review", "pending", "blocked", "deferred", "cancelled"]
    names = {"done": "완료", "in-progress": "진행", "review": "검증 대기", "pending": "대기", "blocked": "막힘", "deferred": "미룸", "cancelled": "취소"}
    parts = [f"{names[k]} {c[k]}" for k in order if c.get(k)]
    lines = [f"태스크 판단 — {source} (태그 {tag}) · 전체 {sum(c.values())}: " + " · ".join(parts)]

    def section(title: str, rows: list[str]) -> None:
        lines.append(f"\n{title}")
        lines.extend(rows if rows else ["  (없음)"])

    section("진행 중", [f"  T{r['태스크']} [{r['상태']}] {r['레인'] or '영역 없음'} · {r['제목']}" for r in result["진행 중"]])
    def batch_row(r: dict) -> str:
        extra = f", 계약 {r['계약']}" if r["계약"] else ""
        extra += f", T{r['기반']} 브랜치에서 이어서" if r["기반"] else ""
        return f"  레인 {r['레인']}: T{r['태스크']} {r['제목']} (파일 {r['파일 수']}{extra})"

    section("이번 배치 (새로 시작)", [batch_row(r) for r in result["배치"]])
    if result["이어서"]:
        section("이어서 (진행 중인 레인 세션의 다음 일)", [f"  레인 {r['레인']}: T{r['태스크']} (지금 T{r['진행 중']} 진행 중)" for r in result["이어서"]])
    if result["다음 배치로"]:
        section("다음 배치로", [f"  T{r['태스크']} {r['제목']} — {r['이유']}" for r in result["다음 배치로"]])
    queues = [f"  {lane}: " + " → ".join("T" + i for i in ids) for lane, ids in result["대기열"].items() if len(ids) > 1]
    if queues:
        section("레인 대기열 (2개 이상)", queues)
    section("보류", [f"  T{r['태스크']} {r['제목']} — {r['이유']}" for r in result["보류"]])
    if result["멈춤"]:
        section("막힘·미룸 (사용자 확인)", [f"  T{r['태스크']} [{r['상태']}] {r['제목']}" for r in result["멈춤"]])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(description="Taskmaster 병렬 판단 (읽기 전용)")
    ap.add_argument("--tasks", default=".taskmaster/tasks/tasks.json")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--max", type=int, default=3, help="배치에 넣을 레인 수")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.tasks)
    if not path.exists():
        print(f"tasks.json을 찾을 수 없습니다: {path}", file=sys.stderr)
        return 2
    tasks, tag = load_tasks(path, args.tag)
    result = analyze(tasks, max(1, args.max))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result, args.tasks, tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
