"""계약 검증기 시험 (실험구조 2.2·2.3·2.4·2.9·2.10)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from common.contracts import (
    CONTRACT_NAMES,
    ContractError,
    ContractJsonError,
    ContractViolationError,
    Json,
    load_schema,
    read_contract,
    read_json,
    validate_contract,
)
from common.schema import MAX_DEPTH, MAX_ERRORS, SchemaUnsupportedError, check_schema, validate
from tests.common.examples import (
    FAKE_ANCHOR,
    answers_example,
    findings_example,
    first_item,
    first_location,
    run_example,
    targets_example,
)

MAX_LINE = 10_000_000  # 실험구조 2.9 줄 번호 상한


def test_common_정답지_2_2예시_통과() -> None:
    assert validate_contract("answers", answers_example()) == []


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (3, [ContractError("$.items[0].anchor", "minLength 4")]),
        (4, []),
        (200, []),
        (201, [ContractError("$.items[0].anchor", "maxLength 200")]),
    ],
)
def test_common_닻_3자·201자_거절(length: int, expected: list[ContractError]) -> None:
    data = answers_example()
    first_item(data)["anchor"] = "a" * length
    assert validate_contract("answers", data) == expected


def test_common_닻_없음_null_통과() -> None:
    data = answers_example()
    first_item(data)["anchor"] = None
    assert validate_contract("answers", data) == []


@pytest.mark.parametrize(
    ("field", "ok", "bad"),
    [
        ("bundle_id", "a" * 40, "a" * 41),  # 2.2 대상 ID 40자
    ],
)
def test_common_대상ID_40자_통과·41자_거절(field: str, ok: str, bad: str) -> None:
    data = answers_example()
    data[field] = ok
    assert validate_contract("answers", data) == []
    data[field] = bad
    assert validate_contract("answers", data) == [ContractError(f"$.{field}", "pattern")]


def test_common_정답ID_30자_통과·31자_거절() -> None:
    data = answers_example()
    first_item(data)["id"] = "E" * 30
    assert validate_contract("answers", data) == []
    first_item(data)["id"] = "E" * 31
    assert validate_contract("answers", data) == [ContractError("$.items[0].id", "pattern")]


@pytest.mark.parametrize(
    ("field", "ok", "bad"),
    [("run_id", "a" * 80, "a" * 81), ("target_id", "a" * 40, "a" * 41)],
)
def test_common_실행ID_80자·대상ID_40자_경계(field: str, ok: str, bad: str) -> None:
    data = run_example()
    data[field] = ok
    assert validate_contract("run", data) == []
    data[field] = bad
    assert validate_contract("run", data) == [ContractError(f"$.{field}", "pattern")]


def test_common_줄번호_상한() -> None:
    data = answers_example()
    location = first_location(first_item(data))
    location.update(line_start=MAX_LINE, line_end=MAX_LINE, file_lines=MAX_LINE)
    assert validate_contract("answers", data) == []
    location["file_lines"] = MAX_LINE + 1
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0].file_lines", f"maximum {MAX_LINE}")
    ]
    findings = findings_example()
    rows = findings["findings"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    rows[0]["line"] = MAX_LINE + 1
    assert validate_contract("findings", findings) == [
        ContractError("$.findings[0].line", f"maximum {MAX_LINE}")
    ]


def test_common_범주_9개_거절() -> None:
    data = answers_example()
    first_item(data)["categories"] = [
        "secret", "source_map", "internal_address", "admin_path", "hidden_route",
        "client_authz", "debug_flag", "vulnerable_library", "secret",
    ]  # fmt: skip
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].categories", "maxItems 8")
    ]


def test_common_계약4개_키워드_모두_지원() -> None:
    for name in CONTRACT_NAMES:
        check_schema(load_schema(name))


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "maxProperties": 3},
        {"type": "string", "format": "email"},
        {"properties": {"a": {"oneOf": [{"type": "string"}]}}},
        {"$ref": "other.json#/x"},
        {"type": "string", "pattern": "^\\s+$"},
        {"type": "string", "maxLength": 300.0},
        {"type": "array", "minItems": -1},
        {"type": "string", "minLength": True},
        {"type": "int"},
        {"type": []},
        {"enum": []},
        {"required": "a"},
        {"required": ["a", "a"]},
        {"items": [{"type": "string"}]},
        {"additionalProperties": "no"},
        {"maximum": "3"},
        {"$defs": {"a": {"$ref": "#/$defs/b"}, "b": {"$ref": "#/$defs/a"}}, "$ref": "#/$defs/a"},
        {"$defs": {"a": {"$ref": "#/$defs/a"}}},
    ],
)
def test_common_모르는·잘못된_키워드_멈춤(schema: dict[str, Json]) -> None:
    with pytest.raises(SchemaUnsupportedError):
        check_schema(schema)


def test_common_결과_예시_통과·101개_거절() -> None:
    assert validate_contract("findings", findings_example(100)) == []
    many = findings_example(101)
    rows = many["findings"]
    assert isinstance(rows, list)
    rows[5] = {"bad": True}  # 상한을 넘은 목록의 원소는 보지 않는다
    assert validate_contract("findings", many) == [ContractError("$.findings", "maxItems 100")]


def test_common_실행원자료_예시_통과() -> None:
    assert validate_contract("run", run_example()) == []


def test_common_실행원자료_새칸_꼴() -> None:
    data = run_example()
    settings = data["settings"]
    assert isinstance(settings, dict)
    settings["deny_rule_forms"] = ["//C:/", "//C:/"]
    data["transcript"] = {"stored": "elsewhere", "bytes": 1, "sha256": "x"}
    assert validate_contract("run", data) == [
        ContractError("$.settings.deny_rule_forms", "uniqueItems"),
        ContractError("$.transcript.stored", "enum"),
        ContractError("$.transcript.sha256", "pattern"),
    ]


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-22T00:00:00",  # 시간대 없음
        "2026-11-22 00:00:00Z",  # 날짜와 시각 사이가 T가 아님
        "2026-02-30T00:00:00Z",  # 없는 날
        "2026-11-22T23:59:60Z",  # 윤초
        "2026-11-22T00:00:00+24:00",
        "2026-11-22T00:00:00Z\n",
    ],
)
def test_common_시각꼴_거절(value: str) -> None:
    data = run_example()
    data["started_at"] = value
    assert validate_contract("run", data) == [ContractError("$.started_at", "format date-time")]


def test_common_정수는_JSON뜻() -> None:
    schema: dict[str, Json] = {"type": "integer", "minimum": 1}
    assert validate(1.0, schema) == []
    assert validate(True, schema) == [ContractError("$", "type integer")]
    assert validate(1.5, schema) == [ContractError("$", "type integer")]
    assert validate(0, schema) == [ContractError("$", "minimum 1")]


def test_common_같음은_JSON뜻() -> None:
    assert validate(True, {"enum": [1]}) == [ContractError("$", "enum")]
    assert validate(1.0, {"const": 1}) == []
    assert validate([1, 1.0], {"uniqueItems": True}) == [ContractError("$", "uniqueItems")]
    assert validate([1, True], {"uniqueItems": True}) == []
    assert validate([{"a": [1]}, {"a": [1.0]}], {"uniqueItems": True}) == [
        ContractError("$", "uniqueItems")
    ]


def test_common_겹침검사_선형() -> None:
    values: list[Json] = [f"v{i}" for i in range(20000)]
    start = time.perf_counter()
    assert validate(values, {"uniqueItems": True}) == []
    assert time.perf_counter() - start < 1.0  # N²이면 2억 번 비교로 수십 초


def test_common_오류글에_값과_낯선키_없음() -> None:
    data = findings_example()
    rows = data["findings"]
    assert isinstance(rows, list)
    first = rows[0]
    assert isinstance(first, dict)
    first["evidence"] = FAKE_ANCHOR * 20
    first[FAKE_ANCHOR + "!"] = 1
    first["extra_key"] = 1
    errors = validate_contract("findings", data)
    assert errors == [
        ContractError("$.findings[0].evidence", "maxLength 300"),
        ContractError("$.findings[0].<키>", "additionalProperties false"),
        ContractError("$.findings[0].extra_key", "additionalProperties false"),
    ]
    assert all(FAKE_ANCHOR not in str(e) for e in errors)


def test_common_오류목록_100곳에서_멈춤() -> None:
    schema: dict[str, Json] = {"type": "array", "items": {"type": "string"}}
    errors = validate(list(range(500)), schema)
    assert len(errors) == MAX_ERRORS + 1
    assert errors[-1] == ContractError("$", f"오류 {MAX_ERRORS}곳에서 멈춤, 나머지 생략")


def test_common_너무_깊은값_검사안함() -> None:
    deep: Json = "x"
    for _ in range(MAX_DEPTH):
        deep = [deep]
    assert validate(deep, {}) == [ContractError("$", f"depth {MAX_DEPTH}")]


def test_common_필수칸_없음() -> None:
    data = answers_example()
    del data["decoys"]
    assert validate_contract("answers", data) == [ContractError("$", "required decoys")]


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1, "a": 2}',
        '{"a": NaN}',
        '{"a": Infinity}',
        '{"a": -Infinity}',
        '{"a": 1e999}',
        '{"a": ' + "1" * 5000 + "}",  # Python 정수 글 길이 한도를 넘는다
        "[" * 100000 + "]" * 100000,
        "[" * (MAX_DEPTH + 1) + "]" * (MAX_DEPTH + 1),
        "{",
    ],
)
def test_common_JSON_같은키·NaN·넘침·깊음_거절(tmp_path: Path, text: str) -> None:
    path = tmp_path / "x.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractJsonError):
        read_json(path)


def test_common_JSON_크기상한·없는파일(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text('{"a": "0123456789"}', encoding="utf-8")
    assert read_json(path, max_bytes=19) == {"a": "0123456789"}
    with pytest.raises(ContractJsonError, match="바이트를 넘음"):
        read_json(path, max_bytes=18)
    with pytest.raises(ContractJsonError, match="읽을 수 없음"):
        read_json(tmp_path / "없음.json")


def test_common_계약읽기_어긋나면_오류목록(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text('{"findings": [], "notes": 3}', encoding="utf-8")
    with pytest.raises(ContractViolationError) as caught:
        read_contract("findings", path)
    assert caught.value.errors == (ContractError("$.notes", "type string"),)


def test_common_대상목록_예시_통과() -> None:
    assert validate_contract("targets", targets_example()) == []
