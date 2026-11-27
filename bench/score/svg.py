"""F-G04 그림 (R1·R5): SVG 글을 표준 라이브러리만으로 직접 쓴다.

그림 셋(파일 이름 = `FIGURE_NAMES`, `docs/보고서/그림/<이름>.svg`):
① `난이도별_재현율` — 난이도마다 조건별 재현율(막대 = 가운데, 선 = 최소~최대)
② `비용_재현율` — 조건별 비용 대 재현율(점 = 대상 실행 하나, 심은 번들만)
③ `범주별_재현율` — 범주마다 조건별 재현율(①과 같은 꼴, `범주별` 표의 그림)

같은 숫자면 같은 바이트(4): 좌표는 분수로 셈해 소수 한 자리 글로 쓰고, 시각·난수·흔들기를 넣지
않는다. 그림의 글은 이 모듈의 상수와 조건·난이도·범주 이름·실행 ID뿐이고 모두 XML로 이스케이프한다
(결과의 `evidence` 같은 바깥 글은 싣지 않는다).
가로 막대로 그린다 — 범주 이름(`vulnerable_library`)이 가로로 놓여도 서로 겹치지 않게. 그림은
`viewBox`로 같은 비율로만 줄어들어 좁은 화면(390px)에서도 글자 사이가 겹치지 않는다(작아질 뿐).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Final
from xml.sax.saxutils import escape

from score.aggregate import CATEGORIES, DIFFICULTIES, Pool, Report, Spread
from score.metrics import NO_VALUE, fmt_fixed, fmt_tenths

__all__ = ["FIGURE_NAMES", "build_figures"]

FIGURE_NAMES: Final = ("난이도별_재현율", "비용_재현율", "범주별_재현율")
_WIDTH: Final = 720
_FONT: Final = 13
_COLORS: Final = ("#4c72b0", "#dd8452", "#55a868", "#8172b3")  # 조건 차례
_INK: Final = "#222222"
_GRID: Final = "#d0d0d0"
_TICKS: Final = 4  # 0·25·50·75·100%
# 가로 막대 그림
_BAR_LEFT: Final = 160
_BAR_RIGHT: Final = 70
_BAR_TOP: Final = 64
_BAR_HEIGHT: Final = 14
_BAR_GAP: Final = 4
_GROUP_GAP: Final = 16
_AXIS_ROOM: Final = 40
# 점 그림
_DOT_LEFT: Final = 64
_DOT_RIGHT: Final = 24
_DOT_TOP: Final = 64
_DOT_PLOT_HEIGHT: Final = 300
_DOT_RADIUS: Final = 5
_COST_STEP: Final = Fraction(1, 4)  # 비용 축은 0.25 USD 단위로 올린다
_SHAPES: Final = 3  # 점 꼴: 원·네모·마름모 차례
_SQUARE: Final = 1
_DIAMOND: Final = 2


def build_figures(report: Report) -> dict[str, str]:
    """F-G04 표와 그림 (R1·R5): 그림 이름 → SVG 글."""
    return {
        "난이도별_재현율": _bars(
            "난이도별 재현율 (막대 = 가운데, 선 = 최소~최대)",
            DIFFICULTIES,
            report.conditions,
            report.by_difficulty,
        ),
        "비용_재현율": _dots(report),
        "범주별_재현율": _bars(
            "범주별 재현율 (막대 = 가운데, 선 = 최소~최대)",
            CATEGORIES,
            report.conditions,
            report.by_category,
        ),
    }


# --- 가로 막대 (①·③) ------------------------------------------------------------------------


def _bars(
    title: str,
    groups: Sequence[str],
    conditions: Sequence[str],
    pools: Mapping[tuple[str, str], Pool],
) -> str:
    plot = _WIDTH - _BAR_LEFT - _BAR_RIGHT
    group_height = len(conditions) * (_BAR_HEIGHT + _BAR_GAP) - _BAR_GAP
    bottom = _BAR_TOP + len(groups) * (group_height + _GROUP_GAP)
    height = bottom + _AXIS_ROOM
    parts = [*_head(height, title), *_legend(conditions, "rect")]
    parts.extend(_x_grid(_BAR_LEFT, plot, _BAR_TOP - 8, bottom, _percent_ticks()))
    for g, group in enumerate(groups):
        top = _BAR_TOP + g * (group_height + _GROUP_GAP)
        label_y = Fraction(top) + Fraction(group_height, 2) + Fraction(_FONT, 3)
        parts.append(_text(_BAR_LEFT - 8, label_y, group, anchor="end"))
        for c, condition in enumerate(conditions):
            y = top + c * (_BAR_HEIGHT + _BAR_GAP)
            parts.extend(_bar(_BAR_LEFT, plot, y, c, pools[(condition, group)].recall_spread))
    parts.append(_text(_BAR_LEFT + Fraction(plot, 2), height - 10, "재현율 (%)", anchor="middle"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _bar(left: int, plot: int, y: int, c: int, value: Spread | None) -> list[str]:
    middle = Fraction(y) + Fraction(_BAR_HEIGHT, 2)
    if value is None:
        return [_text(left + 4, middle + Fraction(_FONT, 3), NO_VALUE, css="empty")]
    color = _COLORS[c % len(_COLORS)]
    x_low, x_mid, x_high = (left + plot * v for v in (value.low, value.mid, value.high))
    label = f"{fmt_tenths(value.mid)}%"
    return [
        f'<rect class="bar" x="{_n(left)}" y="{_n(y)}" width="{_n(x_mid - left)}" '
        f'height="{_BAR_HEIGHT}" fill="{color}"/>',
        _line(x_low, middle, x_high, middle, _INK),
        _line(x_low, middle - 4, x_low, middle + 4, _INK),
        _line(x_high, middle - 4, x_high, middle + 4, _INK),
        _text(max(x_high, x_mid) + 6, middle + Fraction(_FONT, 3), label),
    ]


# --- 점 (②) ---------------------------------------------------------------------------------


def _dots(report: Report) -> str:
    points = [
        (s, s.metrics.cost_usd, s.recall)
        for s in report.runs
        if s.answered and s.complete and s.metrics.cost_usd is not None and s.recall is not None
    ]
    top_cost = max((cost for _, cost, _ in points if cost is not None), default=Fraction(0))
    x_max = max(_COST_STEP, math.ceil(top_cost / _COST_STEP) * _COST_STEP)
    plot_w = _WIDTH - _DOT_LEFT - _DOT_RIGHT
    bottom = _DOT_TOP + _DOT_PLOT_HEIGHT
    height = bottom + _AXIS_ROOM + 8
    title = "조건별 비용 대 재현율 (점 = 대상 실행 하나)"
    parts = [*_head(height, title), *_legend(report.conditions, "dot")]
    x_ticks = [(Fraction(k, _TICKS), fmt_fixed(x_max * k / _TICKS, 2)) for k in range(_TICKS + 1)]
    parts.extend(_x_grid(_DOT_LEFT, plot_w, _DOT_TOP, bottom, x_ticks))
    for frac, label in _percent_ticks():
        y = bottom - _DOT_PLOT_HEIGHT * frac
        parts.append(_line(_DOT_LEFT, y, _DOT_LEFT + plot_w, y, _GRID))
        parts.append(_text(_DOT_LEFT - 6, y + Fraction(_FONT, 3), label, anchor="end"))
    order = {c: i for i, c in enumerate(report.conditions)}
    for s, cost, recall in points:
        assert cost is not None and recall is not None  # 위에서 걸렀다
        x = _DOT_LEFT + plot_w * cost / x_max
        y = bottom - _DOT_PLOT_HEIGHT * recall
        tip = f"{s.run_id}: 재현율 {fmt_tenths(recall)}%, 비용 {fmt_fixed(cost, 2)} USD"
        parts.append(_mark(order[s.condition], x, y, tip))
    if not points:
        parts.append(
            _text(_DOT_LEFT + Fraction(plot_w, 2), bottom - 150, "점 없음", anchor="middle")
        )
    parts.append(_text(_DOT_LEFT + Fraction(plot_w, 2), height - 10, "비용 (USD)", anchor="middle"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _mark(c: int, x: Fraction, y: Fraction, tip: str, *, css: str = "dot") -> str:
    """조건마다 색과 꼴이 다르다(색을 못 가려도 꼴로 가르게): 원 → 네모 → 마름모 → 원."""
    color = _COLORS[c % len(_COLORS)]
    title = f"<title>{escape(tip)}</title>"
    r = _DOT_RADIUS
    cls = f' class="{css}"' if css else ""
    shape = c % _SHAPES
    if shape == _SQUARE:
        return (
            f'<rect{cls} x="{_n(x - r)}" y="{_n(y - r)}" width="{2 * r}" '
            f'height="{2 * r}" fill="{color}">{title}</rect>'
        )
    if shape == _DIAMOND:
        pts = f"{_n(x)},{_n(y - r)} {_n(x + r)},{_n(y)} {_n(x)},{_n(y + r)} {_n(x - r)},{_n(y)}"
        return f'<polygon{cls} points="{pts}" fill="{color}">{title}</polygon>'
    return f'<circle{cls} cx="{_n(x)}" cy="{_n(y)}" r="{r}" fill="{color}">{title}</circle>'


# --- 공통 조각 -------------------------------------------------------------------------------


def _head(height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{height}" '
        f'viewBox="0 0 {_WIDTH} {height}" font-family="sans-serif" font-size="{_FONT}" '
        f'role="img" aria-label="{escape(title)}">',
        f'<rect x="0" y="0" width="{_WIDTH}" height="{height}" fill="#ffffff"/>',
        _text(12, 24, title, weight="bold"),
    ]


def _legend(conditions: Sequence[str], kind: str) -> list[str]:
    parts: list[str] = []
    for c, condition in enumerate(conditions):
        x = 12 + c * 90
        color = _COLORS[c % len(_COLORS)]
        if kind == "rect":
            parts.append(f'<rect x="{x}" y="36" width="12" height="12" fill="{color}"/>')
        else:
            parts.append(_mark(c, Fraction(x + 6), Fraction(42), f"조건 {condition}", css=""))
        parts.append(_text(x + 18, 47, f"조건 {condition}"))
    return parts


def _x_grid(
    left: int, plot: int, top: int, bottom: int, ticks: Sequence[tuple[Fraction, str]]
) -> list[str]:
    parts: list[str] = []
    for frac, label in ticks:
        x = left + plot * frac
        parts.append(_line(x, top, x, bottom, _GRID))
        parts.append(_text(x, bottom + 16, label, anchor="middle"))
    return parts


def _percent_ticks() -> list[tuple[Fraction, str]]:
    return [(Fraction(k, _TICKS), str(100 * k // _TICKS)) for k in range(_TICKS + 1)]


def _line(
    x1: Fraction | int, y1: Fraction | int, x2: Fraction | int, y2: Fraction | int, color: str
) -> str:
    return (
        f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
        f'stroke="{color}" stroke-width="1"/>'
    )


def _text(
    x: Fraction | int,
    y: Fraction | int,
    content: str,
    *,
    anchor: str = "start",
    weight: str | None = None,
    css: str | None = None,
) -> str:
    extra = (f' font-weight="{weight}"' if weight else "") + (f' class="{css}"' if css else "")
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" text-anchor="{anchor}" fill="{_INK}"{extra}>'
        f"{escape(content)}</text>"
    )


def _n(value: Fraction | int) -> str:
    """좌표 글: 분수를 소수 한 자리로(같은 값이면 늘 같은 글)."""
    return fmt_fixed(Fraction(value), 1)
