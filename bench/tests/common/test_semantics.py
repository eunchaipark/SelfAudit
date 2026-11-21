"""정답지·대상 목록 뜻 규칙 시험 (실험구조 2.10)."""

from __future__ import annotations

import pytest

from common.contracts import ContractError, Json, validate_contract
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


def test_common_대상목록_ID겹침·경로꼴() -> None:
    data = targets_example()
    rows = data["targets"]
    assert isinstance(rows, list)
    rows.append(
        {"id": "easy-1", "kind": "planted", "bundle": "../x", "answers": "bench/answers/x.json"}
    )
    assert validate_contract("targets", data) == [
        ContractError("$.targets[2].id", "id 겹침"),
        ContractError("$.targets[2].bundle", "저장소 기준 상대 경로(2.2 꼴)"),
        ContractError("$.targets[2].answers", "bench/answers/<id>.json"),
    ]


@pytest.mark.parametrize(
    ("bundle", "answers", "expected"),
    [
        ("C:\\Users\\fake\\AppData\\Local\\SelfAudit-private\\bundles\\blog", None, []),
        ("bundles/blog", None, ["$.targets[0].bundle"]),
        ("C:\\fake\\blog", "answers/blog.json", ["$.targets[0].answers"]),
    ],
)
def test_common_대상목록_내앱은_절대경로(
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
