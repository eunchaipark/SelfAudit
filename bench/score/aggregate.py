"""F-G03 지표 — 모으기 (R5): 조건·대상마다, 조건 전체·난이도별·범주별, 셋째 차례 권고.

- 조건·대상마다 N번의 최소·가운데·최대(4). 계산하지 않은 값은 빼고 센다.
- 조건 전체·난이도별·범주별은 반복 차례 r마다 '묶음 안 모든 실행의 짝 합 ÷ 정답 합'을 내고
  그 N개의 범위(5). 정밀도도 같은 꼴, 정밀도를 계산하지 않은 실행은 뺀다.
- 난이도별 재현율은 정답의 난이도로, 정밀도는 대상의 난이도로. 범주별 재현율은 정답의 주 범주로,
  정밀도는 결과의 범주로(6).
- `complete: false` 대상(Juice Shop)은 심은 번들 묶음과 섞지 않는다(7). 정답지가 없는 대상(내 앱)은
  결과 수·시간·비용·토큰·도구 호출만(0).
- 셋째 차례 권고(10, 설계 8.2): 범위는 반올림 전 분수로 20%p와 댄다.

조건 이름은 어느 것도 따로 다루지 않는다 — A·B를 바꾸어 넣으면 칸만 바뀐다(공정성).
이 모듈은 순수 계산이다(파일·시각·난수 없음).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from score.match import OTHER_CATEGORY
from score.metrics import RUN_KIND_TARGET, ItemInfo, RunScore, fmt_tenths
from score.read import RunRead, ScoreError

__all__ = [
    "BASE_CONDITIONS",
    "CATEGORIES",
    "DIFFICULTIES",
    "LIMIT_STATUSES",
    "SPREAD_LIMIT",
    "STATUSES",
    "Pool",
    "Report",
    "Rerun",
    "Spread",
    "TargetStats",
    "advice_lines",
    "build_report",
    "spread",
]

BASE_CONDITIONS: Final = ("A", "B")  # 표에 늘 나오는 조건(F-G04 예외: B가 없어도 B 칸은 `-`)
DIFFICULTIES: Final = ("easy", "normal", "hard")
CATEGORIES: Final = (  # 계약 answers.schema.json `category` 차례
    "secret",
    "source_map",
    "internal_address",
    "admin_path",
    "hidden_route",
    "client_authz",
    "debug_flag",
    "vulnerable_library",
)
STATUSES: Final = (
    "ok",
    "format_failure",
    "timeout",
    "budget_exceeded",
    "condition_mismatch",
    "error",
)
LIMIT_STATUSES: Final = frozenset({"timeout", "budget_exceeded"})  # F-G03 9: 상한에 걸림
SPREAD_LIMIT: Final = Fraction(20, 100)  # 셋째 권고 20%p (설계 8.2, 사용자 확인 전 — 첫 실험 뒤)
_TWO_RUNS: Final = 2
_THIRD_RUN: Final = 3


@dataclass(frozen=True)
class Spread:
    """N개 값의 최소·가운데·최대(반올림 전). 가운데는 정렬한 가운데, 짝수 개면 가운데 둘의 평균."""

    low: Fraction
    mid: Fraction
    high: Fraction
    n: int

    @property
    def width(self) -> Fraction:
        return self.high - self.low


def spread(values: Iterable[Fraction | None]) -> Spread | None:
    """계산하지 않은 값(`None`)은 빼고 센다(F-G03 4). 남는 값이 없으면 `None`."""
    kept = sorted(v for v in values if v is not None)
    if not kept:
        return None
    half, odd = divmod(len(kept), 2)
    mid = kept[half] if odd else (kept[half - 1] + kept[half]) / 2
    return Spread(low=kept[0], mid=mid, high=kept[-1], n=len(kept))


@dataclass(frozen=True)
class Pool:
    """한 묶음의 반복 차례별 값(차례 → 분수, 분모 0이면 `None`)."""

    recall: Mapping[int, Fraction | None]
    precision: Mapping[int, Fraction | None]
    location: Mapping[int, Fraction | None]

    @property
    def recall_spread(self) -> Spread | None:
        return spread(self.recall.values())

    @property
    def precision_spread(self) -> Spread | None:
        return spread(self.precision.values())

    @property
    def location_spread(self) -> Spread | None:
        return spread(self.location.values())

    @property
    def repeats(self) -> int:
        """재현율을 낸 차례 수(N)."""
        return sum(1 for v in self.recall.values() if v is not None)


@dataclass(frozen=True)
class TargetStats:
    """조건·대상마다 N번의 범위(F-G03 4·8). 토큰은 `run.json` `usage`의 네 칸 차례."""

    runs: int
    recall: Spread | None
    precision: Spread | None
    results: Spread | None
    minutes: Spread | None
    cost_usd: Spread | None
    tokens: tuple[Spread | None, ...]
    tool_calls: Spread | None


@dataclass(frozen=True)
class Rerun:
    """다시 돌릴 실행(F-G01 2) — 이름과 상태만."""

    run_id: str
    condition: str
    target_id: str
    status: str


@dataclass(frozen=True)
class Report:
    """F-G03 출력: F-G04가 표·그림으로 만드는 원 숫자 전부."""

    conditions: tuple[str, ...]
    runs: tuple[RunScore, ...]  # 지표에 넣은 대상 실행(조건, 대상, 차례, 실행 ID 차례)
    rerun: tuple[Rerun, ...]
    skipped_kinds: Mapping[str, int]  # 넣지 않은 실행 종류(빈·문지기) → 수
    status_counts: Mapping[str, Mapping[str, int]]  # 조건 → 상태 → 대상 실행 수
    by_target: Mapping[tuple[str, str], TargetStats]
    overall: Mapping[str, Pool]
    by_difficulty: Mapping[tuple[str, str], Pool]
    by_category: Mapping[tuple[str, str], Pool]
    practice: Mapping[str, Pool]
    minutes: Mapping[str, Spread | None]  # 조건 → 심은 번들 실행의 시간(분) 범위
    cost_usd: Mapping[str, Spread | None]
    difficulty_targets: Mapping[str, tuple[str, ...]]  # 난이도 → 그 난이도의 심은 번들 ID
    advice: tuple[str, ...]

    def limited(self, condition: str) -> int:
        """상한에 걸린 대상 실행 수(F-G03 9)."""
        counts = self.status_counts.get(condition, {})
        return sum(counts.get(status, 0) for status in sorted(LIMIT_STATUSES))


def build_report(scores: Iterable[RunScore], rerun: Iterable[RunRead]) -> Report:
    """F-G03 지표 (R5): 실행 하나의 지표(`score_run`)를 모아 표·그림의 원 숫자를 만든다.

    받는 차례와 상관없이 같은 값을 낸다(F-G05 5). 같은 (조건, 대상, 차례)의 채점할 실행이 둘이면
    `ScoreError` — 어느 것을 넣을지 사람이 정해야 한다(몰래 하나를 고르지 않는다).
    """
    all_scores = sorted(scores, key=lambda s: (s.condition, s.target_id, s.repeat, s.run_id))
    skipped = Counter(s.run_kind for s in all_scores if s.run_kind != RUN_KIND_TARGET)
    runs = tuple(s for s in all_scores if s.run_kind == RUN_KIND_TARGET)
    _check_unique(runs)
    rerun_runs = sorted(
        (r for r in rerun if r.record.get("run_kind") == RUN_KIND_TARGET),
        key=lambda r: (r.condition, r.target_id, r.run_id),
    )
    conditions = _conditions(runs, rerun_runs)
    planted = [s for s in runs if s.answered and s.complete]
    practice = [s for s in runs if s.answered and not s.complete]
    difficulty_targets = {
        d: tuple(sorted({s.target_id for s in planted if s.target_difficulty == d}))
        for d in DIFFICULTIES
    }
    by_difficulty = {
        (c, d): _pool(
            _of(planted, c),
            item_ok=_item_difficulty(d),
            precision_run=_target_difficulty(d),
        )
        for c in conditions
        for d in DIFFICULTIES
    }
    return Report(
        conditions=conditions,
        runs=runs,
        rerun=tuple(Rerun(r.run_id, r.condition, r.target_id, r.status) for r in rerun_runs),
        skipped_kinds=dict(sorted(skipped.items())),
        status_counts=_status_counts(conditions, runs, rerun_runs),
        by_target=_by_target(runs),
        overall={c: _pool(_of(planted, c)) for c in conditions},
        by_difficulty=by_difficulty,
        by_category={
            (c, k): _pool(
                _of(planted, c),
                item_ok=_item_category(k),
                finding_ok=_finding_category(k),
            )
            for c in conditions
            for k in CATEGORIES
        },
        practice={c: _pool(_of(practice, c)) for c in conditions},
        minutes={c: spread(s.metrics.wall_s / 60 for s in _of(planted, c)) for c in conditions},
        cost_usd={c: spread(s.metrics.cost_usd for s in _of(planted, c)) for c in conditions},
        difficulty_targets=difficulty_targets,
        advice=advice_lines(by_difficulty, difficulty_targets),
    )


def advice_lines(
    by_difficulty: Mapping[tuple[str, str], Pool], difficulty_targets: Mapping[str, Sequence[str]]
) -> tuple[str, ...]:
    """F-G03 10 셋째를 더할지 (설계 8.2): 난이도마다 줄 하나 이하.

    ㉮ N = 2에서 어느 한 조건이라도 범위 > 20%p → 그 난이도 번들 둘을 두 조건 모두 셋째로.
    ㉯ N ≥ 3이면 더 권하지 않고, A·B 범위(최소~최대)가 겹치면 '차이를 말할 수 없음'.
    ㉰ N = 2로 끝난 난이도는 '범위가 두 값'(R1 한계). A·B의 N이 다르면 그것부터 알린다.
    """
    lines: list[str] = []
    for d in DIFFICULTIES:
        pools = {c: by_difficulty.get((c, d)) for c in BASE_CONDITIONS}
        spreads = {c: (p.recall_spread if p is not None else None) for c, p in pools.items()}
        counts = {c: (p.repeats if p is not None else 0) for c, p in pools.items()}
        if not any(counts.values()):
            continue
        if len(set(counts.values())) > 1:
            shown = ", ".join(f"{c} {n}" for c, n in counts.items())
            lines.append(f"{d}: 조건마다 반복 수가 다름({shown}) — 같은 N으로 맞춘 뒤 보기")
            continue
        n = counts[BASE_CONDITIONS[0]]
        if n == _TWO_RUNS:
            lines.append(_two_runs_line(d, spreads, difficulty_targets.get(d, ())))
        elif n >= _THIRD_RUN and _overlap(spreads):
            ranges = ", ".join(f"{c} {_range_text(s)}" for c, s in spreads.items())
            lines.append(f"{d}: 차이를 말할 수 없음 (범위가 겹침: {ranges})")
    return tuple(lines)


# --- 묶기 ------------------------------------------------------------------------------------


def _pool(
    runs: Iterable[RunScore],
    *,
    item_ok: Callable[[ItemInfo], bool] = lambda _i: True,
    finding_ok: Callable[[str], bool] = lambda _c: True,
    precision_run: Callable[[RunScore], bool] = lambda _s: True,
) -> Pool:
    """반복 차례마다 (짝 합, 정답 합)·(맞은 결과 합, 판정한 결과 합)·(위치까지 합, 짝 합)."""
    recall: dict[int, list[int]] = {}
    precision: dict[int, list[int]] = {}
    location: dict[int, list[int]] = {}
    for s in runs:
        rec = recall.setdefault(s.repeat, [0, 0])
        for item in s.items:
            if item_ok(item):
                rec[0] += item.id in s.matched_ids
                rec[1] += 1
        if not (s.has_results and precision_run(s)):
            continue
        prec = precision.setdefault(s.repeat, [0, 0])
        loc = location.setdefault(s.repeat, [0, 0])
        located = s.match.located if s.match is not None else frozenset()
        for index, (finding, verdict) in enumerate(zip(s.findings, s.verdicts, strict=True)):
            if finding.category == OTHER_CATEGORY or not finding_ok(finding.category):
                continue
            prec[1] += 1
            if verdict == "match":
                prec[0] += 1
                loc[1] += 1
                loc[0] += index in located
    return Pool(recall=_ratios(recall), precision=_ratios(precision), location=_ratios(location))


def _item_difficulty(d: str) -> Callable[[ItemInfo], bool]:
    return lambda item: item.difficulty == d


def _target_difficulty(d: str) -> Callable[[RunScore], bool]:
    return lambda s: s.target_difficulty == d


def _item_category(k: str) -> Callable[[ItemInfo], bool]:
    return lambda item: item.category == k


def _finding_category(k: str) -> Callable[[str], bool]:
    return lambda category: category == k


def _ratios(sums: Mapping[int, list[int]]) -> dict[int, Fraction | None]:
    return {r: (Fraction(num, den) if den else None) for r, (num, den) in sorted(sums.items())}


def _by_target(runs: Sequence[RunScore]) -> dict[tuple[str, str], TargetStats]:
    groups: dict[tuple[str, str], list[RunScore]] = {}
    for s in runs:
        groups.setdefault((s.condition, s.target_id), []).append(s)
    out: dict[tuple[str, str], TargetStats] = {}
    for key, group in sorted(groups.items()):
        token_kinds = len(group[0].metrics.tokens)
        out[key] = TargetStats(
            runs=len(group),
            recall=spread(s.recall for s in group),
            precision=spread(s.precision for s in group),
            results=spread(_opt_fraction(s.results) for s in group),
            minutes=spread(s.metrics.wall_s / 60 for s in group),
            cost_usd=spread(s.metrics.cost_usd for s in group),
            tokens=tuple(
                spread(_opt_fraction(s.metrics.tokens[k]) for s in group)
                for k in range(token_kinds)
            ),
            tool_calls=spread(Fraction(s.metrics.tool_calls) for s in group),
        )
    return out


def _status_counts(
    conditions: Sequence[str], runs: Sequence[RunScore], rerun: Sequence[RunRead]
) -> dict[str, dict[str, int]]:
    counts = {c: dict.fromkeys(STATUSES, 0) for c in conditions}
    for status, condition in [(s.status, s.condition) for s in runs] + [
        (r.status, r.condition) for r in rerun
    ]:
        counts[condition][status] += 1
    return counts


def _conditions(runs: Sequence[RunScore], rerun: Sequence[RunRead]) -> tuple[str, ...]:
    seen = {s.condition for s in runs} | {r.condition for r in rerun}
    return BASE_CONDITIONS + tuple(sorted(seen - set(BASE_CONDITIONS)))


def _check_unique(runs: Sequence[RunScore]) -> None:
    seen: set[tuple[str, str, int]] = set()
    for s in runs:
        key = (s.condition, s.target_id, s.repeat)
        if key in seen:
            raise ScoreError(
                f"{s.target_id}: 조건 {s.condition} 차례 {s.repeat}의 채점할 실행이 둘 이상"
            )
        seen.add(key)


def _of(runs: Iterable[RunScore], condition: str) -> list[RunScore]:
    return [s for s in runs if s.condition == condition]


def _opt_fraction(value: int | None) -> Fraction | None:
    return None if value is None else Fraction(value)


# --- 셋째 권고 글 ----------------------------------------------------------------------------


def _two_runs_line(d: str, spreads: Mapping[str, Spread | None], targets: Sequence[str]) -> str:
    over = [c for c, s in spreads.items() if s is not None and s.width > SPREAD_LIMIT]
    if not over:
        return f"{d}: 범위가 두 값 (N = 2, 셋째 없음)"
    bundles = "·".join(targets) if targets else "-"
    why = ", ".join(f"{c} {_width_text(spreads[c])}%p" for c in over)
    return f"{d}: 번들 {bundles}를 두 조건 모두 셋째 차례로 (20%p 넘음: {why})"


def _overlap(spreads: Mapping[str, Spread | None]) -> bool:
    a, b = (spreads[c] for c in BASE_CONDITIONS)
    if a is None or b is None:
        return False
    return a.low <= b.high and b.low <= a.high


def _width_text(s: Spread | None) -> str:
    return "-" if s is None else fmt_tenths(s.width)


def _range_text(s: Spread | None) -> str:
    return "-" if s is None else f"{fmt_tenths(s.low)}~{fmt_tenths(s.high)}%"
