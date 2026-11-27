"""F-G03 지표 — 실행 하나 (R5): 재현율·정밀도·위치 정확도와 시간·비용·토큰·도구 호출 수.

- 재현율 = 짝 수 ÷ 정답 수, 정밀도 = 짝 수 ÷ (낸 결과 수 − `other` 수), 위치 정확도 = 위치까지
  맞은 수 ÷ 짝 수 (기능명세 F-G03 1). 정밀도 분모는 맞음이 아닌 결과 전부(중복·미끼 헛짚음·틀림)를
  넣는다 — `MatchResult.wrong`은 ㉰만 세므로 쓰지 않고 결과 수에서 직접 뺀다(T26 넘김).
- `timeout`·`budget_exceeded`·`format_failure`는 재현율 0, 정밀도·위치 정확도는 계산하지 않는다(3).
- 값은 반올림 전 분수(`Fraction`)로 들고 다닌다. 반올림은 보일 때 한 번만(1절 '백분율':
  소수 한 자리, 0.05는 올림) — 모으기·범위 비교가 반올림에 흔들리지 않게(10 '반올림 전 %p').

이 모듈은 순수 계산이다(파일·시각·난수 없음). 결과·정답지의 글을 오류에 싣지 않는다.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Final

from common.contracts import Json
from score.match import (
    DEFAULT_RULES,
    OTHER_CATEGORY,
    MatchResult,
    Rules,
    Verdict,
    answer_key,
    match_run,
)
from score.read import STATUS_OK, Finding, RunRead

__all__ = [
    "NO_VALUE",
    "RUN_KIND_TARGET",
    "ItemInfo",
    "RunMetrics",
    "RunScore",
    "fmt_fixed",
    "fmt_percent",
    "fmt_tenths",
    "item_infos",
    "score_run",
]

NO_VALUE: Final = "-"  # 계산하지 않은 값 (1절 '백분율', F-G04 예외)
RUN_KIND_TARGET: Final = "target"  # F-G03 0: 지표에 넣는 실행 종류
_PERCENT_TENTHS: Final = 1000  # 비율 → 0.1% 단위
_HALF: Final = Fraction(1, 2)
_TOKEN_KEYS: Final = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


@dataclass(frozen=True)
class ItemInfo:
    """정답 하나에서 모으기에 쓰는 칸: 난이도(정답의 것), 주 범주(첫째), 숨긴 꼴."""

    id: str
    difficulty: str
    category: str
    hiding: str


@dataclass(frozen=True)
class RunMetrics:
    """`run.json` `metrics` 값 그대로(F-G03 8). `null`은 `None`. 도구 호출은 이름별 수의 합."""

    wall_s: Fraction
    cost_usd: Fraction | None
    tokens: tuple[int | None, ...]  # _TOKEN_KEYS 차례
    tool_calls: int


@dataclass(frozen=True)
class RunScore:
    """F-G03 실행 하나. 짝짓기(F-G02)를 하지 않은 실행은 `match`가 `None`이다.

    `results`는 낸 결과 수 — 결과가 있는 상태(`ok`)일 때만 수, 그 밖은 `None`.
    """

    run_dir: Path
    run_id: str
    run_kind: str
    target_id: str
    target_kind: str
    condition: str
    repeat: int
    status: str
    answered: bool  # 정답지가 있는 대상인가(내 앱은 아님, F-B05 3)
    complete: bool
    target_difficulty: str | None
    items: tuple[ItemInfo, ...]
    findings: tuple[Finding, ...]
    match: MatchResult | None
    metrics: RunMetrics
    transcript_stored: str
    transcript_sha256: str
    matched_ids: frozenset[str] = field(default_factory=frozenset)

    @property
    def has_results(self) -> bool:
        return self.status == STATUS_OK

    @property
    def results(self) -> int | None:
        return len(self.findings) if self.has_results else None

    @property
    def verdicts(self) -> tuple[Verdict, ...]:
        return self.match.verdicts if self.match is not None else ()

    @property
    def matched(self) -> int:
        return len(self.matched_ids)

    @property
    def others(self) -> int:
        return sum(1 for f in self.findings if f.category == OTHER_CATEGORY)

    @property
    def duplicates(self) -> int:
        return self.match.duplicates if self.match is not None else 0

    @property
    def decoy_misses(self) -> int:
        return len(self.match.decoy_misses) if self.match is not None else 0

    @property
    def located(self) -> int:
        return len(self.match.located) if self.match is not None else 0

    @property
    def recall(self) -> Fraction | None:
        """짝 수 ÷ 정답 수. 정답지가 없거나 정답 수 0이면 `None`(F-G03 0·예외)."""
        if not self.answered or not self.items:
            return None
        return Fraction(self.matched, len(self.items))

    @property
    def precision(self) -> Fraction | None:
        """짝 수 ÷ (낸 결과 수 − `other` 수). 결과 없는 상태·분모 0이면 `None`(F-G03 3·예외)."""
        if not self.answered or not self.has_results:
            return None
        judged = len(self.findings) - self.others
        return Fraction(self.matched, judged) if judged else None

    @property
    def location_accuracy(self) -> Fraction | None:
        if not self.answered or not self.has_results or not self.matched:
            return None
        return Fraction(self.located, self.matched)


def item_infos(answers: Mapping[str, Json]) -> tuple[ItemInfo, ...]:
    """계약 `answers`를 지난 정답지에서 정답마다 (ID, 난이도, 주 범주, 숨긴 꼴)."""
    out: list[ItemInfo] = []
    for item in _list(answers, "items"):
        assert isinstance(item, dict)  # 계약을 지난 값
        categories = _list(item, "categories")
        out.append(
            ItemInfo(
                id=_str(item["id"]),
                difficulty=_str(item["difficulty"]),
                category=_str(categories[0]),
                hiding=_str(item["hiding"]),
            )
        )
    return tuple(out)


def score_run(
    run: RunRead, answers: Mapping[str, Json] | None, rules: Rules = DEFAULT_RULES
) -> RunScore:
    """F-G03 지표 (R5): 실행 하나를 짝짓고(F-G02) 지표에 쓰는 수를 모은다.

    `answers`가 `None`인 대상(내 앱)은 짝짓지 않고 결과 수·시간·비용만 남긴다(F-G03 0).
    결과 차례는 `findings.json`의 차례(F-G01이 정한 차례)다.
    """
    record = run.record
    findings = run.findings or ()
    match: MatchResult | None = None
    if answers is not None and run.findings is not None:
        match = match_run(findings, answer_key(answers), rules=rules)
    return RunScore(
        run_dir=run.run_dir,
        run_id=run.run_id,
        run_kind=_str(record["run_kind"]),
        target_id=run.target_id,
        target_kind=_str(record["target_kind"]),
        condition=run.condition,
        repeat=_int(record["repeat_index"]),
        status=run.status,
        answered=answers is not None,
        complete=answers is not None and answers.get("complete") is True,
        target_difficulty=None if answers is None else _str(answers["difficulty"]),
        items=() if answers is None else item_infos(answers),
        findings=findings,
        match=match,
        metrics=_metrics(_object(record, "metrics")),
        transcript_stored=_str(_object(record, "transcript")["stored"]),
        transcript_sha256=_str(_object(record, "transcript")["sha256"]),
        matched_ids=frozenset(match.pairs.values()) if match is not None else frozenset(),
    )


# --- 보이는 꼴 (1절 '백분율') ----------------------------------------------------------------


def fmt_tenths(value: Fraction) -> str:
    """비율 → 백분율 숫자(소수 한 자리, 0.05는 올림). 66.666…% → `66.7`."""
    return fmt_fixed(value * 100, 1)


def fmt_percent(value: Fraction | None) -> str:
    """비율 → `66.7%`, 계산하지 않은 값 → `-`."""
    return NO_VALUE if value is None else f"{fmt_tenths(value)}%"


def fmt_fixed(value: Fraction, places: int) -> str:
    """소수 `places` 자리, 반올림은 0에서 먼 쪽으로(Decimal ROUND_HALF_UP과 같다).

    분수로 바로 셈한다 — float·Decimal 나눗셈의 끝자리 오차가 0.05 경계를 넘기지 않게.
    """
    scale = 10**places
    sign = "-" if value < 0 else ""
    units = math.floor(abs(value) * scale + _HALF)
    whole, part = divmod(units, scale)
    if places == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}.{part:0{places}d}"


# --- 원자료 칸 꺼내기 ------------------------------------------------------------------------


def _metrics(value: Mapping[str, Json]) -> RunMetrics:
    usage = _object(value, "usage")
    calls = _object(value, "tool_calls")
    return RunMetrics(
        wall_s=_fraction(value["wall_s"]),
        cost_usd=None if value["total_cost_usd"] is None else _fraction(value["total_cost_usd"]),
        tokens=tuple(_opt_int(usage[key]) for key in _TOKEN_KEYS),
        tool_calls=sum(_int(n) for n in calls.values()),
    )


def _fraction(value: Json) -> Fraction:
    """JSON 수 → 분수. float는 짧은 글 꼴(repr)로 — 0.1이 0.1000000000000000055…가 되지 않게."""
    assert isinstance(value, int | float) and not isinstance(value, bool)  # 계약을 지난 값
    return Fraction(value) if isinstance(value, int) else Fraction(repr(value))


def _object(value: Mapping[str, Json], key: str) -> Mapping[str, Json]:
    inner = value[key]
    assert isinstance(inner, dict)  # 계약을 지난 값
    return inner


def _list(value: Mapping[str, Json], key: str) -> Sequence[Json]:
    inner = value[key]
    assert isinstance(inner, list)
    return inner


def _str(value: Json) -> str:
    assert isinstance(value, str)
    return value


def _int(value: Json) -> int:
    # 계약 검증은 JSON 뜻이라 `12.0`도 정수로 지난다(README '공통 함수')
    assert isinstance(value, int | float) and not isinstance(value, bool)
    return int(value)


def _opt_int(value: Json) -> int | None:
    return None if value is None else _int(value)
