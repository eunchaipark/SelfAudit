"""F-G02 맞춤 판정 (R5) 시험. 기능명세 F-G02 예시를 옮겼다(정답지·결과는 가상).

정답지는 `fixtures/g01_g02/`(손으로 만든 작은 정답지 ㉮·㉯·㉰와 압축 번들). 계약을 지나는지도 본다.
"""

from __future__ import annotations

import gc
import itertools
import random
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from score import match as sm
from score.read import Finding

FIXTURES = Path(__file__).parent / "fixtures" / "g01_g02"
J = "assets/index-3f2a.js"
M = "assets/index-3f2a.js.map"
KEY_E1 = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
N2_FILE = "assets/m-9c1e.js"
N2_B64 = "emVsdG9fYjBDNGZyWXp0NEJLT0JHUjBFT2NsaWVicHJwcERZTzg="
N2_DECODED = KEY_E1
LINEAR_RATIO_LIMIT = (
    8.0  # 선형이면 4배 입력에 약 4배, 제곱이면 약 16배 — 그 가운데(test_f_r06과 같은 근거)
)


def answers(name: str) -> dict[str, Json]:
    return read_contract("answers", FIXTURES / f"answers_{name}.json")


def key(name: str) -> sm.AnswerKey:
    return sm.answer_key(answers(name))


def findings(*rows: tuple[str, str, int | None, str]) -> list[Finding]:
    return [Finding(i, c, file, line, ev) for i, (c, file, line, ev) in enumerate(rows)]


def run(name: str, *rows: tuple[str, str, int | None, str], **kw: object) -> sm.MatchResult:
    return sm.match_run(findings(*rows), key(name), **kw)  # type: ignore[arg-type]


# 정답지 ㉮의 결과 8개 (기능명세 F-G02 예시 첫 표)
GA_ROWS: tuple[tuple[str, str, int | None, str], ...] = (
    ("secret", J, 13, f'payKey: "{KEY_E1}"'),
    ("secret", M, None, KEY_E1),
    ("internal_address", "./assets/index-3f2a.js", 40, 'base:"http://10.20.30.40:8080"'),
    ("admin_path", "assets\\index-3f2a.js", 60, 'fetch("/internal-admin/users")'),
    ("debug_flag", J, 83, "debug: true"),
    ("secret", J, 20, 'apiKey: "YOUR_API_KEY"'),
    ("other", J, 5, "eval(x)"),
    ("source_map", "assets/Index-3f2a.js.map", 1, '"sourcesContent"'),
)


# --- 정답지 ㉮ -------------------------------------------------------------------------------


def test_F_G02_예시정답지_계약에맞음() -> None:
    for name in ("ga", "gb", "n2", "gc"):
        answers(name)  # 어긋나면 ContractViolationError


def test_F_G02_예시_결과8개_모두() -> None:
    result = run("ga", *GA_ROWS)
    assert result.pairs == {0: "E1-01", 2: "E1-02", 3: "E1-03"}
    assert result.verdicts == (
        "match",
        "duplicate",
        "match",
        "match",
        "wrong",
        "decoy",
        "other",
        "wrong",
    )
    assert (result.matched, result.duplicates, result.others) == (3, 1, 1)
    assert result.decoy_misses == {5: "E1-D1"}
    assert result.located == frozenset({2})


def test_F_G02_동점_닻먼저_줄가까운것() -> None:
    # 0번 (닻, 줄 차이 1)이 1번 (닻, 무한)보다 앞선다
    result = run("ga", GA_ROWS[0], GA_ROWS[1])
    assert result.pairs == {0: "E1-01"}
    assert result.verdicts == ("match", "duplicate")
    # 닻이 같으면 줄이 가까운 것 — 차례가 뒤라도 줄 12(차이 0)가 13(차이 1)보다 앞선다
    near = run("ga", GA_ROWS[0], ("secret", J, 12, KEY_E1))
    assert near.pairs == {1: "E1-01"}
    assert near.located == frozenset({1})
    # 닻 맞음이 줄 맞음보다 앞선다 — 줄만 맞은 0번(차이 0)보다 닻이 맞은 1번(차이 무한)
    anchored = run("ga", ("secret", J, 12, "k"), ("secret", M, None, KEY_E1))
    assert anchored.pairs == {1: "E1-01"}
    assert anchored.verdicts == ("duplicate", "match")


def test_F_G02_같은정답_두번_중복은틀림() -> None:
    result = run("ga", GA_ROWS[2], GA_ROWS[2])
    assert result.pairs == {0: "E1-02"}  # 열쇠가 같으면 결과 차례가 앞선 것
    assert result.duplicates == 1
    assert result.decoy_misses == {}


def test_F_G02_역슬래시·점슬래시_정규화() -> None:
    result = run("ga", GA_ROWS[2], GA_ROWS[3], ("secret", "././assets/index-3f2a.js", 12, "k"))
    assert result.pairs == {0: "E1-02", 1: "E1-03", 2: "E1-01"}


def test_F_G02_대상폴더_절대경로를_지움() -> None:
    root = "C:\\RUN\\target"
    hit = run(
        "n2", ("secret", "C:\\RUN\\target\\assets\\m-9c1e.js", None, N2_B64), target_root=root
    )
    assert hit.pairs == {0: "N2-01"}
    # 앞부분이 글자로 다르면(소문자) 지우지 않는다 → 정답 파일과 다름, 틀림
    miss = run("n2", ("secret", "c:/run/target/assets/m-9c1e.js", None, N2_B64), target_root=root)
    assert miss.verdicts == ("wrong",)


def test_F_G02_대소문자다른파일_짝아님() -> None:
    assert run("ga", GA_ROWS[7]).verdicts == ("wrong",)
    assert run("ga", ("source_map", M, 1, '"sourcesContent"')).pairs == {0: "E1-05"}


def test_F_G02_정답범주밖_짝아님() -> None:
    # E1-02는 internal_address만 — 같은 줄·같은 닻이어도 admin_path로는 짝이 아니다
    result = run("ga", ("admin_path", J, 40, 'base:"http://10.20.30.40:8080"'))
    assert result.verdicts == ("wrong",)


def test_F_G02_둘째범주도_맞음() -> None:
    # N1-01의 둘째 범주 admin_path. 줄 30은 N1-01(차이 0)·N1-02(차이 1) 모두 후보 — 줄 가까운 쪽
    result = run("gb", ("admin_path", "a.js", 30, "zz"))
    assert result.pairs == {0: "N1-01"}
    assert run("gb", ("internal_address", "a.js", 30, "zz")).pairs == {0: "N1-01"}


def test_F_G02_line_end더하기2_맞음() -> None:
    result = run("ga", ("admin_path", J, 59, "zz"), ("admin_path", J, 53, "zz"))
    assert result.pairs == {0: "E1-03"}  # 둘 다 줄 차이 2 — 결과 차례가 앞선 것
    assert run("ga", ("admin_path", J, 59, "zz")).pairs == {0: "E1-03"}
    assert run("ga", ("admin_path", J, 53, "zz")).pairs == {0: "E1-03"}


def test_F_G02_line_end더하기3_틀림() -> None:
    assert run("ga", ("admin_path", J, 60, "zz")).verdicts == ("wrong",)
    assert run("ga", ("admin_path", J, 52, "zz")).verdicts == ("wrong",)
    assert run("ga", GA_ROWS[4]).verdicts == ("wrong",)  # 예시 4번: 83(차이 3), 닻 없음


def test_F_G02_줄틀려도_닻있으면_맞음() -> None:
    result = run("ga", GA_ROWS[3])
    assert result.pairs == {0: "E1-03"}
    assert result.located == frozenset()  # 60 ∉ 55~57


def test_F_G02_닻null·줄null_짝아님() -> None:
    # E1-05는 닻이 없다. 줄이 null이면 후보 짝이 아니다(예외 칸)
    assert run("ga", ("source_map", M, None, '"sourcesContent"')).verdicts == ("wrong",)
    # 닻이 있는 정답이라도 줄 null + 닻 없는 evidence면 아님
    assert run("ga", ("internal_address", J, None, "zz")).verdicts == ("wrong",)


def test_F_G02_map위치로도_맞음() -> None:
    result = run("ga", ("secret", M, None, f'"{KEY_E1}"'))
    assert result.pairs == {0: "E1-01"}
    assert result.located == frozenset()


def test_F_G02_닻없는정답_줄로가를수없어도_줄맞춤() -> None:
    result = run("ga", ("source_map", M, 1, '"sourcesContent"'))
    assert result.pairs == {0: "E1-05"}
    assert result.located == frozenset()  # 닻이 없어 그 위치에서 '위치까지 맞음'이 되지 않음


def test_F_G02_other_분모밖() -> None:
    result = run("ga", GA_ROWS[6], ("other", J, 12, KEY_E1))
    assert result.verdicts == ("other", "other")
    assert result.pairs == {}
    assert result.decoy_misses == {}  # other는 미끼 헛짚음으로도 세지 않는다


def test_F_G02_미끼위치_헛짚음() -> None:
    assert run("ga", GA_ROWS[5]).decoy_misses == {0: "E1-D1"}
    # 미끼 맞춤은 범주를 보지 않는다
    assert run("ga", ("debug_flag", J, 21, "zz")).decoy_misses == {0: "E1-D1"}


def test_F_G02_결과하나가_정답둘_하나만() -> None:
    result = run("gb", ("admin_path", "a.js", 30, 'r("/admin/export") http://10.1.2.3/ops'))
    assert result.matched == 1
    assert result.pairs == {0: "N1-01"}  # 둘 다 닻 맞음, 줄 차이 0 < 1


def test_F_G02_최대짝이_욕심짝보다_많음() -> None:
    result = run(
        "gb",
        ("admin_path", "a.js", 30, 'r("/admin/export")'),
        ("admin_path", "a.js", 33, "route table"),
    )
    assert result.pairs == {0: "N1-01", 1: "N1-02"}
    assert result.located == frozenset({0})


def test_F_G02_결과차례바꿔도_같은짝() -> None:
    base = run("ga", *GA_ROWS)
    for order in (tuple(reversed(range(len(GA_ROWS)))), (5, 3, 1, 7, 0, 6, 2, 4)):
        result = run("ga", *(GA_ROWS[i] for i in order))
        assert sorted(result.pairs.values()) == sorted(base.pairs.values())
        assert (result.matched, result.duplicates, result.others) == (3, 1, 1)
        assert sorted(result.decoy_misses.values()) == ["E1-D1"]
        assert len(result.located) == len(base.located)
        # 맞은 결과의 내용(차례가 아닌)이 같다
        moved = {GA_ROWS[order[r]]: item for r, item in result.pairs.items()}
        assert moved == {GA_ROWS[r]: item for r, item in base.pairs.items()}


# --- 압축 번들 (줄로 가를 수 없는 위치) ---------------------------------------------------------


def n2_rows() -> list[tuple[tuple[str, str, int | None, str], list[str], dict[int, str], bool]]:
    """(결과, 판정, 미끼 헛짚음, 위치까지 맞음) — 기능명세 F-G02 압축 번들 여섯 줄."""
    return [
        (("secret", N2_FILE, 1, 'k:"YOUR_API_KEY"'), ["decoy"], {0: "N2-D1"}, False),
        (("secret", N2_FILE, None, 'k:"YOUR_API_KEY"'), ["decoy"], {0: "N2-D1"}, False),
        (("secret", N2_FILE, None, f'atob("{N2_B64}")'), ["match"], {}, False),
        (("secret", N2_FILE, None, N2_DECODED), ["match"], {}, False),
        (("secret", N2_FILE, 1, N2_DECODED), ["match"], {}, True),
        (("secret", N2_FILE, 1, "token"), ["wrong"], {}, False),
    ]


@pytest.mark.parametrize("file_lines", [1, 2])
def test_F_G02_압축번들_닻·풀어낸값으로만(file_lines: int) -> None:
    data = answers("n2")
    for group in ("items", "decoys"):
        entries = data[group]
        assert isinstance(entries, list)
        for entry in entries:
            assert isinstance(entry, dict)
            locations = entry["locations"]
            assert isinstance(locations, list)
            for location in locations:
                assert isinstance(location, dict)
                if location["file"] == N2_FILE:
                    location["file_lines"] = file_lines
    answer = sm.answer_key(data)
    for row, verdicts, decoys, located in n2_rows():
        result = sm.match_run(findings(row), answer)
        assert list(result.verdicts) == verdicts, row[3]
        assert result.decoy_misses == decoys
        assert result.located == (frozenset({0}) if located else frozenset())


def test_F_G02_압축번들_닻없는소스맵은_줄로() -> None:
    result = run("n2", ("source_map", "assets/m-9c1e.js.map", 1, "zz"))
    assert result.pairs == {0: "N2-02"}
    assert result.located == frozenset()


def five_line_key(category: str, line: int, anchor: str) -> sm.AnswerKey:
    location = sm.Location("b.js", line, line, 5)
    item = sm.Entry("B-01", frozenset({category}), (location,), anchor, None)
    return sm.AnswerKey((item,), ())


def test_F_G02_다섯줄파일_범위가덮으면_줄로안됨() -> None:
    covered = sm.match_run(
        findings(("secret", "b.js", 3, "zz")), five_line_key("secret", 3, "abcd1234")
    )
    assert covered.verdicts == ("wrong",)  # 1 ≤ 1, 5 ≥ 5 → 덮음
    split = sm.match_run(
        findings(("debug_flag", "b.js", 1, "zz")), five_line_key("debug_flag", 1, "dbgOn")
    )
    assert split.pairs == {0: "B-01"}  # 1 + 2 = 3 < 5 → 줄로 가를 수 있음
    assert split.located == frozenset({0})


# --- 정답지 ㉰ (위치 닻, CR-008) -------------------------------------------------------------


def test_F_G02_위치닻으로_맞음() -> None:
    hit = run("gc", ("secret", "assets/b-2.js", 1, 'k+"Wd93RtYb0"'))
    assert hit.pairs == {0: "N2-04"}
    assert hit.located == frozenset({0})
    no_line = run("gc", ("secret", "assets/b-2.js", None, 'k+"Wd93RtYb0"'))
    assert no_line.pairs == {0: "N2-04"}
    assert no_line.located == frozenset()
    off_line = run("gc", ("secret", "assets/b-2.js", 2, 'k+"Wd93RtYb0"'))
    assert off_line.pairs == {0: "N2-04"}
    assert off_line.located == frozenset()  # 줄 조건도 함께 건다(2 ∉ 1~1)
    joined = run("gc", ("secret", "assets/b-2.js", 1, "qorvo_7Hk2LmWd93RtYb0"))
    assert joined.pairs == {0: "N2-04"}
    assert joined.located == frozenset({0})


def test_F_G02_다른위치의_위치닻은_짝아님() -> None:
    result = run("gc", ("secret", "assets/a-1.js", 1, 'k+"Wd93RtYb0"'))
    assert result.verdicts == ("wrong",)
    assert result.decoy_misses == {}


def test_F_G02_미끼풀어낸값_헛짚음() -> None:
    result = run("gc", ("secret", "assets/a-1.js", None, 'color = "#2f6fb0"'))
    assert result.verdicts == ("decoy",)
    assert result.decoy_misses == {0: "N2-D3"}


def test_F_G02_위치닻끄면_다시채점() -> None:
    rules = sm.Rules(location_anchors=False)
    result = run("gc", ("secret", "assets/b-2.js", 1, 'k+"Wd93RtYb0"'), rules=rules)
    assert result.verdicts == ("wrong",)


def test_F_G02_줄허용T_바꿔다시채점() -> None:
    row = ("admin_path", J, 59, "zz")
    assert run("ga", row, rules=sm.Rules(tolerance=0)).verdicts == ("wrong",)
    assert run("ga", row, rules=sm.Rules(tolerance=5)).pairs == {0: "E1-03"}


# --- 짝짓기 차례가 명세 그대로인가 (작은 그래프 모두와 무작위) -----------------------------------


def literal_choose(
    edges: Sequence[tuple[tuple[int, float, int, str], int, int]], n_left: int, n_right: int
) -> dict[int, int]:
    """명세 F-G02 5를 글 그대로: 짝마다 '고른 짝 + 이 짝'으로 M을 이룰 수 있는지 다시 센다."""

    def max_size(fixed: dict[int, int]) -> int:
        used_l, used_r = set(fixed), set(fixed.values())
        rest = [(r, e) for _, r, e in edges if r not in used_l and e not in used_r]
        best = 0
        lefts = sorted({r for r, _ in rest})
        options = {r: [e for rr, e in rest if rr == r] for r in lefts}

        def go(i: int, taken: frozenset[int], count: int) -> None:
            nonlocal best
            best = max(best, count)
            if i == len(lefts) or count + len(lefts) - i <= best:
                return
            for e in options[lefts[i]]:
                if e not in taken:
                    go(i + 1, taken | {e}, count + 1)
            go(i + 1, taken, count)

        go(0, frozenset(), 0)
        return len(fixed) + best

    target = max_size({})
    chosen: dict[int, int] = {}
    for _, r, e in sorted(edges):
        if r in chosen or e in chosen.values():
            continue
        if max_size({**chosen, r: e}) == target:
            chosen[r] = e
    return chosen


def random_edges(
    rng: random.Random, n_left: int, n_right: int, density: float
) -> list[tuple[tuple[int, float, int, str], int, int]]:
    edges = []
    for r, e in itertools.product(range(n_left), range(n_right)):
        if rng.random() < density:
            k = (rng.randint(0, 1), float(rng.randint(0, 3)), r, f"I-{e:02d}")
            edges.append((k, r, e))
    return edges


def test_F_G02_빠른짝짓기가_명세차례와_같음() -> None:
    rng = random.Random(20261126)  # noqa: S311 — 시험 그래프를 고르는 것이다(암호용 아님)
    for _ in range(400):
        n_left, n_right = rng.randint(1, 6), rng.randint(1, 6)
        edges = random_edges(rng, n_left, n_right, rng.choice([0.2, 0.4, 0.7]))
        assert sm._choose_pairs(edges, n_left, n_right) == literal_choose(edges, n_left, n_right)


# --- 처리량 (보안규칙 5장: 입력 2·4배, 원문이 모두 다른 걸림 N 1만·2만) --------------------------


def elapsed(call: Callable[[], object]) -> float:
    gc.collect()
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def wide_case(n_items: int, n_findings: int) -> tuple[sm.AnswerKey, list[Finding]]:
    """한 줄 압축 파일 하나에 정답 n_items개(닻이 모두 다름, 한글 포함), 결과는 원문이 모두 다름.

    결과마다 정답 하나의 닻을 든다 — 걸림(후보 짝) 수가 결과 수와 같고, 같은 정답을 여러
    결과가 가리켜 중복·최대 짝 계산이 함께 돈다.
    """
    file = "assets/한글-묶음.js"
    items = tuple(
        sm.Entry(
            f"X-{i:05d}",
            frozenset({"secret"}),
            (sm.Location(file, 1, 1, 1, f"위치닻{i:06d}"),),
            f"닻값{i:06d}_키",
            None,
        )
        for i in range(n_items)
    )
    rows = [
        Finding(r, "secret", file, None, f"결과 {r:06d}: 닻값{r % n_items:06d}_키 근처")
        for r in range(n_findings)
    ]
    return sm.AnswerKey(items, ()), rows


@pytest.mark.parametrize(("n_items", "n_findings"), [(50, 10_000), (50, 20_000)])
def test_F_G02_처리량_걸림N_선형(n_items: int, n_findings: int) -> None:
    answer, rows = wide_case(n_items, n_findings)
    result = sm.match_run(rows, answer)
    assert result.matched == n_items
    assert result.duplicates == n_findings - n_items


def test_F_G02_처리량_결과수_4배에_4배쯤() -> None:
    small = wide_case(50, 2_500)
    large = wide_case(50, 10_000)
    t_small = elapsed(lambda: sm.match_run(small[1], small[0]))
    t_large = elapsed(lambda: sm.match_run(large[1], large[0]))
    assert t_large / max(t_small, 1e-3) < LINEAR_RATIO_LIMIT
