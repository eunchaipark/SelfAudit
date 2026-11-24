"""F-B03 정답지 만들기 명령 (`build_tools.locate`, T22 반려 1 3 — 번들을 고쳐도 명령 하나로 다시).

원본·결과물·정답지는 tmp_path 아래(저장소 파일을 바꾸지 않는다). 값은 모두 가짜다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from common.contracts import Json, read_contract
from sources.build_tools import fake, locate
from sources.build_tools.locate import ANSWERS_IN, LocateError, write_answers
from sources.build_tools.verify import check_bundle
from tests.bundles.conftest import Dirs, WriteSource, make_plan

LF = chr(0x0A)
APP = LF.join(
    [
        "// 작은 앱",
        'const KEY = "{{v:X1-01}}";',
        'const PARTS = ["{{v:X1-02|split:2:0}}", "{{v:X1-02|split:2:1}}"];',
        # 미끼는 정답 닻에서 300자 넘게 떨어진다(F-B07 20) — 같은 줄 앞에 빈 글을 둔다
        f'const PAD = "{"-" * 320}", DOC = "YOUR_API_KEY";',
        "",
    ]
)
VALUES: dict[str, Json] = {
    "X1-01": {"form": "key", "prefix": "zelto_"},
    "X1-02": {"form": "password"},
}


def _spec(**overrides: Json) -> dict[str, Json]:
    item: dict[str, Json] = {
        "id": "X1-01",
        "categories": ["secret"],
        "hiding": "plain",
        "anchor": {"value": "X1-01"},
        "decoded_anchor": None,
        "at": [
            {"file": "assets/app.js", "marker": "const KEY"},
            {"file": "assets/app.js", "map": True},
        ],
        "planted": "가짜(생성)",
        "why": "가상",
    }
    split: dict[str, Json] = {
        "id": "X1-02",
        "categories": ["secret"],
        "hiding": "split",
        "anchor": {"value": "X1-02", "chain": "split:2:1"},
        "decoded_anchor": {"value": "X1-02"},
        "at": [
            {"file": "assets/app.js", "marker": "const PARTS"},
            {"file": "assets/app.js", "map": True},
        ],
        "planted": "가짜(생성)",
        "why": "가상",
    }
    decoy: dict[str, Json] = {
        "id": "X1-D1",
        "hiding": "plain",
        "anchor": "YOUR_API_KEY",
        "at": [
            {"file": "assets/app.js", "marker": "DOC = "},
            {"file": "assets/app.js", "map": True},
        ],
        "why": "자리표시값",
    }
    spec: dict[str, Json] = {
        "schema": "selfaudit-bench/answers-in@1",
        "bundle_id": "normal-9",
        "origin": "planted",
        "difficulty": "normal",
        "items": [item, split],
        "decoys": [decoy],
    }
    spec.update(overrides)
    return spec


def _source(write_source: WriteSource, spec: dict[str, Json]) -> Path:
    plan = make_plan(
        "normal-9",
        values=VALUES,
        hash_names=["assets/app.js"],
        sourcemaps=["assets/app.js"],
        sourcemap_content=True,
    )
    root = write_source("normal-9", plan, {"assets/app.js": APP})
    (root / ANSWERS_IN).write_bytes(json.dumps(spec, ensure_ascii=False).encode("utf-8"))
    return root


def test_F_B03_정답지명령_줄표식과_맵으로_위치(write_source: WriteSource, dirs: Dirs) -> None:
    _source(write_source, _spec())
    path, result = write_answers(
        "normal-9", dirs.sources, dirs.bundles, dirs.bundles.parent / "ans"
    )
    answers = read_contract("answers", path)
    js = result.files["assets/app.js"]
    items = answers["items"]
    assert isinstance(items, list) and isinstance(items[0], dict) and isinstance(items[1], dict)
    assert items[0]["locations"] == [
        {"file": js, "line_start": 2, "line_end": 2, "file_lines": 5},
        {"file": f"{js}.map", "line_start": 1, "line_end": 1, "file_lines": 1},
    ]
    key = fake.make_key("normal-9", "X1-01", "zelto_")
    assert items[0]["anchor"] == key
    password = fake.make_password("normal-9", "X1-02")
    assert items[1]["anchor"] == fake.split_value(password, 2)[1]
    assert items[1]["decoded_anchor"] == password
    assert answers["bundle_manifest_sha256"] == result.bundle_manifest_sha256
    assert answers["complete"] is True
    rules = {p.rule for p in check_bundle(result.bundle_dir, answers).problems}
    assert rules <= {"3", "4", "5"}  # 작은 시험 번들이라 개수·범주·방법만 모자람


def test_F_B03_정답지명령_다시돌려도_같은바이트(write_source: WriteSource, dirs: Dirs) -> None:
    _source(write_source, _spec())
    out = dirs.bundles.parent / "ans"
    first, _ = write_answers("normal-9", dirs.sources, dirs.bundles, out)
    data = first.read_bytes()
    second, _ = write_answers("normal-9", dirs.sources, dirs.bundles, out)
    assert second.read_bytes() == data


@pytest.mark.parametrize(("marker", "count"), [("const", 3), ("no such text", 0)])
def test_F_B03_줄표식이_한줄이아니면_멈춤(
    marker: str, count: int, write_source: WriteSource, dirs: Dirs
) -> None:
    spec = _spec()
    items = spec["items"]
    assert isinstance(items, list) and isinstance(items[0], dict)
    items[0]["at"] = [{"file": "assets/app.js", "marker": marker}]
    _source(write_source, spec)
    with pytest.raises(LocateError, match=f"{count}줄"):
        write_answers("normal-9", dirs.sources, dirs.bundles, dirs.bundles.parent / "ans")


def test_F_B03_정답지명령_오류글에_값없음(write_source: WriteSource, dirs: Dirs) -> None:
    spec = _spec()
    items = spec["items"]
    assert isinstance(items, list) and isinstance(items[0], dict)
    key = fake.make_key("normal-9", "X1-01", "zelto_")
    items[0]["at"] = [
        {"file": "assets/app.js", "marker": key[:12]},
        {"file": "nope.js", "map": True},
    ]
    _source(write_source, spec)
    with pytest.raises(LocateError) as caught:
        write_answers("normal-9", dirs.sources, dirs.bundles, dirs.bundles.parent / "ans")
    assert key[:12] not in str(caught.value)
    assert "X1-01" in str(caught.value)


# --- 64자 앞 조각 (F-B03 5, 설계 8.8 2) -------------------------------------------------------

TOKEN_HEAD = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"  # JWT 머리 36자(토큰마다 같다)


def _short_entry(
    entry_id: str,
    anchor: str | None,
    decoded: str | None = None,
    file: str = "a.js",
    lines: int = 1,
    loc_anchor: str | None = None,
) -> dict[str, Json]:
    loc: dict[str, Json] = {"file": file, "line_start": 1, "line_end": 1, "file_lines": lines}
    if loc_anchor is not None:
        loc["anchor"] = loc_anchor
    return {"id": entry_id, "locations": [loc], "anchor": anchor, "decoded_anchor": decoded}


def _shortened(entries: list[dict[str, Json]], texts: dict[str, bytes]) -> list[tuple[Json, Json]]:
    answers: dict[str, Json] = {"items": list(entries), "decoys": []}
    locate._shorten(answers, texts)
    return [(e["anchor"], e["decoded_anchor"]) for e in entries]


def test_F_B03_64자넘는닻_앞16자로_고유() -> None:
    """예시: easy-1 E1-02 토큰 147자, 위치 맵 1~1줄 → 번들에 토큰이 하나라 앞 16자."""
    token = TOKEN_HEAD + "." + "b" * 66 + "." + "c" * 43
    item = _short_entry("E1-02", token, file="a.js.map")
    assert _shortened([item], {"a.js.map": token.encode()}) == [(token[:16], None)]


def test_F_B03_머리가같은_토큰둘이면_37자부터() -> None:
    """예시: 같은 번들에 토큰 둘, 머리 36자가 같음.

    16~36자 조각은 다른 토큰에도 나옴 → 37자 이상.
    """
    one = TOKEN_HEAD + ".eyJzdWIiOiJ1LTEifQ." + "c" * 43
    two = TOKEN_HEAD + ".eyJzdWIiOiJ1LTIifQ." + "d" * 43
    texts = {"a.js": one.encode(), "b.js": two.encode()}
    first = _short_entry("N9-01", one)
    second = _short_entry("N9-02", two, file="b.js")
    (a1, _), (a2, _) = _shortened([first, second], texts)
    assert isinstance(a1, str) and isinstance(a2, str)
    assert len(a1) > len(TOKEN_HEAD) and one.startswith(a1) and a1 not in two
    assert len(a2) > len(TOKEN_HEAD) and two.startswith(a2) and a2 not in one


def test_F_B03_줄로가를수있는위치뿐이면_64자규칙밖() -> None:
    """예시: 닻 70자, 위치가 모두 줄로 가를 수 있음(120줄 파일의 12줄) → 그대로."""
    anchor = "k" * 70
    item = _short_entry("E9-01", anchor, lines=120)
    locations = item["locations"]
    assert isinstance(locations, list) and isinstance(locations[0], dict)
    locations[0].update({"line_start": 12, "line_end": 12})
    assert _shortened([item], {"a.js": anchor.encode()}) == [(anchor, None)]


def test_F_B03_풀어낸값_152자면_앞16자·40자면_전체() -> None:
    """예시: 풀어낸 값 152자, 앞 16자가 번들·다른 닻과 겹치지 않음 → 앞 16자 / 40자 → 값 전체."""
    long_value = "Q" + "w" * 151
    short_value = "R" + "x" * 39
    texts = {"a.js": b"piece-one;piece-two"}
    one = _short_entry("H9-02", "piece-one", decoded=long_value)
    two = _short_entry("H9-03", "piece-two", decoded=short_value)
    assert _shortened([one, two], texts) == [
        ("piece-one", long_value[:16]),
        ("piece-two", short_value),
    ]


def test_F_B03_풀어낸값_앞조각이_번들에있으면_더길게() -> None:
    """예시: 풀어낸 값 80자, 첫 조각 18자가 번들에 그대로 → 16·17·18자는 안 됨(그 정답 위치
    안이어도) → 19자."""
    first_piece = "M" + "n" * 17
    value = first_piece + "p" * 62
    item = _short_entry("N9-01", first_piece, decoded=value)
    assert _shortened([item], {"a.js": first_piece.encode()}) == [(first_piece, value[:19])]


def test_F_B03_풀어낸값_앞조각이_다른풀어낸값안에들면_더길게() -> None:
    """예시: 16자 조각은 번들에 없지만 다른 정답의 풀어낸 값(40자) 안에 듦 → 17자."""
    value = "T" + "u" * 79
    other = "zz" + value[:16] + "y" * 22  # 40자, 앞 16자 조각을 품는다
    item = _short_entry("N9-01", "keep-a", decoded=value)
    neighbour = _short_entry("N9-02", "keep-b", decoded=other)
    result = _shortened([item, neighbour], {"a.js": b"keep-a keep-b"})
    assert result[0] == ("keep-a", value[:17])


def test_F_B03_풀어낸값_64자안에_없으면_멈춤() -> None:
    """예시: 16~19자 조각은 번들에 있고, 20자부터는 다른 정답의 위치 닻(4자)을 품음 → 멈춤."""
    value = "V" * 16 + "Wxyz" + "a" * 60  # 20자 조각의 끝 4자가 다른 정답의 위치 닻
    texts = {"a.js": value[:19].encode(), "b.js": b"Wxyz", "c.js": b"other"}
    item = _short_entry("N9-01", value[:19], decoded=value)
    other = _short_entry("N9-02", "other", file="b.js", loc_anchor="Wxyz")
    with pytest.raises(LocateError, match="N9-01") as err:
        _shortened([item, other], texts)
    assert value not in str(err.value)


def test_F_B03_정답지명령_위치닻·맵이름·미끼칸(write_source: WriteSource, dirs: Dirs) -> None:
    """F-B03 7·12: 위치 닻(글·가짜 값 꼴), 맵 파일 이름 닻(`map_of`),
    미끼 `hiding`·`decoded_anchor`."""
    spec = _spec()
    items, decoys = spec["items"], spec["decoys"]
    assert isinstance(items, list) and isinstance(decoys, list)
    split, decoy = items[1], decoys[0]
    assert isinstance(split, dict) and isinstance(decoy, dict)
    split["at"] = [
        {"file": "assets/app.js", "marker": "const PARTS"},
        {"file": "assets/app.js", "map": True, "anchor": {"value": "X1-02", "chain": "split:2:0"}},
    ]
    items.append(
        {
            "id": "X1-03",
            "categories": ["source_map"],
            "hiding": "none",
            "anchor": {"map_of": "assets/app.js"},
            "decoded_anchor": None,
            "at": [
                {"file": "assets/app.js", "marker": "sourceMappingURL="},
                {"file": "assets/app.js", "map": True, "anchor": "sourcesContent"},
            ],
            "planted": "가상",
            "why": "가상",
        }
    )
    decoy.update({"hiding": "encoded", "decoded_anchor": "plain words"})
    _source(write_source, spec)
    path, result = write_answers("normal-9", dirs.sources, dirs.bundles, dirs.bundles.parent / "a")
    answers = read_contract("answers", path)
    js = result.files["assets/app.js"]
    entries: list[Any] = [*answers["items"], *answers["decoys"]]  # type: ignore[misc]
    got: dict[str, Any] = {str(e["id"]): e for e in entries}
    password = fake.make_password("normal-9", "X1-02")
    assert got["X1-02"]["locations"][1]["anchor"] == fake.split_value(password, 2)[0]
    assert got["X1-03"]["anchor"] == f"{Path(js).name}.map"
    assert got["X1-03"]["locations"][1]["anchor"] == "sourcesContent"
    assert got["X1-D1"]["hiding"] == "encoded"
    assert got["X1-D1"]["decoded_anchor"] == "plain words"
    assert list(got["X1-D1"]) == ["id", "locations", "anchor", "hiding", "decoded_anchor", "why"]
