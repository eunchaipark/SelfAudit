"""F-G04 표 (R1·R5): F-G03 숫자를 보고서용 Markdown 표 글로 만든다.

- 표 이름과 칸은 기능명세 F-G04 2. 범위는 `60.0~70.0% (70.0%)`(최소~최대 (가운데)).
- 같은 숫자면 같은 글(4). 시각·난수·사전 차례에 기대지 않는다(행·칸 차례는 상수).
- 칸 안 글은 `md_cell`로 — `|`는 `\\|`(5), 그 밖에 표를 깨거나 꾸밈이 되는 글자도 글자로 남긴다.

표 글은 끝 줄바꿈이 없다. 보고서에는 `<!-- 표:<이름> -->` 다음 줄부터 `<!-- /표 -->` 앞 줄까지
그대로 넣는다(F-G05가 앞뒤 줄바꿈 하나씩을 빼고 댄다).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from typing import Final

from score.aggregate import CATEGORIES, DIFFICULTIES, STATUSES, Pool, Report, Spread
from score.metrics import NO_VALUE, fmt_fixed, fmt_tenths

__all__ = [
    "TABLE_NAMES",
    "build_tables",
    "fixed_or_dash",
    "fmt_range",
    "marked",
    "md_cell",
    "md_table",
]

TABLE_NAMES: Final = ("조건별", "난이도별", "범주별", "상태별", "JuiceShop")
_MINUTE_PLACES: Final = 1
_USD_PLACES: Final = 2
_LOWER_BOUND: Final = "≥ "  # F-G03 7: 정답지가 전부가 아닌 대상의 정밀도는 하한
# 칸 안에서 표를 깨거나(`|`) 꾸밈·링크·HTML·수식이 되는 글자. 앞에 `\`를 붙이면 글자로 남는다
_MD_SPECIAL: Final = frozenset("\\`*_[]<>&|~$")
_HIDDEN_KINDS: Final = frozenset({"Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"})


def build_tables(report: Report) -> dict[str, str]:
    """F-G04 표와 그림 (R1·R5): 표 이름 → Markdown 표 글(이름 차례는 `TABLE_NAMES`)."""
    return {
        "조건별": _by_condition(report),
        "난이도별": _by_group(report, "난이도", DIFFICULTIES, report.by_difficulty),
        "범주별": _by_group(report, "범주", CATEGORIES, report.by_category),
        "상태별": _by_status(report),
        "JuiceShop": _practice(report),
    }


def marked(tables: Mapping[str, str]) -> str:
    """표마다 보고서에 넣을 꼴(표식 + 표 글 + 끝 표식)을 이어 붙인 글."""
    blocks = [f"<!-- 표:{name} -->\n{text}\n<!-- /표 -->\n" for name, text in tables.items()]
    return "\n".join(blocks)


def fmt_range(value: Spread | None, prefix: str = "") -> str:
    """`60.0~70.0% (70.0%)` — 최소~최대 (가운데). 값이 없으면 `-`."""
    if value is None:
        return NO_VALUE
    low, high, mid = (fmt_tenths(v) for v in (value.low, value.high, value.mid))
    return f"{prefix}{low}~{high}% ({mid}%)"


def md_table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [_row(header), "|" + "---|" * len(header)]
    lines.extend(_row(row) for row in rows)
    return "\n".join(lines)


def md_cell(text: str) -> str:
    """바깥 글(결과의 `evidence`·`reason` 등)을 표 칸 하나에 글자 그대로 보이게.

    줄바꿈은 `<br>`, 보이지 않는 글자(제어·서식·줄 구분)는 `\\uXXXX` 글로 — 보고서에 숨은 글자가
    들어가지 않게(숨은글자 검사) 하고, 읽는 사람이 거기 무엇이 있었는지 알게 한다.
    """
    out: list[str] = []
    for char in text.replace("\r\n", "\n").replace("\r", "\n"):
        if char == "\n":
            out.append("<br>")
        elif char in _MD_SPECIAL:
            out.append("\\" + char)
        elif unicodedata.category(char) in _HIDDEN_KINDS:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return "".join(out)


# --- 표마다 ----------------------------------------------------------------------------------


def _by_condition(report: Report) -> str:
    header = (
        "조건",
        "재현율 최소~최대(가운데)",
        "정밀도 최소~최대(가운데)",
        "위치 정확도 가운데",
        "시간 가운데(분)",
        "비용 가운데(USD)",
        "상한에 걸린 실행 수",
    )
    rows = []
    for c in report.conditions:
        pool = report.overall[c]
        rows.append(
            (
                c,
                fmt_range(pool.recall_spread),
                fmt_range(pool.precision_spread),
                _mid_percent(pool.location_spread),
                _mid_fixed(report.minutes[c], _MINUTE_PLACES),
                _mid_fixed(report.cost_usd[c], _USD_PLACES),
                str(report.limited(c)),
            )
        )
    return md_table(header, rows)


def _by_group(
    report: Report, label: str, keys: Sequence[str], pools: Mapping[tuple[str, str], Pool]
) -> str:
    header = (label, *(f"조건 {c} 재현율 범위" for c in report.conditions))
    rows = [
        (key, *(fmt_range(pools[(c, key)].recall_spread) for c in report.conditions))
        for key in keys
    ]
    return md_table(header, rows)


def _by_status(report: Report) -> str:
    header = ("조건", *STATUSES)
    rows = [
        (c, *(str(report.status_counts[c][status]) for status in STATUSES))
        for c in report.conditions
    ]
    return md_table(header, rows)


def _practice(report: Report) -> str:
    header = ("조건", "재현율 범위", "정밀도 하한 범위")
    rows = [
        (
            c,
            fmt_range(report.practice[c].recall_spread),
            fmt_range(report.practice[c].precision_spread, _LOWER_BOUND),
        )
        for c in report.conditions
    ]
    return md_table(header, rows)


def _mid_percent(value: Spread | None) -> str:
    return NO_VALUE if value is None else f"{fmt_tenths(value.mid)}%"


def _mid_fixed(value: Spread | None, places: int) -> str:
    return NO_VALUE if value is None else fmt_fixed(value.mid, places)


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def fixed_or_dash(value: Fraction | None, places: int) -> str:
    """수 하나를 소수 `places` 자리로, 없으면 `-`(요약 표용)."""
    return NO_VALUE if value is None else fmt_fixed(value, places)
