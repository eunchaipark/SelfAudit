"""F-B03 정답지 만들기 명령 (`build_tools.locate`, T22 반려 1 3 — 번들을 고쳐도 명령 하나로 다시).

원본·결과물·정답지는 tmp_path 아래(저장소 파일을 바꾸지 않는다). 값은 모두 가짜다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from sources.build_tools import fake
from sources.build_tools.locate import ANSWERS_IN, LocateError, write_answers
from sources.build_tools.verify import check_bundle
from tests.bundles.conftest import Dirs, WriteSource, make_plan

LF = chr(0x0A)
APP = LF.join(
    [
        "// 작은 앱",
        'const KEY = "{{v:X1-01}}";',
        'const PARTS = ["{{v:X1-02|split:2:0}}", "{{v:X1-02|split:2:1}}"];',
        'const DOC = "YOUR_API_KEY";',
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
        "anchor": "YOUR_API_KEY",
        "at": [
            {"file": "assets/app.js", "marker": "const DOC"},
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
