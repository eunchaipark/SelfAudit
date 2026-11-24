"""F-B07 심은 번들 전체 구성 검사와 CR-008 새 규칙 14~20 (기능명세 F-B07, 설계 8.4·8.8).

앞쪽은 저장소의 번들 여섯을 모아 센다(규칙 1·4·8·9·15). 뒤쪽은 규칙 14~20을 작은 번들
(tmp_path)로 하나씩 본다. 값은 모두 가짜다 — 서비스 꼴을 걸리게 하는 시험 값은 없다.
"""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import Mapping, Sequence

import pytest

from common.contracts import Json, read_json
from common.fingerprint import bundle_manifest_sha256
from sources.build_tools import fake
from sources.build_tools.verify import (
    DECOY_DISTANCE,
    REPO_ROOT,
    BundleReport,
    Problem,
    _check_distance,
    _entry,
    check_bundle,
    check_target,
    decoy_hiding_gaps,
    repo_target,
)
from tests.conftest import MakeBundle

BENCH = REPO_ROOT / "bench"
DIFFICULTIES = ("easy", "normal", "hard")
ALL_CATEGORIES = 8
# 검사 '실험자료'(ops/scripts/check_bench.py SKIP_DIRS)와 같게 건너뛰는 폴더
SKIP_DIRS = frozenset({".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"})
LF = chr(0x0A)
_NAMES = itertools.count()  # 한 시험 안에서 작은 번들을 여러 번 만들 때 폴더 이름

type Answers = dict[str, Json]


def _planted_ids() -> list[str]:
    targets = read_json(BENCH / "targets.json")
    assert isinstance(targets, dict) and isinstance(targets["targets"], list)
    return [
        str(t["id"])
        for t in targets["targets"]
        if isinstance(t, dict) and t.get("kind") == "planted"
    ]


def _reports() -> list[BundleReport]:
    return [check_target(repo_target(bundle_id)) for bundle_id in _planted_ids()]


# --- 번들 여섯 (규칙 1·4·8·9·15) -------------------------------------------------------------


def test_F_B07_심은번들_6개() -> None:
    reports = _reports()
    assert len(reports) == 6
    for report in reports:
        assert report.problems == (), (report.bundle_id, [str(p) for p in report.problems])


def test_F_B07_난이도마다_2개() -> None:
    difficulties = [str(report.difficulty) for report in _reports()]
    assert sorted(difficulties) == sorted(DIFFICULTIES * 2)


def test_F_B07_난이도마다_범주8개() -> None:
    by_difficulty: dict[str, set[str]] = {}
    for report in _reports():
        assert report.difficulty is not None
        assert len(report.categories) >= 6, report.bundle_id
        by_difficulty.setdefault(report.difficulty, set()).update(report.categories)
    assert {d: len(c) for d, c in by_difficulty.items()} == dict.fromkeys(DIFFICULTIES, 8)


def test_F_B07_정답지마다_지문이_번들과같음() -> None:
    for bundle_id in _planted_ids():
        answers = read_json(BENCH / "answers" / f"{bundle_id}.json")
        assert isinstance(answers, dict)
        assert answers["bundle_manifest_sha256"] == bundle_manifest_sha256(
            BENCH / "bundles" / bundle_id
        ), bundle_id
        record = read_json(BENCH / "sources" / bundle_id / "build.json")
        assert isinstance(record, dict)
        assert record["bundle_manifest_sha256"] == answers["bundle_manifest_sha256"], bundle_id


def test_F_B07_bench전체_서비스꼴키없음() -> None:
    """규칙 9: `bench/` 아래 글 파일에 서비스 꼴 키가 없다.

    검사 '실험자료'와 같은 꼴 목록·같은 건너뜀.
    """
    binary = fake.binary_suffixes()
    found: list[str] = []
    checked = 0
    for path in sorted(BENCH.rglob("*")):
        rel = path.relative_to(BENCH)
        if not path.is_file() or SKIP_DIRS.intersection(rel.parts) or path.suffix in binary:
            continue
        checked += 1
        text = path.read_bytes().decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            found += [f"{rel.as_posix()}:{lineno} {n}" for n in fake.service_shape_names(line)]
    assert checked > 100
    assert found == []


def test_F_B07_숨긴방법마다_같은방법미끼() -> None:
    """규칙 15 (F-B02 8): 난이도마다 정답이 쓰는 숨긴 방법(`none` 빼고)마다 그 방법을 거친 미끼."""
    reports = _reports()
    assert decoy_hiding_gaps(reports) == {}
    for report in reports:
        assert report.decoy_hidings, report.bundle_id  # 규칙 19: 미끼마다 hiding


def test_F_B07_숨긴방법마다_같은방법미끼_예시() -> None:
    """명세 예시: easy 둘의 정답이 plain·comment·config·none, 미끼는 plain·config뿐.

    → comment 빠짐.
    """
    one = BundleReport(
        "easy-1", "easy", (), (), frozenset(), frozenset({"plain", "none"}), frozenset({"plain"})
    )
    two = BundleReport(
        "easy-2",
        "easy",
        (),
        (),
        frozenset(),
        frozenset({"comment", "config"}),
        frozenset({"config"}),
    )
    assert decoy_hiding_gaps([one, two]) == {"easy": frozenset({"comment"})}


def test_F_B07_normal2_숨은키오스크모드_정답() -> None:
    """설계 8.8 7㉯: `?kiosk`로만 켜지는 숨은 모드는 정답 N2-10(hidden_route).

    normal-2 정답 10개.
    """
    answers = read_json(BENCH / "answers" / "normal-2.json")
    assert isinstance(answers, dict) and isinstance(answers["items"], list)
    items = {str(i["id"]): i for i in answers["items"] if isinstance(i, dict)}
    assert len(items) == 10
    kiosk = items["N2-10"]
    assert kiosk["categories"] == ["hidden_route"]
    assert kiosk["anchor"] == "kiosk"


# --- 작은 번들로 규칙 14~20 -------------------------------------------------------------------


def _loc(file: str, lines: int = 1, line: int = 1, anchor: str | None = None) -> dict[str, Json]:
    loc: dict[str, Json] = {"file": file, "line_start": line, "line_end": line, "file_lines": lines}
    if anchor is not None:
        loc["anchor"] = anchor
    return loc


def _item(
    entry_id: str,
    anchor: str | None,
    locations: Sequence[dict[str, Json]],
    hiding: str = "config",
    decoded: str | None = None,
    category: str = "secret",
) -> dict[str, Json]:
    return {
        "id": entry_id,
        "categories": [category],
        "difficulty": "normal",
        "hiding": hiding,
        "locations": list(locations),
        "anchor": anchor,
        "decoded_anchor": decoded,
        "planted": "가상",
        "why": "가상",
    }


def _decoy(
    entry_id: str,
    anchor: str | None,
    locations: Sequence[dict[str, Json]],
    hiding: str | None = "config",
    decoded: str | None = None,
) -> dict[str, Json]:
    decoy: dict[str, Json] = {"id": entry_id, "locations": list(locations), "anchor": anchor}
    if hiding is not None:
        decoy["hiding"] = hiding
    if decoded is not None:
        decoy["decoded_anchor"] = decoded
    decoy["why"] = "가상"
    return decoy


def _check(
    make_bundle: MakeBundle,
    files: Mapping[str, str],
    items: Sequence[dict[str, Json]],
    decoys: Sequence[dict[str, Json]] = (),
) -> set[tuple[str, str]]:
    """작은 번들의 문제 `(규칙, 자리)`. 개수·범주·방법(3·4·5)은 작은 번들이라 늘 모자라 뺀다."""
    data = {rel: text.encode("utf-8") for rel, text in files.items()}
    bundle = make_bundle(data, name=f"bundle-{next(_NAMES)}")
    answers: Answers = {
        "schema": "selfaudit-bench/answers@1",
        "bundle_id": "normal-9",
        "origin": "planted",
        "difficulty": "normal",
        "bundle_manifest_sha256": bundle_manifest_sha256(bundle),
        "complete": True,
        "items": list(items),
        "decoys": list(decoys),
    }
    problems = check_bundle(bundle, answers).problems
    return {(p.rule, p.where) for p in problems if p.rule not in {"3", "4", "5"}}


def test_F_B07_줄로못가르는위치_닻없으면_실패(make_bundle: MakeBundle) -> None:
    """규칙 14: 압축 파일(1~1줄, 2줄)에 정답 닻도 위치 닻도 없으면 실패, 위치 닻을 두면 통과."""
    files = {"a.js": "var k='q7Rk2Lm9';" + LF, "b.js": "send(k);" + LF + "//# x" + LF}
    bare = _item("N9-01", "q7Rk2Lm9", [_loc("a.js"), _loc("b.js", lines=2)])
    assert _check(make_bundle, files, [bare]) == {("14", "N9-01.locations[1]")}
    anchored = _item("N9-01", "q7Rk2Lm9", [_loc("a.js"), _loc("b.js", lines=2, anchor="send(k)")])
    assert _check(make_bundle, files, [anchored]) == set()


def test_F_B07_위치닻_다른파일에도나오면_실패(make_bundle: MakeBundle) -> None:
    """규칙 6 위치 닻 판: 그 위치 밖(정답의 다른 위치도)에 나오면 ㉯, 그 위치에 없으면 ㉮."""
    files = {"a.js": "var k='q7Rk2Lm9';send(k);" + LF, "b.js": "send(k);" + LF}
    item = _item("N9-01", "q7Rk2Lm9", [_loc("a.js"), _loc("b.js", anchor="send(k)")])
    assert _check(make_bundle, files, [item]) == {("6㉯", "N9-01.locations[1]")}
    missing = _item("N9-01", "q7Rk2Lm9", [_loc("a.js"), _loc("b.js", anchor="call(k)")])
    assert _check(make_bundle, files, [missing]) == {
        ("6㉮", "N9-01.locations[1]"),
        ("14", "N9-01.locations[1]"),  # 그 파일에 닻·위치 닻이 없다
    }


def test_F_B07_닻풀어낸값없는정답은_규칙14밖(make_bundle: MakeBundle) -> None:
    """명세 예시: 닻·풀어낸 값이 없는 source_map 정답은 줄 맞춤을 쓰므로 규칙 14 밖."""
    files = {"a.js.map": '{"version":3}' + LF}
    item = _item("N9-05", None, [_loc("a.js.map")], hiding="none", category="source_map")
    assert _check(make_bundle, files, [item]) == set()


def test_F_B07_줄로못가르는위치_닻64자넘으면_실패(make_bundle: MakeBundle) -> None:
    """규칙 16: 줄로 가를 수 없는 위치가 있으면 닻 65자 실패·64자 통과.

    120줄 파일 12줄이면 규칙 밖.
    """
    for length, expected in ((65, {("16", "N9-01.anchor")}), (64, set())):
        anchor = "k" + "7" * (length - 1)
        item = _item("N9-01", anchor, [_loc("a.js")])
        assert _check(make_bundle, {"a.js": f"var k='{anchor}';{LF}"}, [item]) == expected
    lines = [f"// {i}" for i in range(1, 121)]
    long_anchor = "k" + "7" * 69
    lines[11] = f"var k='{long_anchor}';"
    item = _item("E9-01", long_anchor, [_loc("a.js", lines=120, line=12)])
    assert _check(make_bundle, {"a.js": LF.join(lines) + LF}, [item]) == set()


def test_F_B07_줄로못가르는위치_풀어낸값·위치닻도_64자(make_bundle: MakeBundle) -> None:
    decoded = "v" * 65
    item = _item("N9-01", "q7Rk2Lm9", [_loc("a.js")], hiding="split", decoded=decoded)
    assert _check(make_bundle, {"a.js": "var k='q7Rk2Lm9';" + LF}, [item]) == {
        ("16", "N9-01.decoded_anchor")
    }
    long_loc = "w" * 65
    files = {"a.js": "var k='q7Rk2Lm9';" + LF, "b.js": long_loc + LF}
    item = _item("N9-01", "q7Rk2Lm9", [_loc("a.js"), _loc("b.js", anchor=long_loc)])
    assert _check(make_bundle, files, [item]) == {("16", "N9-01.locations[1].anchor")}


def _hex(n: int, seed: str) -> str:
    return (seed * n)[:n]


def test_F_B07_같은인코딩_미끼정답_길이비1_5넘으면_실패(make_bundle: MakeBundle) -> None:
    """규칙 17 (F-B02 9 예시): 16진 정답 32자 · 미끼 60자뿐 → 실패. 48자·44자 → 통과.
    정답 base64 52자 · 미끼 16진 76자뿐 → 규칙 밖(인코딩이 다름). 파일을 나눠 규칙 20을 피한다."""
    answer = _hex(32, "4a6b")
    for decoy_len, expected in ((60, {("17", "N9-01")}), (48, set()), (44, set())):
        decoy = _hex(decoy_len, "5c7d")
        files = {"a.js": f'h("{answer}");{LF}', "b.js": f'h("{decoy}");{LF}'}
        item = _item("N9-01", answer, [_loc("a.js")], hiding="encoded", decoded="x" * 16)
        trap = _decoy("N9-D1", decoy, [_loc("b.js")], hiding="encoded", decoded="y" * 16)
        assert _check(make_bundle, files, [item], [trap]) == expected, decoy_len
    base64_answer = "emVsdG9fYjBDNGZyWXp0NEJLT0JHUjBFT2NsaWVicHJwcERZTzg="
    # 76자 미끼는 64자를 넘어 줄로 가를 수 있는 위치(120줄 파일의 1줄)에 둔다(규칙 16 밖)
    files = {
        "a.js": f'atob("{base64_answer}");{LF}',
        "b.js": f'h("{_hex(76, "5c7d")}");{LF}' + "//" + LF * 119,
    }
    item = _item("N9-01", base64_answer, [_loc("a.js")], hiding="encoded", decoded="x" * 16)
    far = [_loc("b.js", lines=120)]
    trap = _decoy("N9-D1", _hex(76, "5c7d"), far, hiding="encoded", decoded="y" * 16)
    assert _check(make_bundle, files, [item], [trap]) == set()


def test_F_B07_같은인코딩_길이는_번들의_인코딩글전체(make_bundle: MakeBundle) -> None:
    """미끼 닻이 긴 base64 글의 앞 조각이어도 길이는 번들에 든 인코딩된 글 전체로 잰다."""
    answer = "a2V5LXZhbHVlLWZvci1jaGVjaw=="  # 28자
    long_decoy = "PHN2Zz48L3N2Zz4" + "A" * 85  # 100자, 닻은 앞 16자
    files = {"a.js": f'atob("{answer}");{LF}', "b.js": f'atob("{long_decoy}");{LF}'}
    item = _item("N9-01", answer, [_loc("a.js")], hiding="encoded", decoded="key-value-for-check")
    trap = _decoy("N9-D1", long_decoy[:16], [_loc("b.js")], hiding="encoded", decoded="<svg>")
    assert _check(make_bundle, files, [item], [trap]) == {("17", "N9-01")}


def _token(last: str) -> str:
    token = fake.make_token("normal-9", "N9-02", {"sub": "u-1", "iat": 1763600000})
    return token[:-1] + last


def test_F_B07_토큰끝글자J_실패(make_bundle: MakeBundle) -> None:
    """규칙 10 (F-B02 4ⓑ 예시): 서명 끝 글자 `J`(끝 2비트가 0이 아님) 실패, `8` 통과."""
    for last, expected in (("J", {("10", "N9-02.anchor")}), ("8", set())):
        token = _token(last)
        item = _item("N9-02", token, [_loc("a.js", lines=120, line=1)])
        files = {"a.js": f"var t='{token}';{LF}" + "//" + LF * 119}
        assert _check(make_bundle, files, [item]) == expected, last


def test_F_B07_예약이름_한쪽만_실패(make_bundle: MakeBundle) -> None:
    """규칙 18 (F-B02 6 예시): 미끼 주소에만 `.example` → 실패. 정답에도 쓰면 통과."""
    pad = "/" + "-" * DECOY_DISTANCE + "/"
    trap_url = "https://cdn.pagebird.example/covers/"
    files = {"a.js": f"var a='10.20.30.40';var p='{pad}';var c='{trap_url}';{LF}"}
    item = _item("N9-01", "10.20.30.40", [_loc("a.js")], category="internal_address")
    trap = _decoy("N9-D1", trap_url, [_loc("a.js")])
    assert _check(make_bundle, files, [item], [trap]) == {("18", "N9-D1")}
    files = {"a.js": f"var a='ops.intra.example';var p='{pad}';var c='{trap_url}';{LF}"}
    item = _item("N9-01", "ops.intra.example", [_loc("a.js")], category="internal_address")
    assert _check(make_bundle, files, [item], [trap]) == set()


def test_F_B07_미끼hiding_빠지면_실패(make_bundle: MakeBundle) -> None:
    """규칙 19: 심은 번들의 미끼에 hiding이 없으면 실패."""
    pad = "-" * DECOY_DISTANCE
    files = {"a.js": f"var k='q7Rk2Lm9';var p='{pad}';var d='YOUR_API_KEY';{LF}"}
    item = _item("N9-01", "q7Rk2Lm9", [_loc("a.js")])
    trap = _decoy("N9-D1", "YOUR_API_KEY", [_loc("a.js")], hiding=None)
    assert _check(make_bundle, files, [item], [trap]) == {("19", "N9-D1")}


def _distance_files(gap: int, decoy_first: bool = True) -> dict[str, str]:
    """미끼 닻 `#2f6fb0`(7자)와 정답 닻 `10.20.30.40:8080`(16자) 사이에 글 `gap`자."""
    left, right = (
        ("#2f6fb0", "10.20.30.40:8080") if decoy_first else ("10.20.30.40:8080", "#2f6fb0")
    )
    return {"a.js": left + "x" * gap + right + LF}


def _distance_entries() -> tuple[dict[str, Json], dict[str, Json]]:
    item = _item("N9-01", "10.20.30.40:8080", [_loc("a.js")], category="internal_address")
    trap = _decoy("N9-D1", "#2f6fb0", [_loc("a.js")])
    return item, trap


def test_F_B07_미끼닻_정답닻_300자안이면_실패(make_bundle: MakeBundle) -> None:
    """규칙 20 (설계 8.8 6 예시): 두 글을 덮는 구간 26자·300자 실패, 301자 통과.

    차례는 가리지 않는다.
    """
    item, trap = _distance_entries()
    example = {"a.js": '["#2f6fb0","10.20.30.40:8080"]' + LF}
    assert _check(make_bundle, example, [item], [trap]) == {("20", "N9-D1")}
    cases: tuple[tuple[int, bool, set[tuple[str, str]]], ...] = (
        (277, True, {("20", "N9-D1")}),
        (278, True, set()),
        (278, False, set()),
    )
    for gap, decoy_first, expected in cases:
        files = _distance_files(gap, decoy_first)
        assert _check(make_bundle, files, [item], [trap]) == expected, (gap, decoy_first)


def test_F_B07_미끼닻_정답닻_파일이다르면_규칙20밖(make_bundle: MakeBundle) -> None:
    files = {"a.js": "#2f6fb0" + LF, "b.js": "10.20.30.40:8080" + LF}
    item = _item("N9-01", "10.20.30.40:8080", [_loc("b.js")], category="internal_address")
    trap = _decoy("N9-D1", "#2f6fb0", [_loc("a.js")])
    assert _check(make_bundle, files, [item], [trap]) == set()


def test_F_B07_미끼위치닻_다른범주정답위치닻_가까우면_실패(make_bundle: MakeBundle) -> None:
    """규칙 20은 범주를 가리지 않고 위치 닻도 본다."""
    files = {
        "a.js": "var k='q7Rk2Lm9';" + LF,
        "b.js": "var d='Lm7q';" + LF,
        "c.js": "tenantAdmin;" + "y" * 10 + "paletteMain;" + LF,
    }
    item = _item(
        "N9-01",
        "q7Rk2Lm9",
        [_loc("a.js"), _loc("c.js", anchor="tenantAdmin")],
        category="admin_path",
    )
    trap = _decoy("N9-D1", "Lm7q", [_loc("b.js"), _loc("c.js", anchor="paletteMain")])
    assert _check(make_bundle, files, [item], [trap]) == {("20", "N9-D1")}


def test_F_B07_미끼거리_오류글에_닻값이_없음(make_bundle: MakeBundle) -> None:
    item, trap = _distance_entries()
    bundle = make_bundle({"a.js": b'["#2f6fb0","10.20.30.40:8080"]\n'})
    answers: Answers = {
        "schema": "selfaudit-bench/answers@1",
        "bundle_id": "normal-9",
        "origin": "planted",
        "difficulty": "normal",
        "bundle_manifest_sha256": bundle_manifest_sha256(bundle),
        "complete": True,
        "items": [item],
        "decoys": [trap],
    }
    text = " ".join(map(str, check_bundle(bundle, answers).problems))
    assert "#2f6fb0" not in text and "10.20.30.40" not in text
    assert "N9-D1" in text and "N9-01" in text


def _brute_distance(text: str, decoys: Sequence[str], answers: Sequence[str]) -> bool:
    """모든 짝을 직접 견준다(시험의 기준값). 300자 안 짝이 있으면 True."""

    def places(needle: str) -> list[int]:
        out, start = [], text.find(needle)
        while start >= 0:
            out.append(start)
            start = text.find(needle, start + 1)
        return out

    for d in decoys:
        for a in answers:
            for ds in places(d):
                for as_ in places(a):
                    span = max(ds + len(d), as_ + len(a)) - min(ds, as_)
                    if span <= DECOY_DISTANCE:
                        return True
    return False


def test_F_B07_미끼거리_마지막하나만견줘도_모든짝과같음() -> None:
    """규칙 20 셈(반대쪽 마지막 하나와만 견줌)이 모든 짝을 견준 것과 같은 답을 낸다 — 길이가 다른
    닻·겹쳐 나옴·품음을 섞은 글 200개로 견준다(시드 고정)."""
    import random

    rng = random.Random("F-B07/20")  # noqa: S311 — 시험 글을 고르는 것이다(암호용 아님)
    for _ in range(200):
        decoy = "".join(rng.choice("ab") for _ in range(rng.randint(2, 6)))
        answer = "".join(rng.choice("ab") for _ in range(rng.randint(2, 9)))
        text = "".join(rng.choice("abx") for _ in range(rng.randint(1, 900)))
        entries = [
            _entry({"id": "A", "locations": [], "anchor": answer}, decoy=False),
            _entry({"id": "D", "locations": [], "anchor": decoy}, decoy=True),
        ]
        out: list[Problem] = []
        _check_distance(entries, {"a.js": text.encode()}, out)
        assert bool(out) == _brute_distance(text, [decoy], [answer]), (decoy, answer, len(text))


@pytest.mark.parametrize("count", [10_000, 20_000])
def test_F_B07_미끼거리_나온곳N개_시간(count: int) -> None:
    """보안규칙 5장: 닻이 N곳(1만·2만)에 나와도 흘려 보내며 센다 — 시간이 N에 비례(2초 안)."""
    text = ("q" * 400).join(["#2f6fb0"] * count) + ("q" * 400) + "10.20.30.40:8080"
    entries = [
        _entry({"id": "A", "locations": [], "anchor": "10.20.30.40:8080"}, decoy=False),
        _entry({"id": "D", "locations": [], "anchor": "#2f6fb0"}, decoy=True),
    ]
    out: list[Problem] = []
    started = time.perf_counter()
    _check_distance(entries, {"a.js": text.encode()}, out)
    assert out == []
    assert time.perf_counter() - started < 2


def test_F_B07_규칙20_상한은_결과계약_evidence와같음() -> None:
    schema = json.loads((BENCH / "contracts" / "findings.schema.json").read_text(encoding="utf-8"))
    evidence = schema["properties"]["findings"]["items"]["properties"]["evidence"]
    assert evidence["maxLength"] == DECOY_DISTANCE
