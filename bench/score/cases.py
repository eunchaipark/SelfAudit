"""F-G06 사례 뽑기 (R1): 'REA가 있어야만 찾은 것'·반대 방향·'REA가 헛짚은 것'의 후보 목록.

1. B만 찾은 정답 — 대상·정답마다 조건 B 실행 가운데 1번 이상 짝, 조건 A 실행에서는 한 번도 짝 아님.
2. A만 찾은 정답 — 그 반대(결과의 방향을 정해 두지 않는다, 요구사항 3절).
3. B의 미끼 헛짚음 — 조건 B 결과 가운데 미끼 헛짚음(F-G02 6㉯).
4. 항목마다 대상·정답(미끼)·`hiding`·실행 ID·결과 차례·`evidence`·`reason`·대화 기록 줄.
   대화 기록 줄은 그 결과의 `evidence`가 처음 나온 도구 결과(`tool_result`) 줄(못 찾으면 `-`).
   대화 기록이 저장소 밖(`stored: archive`)이면 열지 않고 `run.json`의 sha256만 적는다.
5. 차례: 대상 ID → 정답(미끼) ID → 실행 ID(→ 결과 차례).
6. 심은 번들(`target_kind: planted`)만 — Juice Shop·내 앱은 뽑지 않는다.

1·2는 그 대상에 두 조건 모두 채점한 실행이 있을 때만 본다 — 한 조건의 실행이 모두 다시 돌릴
실행이면 '한 번도 짝 아님'이 실행이 없어서 참이 되어, 찾지 못한 것과 돌지 않은 것이 섞인다.
`evidence`를 대화 기록에서 찾을 때는 글 그대로와 JSON 글 안 꼴(따옴표·역슬래시가 `\\`로 바뀐 꼴)을
함께 본다 — MCP 도구 결과는 JSON 글이라 글 그대로만 찾으면 조건 B만 `-`가 많아진다(공정성).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from common.contracts import ContractJsonError, Json, read_json, validate_contract
from score.metrics import NO_VALUE, RunScore
from score.read import FINDINGS_JSON, ScoreError
from score.tables import md_cell, md_table

__all__ = [
    "KINDS",
    "Candidate",
    "CaseDetail",
    "Hit",
    "cases_markdown",
    "find_in_transcript",
    "read_details",
    "select_cases",
]

KIND_B_ONLY: Final = "B만 찾은 정답"
KIND_A_ONLY: Final = "A만 찾은 정답"
KIND_B_DECOY: Final = "B의 미끼 헛짚음"
KINDS: Final = (KIND_B_ONLY, KIND_A_ONLY, KIND_B_DECOY)
CONDITION_A: Final = "A"
CONDITION_B: Final = "B"
TRANSCRIPT: Final = "transcript.jsonl"
STORED_HERE: Final = "results"
# 저장소 안 대화 기록 상한: 실행기가 이보다 큰 기록은 저장소 밖에 둔다(F-R06 6, 2MB)
_TRANSCRIPT_LIMIT_BYTES: Final = 2 * 1024 * 1024
_PLANTED: Final = "planted"
# JSON 글로 바꾸면 꼴이 바뀌는 글자: 보이는 ASCII(0x20~0x7e) 밖, 따옴표(0x22), 역슬래시(0x5c)
_UNSAFE: Final = re.compile(r"[^\x20\x21\x23-\x5b\x5d-\x7e]")
_EMPTY: Final = "사례 후보 없음"
_HEADER: Final = (
    "대상",
    "정답(미끼)",
    "hiding",
    "실행",
    "결과 차례",
    "evidence",
    "reason",
    "대화 기록 줄",
)


@dataclass(frozen=True)
class Hit:
    """후보 하나가 나온 실행 하나의 결과 하나."""

    run_id: str
    index: int


@dataclass(frozen=True)
class Candidate:
    kind: str
    target_id: str
    entry_id: str
    hiding: str
    hits: tuple[Hit, ...]


@dataclass(frozen=True)
class CaseDetail:
    evidence: str
    reason: str
    where: str  # 대화 기록 줄 번호, `sha256:<64자>`(저장소 밖), 또는 `-`


def select_cases(
    runs: Iterable[RunScore], answers_by_target: Mapping[str, Mapping[str, Json] | None]
) -> tuple[Candidate, ...]:
    """F-G06 사례 뽑기 (R1): 채점한 대상 실행에서 후보를 고른다(순수 계산, 차례 5)."""
    by_target: dict[str, list[RunScore]] = {}
    for s in runs:
        if s.target_kind == _PLANTED and s.answered:
            by_target.setdefault(s.target_id, []).append(s)
    out: list[Candidate] = []
    for target_id in sorted(by_target):
        group = sorted(by_target[target_id], key=lambda s: s.run_id)
        answers = answers_by_target[target_id]
        assert answers is not None  # answered인 실행만 모았다
        out.extend(_only_cases(target_id, group, _hiding(answers, "items")))
        out.extend(_decoy_cases(target_id, group, _hiding(answers, "decoys")))
    return tuple(sorted(out, key=lambda c: (KINDS.index(c.kind), c.target_id, c.entry_id)))


def read_details(
    runs: Iterable[RunScore], candidates: Iterable[Candidate]
) -> tuple[dict[tuple[str, int], CaseDetail], tuple[str, ...]]:
    """후보 결과마다 `evidence`·`reason`·대화 기록 줄. 둘째 값은 알림(실행 ID와 까닭만)."""
    wanted: dict[str, set[int]] = {}
    for candidate in candidates:
        for hit in candidate.hits:
            wanted.setdefault(hit.run_id, set()).add(hit.index)
    details: dict[tuple[str, int], CaseDetail] = {}
    notes: list[str] = []
    for s in sorted(runs, key=lambda s: s.run_id):
        indexes = sorted(wanted.get(s.run_id, ()))
        if not indexes:
            continue
        reasons = _reasons(s.run_dir)
        where, note = _transcript_where(s, {i: s.findings[i].evidence for i in indexes})
        if note:
            notes.append(f"{s.run_id}: {note}")
        for i in indexes:
            details[(s.run_id, i)] = CaseDetail(
                evidence=s.findings[i].evidence, reason=reasons[i], where=where[i]
            )
    return details, tuple(notes)


def cases_markdown(
    candidates: Sequence[Candidate], details: Mapping[tuple[str, int], CaseDetail]
) -> str:
    """사례 후보 목록(Markdown). 종류마다 절 하나, 후보가 없으면 '사례 후보 없음'(예외)."""
    parts = ["# 사례 후보 (F-G06)", ""]
    for kind in KINDS:
        chosen = [c for c in candidates if c.kind == kind]
        rows = sum(len(c.hits) for c in chosen)
        parts.append(f"## {kind} (후보 {len(chosen)}개, 줄 {rows}개)")
        parts.append("")
        parts.append(md_table(_HEADER, _rows(chosen, details)) if chosen else _EMPTY)
        parts.append("")
    return "\n".join(parts)


def find_in_transcript(data: bytes, needles: Mapping[int, str]) -> dict[int, int | None]:
    """결과 차례 → `evidence`가 처음 나온 `tool_result` 줄 번호(1부터), 없으면 `None`.

    줄 목록을 한꺼번에 만들지 않는다(BytesIO는 입력 버퍼를 나눠 쓴다). 찾을 것이 다 찾아지면 멈춘다.
    """
    forms = {i: _forms(text) for i, text in needles.items()}
    cores = {i: _core(text) for i, text in needles.items()}
    found: dict[int, int | None] = dict.fromkeys(needles)
    pending = set(needles)
    for number, line in enumerate(io.BytesIO(data), start=1):
        if not pending:
            break
        texts = list(_tool_results(line))
        if not texts:
            continue
        # 조각마다 따로 찾으면 되풀이가 (조각 × 찾을 것 × 꼴)만큼 돈다. 조각 사이에 NUL을 두고
        # 이어 붙여 한 번에 본다(NUL은 조각을 넘는 맞춤을 막는다 — evidence에 NUL이 있을 때만 예외)
        blob = "\x00".join(texts)
        hits = [i for i in pending if cores[i] in blob and any(form in blob for form in forms[i])]
        for i in hits:
            found[i] = number
            pending.discard(i)
    return found


# --- 고르기 ----------------------------------------------------------------------------------


def _only_cases(
    target_id: str, group: Sequence[RunScore], hiding: Mapping[str, str]
) -> Iterator[Candidate]:
    a_runs = [s for s in group if s.condition == CONDITION_A]
    b_runs = [s for s in group if s.condition == CONDITION_B]
    if not a_runs or not b_runs:
        return
    a_hits = _item_hits(a_runs)
    b_hits = _item_hits(b_runs)
    for item_id in sorted(hiding):
        a, b = a_hits.get(item_id, ()), b_hits.get(item_id, ())
        if b and not a:
            yield Candidate(KIND_B_ONLY, target_id, item_id, hiding[item_id], tuple(b))
        elif a and not b:
            yield Candidate(KIND_A_ONLY, target_id, item_id, hiding[item_id], tuple(a))


def _decoy_cases(
    target_id: str, group: Sequence[RunScore], hiding: Mapping[str, str]
) -> Iterator[Candidate]:
    hits: dict[str, list[Hit]] = {}
    for s in group:
        if s.condition != CONDITION_B or s.match is None:
            continue
        for index, decoy_id in sorted(s.match.decoy_misses.items()):
            hits.setdefault(decoy_id, []).append(Hit(s.run_id, index))
    for decoy_id in sorted(hits):
        yield Candidate(
            KIND_B_DECOY, target_id, decoy_id, hiding.get(decoy_id, NO_VALUE), tuple(hits[decoy_id])
        )


def _item_hits(runs: Sequence[RunScore]) -> dict[str, list[Hit]]:
    out: dict[str, list[Hit]] = {}
    for s in runs:  # 실행 ID 차례로 받는다
        if s.match is None:
            continue
        for index, item_id in sorted(s.match.pairs.items()):
            out.setdefault(item_id, []).append(Hit(s.run_id, index))
    return out


def _hiding(answers: Mapping[str, Json], group: str) -> dict[str, str]:
    entries = answers[group]
    assert isinstance(entries, list)  # 계약을 지난 값
    out: dict[str, str] = {}
    for entry in entries:
        assert isinstance(entry, dict)
        entry_id, hiding = entry["id"], entry.get("hiding", NO_VALUE)
        assert isinstance(entry_id, str) and isinstance(hiding, str)
        out[entry_id] = hiding
    return out


def _rows(
    candidates: Sequence[Candidate], details: Mapping[tuple[str, int], CaseDetail]
) -> Iterator[tuple[str, ...]]:
    for c in candidates:
        for hit in c.hits:
            d = details.get((hit.run_id, hit.index), CaseDetail(NO_VALUE, NO_VALUE, NO_VALUE))
            yield (
                c.target_id,
                c.entry_id,
                c.hiding,
                hit.run_id,
                str(hit.index),
                md_cell(d.evidence),
                md_cell(d.reason),
                d.where,
            )


# --- 원자료 읽기 (바깥과 닿는 곳) --------------------------------------------------------------


def _reasons(run_dir: Path) -> list[str]:
    """`findings.json`의 `reason`(F-G01 `Finding`은 싣지 않는다 — T26 넘김). 계약으로 다시 본다."""
    try:
        value = read_json(run_dir / FINDINGS_JSON)
    except ContractJsonError:
        raise ScoreError(f"{run_dir.name}: findings.json을 다시 읽지 못함") from None
    if validate_contract("findings", value):
        raise ScoreError(f"{run_dir.name}: findings.json이 계약에 어긋남(읽은 뒤 바뀜)")
    assert isinstance(value, dict)
    items = value["findings"]
    assert isinstance(items, list)
    out: list[str] = []
    for item in items:
        assert isinstance(item, dict)
        reason = item["reason"]
        assert isinstance(reason, str)
        out.append(reason)
    return out


def _transcript_where(s: RunScore, needles: Mapping[int, str]) -> tuple[dict[int, str], str]:
    """결과 차례 → 대화 기록 줄 글, 그리고 알림(없으면 빈 글)."""
    if s.transcript_stored != STORED_HERE:
        return dict.fromkeys(needles, f"sha256:{s.transcript_sha256}"), ""
    dash = dict.fromkeys(needles, NO_VALUE)
    path = s.run_dir / TRANSCRIPT
    try:
        with path.open("rb") as f:
            data = f.read(_TRANSCRIPT_LIMIT_BYTES + 1)
    except OSError as e:
        return dash, f"대화 기록을 읽지 못함 ({type(e).__name__})"
    if len(data) > _TRANSCRIPT_LIMIT_BYTES:
        return dash, "대화 기록이 저장소 안 상한(2MB)보다 큼"
    if hashlib.sha256(data).hexdigest() != s.transcript_sha256:
        return dash, "대화 기록 sha256이 run.json과 다름"
    found = find_in_transcript(data, needles)
    return {i: (NO_VALUE if n is None else str(n)) for i, n in found.items()}, ""


def _tool_results(line: bytes) -> Iterator[str]:
    """stream-json 줄 하나의 `tool_result` 글(글 그대로 또는 text 조각들)."""
    if b"tool_result" not in line:
        return
    try:
        obj = json.loads(line)
    except (ValueError, RecursionError):
        return
    message = obj.get("message") if isinstance(obj, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "tool_result"):
            continue
        inner = block.get("content")
        if isinstance(inner, str):
            yield inner
        elif isinstance(inner, list):
            for part in inner:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    yield part["text"]


def _core(text: str) -> str:
    """모든 꼴(`_forms`)에 그대로 들어 있는 가장 긴 조각 — JSON 글로 바꿔도 변하지 않는 글자(따옴표·
    역슬래시 밖의 보이는 ASCII)만 이어진 곳. 이것이 없는 줄은 꼴들을 볼 것도 없다(빠른 거르기)."""
    pieces = _UNSAFE.split(text)
    return max(pieces, key=len)


def _forms(text: str) -> tuple[str, ...]:
    """글 그대로, JSON 글 안 꼴(ASCII 밖 그대로·`\\uXXXX`), 그 꼴이 한 번 더 JSON 글에 실린 꼴
    (도구가 낸 JSON 글의 칸 값이 다시 JSON 글일 때 — 실험구조 8.10 2의 두 겹과 같은 까닭)."""
    once = [json.dumps(text, ensure_ascii=False)[1:-1], json.dumps(text)[1:-1]]
    twice = [json.dumps(form)[1:-1] for form in once]
    return tuple(dict.fromkeys([text, *once, *twice]))
