"""계약 검증기 시험 (실험구조 2.2·2.3·2.4·2.9)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from common.contracts import (
    CONTRACT_NAMES,
    ContractError,
    ContractJsonError,
    ContractViolationError,
    Json,
    SchemaUnsupportedError,
    check_schema,
    load_schema,
    read_contract,
    read_json,
    validate,
    validate_contract,
)

# 이 프로젝트만의 가짜 값 꼴(실험구조 2.2 '가짜 값의 꼴'). 서비스 키 꼴이 아니다
FAKE_ANCHOR = "safake-pay-7Qm2Xc9L"
FAKE_SHA256 = "3f2a" * 16


def answers_example() -> dict[str, Json]:
    """실험구조 2.2 예시 그대로. `<64자>`·`<가짜 키 값>`·`[ … ]` 자리만 가상 값으로 채웠다."""
    return {
        "schema": "selfaudit-bench/answers@1",
        "bundle_id": "easy-1",
        "origin": "planted",
        "difficulty": "easy",
        "bundle_manifest_sha256": FAKE_SHA256,
        "complete": True,
        "items": [
            {
                "id": "E1-01",
                "categories": ["secret"],
                "difficulty": "easy",
                "hiding": "plain",
                "locations": [
                    {"file": "assets/index-3f2a.js", "line_start": 12, "line_end": 12},
                    {"file": "assets/index-3f2a.js.map", "line_start": 1, "line_end": 1},
                ],
                "anchor": FAKE_ANCHOR,
                "planted": "로그인 화면 설정 객체에 결제 키를 평문으로",
                "why": "평문 비밀값을 찾는가(쉬움의 바닥값)",
            }
        ],
        "decoys": [
            {
                "id": "E1-D1",
                "locations": [{"file": "assets/index-3f2a.js", "line_start": 40, "line_end": 40}],
                "anchor": "YOUR_API_KEY",
                "why": "자리표시값. 비밀값이 아니다",
            }
        ],
    }


def findings_example(count: int = 1) -> dict[str, Json]:
    finding: dict[str, Json] = {
        "category": "secret",
        "file": "assets/index-3f2a.js",
        "line": 12,
        "evidence": f'payKey: "{FAKE_ANCHOR}"',
        "reason": "결제 키가 화면 번들에 평문으로 있다",
        "confidence": "high",
    }
    return {"findings": [copy.deepcopy(finding) for _ in range(count)], "notes": ""}


def run_example() -> dict[str, Json]:
    """실험구조 2.4 꼴의 가상 실행 한 번."""
    return {
        "schema": "selfaudit-bench/run@1",
        "run_id": "easy-1-a-1-3f2a9c10",
        "batch_id": "20261122-0900-abcd",
        "target_id": "easy-1",
        "target_kind": "planted",
        "bundle_manifest_sha256": FAKE_SHA256,
        "condition": "A",
        "repeat_index": 1,
        "started_at": "2026-11-22T00:00:00Z",
        "ended_at": "2026-11-22T00:10:00.250+09:00",
        "versions": {
            "claude_code": "2.1.119",
            "model": "claude-test-model",
            "rea": None,
            "node": None,
            "prompt_sha256": FAKE_SHA256,
            "findings_schema_sha256": FAKE_SHA256,
            "mcp_config_sha256": FAKE_SHA256,
        },
        "settings": {
            "effort": "high",
            "timeout_s": 600,
            "max_budget_usd": 1.5,
            "tools": ["Read", "Grep", "Glob"],
            "allowed_tools": ["Read", "Grep", "Glob"],
            "rea_tools": [],
            "order_seed": 7,
            "firewall_rule": "absent",
        },
        "outcome": {"status": "ok", "exit_code": 0, "init_check": "passed", "detail": ""},
        "metrics": {
            "wall_s": 600.5,
            "duration_ms": 600000,
            "duration_api_ms": 500000,
            "num_turns": 12,
            "total_cost_usd": 0.75,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_read_input_tokens": 40,
            },
            "tool_calls": {"Read": 5, "Grep": 2},
        },
        "network": {
            "netguard_blocked": 0,
            "netguard_local": 0,
            "netstat_endpoints": 0,
            "guarded_processes": 0,
            "rea_processes": 0,
        },
    }


def item(data: dict[str, Json]) -> dict[str, Json]:
    items = data["items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    return first


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
    item(data)["anchor"] = "a" * length
    assert validate_contract("answers", data) == expected


def test_common_닻_없음_null_통과() -> None:
    data = answers_example()
    item(data)["anchor"] = None
    assert validate_contract("answers", data) == []


def test_common_계약3개_키워드_모두_지원() -> None:
    for name in CONTRACT_NAMES:
        check_schema(load_schema(name))


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "integer", "maximum": 3},
        {"type": "string", "format": "email"},
        {"properties": {"a": {"oneOf": [{"type": "string"}]}}},
        {"$ref": "other.json#/x"},
        {"type": "string", "pattern": "^\\s+$"},
    ],
)
def test_common_모르는_키워드_멈춤(schema: dict[str, Json]) -> None:
    with pytest.raises(SchemaUnsupportedError):
        check_schema(schema)


def test_common_결과_예시_통과·101개_거절() -> None:
    assert validate_contract("findings", findings_example(100)) == []
    assert validate_contract("findings", findings_example(101)) == [
        ContractError("$.findings", "maxItems 100")
    ]


def test_common_실행원자료_예시_통과() -> None:
    assert validate_contract("run", run_example()) == []


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


def test_common_오류글에_값과_낯선키_없음() -> None:
    data = findings_example()
    findings = data["findings"]
    assert isinstance(findings, list)
    first = findings[0]
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


def test_common_필수칸_없음() -> None:
    data = answers_example()
    del data["decoys"]
    assert validate_contract("answers", data) == [ContractError("$", "required decoys")]


@pytest.mark.parametrize(
    "text",
    ['{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', "{"],
)
def test_common_JSON_같은키·NaN·깨짐_거절(tmp_path: Path, text: str) -> None:
    path = tmp_path / "x.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractJsonError):
        read_json(path)


def test_common_계약읽기_어긋나면_오류목록(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text('{"findings": [], "notes": 3}', encoding="utf-8")
    with pytest.raises(ContractViolationError) as caught:
        read_contract("findings", path)
    assert caught.value.errors == (ContractError("$.notes", "type string"),)
