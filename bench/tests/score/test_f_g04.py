"""F-G04 표와 그림 (R1·R5) 시험. 기능명세 F-G04 예시를 옮겼다(값은 가상).

만들기 함수는 `test_f_g03`의 것을 쓴다(그 파일 머리 문서).
"""

from __future__ import annotations

import hashlib
import re
from fractions import Fraction
from xml.etree import ElementTree

from score import aggregate as sa
from score.metrics import RunScore, fmt_fixed, fmt_percent
from score.svg import FIGURE_NAMES, build_figures
from score.tables import TABLE_NAMES, build_tables, fmt_range, marked, md_cell
from tests.score.test_f_g03 import answers_doc, fake_score, hit, miss, scored, xy_runs


def ab_runs() -> list[RunScore]:
    """조건 A·B, easy·hard 대상 하나씩, 두 차례."""
    easy, hard = answers_doc("easy-1", 4), answers_doc("hard-1", 5, difficulty="hard")
    runs = []
    for c, ks in (("A", (1, 2)), ("B", (3, 4))):
        for r, k in enumerate(ks, start=1):
            runs.append(scored(easy, "easy-1", c, r, [hit(i) for i in range(k)] + [miss(0)]))
            runs.append(scored(hard, "hard-1", c, r, [hit(i) for i in range(k)]))
    return runs


def test_F_G04_백분율_소수한자리() -> None:
    cases = {
        Fraction(2, 3): "66.7%",
        Fraction(1, 3): "33.3%",
        Fraction(4, 5): "80.0%",
        Fraction(1, 16): "6.3%",  # 6.25 — 0.05는 올린다(짝수 쪽 반올림이면 6.2)
        Fraction(3, 16): "18.8%",
        Fraction(1, 2000): "0.1%",  # 0.05
        Fraction(0): "0.0%",
        Fraction(1): "100.0%",
    }
    assert {v: fmt_percent(v) for v in cases} == cases
    assert fmt_percent(None) == "-"
    assert fmt_fixed(Fraction(5, 8), 2) == "0.63"  # 0.625
    assert fmt_fixed(Fraction(25, 2), 0) == "13"


def test_F_G04_범위꼴() -> None:
    value = sa.spread([Fraction(6, 10), Fraction(7, 10), Fraction(7, 10)])
    assert fmt_range(value) == "60.0~70.0% (70.0%)"
    assert fmt_range(None) == "-"


def test_F_G04_조건별표_B줄_재현율칸() -> None:
    x = answers_doc("x-1", 10)
    runs = [
        scored(x, "x-1", "B", r, [hit(i) for i in range(k)])
        for r, k in enumerate((6, 7, 7), start=1)
    ]
    table = build_tables(sa.build_report(runs, []))["조건별"]
    b_row = next(line for line in table.split("\n") if line.startswith("| B |"))
    assert b_row.split(" | ")[1] == "60.0~70.0% (70.0%)"
    a_row = next(line for line in table.split("\n") if line.startswith("| A |"))
    assert a_row == "| A | - | - | - | - | - | 0 |"


def test_F_G04_조건별표_칸() -> None:
    table = build_tables(sa.build_report(ab_runs(), []))["조건별"]
    assert table.split("\n") == [
        "| 조건 | 재현율 최소~최대(가운데) | 정밀도 최소~최대(가운데) | 위치 정확도 가운데 "
        "| 시간 가운데(분) | 비용 가운데(USD) | 상한에 걸린 실행 수 |",
        "|---|---|---|---|---|---|---|",
        # 차례 1: (1 + 1) ÷ 9, 차례 2: (2 + 2) ÷ 9 / 정밀도 2 ÷ 3, 4 ÷ 5
        "| A | 22.2~44.4% (33.3%) | 66.7~80.0% (73.3%) | 100.0% | 10.0 | 0.75 | 0 |",
        "| B | 66.7~88.9% (77.8%) | 85.7~88.9% (87.3%) | 100.0% | 10.0 | 0.75 | 0 |",
    ]


def test_F_G04_상태별표_예시() -> None:
    answers = answers_doc("easy-1", 4)
    runs = [scored(answers, "easy-1", "A", r, [hit(0)]) for r in range(1, 17)]
    runs.append(scored(answers, "easy-1", "A", 17, None, "timeout"))
    runs.append(scored(answers, "easy-1", "A", 18, None, "format_failure"))
    table = build_tables(sa.build_report(runs, []))["상태별"]
    lines = table.split("\n")
    assert lines[0] == (
        "| 조건 | ok | format_failure | timeout | budget_exceeded | condition_mismatch | error |"
    )
    assert lines[2] == "| A | 16 | 1 | 1 | 0 | 0 | 0 |"
    assert lines[3] == "| B | 0 | 0 | 0 | 0 | 0 | 0 |"  # B가 없어도 표는 만든다


def test_F_G04_난이도별·범주별·JuiceShop표() -> None:
    juice = answers_doc("juice-shop", 10, origin="practice")
    j = scored(
        juice,
        "juice-shop",
        "A",
        1,
        [hit(0), hit(1), hit(2)] + [miss(k) for k in range(4)],
        kind="practice",
    )
    tables = build_tables(sa.build_report([*ab_runs(), j], []))
    assert tables["난이도별"].split("\n")[2:] == [
        "| easy | 25.0~50.0% (37.5%) | 75.0~100.0% (87.5%) |",
        "| normal | - | - |",
        "| hard | 20.0~40.0% (30.0%) | 60.0~80.0% (70.0%) |",
    ]
    category_rows = tables["범주별"].split("\n")[2:]
    assert len(category_rows) == 8
    assert category_rows[0] == "| secret | 22.2~44.4% (33.3%) | 66.7~88.9% (77.8%) |"
    assert category_rows[-1] == "| vulnerable_library | - | - |"
    assert tables["JuiceShop"].split("\n")[2:] == [
        "| A | 30.0~30.0% (30.0%) | ≥ 42.9~42.9% (42.9%) |",
        "| B | - | - |",
    ]


def test_F_G04_표_같은입력_같은글() -> None:
    one = marked(build_tables(sa.build_report(ab_runs(), [])))
    two = marked(build_tables(sa.build_report(list(reversed(ab_runs())), [])))
    assert one == two
    assert list(build_tables(sa.build_report(ab_runs(), []))) == list(TABLE_NAMES)


def test_F_G04_표식꼴() -> None:
    text = marked({"조건별": "| a |\n|---|"})
    assert text == "<!-- 표:조건별 -->\n| a |\n|---|\n<!-- /표 -->\n"


def test_F_G04_칸안_바깥글() -> None:
    assert md_cell("a|b") == "a\\|b"
    assert md_cell("x\ny\r\nz") == "x<br>y<br>z"
    assert md_cell("<script>`*$") == "\\<script\\>\\`\\*\\$"
    assert md_cell("키​값‮") == "키\\u200b값\\u202e"  # 보이지 않는 글자는 글로


def test_F_G04_SVG_같은입력_같은바이트() -> None:
    one = build_figures(sa.build_report(ab_runs(), []))
    two = build_figures(sa.build_report(list(reversed(ab_runs())), []))
    digest = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in one.items()}
    assert digest == {k: hashlib.sha256(v.encode()).hexdigest() for k, v in two.items()}


def test_F_G04_SVG_XML로_읽힘() -> None:
    for text in build_figures(sa.build_report(ab_runs(), [])).values():
        root = ElementTree.fromstring(text)  # noqa: S314 — 이 시험이 만든 글
        assert root.tag.endswith("svg")
        assert root.get("viewBox") is not None


def test_F_G04_SVG_빈칸_빈막대() -> None:
    a_only = [s for s in ab_runs() if s.condition == "A"]
    figures = build_figures(sa.build_report(a_only, []))
    difficulty = figures["난이도별_재현율"]
    # 막대는 A의 easy·hard 둘. A normal과 B 셋은 막대 없이 `-`
    assert difficulty.count('class="bar"') == 2
    assert difficulty.count('class="empty"') == 4
    category = figures["범주별_재현율"]
    assert category.count('class="bar"') == 1  # A의 secret만
    assert category.count('class="empty"') == 15


def test_F_G04_SVG_점은_실행하나씩() -> None:
    figure = build_figures(sa.build_report(ab_runs(), []))["비용_재현율"]
    assert figure.count('class="dot"') == 8  # 대상 실행 8개, 범례는 class가 없다
    assert "easy-1-a-1-ab12ab12: 재현율 25.0%, 비용 0.75 USD" in figure
    empty = build_figures(sa.build_report([], []))["비용_재현율"]
    assert "점 없음" in empty


def test_F_G04_SVG_막대길이는_가운데값() -> None:
    runs = [fake_score("easy-1", "A", r, 10, k, difficulty="easy") for r, k in ((1, 4), (2, 6))]
    figure = build_figures(sa.build_report(runs, []))["난이도별_재현율"]
    widths = re.findall(r'class="bar" x="160.0" y="[0-9.]+" width="([0-9.]+)"', figure)
    assert widths == ["245.0"]  # 가운데 50% × 그림 너비 490


def test_F_G04_그림3장_이름() -> None:
    assert FIGURE_NAMES == ("난이도별_재현율", "비용_재현율", "범주별_재현율")
    assert list(build_figures(sa.build_report(xy_runs(), []))) == list(FIGURE_NAMES)
