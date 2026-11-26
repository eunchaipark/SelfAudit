"""F-G02 맞춤 판정 (R5): 결과와 정답을 사람 판단 없이 같게 짝짓는다 (실험구조 2.5·8.4·8.8).

판정 차례(기능명세 F-G02 처리 규칙 번호):
1. 경로 정규화 — `common.paths.normalize_finding_path`, 그 뒤 글자 그대로(대소문자 가림) 비교.
2. 후보 짝 — 범주 안 + 같은 파일 + (줄로 가를 수 있는 위치에서 줄 맞음 또는 닻 맞음).
   닻은 정답의 `anchor`·`decoded_anchor`와 **그 위치의** 위치 닻(`locations[].anchor`).
3. `other`는 짝짓지 않는다.
4·5. 최대 1:1 짝 가운데 열쇠 (닻 맞음 0/1, 줄 차이, 결과 차례, 정답 ID)로 하나씩 고른다.
6. 짝 안 된 결과: 중복 → 미끼 헛짚음 → 틀림.
7. 위치까지 맞음.

'사용자 확인 전'인 값(줄 허용 T, 위치 닻)은 `Rules`로 바꿔 다시 채점할 수 있다(설계 7절).
이 모듈은 순수 계산이다(파일·시각·난수 없음). 결과·정답지의 글을 오류에 싣지 않는다.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from common.contracts import Json
from common.lines import window_covers_file
from common.paths import normalize_finding_path
from score.read import Finding

__all__ = [
    "DEFAULT_RULES",
    "OTHER_CATEGORY",
    "TOLERANCE",
    "AnswerKey",
    "Entry",
    "Location",
    "MatchResult",
    "Rules",
    "Verdict",
    "answer_key",
    "match_run",
]

TOLERANCE: Final = 2  # 줄 허용 T (설계 2.5, 사용자 확인 전 — 다시 채점으로 바꿈)
OTHER_CATEGORY: Final = "other"
_NO_LINE: Final = math.inf  # 규칙 4: `line`이 null이면 줄 차이는 무한
_ANCHORED: Final = 0  # 열쇠 첫 칸: 닻 맞음이 앞선다
_LINE_ONLY: Final = 1

type Verdict = Literal["match", "duplicate", "decoy", "wrong", "other"]


@dataclass(frozen=True)
class Rules:
    """다시 채점할 때 바꾸는 값(설계 2.5 '확인'·7절). 기본값이 지금 정한 값이다.

    - `tolerance`: 줄 허용 T(0·2·5로 다시 채점, 설계 2.5).
    - `location_anchors`: 위치 닻을 닻 맞춤·미끼·위치 정확도에 쓰는가(설계 해석, 8.4 2).
    """

    tolerance: int = TOLERANCE
    location_anchors: bool = True


DEFAULT_RULES: Final = Rules()


@dataclass(frozen=True)
class Location:
    file: str
    line_start: int
    line_end: int
    file_lines: int
    anchor: str | None = None


@dataclass(frozen=True)
class Entry:
    """정답 하나 또는 미끼 하나. 미끼는 `categories`가 비어 있다(미끼 맞춤은 범주를 보지 않음)."""

    id: str
    categories: frozenset[str]
    locations: tuple[Location, ...]
    anchor: str | None
    decoded_anchor: str | None


@dataclass(frozen=True)
class AnswerKey:
    items: tuple[Entry, ...]
    decoys: tuple[Entry, ...]


@dataclass(frozen=True)
class MatchResult:
    """F-G02 출력(실행 하나). 차례는 모두 결과 차례(0부터)다.

    - `verdicts`: 결과마다 맞음·중복·미끼 헛짚음·틀림·`other` 가운데 하나
    - `pairs`: 짝(결과 차례 → 정답 ID), `decoy_misses`: 미끼 헛짚음(결과 차례 → 미끼 ID)
    - `located`: 위치까지 맞은 결과 차례
    """

    verdicts: tuple[Verdict, ...]
    pairs: Mapping[int, str]
    decoy_misses: Mapping[int, str]
    located: frozenset[int] = field(default_factory=frozenset)

    @property
    def matched(self) -> int:
        return len(self.pairs)

    @property
    def duplicates(self) -> int:
        return self.verdicts.count("duplicate")

    @property
    def others(self) -> int:
        return self.verdicts.count("other")

    @property
    def wrong(self) -> int:
        return self.verdicts.count("wrong")


def answer_key(answers: Mapping[str, Json]) -> AnswerKey:
    """계약 `answers`를 지난 정답지에서 짝짓기에 쓰는 칸만 꺼낸다."""
    return AnswerKey(
        items=tuple(_entry(item, with_categories=True) for item in _list(answers, "items")),
        decoys=tuple(_entry(decoy, with_categories=False) for decoy in _list(answers, "decoys")),
    )


def match_run(
    findings: Sequence[Finding],
    key: AnswerKey,
    *,
    target_root: str | None = None,
    rules: Rules = DEFAULT_RULES,
) -> MatchResult:
    """F-G02 맞춤 판정 (R5): 실행 하나의 결과를 정답지와 짝짓는다.

    `target_root`는 그 실행의 대상 폴더 절대 경로(`<RUN>`을 풀 때만, 규칙 1). 결과 차례는
    `findings`의 차례다(`Finding.index`가 아니라 넘긴 차례 — F-G01이 같게 만든다).
    """
    files = [normalize_finding_path(f.file, target_root) for f in findings]
    item_index = _index_by_file(key.items)
    edges: list[tuple[tuple[int, float, int, str], int, int]] = []
    for r, (finding, file) in enumerate(zip(findings, files, strict=True)):
        if finding.category == OTHER_CATEGORY:
            continue
        for e, hit in _best_hits(finding, file, key.items, item_index, rules).items():
            edges.append(((hit[0], hit[1], r, key.items[e].id), r, e))
    chosen = _choose_pairs(edges, len(findings), len(key.items))
    candidates_of = _candidate_items(edges)
    decoy_index = _index_by_file(key.decoys)
    matched_items = frozenset(chosen.values())
    verdicts: list[Verdict] = []
    decoy_misses: dict[int, str] = {}
    for r, (finding, file) in enumerate(zip(findings, files, strict=True)):
        verdict, decoy = _verdict(
            r, finding, file, chosen, matched_items, candidates_of, key, decoy_index, rules
        )
        verdicts.append(verdict)
        if decoy is not None:
            decoy_misses[r] = decoy
    located = frozenset(
        r for r, e in chosen.items() if _is_located(findings[r], files[r], key.items[e], rules)
    )
    return MatchResult(
        verdicts=tuple(verdicts),
        pairs={r: key.items[e].id for r, e in sorted(chosen.items())},
        decoy_misses=decoy_misses,
        located=located,
    )


# --- 후보 짝 (규칙 1·2·4) --------------------------------------------------------------------


def _index_by_file(entries: Sequence[Entry]) -> dict[str, list[tuple[int, Location]]]:
    """파일 → (정답·미끼 차례, 위치). 결과마다 정답지 전체를 다시 훑지 않게(처리량)."""
    index: dict[str, list[tuple[int, Location]]] = {}
    for e, entry in enumerate(entries):
        for location in entry.locations:
            index.setdefault(location.file, []).append((e, location))
    return index


def _best_hits(
    finding: Finding,
    file: str,
    entries: Sequence[Entry],
    index: Mapping[str, list[tuple[int, Location]]],
    rules: Rules,
    *,
    check_category: bool = True,
) -> dict[int, tuple[int, float]]:
    """정답(또는 미끼) 차례 → 후보가 되는 위치 가운데 가장 앞선 (닻 0/1, 줄 차이) (규칙 4)."""
    best: dict[int, tuple[int, float]] = {}
    for e, location in index.get(file, ()):
        entry = entries[e]
        if check_category and finding.category not in entry.categories:
            continue
        hit = _hit_at(finding, entry, location, rules)
        if hit is not None and (e not in best or hit < best[e]):
            best[e] = hit
    return best


def _hit_at(
    finding: Finding, entry: Entry, location: Location, rules: Rules
) -> tuple[int, float] | None:
    """규칙 2㉢: 그 위치에서 줄 맞음 또는 닻 맞음이면 (닻 0/1, 줄 차이), 아니면 None."""
    anchored = _anchored_at(finding, entry, location, rules)
    line_hit = _line_usable(entry, location, rules) and _line_within(
        finding.line, location.line_start - rules.tolerance, location.line_end + rules.tolerance
    )
    if not (anchored or line_hit):
        return None
    return (_ANCHORED if anchored else _LINE_ONLY), _line_gap(finding.line, location)


def _anchored_at(finding: Finding, entry: Entry, location: Location, rules: Rules) -> bool:
    """닻 맞음: 정답의 닻·풀어낸 값, 또는 **그 위치의** 위치 닻이 `evidence`에 글자 그대로."""
    anchors = [entry.anchor, entry.decoded_anchor]
    if rules.location_anchors:
        anchors.append(location.anchor)
    return any(anchor is not None and anchor in finding.evidence for anchor in anchors)


def _line_usable(entry: Entry, location: Location, rules: Rules) -> bool:
    """줄 맞춤을 쓰는가: 줄로 가를 수 있는 위치이거나, 정답에 닻·풀어낸 값이 둘 다 없다."""
    if entry.anchor is None and entry.decoded_anchor is None:
        return True
    return not _covers(location, rules)


def _covers(location: Location, rules: Rules) -> bool:
    return window_covers_file(
        location.line_start, location.line_end, location.file_lines, rules.tolerance
    )


def _line_within(line: int | None, low: int, high: int) -> bool:
    return line is not None and low <= line <= high


def _line_gap(line: int | None, location: Location) -> float:
    """규칙 4: 범위 `[line_start, line_end]` 안이면 0, 밖이면 가까운 끝과의 차, null이면 무한."""
    if line is None:
        return _NO_LINE
    if location.line_start <= line <= location.line_end:
        return 0
    return min(abs(line - location.line_start), abs(line - location.line_end))


def _candidate_items(edges: Iterable[tuple[object, int, int]]) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {}
    for _, r, e in edges:
        out.setdefault(r, set()).add(e)
    return out


# --- 짝 안 된 결과·위치 정확도 (규칙 3·6·7) ----------------------------------------------------


def _verdict(
    r: int,
    finding: Finding,
    file: str,
    chosen: Mapping[int, int],
    matched_items: frozenset[int],
    candidates_of: Mapping[int, set[int]],
    key: AnswerKey,
    decoy_index: Mapping[str, list[tuple[int, Location]]],
    rules: Rules,
) -> tuple[Verdict, str | None]:
    if finding.category == OTHER_CATEGORY:
        return "other", None
    if r in chosen:
        return "match", None
    if candidates_of.get(r, set()) & matched_items:
        return "duplicate", None  # ㉮를 ㉯보다 먼저(같은 정답을 다시 가리킨 결과)
    hits = _best_hits(finding, file, key.decoys, decoy_index, rules, check_category=False)
    if not hits:
        return "wrong", None
    best = min(hits, key=lambda d: (hits[d], key.decoys[d].id))
    return "decoy", key.decoys[best].id


def _is_located(finding: Finding, file: str, item: Entry, rules: Rules) -> bool:
    """규칙 7: 같은 파일의 어느 위치에서 줄이 `[line_start, line_end]` 안(허용 없이)이고,
    줄로 가를 수 없는 위치라면 닻·풀어낸 값·그 위치의 위치 닻이 `evidence`에 있다."""
    for location in item.locations:
        if location.file != file:
            continue
        if not _line_within(finding.line, location.line_start, location.line_end):
            continue
        if not _covers(location, rules) or _anchored_at(finding, item, location, rules):
            return True
    return False


# --- 짝짓기 (규칙 5) -------------------------------------------------------------------------
#
# 명세 차례: 최대 짝 수 M을 구하고, 열쇠 차례로 짝을 하나씩 보며 '고른 짝 + 이 짝'으로 M을
# 이룰 수 있으면 고른다. 짝마다 최대 짝을 새로 구하면 짝 수의 제곱이 되므로(처리량, 보안규칙
# 5장), '이 짝이 어떤 최대 짝에 드는가'를 한 번의 그래프 훑기로 모든 짝에 대해 구한다
# (교대 경로 그래프의 강한 연결 요소 + 짝 없는 꼭짓점에서의 도달). 고를 수 있는 짝의 집합은
# 고른 짝이 늘수록 줄기만 하므로, 옛 집합에 없는 짝은 다시 구하지 않고 건너뛴다.


def _choose_pairs(
    edges: Sequence[tuple[tuple[int, float, int, str], int, int]], n_left: int, n_right: int
) -> dict[int, int]:
    """결과 차례 → 정답 차례. 최대 1:1 짝 가운데 열쇠 차례로 앞선 것을 고른다."""
    graph = _Graph(n_left, n_right, [(r, e) for _, r, e in edges])
    graph.maximize()
    target = graph.size()
    allowed = graph.allowed_edges()
    stale = False
    chosen: dict[int, int] = {}
    for _, r, e in sorted(edges):
        if graph.fixed_left[r] or graph.fixed_right[e] or (r, e) not in allowed:
            continue
        if graph.mate_left[r] != e:
            if stale:
                allowed = graph.allowed_edges()
                stale = False
                if (r, e) not in allowed:
                    continue
            graph.force(r, e)
        graph.fix(r, e)
        chosen[r] = e
        stale = True
    if len(chosen) != target:
        raise AssertionError("짝짓기가 최대 짝 수를 이루지 못함")  # 위 성질이 깨지면 멈춘다
    return chosen


class _Graph:
    """결과(왼쪽)–정답(오른쪽) 이분 그래프와 지금의 최대 짝. 고른(fix) 꼭짓점은 빼고 본다."""

    def __init__(self, n_left: int, n_right: int, edges: Iterable[tuple[int, int]]) -> None:
        self.adj: list[list[int]] = [[] for _ in range(n_left)]
        for r, e in edges:
            self.adj[r].append(e)
        self.n_left = n_left
        self.n_right = n_right
        self.mate_left = [-1] * n_left
        self.mate_right = [-1] * n_right
        self.fixed_left = [False] * n_left
        self.fixed_right = [False] * n_right

    def size(self) -> int:
        return sum(1 for m in self.mate_left if m != -1)

    def fix(self, r: int, e: int) -> None:
        self.fixed_left[r] = True
        self.fixed_right[e] = True

    def force(self, r: int, e: int) -> None:
        """짝 (r, e)를 넣고 r·e의 옛 짝을 풀어, 남은 그래프에서 다시 최대로 만든다."""
        old_e, old_r = self.mate_left[r], self.mate_right[e]
        if old_e != -1:
            self.mate_right[old_e] = -1
        if old_r != -1:
            self.mate_left[old_r] = -1
        self.mate_left[r] = e
        self.mate_right[e] = r
        self.fix(r, e)
        self.maximize()

    def maximize(self) -> None:
        """고르지 않은 꼭짓점 사이에서 늘림 경로가 없을 때까지 늘린다(한 바퀴에 그래프 한 번)."""
        while True:
            seen = [False] * self.n_right
            grew = False
            for r in range(self.n_left):
                if self.mate_left[r] == -1 and not self.fixed_left[r] and self._augment(r, seen):
                    grew = True
            if not grew:
                return

    def _augment(self, start: int, seen: list[bool]) -> bool:
        """`start`에서 늘림 경로를 찾아 뒤집는다(되부름 없이 — 결과가 많아도 깊이 상한 없음)."""
        stack: list[tuple[int, int]] = [(start, 0)]
        path: list[int] = []  # stack[i]의 왼쪽 꼭짓점이 건너간 오른쪽 꼭짓점
        while stack:
            r, pos = stack[-1]
            nexts = self.adj[r]
            while pos < len(nexts) and (seen[nexts[pos]] or self.fixed_right[nexts[pos]]):
                pos += 1
            if pos == len(nexts):
                stack.pop()
                if path:
                    path.pop()
                continue
            e = nexts[pos]
            stack[-1] = (r, pos + 1)
            seen[e] = True
            path.append(e)
            mate = self.mate_right[e]
            if mate == -1:
                for (left, _), right in zip(stack, path, strict=True):
                    self.mate_left[left] = right
                    self.mate_right[right] = left
                return True
            stack.append((mate, 0))
        return False

    def allowed_edges(self) -> set[tuple[int, int]]:
        """고르지 않은 꼭짓점 사이의 짝 가운데 어떤 최대 짝에 드는 것 모두.

        방향 그래프 D: 짝 아닌 변은 결과 → 정답, 짝인 변은 정답 → 결과. 짝 아닌 변 (r, e)가 어떤
        최대 짝에 드는 것은 ㉠ r·e가 D의 같은 강한 연결 요소(교대 고리) ㉡ 짝 없는 결과에서 r에
        닿음(짝 없는 끝에서 시작하는 짝수 교대 경로) ㉢ e에서 짝 없는 정답에 닿음 — 셋 가운데
        하나일 때와 같다. 짝인 변은 늘 든다.
        """
        n = self.n_left + self.n_right
        out: list[list[int]] = [[] for _ in range(n)]
        live: list[tuple[int, int]] = []
        for r in range(self.n_left):
            if self.fixed_left[r]:
                continue
            for e in self.adj[r]:
                if self.fixed_right[e]:
                    continue
                live.append((r, e))
                node_e = self.n_left + e
                if self.mate_left[r] == e:
                    out[node_e].append(r)
                else:
                    out[r].append(node_e)
        free_left = [
            r for r in range(self.n_left) if not self.fixed_left[r] and self.mate_left[r] == -1
        ]
        free_right = [
            self.n_left + e
            for e in range(self.n_right)
            if not self.fixed_right[e] and self.mate_right[e] == -1
        ]
        reach = _reachable(out, free_left)
        back: list[list[int]] = [[] for _ in range(n)]
        for a, targets in enumerate(out):
            for b in targets:
                back[b].append(a)
        coreach = _reachable(back, free_right)
        component = _strong_components(out)
        return {
            (r, e)
            for r, e in live
            if self.mate_left[r] == e
            or reach[r]
            or coreach[self.n_left + e]
            or component[r] == component[self.n_left + e]
        }


def _reachable(out: Sequence[Sequence[int]], starts: Iterable[int]) -> list[bool]:
    seen = [False] * len(out)
    queue: deque[int] = deque()
    for s in starts:
        seen[s] = True
        queue.append(s)
    while queue:
        a = queue.popleft()
        for b in out[a]:
            if not seen[b]:
                seen[b] = True
                queue.append(b)
    return seen


def _strong_components(out: Sequence[Sequence[int]]) -> list[int]:
    """Tarjan의 강한 연결 요소(되부름 없이). 꼭짓점 → 요소 번호."""
    n = len(out)
    order = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    component = [-1] * n
    stack: list[int] = []
    counter = 0
    groups = 0
    for root in range(n):
        if order[root] != -1:
            continue
        work: list[tuple[int, int]] = [(root, 0)]
        order[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack[root] = True
        while work:
            a, pos = work[-1]
            if pos < len(out[a]):
                work[-1] = (a, pos + 1)
                b = out[a][pos]
                if order[b] == -1:
                    order[b] = low[b] = counter
                    counter += 1
                    stack.append(b)
                    on_stack[b] = True
                    work.append((b, 0))
                elif on_stack[b]:
                    low[a] = min(low[a], order[b])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[a])
            if low[a] == order[a]:
                while True:
                    b = stack.pop()
                    on_stack[b] = False
                    component[b] = groups
                    if b == a:
                        break
                groups += 1
    return component


# --- 정답지 꺼내기 ---------------------------------------------------------------------------


def _entry(value: Json, *, with_categories: bool) -> Entry:
    assert isinstance(value, dict)  # 계약 `answers`를 지난 값
    categories = value.get("categories") if with_categories else []
    assert isinstance(categories, list)
    return Entry(
        id=_str(value["id"]),
        categories=frozenset(_str(c) for c in categories),
        locations=tuple(_location(loc) for loc in _list(value, "locations")),
        anchor=_opt_str(value.get("anchor")),
        decoded_anchor=_opt_str(value.get("decoded_anchor")),
    )


def _location(value: Json) -> Location:
    assert isinstance(value, dict)
    return Location(
        file=_str(value["file"]),
        line_start=_int(value["line_start"]),
        line_end=_int(value["line_end"]),
        file_lines=_int(value["file_lines"]),
        anchor=_opt_str(value.get("anchor")),
    )


def _list(value: Mapping[str, Json], key: str) -> list[Json]:
    inner = value[key]
    assert isinstance(inner, list)
    return inner


def _str(value: Json) -> str:
    assert isinstance(value, str)
    return value


def _opt_str(value: Json) -> str | None:
    return None if value is None else _str(value)


def _int(value: Json) -> int:
    # 계약 검증은 JSON 뜻이라 `12.0`도 정수로 지난다(README '공통 함수')
    assert isinstance(value, int | float) and not isinstance(value, bool)
    return int(value)
