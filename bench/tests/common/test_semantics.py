"""정답지·대상 목록 뜻 규칙 시험 (실험구조 2.10)."""

from __future__ import annotations

import pytest

from common.contracts import REPO_ROOT, ContractError, Json, validate_contract
from tests.common.examples import answers_example, first_item, first_location, targets_example


def test_common_정답지_줄범위_거꾸로·파일줄수_넘음() -> None:
    data = answers_example()
    location = first_location(first_item(data))
    location.update(line_start=13, line_end=12)
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0]", "line_end >= line_start")
    ]
    location.update(line_start=12, line_end=121)
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0]", "line_end <= file_lines")
    ]


def test_common_정답지_ID_겹침() -> None:
    data = answers_example()
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    decoys[0]["id"] = "E1-01"
    assert validate_contract("answers", data) == [ContractError("$.decoys[0].id", "id 겹침")]


@pytest.mark.parametrize(
    ("origin", "difficulty", "complete", "expected"),
    [
        ("planted", "easy", True, []),
        ("practice", "mixed", False, []),
        ("planted", "mixed", True, ["$.difficulty"]),
        ("practice", "easy", False, ["$.difficulty"]),
        ("practice", "mixed", True, ["$.complete"]),
        ("planted", "hard", False, ["$.complete"]),
    ],
)
def test_common_정답지_종류와_난이도·complete(
    origin: str, difficulty: str, complete: bool, expected: list[str]
) -> None:
    data = answers_example()
    data.update(origin=origin, difficulty=difficulty, complete=complete)
    assert [e.where for e in validate_contract("answers", data)] == expected


@pytest.mark.parametrize(
    ("hiding", "decoded", "expected"),
    [
        ("encoded", "zelto_fakeDecodedValue01", []),
        ("split", "zelto_fakeDecodedValue01", []),
        ("plain", "zelto_fakeDecodedValue01", ["split·encoded·obfuscated만"]),
        ("encoded", None, []),
        ("encoded", "SAME", ["anchor와 같음"]),
    ],
)
def test_common_정답지_풀어낸값(hiding: str, decoded: str | None, expected: list[str]) -> None:
    data = answers_example()
    item = first_item(data)
    item["hiding"] = hiding
    item["decoded_anchor"] = item["anchor"] if decoded == "SAME" else decoded
    assert [e.rule for e in validate_contract("answers", data)] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PAY_TAIL_piece_01", []),
        (None, []),
        (
            "ITEM_ANCHOR",
            [("$.items[0].locations[0].anchor", "정답·미끼의 anchor·decoded_anchor와 같음")],
        ),
        (
            "DECODED",
            [("$.items[0].locations[0].anchor", "정답·미끼의 anchor·decoded_anchor와 같음")],
        ),
        ("abc", [("$.items[0].locations[0].anchor", "minLength 4")]),
    ],
)
def test_common_정답지_위치닻(value: str | None, expected: list[tuple[str, str]]) -> None:
    """실험구조 8.4 2: 위치마다 선택 칸 anchor, 그 정답의 닻·풀어낸 값과 달라야 한다."""
    data = answers_example()
    item = first_item(data)
    item.update(hiding="encoded", decoded_anchor="zelto_fakeDecodedValue01")
    location = first_location(item)
    location["anchor"] = {"ITEM_ANCHOR": item["anchor"], "DECODED": item["decoded_anchor"]}.get(
        value or "", value
    )
    assert [(e.where, e.rule) for e in validate_contract("answers", data)] == expected


def test_common_정답지_위치닻_미끼도() -> None:
    data = answers_example()
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    locations = decoys[0]["locations"]
    assert isinstance(locations, list) and isinstance(locations[0], dict)
    locations[0]["anchor"] = "cover_piece_only_here"
    assert validate_contract("answers", data) == []
    locations[0]["anchor"] = decoys[0]["anchor"]
    assert [e.where for e in validate_contract("answers", data)] == [
        "$.decoys[0].locations[0].anchor"
    ]


@pytest.mark.parametrize(
    ("hiding", "decoded", "expected"),
    [
        ("encoded", "Lobby kiosk: tap a room", []),
        ("split", "Lobby kiosk: tap a room", []),
        (None, None, []),
        ("comment", None, []),
        (None, "Lobby kiosk: tap a room", ["split·encoded·obfuscated만"]),
        ("plain", "Lobby kiosk: tap a room", ["split·encoded·obfuscated만"]),
        ("encoded", "SAME", ["anchor와 같음"]),
        ("hidden", None, ["enum"]),
    ],
)
def test_common_정답지_미끼_hiding·풀어낸값(
    hiding: str | None, decoded: str | None, expected: list[str]
) -> None:
    """실험구조 8.4 3·6: 미끼의 선택 칸 hiding·decoded_anchor, 뜻 규칙은 정답과 같다."""
    data = answers_example()
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    decoy = decoys[0]
    if hiding is not None:
        decoy["hiding"] = hiding
    if decoded is not None:
        decoy["decoded_anchor"] = decoy["anchor"] if decoded == "SAME" else decoded
    assert [e.rule for e in validate_contract("answers", data)] == expected


def test_common_대상목록_ID겹침·경로꼴() -> None:
    data = targets_example()
    rows = data["targets"]
    assert isinstance(rows, list)
    rows.append(
        {"id": "easy-1", "kind": "planted", "bundle": "../x", "answers": "bench/answers/x.json"}
    )
    rows.append(
        {
            "id": "juice-shop-18",
            "kind": "practice",
            "bundle": ".tools/juice-shop/frontend/dist",
            "answers": "bench/answers/juice-shop-18.json",
        }
    )
    assert validate_contract("targets", data) == [
        ContractError("$.targets[2].id", "id 겹침"),
        ContractError("$.targets[2].bundle", "bench/bundles/<id>"),
        ContractError("$.targets[2].answers", "bench/answers/<id>.json"),
        ContractError("$.targets[3].bundle", "bench/bundles/<id>"),
    ]


BS = chr(92)
INSIDE_REPO = str(REPO_ROOT / "bench" / "bundles" / "blog")
SNEAK_IN = str(REPO_ROOT.parent / "zz") + BS + ".." + BS + REPO_ROOT.name + BS + "bench"


@pytest.mark.parametrize(
    ("bundle", "answers", "expected"),
    [
        ("C:\\Users\\fake\\AppData\\Local\\SelfAudit-private\\bundles\\blog", None, []),
        ("D:/private/blog", "D:/private/answers/blog.json", []),
        ("bundles/blog", None, ["$.targets[0].bundle"]),
        ("C:\\fake\\blog", "answers/blog.json", ["$.targets[0].answers"]),
        (BS * 2 + "server" + BS + "share" + BS + "blog", None, ["$.targets[0].bundle"]),  # UNC
        (BS * 2 + "?" + BS + "C:" + BS + "fake" + BS + "blog", None, ["$.targets[0].bundle"]),
        (BS * 2 + "." + BS + "C:" + BS + "fake" + BS + "blog", None, ["$.targets[0].bundle"]),
        ("C:fake\\blog", None, ["$.targets[0].bundle"]),  # 드라이브 상대
        (INSIDE_REPO, None, ["$.targets[0].bundle"]),  # 저장소 안
        (INSIDE_REPO + (BS + "..") * 4 + BS + "x", None, []),  # 풀면 저장소 밖
        (SNEAK_IN, None, ["$.targets[0].bundle"]),  # 글로는 밖, 풀면 저장소 안
    ],
)
def test_common_대상목록_내앱은_저장소밖_드라이브경로(
    bundle: str, answers: str | None, expected: list[str]
) -> None:
    entry: dict[str, Json] = {
        "id": "mine-blog",
        "kind": "mine",
        "bundle": bundle,
        "answers": answers,
    }
    data: dict[str, Json] = {"schema": "selfaudit-bench/targets@1", "targets": [entry]}
    assert [e.where for e in validate_contract("targets", data)] == expected
