"""시험에 쓰는 가상 계약 값 (실험구조 2.2~2.4·2.10 예시 꼴). 값은 모두 가상이다."""

from __future__ import annotations

import copy

from common.contracts import Json

# 이 프로젝트만의 가짜 값 꼴(실험구조 2.2 '가짜 값의 꼴', D-043 ㉯). 서비스 키 꼴이 아니다
FAKE_ANCHOR = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
FAKE_SHA256 = "3f2a" * 16


def answers_example() -> dict[str, Json]:
    """실험구조 2.2 예시. `<64자>`·`<가짜 키 값>`·`[ … ]` 자리와 2.10 칸을 가상 값으로."""
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
                    {
                        "file": "assets/index-3f2a.js",
                        "line_start": 12,
                        "line_end": 12,
                        "file_lines": 120,
                    },
                    {
                        "file": "assets/index-3f2a.js.map",
                        "line_start": 1,
                        "line_end": 1,
                        "file_lines": 1,
                    },
                ],
                "anchor": FAKE_ANCHOR,
                "decoded_anchor": None,
                "planted": "로그인 화면 설정 객체에 결제 키를 평문으로",
                "why": "평문 비밀값을 찾는가(쉬움의 바닥값)",
            }
        ],
        "decoys": [
            {
                "id": "E1-D1",
                "locations": [
                    {
                        "file": "assets/index-3f2a.js",
                        "line_start": 40,
                        "line_end": 40,
                        "file_lines": 120,
                    }
                ],
                "anchor": "YOUR_API_KEY",
                "why": "자리표시값. 비밀값이 아니다",
            }
        ],
    }


def first_item(data: dict[str, Json]) -> dict[str, Json]:
    items = data["items"]
    assert isinstance(items, list)
    first = items[0]
    assert isinstance(first, dict)
    return first


def first_location(entry: dict[str, Json]) -> dict[str, Json]:
    locations = entry["locations"]
    assert isinstance(locations, list)
    first = locations[0]
    assert isinstance(first, dict)
    return first


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
    """실험구조 2.4·2.10 꼴의 가상 실행 한 번."""
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
            "plan_sha256": FAKE_SHA256,
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
            "deny_rule_forms": ["//C:/"],
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
        "transcript": {"stored": "results", "bytes": 2097152, "sha256": FAKE_SHA256},
    }


def targets_example() -> dict[str, Json]:
    """F-B05 예시 꼴: 저장소 안 목록."""
    return {
        "schema": "selfaudit-bench/targets@1",
        "targets": [
            {
                "id": "easy-1",
                "kind": "planted",
                "bundle": "bench/bundles/easy-1",
                "answers": "bench/answers/easy-1.json",
            },
            {
                "id": "juice-shop-17",
                "kind": "practice",
                "bundle": ".tools/juice-shop/frontend/dist",
                "answers": "bench/answers/juice-shop-17.json",
            },
        ],
    }
