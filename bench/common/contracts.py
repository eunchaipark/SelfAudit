"""계약 읽기·검증: `bench/contracts/*.schema.json` (실험구조 2.2~2.4·2.10, 정한 것과 근거는 2.9).

`validate_contract`는 계약(스키마)을 본 뒤, 스키마로 쓸 수 없는 뜻 규칙(정답지·대상 목록)까지 본다.
오류 글에는 값을 싣지 않는다(위치와 규칙만).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Final, Literal

from common.schema import (
    ContractError,
    Json,
    SchemaUnsupportedError,
    check_schema,
    is_too_deep,
    validate,
)

__all__ = [
    "CONTRACTS_DIR",
    "CONTRACT_NAMES",
    "MAX_JSON_BYTES",
    "ContractError",
    "ContractJsonError",
    "ContractName",
    "ContractViolationError",
    "Json",
    "SchemaUnsupportedError",
    "check_answers_semantics",
    "check_targets_semantics",
    "load_schema",
    "read_contract",
    "read_json",
    "validate_contract",
]

type ContractName = Literal["answers", "findings", "run", "targets"]

CONTRACT_NAMES: Final[tuple[ContractName, ...]] = ("answers", "findings", "run", "targets")
CONTRACTS_DIR: Final = Path(__file__).resolve().parents[1] / "contracts"
# 계약 파일 하나의 크기 상한. 가장 큰 결과(100개 × 칸 상한 1,100자 × UTF-8 4바이트 + notes)가
# 약 0.45MB라 그 9배쯤의 울타리다. 대화 기록(jsonl)은 이 함수로 읽지 않는다
MAX_JSON_BYTES: Final = 4 * 1024 * 1024
_ERRORS_IN_MESSAGE: Final = 20

_HIDDEN_KINDS: Final = frozenset({"split", "encoded", "obfuscated"})
_REPO_KINDS: Final = frozenset({"planted", "practice"})
_ANSWERS_DIR: Final = "bench/answers"
_BUNDLES_DIR: Final = "bench/bundles"
_DRIVE: Final = re.compile("[A-Za-z]:")
REPO_ROOT: Final = CONTRACTS_DIR.parents[1]


class ContractJsonError(ValueError):
    """JSON으로 읽을 수 없다(없음·너무 큼·깨짐·같은 키·NaN·너무 깊음). 값은 싣지 않는다."""


class ContractViolationError(ValueError):
    """`read_contract`가 계약에 어긋난 파일을 만났다. `errors`에 어긋난 곳이 모두 있다."""

    def __init__(self, path: Path, errors: list[ContractError]) -> None:
        self.path = path
        self.errors = tuple(errors)
        shown = "; ".join(map(str, errors[:_ERRORS_IN_MESSAGE]))
        more = len(errors) - _ERRORS_IN_MESSAGE
        tail = f" … 외 {more}곳" if more > 0 else ""
        super().__init__(f"{path.name}: 계약에 어긋남 {len(errors)}곳 — {shown}{tail}")


# --- 읽기 ------------------------------------------------------------------------------------


def read_json(path: Path, max_bytes: int = MAX_JSON_BYTES) -> Json:
    """JSON 파일 하나를 엄격하게 읽는다(2.9): 크기 상한, UTF-8, 같은 키 두 번·NaN·Infinity·
    넘치는 수(`1e999`)·너무 긴 정수·MAX_DEPTH보다 깊은 값은 거절한다."""
    try:
        with path.open("rb") as f:
            data = f.read(max_bytes + 1)
    except OSError as e:
        raise ContractJsonError(f"{path.name}: 읽을 수 없음 ({type(e).__name__})") from None
    if len(data) > max_bytes:
        raise ContractJsonError(f"{path.name}: {max_bytes}바이트를 넘음")
    try:
        value: Json = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_no_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as e:
        # ValueError: 깨진 JSON·UTF-8 아님·너무 긴 정수. RecursionError: 아주 깊은 중첩
        raise ContractJsonError(
            f"{path.name}: JSON으로 읽을 수 없음 ({type(e).__name__})"
        ) from None
    if is_too_deep(value):
        raise ContractJsonError(f"{path.name}: 값이 너무 깊음")
    return value


def _unique_keys(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    out: dict[str, Json] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("같은 키가 두 번 있다")
        out[key] = value
    return out


def _no_constant(_name: str) -> Json:
    raise ValueError("NaN·Infinity는 JSON 값이 아니다")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("float 범위를 넘는 수")
    return value


def load_schema(name: ContractName) -> dict[str, Json]:
    """계약 하나를 읽고, 이 검증기가 다 아는 키워드만 바르게 쓰는지 확인한다."""
    schema = read_json(CONTRACTS_DIR / f"{name}.schema.json")
    if not isinstance(schema, dict):
        raise SchemaUnsupportedError(f"{name}: 계약 맨 위가 객체가 아님")
    check_schema(schema)
    return schema


def validate_contract(name: ContractName, instance: Json) -> list[ContractError]:
    """`instance`가 계약 `name`에 맞는지. 맞으면 빈 목록, 아니면 어긋난 곳(차례는 늘 같다).

    스키마에 맞을 때만 뜻 규칙(`answers`·`targets`)을 이어서 본다.
    """
    errors = validate(instance, load_schema(name))
    if errors or not isinstance(instance, dict):
        return errors
    if name == "answers":
        return check_answers_semantics(instance)
    if name == "targets":
        return check_targets_semantics(instance)
    return []


def read_contract(name: ContractName, path: Path) -> dict[str, Json]:
    """파일을 읽어 계약으로 검증한다. 어긋나면 `ContractViolationError`(오류 목록 포함)."""
    value = read_json(path)
    errors = validate_contract(name, value)
    if errors:
        raise ContractViolationError(path, errors)
    assert isinstance(value, dict)  # 네 계약 모두 맨 위가 type object라 검증을 지나면 객체다
    return value


# --- 뜻 규칙 (스키마에 맞은 값만 받는다) ---------------------------------------------------------


def check_answers_semantics(answers: Mapping[str, Json]) -> list[ContractError]:
    """정답지 뜻 규칙(2.10): 줄 범위, ID 고유, 종류와 난이도·complete, 풀어낸 값."""
    errors: list[ContractError] = []
    _check_origin(answers, errors)
    seen: set[str] = set()
    for group in ("items", "decoys"):
        for i, entry in enumerate(_objects(answers.get(group))):
            where = f"$.{group}[{i}]"
            entry_id = entry.get("id")
            if isinstance(entry_id, str):
                if entry_id in seen:
                    errors.append(ContractError(f"{where}.id", "id 겹침"))
                seen.add(entry_id)
            for j, location in enumerate(_objects(entry.get("locations"))):
                _check_location(location, f"{where}.locations[{j}]", errors)
            if group == "items":
                _check_decoded(entry, where, errors)
    return errors


def _check_origin(answers: Mapping[str, Json], errors: list[ContractError]) -> None:
    planted = answers.get("origin") == "planted"
    if (answers.get("difficulty") == "mixed") == planted:
        errors.append(ContractError("$.difficulty", "planted는 easy·normal·hard, practice는 mixed"))
    if answers.get("complete") is not planted:
        errors.append(ContractError("$.complete", "planted는 true, practice는 false"))


def _check_location(location: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    start, end, lines = (location.get(k) for k in ("line_start", "line_end", "file_lines"))
    if not (isinstance(start, int | float) and isinstance(end, int | float)):
        return
    if end < start:
        errors.append(ContractError(where, "line_end >= line_start"))
    if isinstance(lines, int | float) and end > lines:
        errors.append(ContractError(where, "line_end <= file_lines"))


def _check_decoded(item: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    decoded = item.get("decoded_anchor")
    if decoded is None:
        return
    if item.get("hiding") not in _HIDDEN_KINDS:
        errors.append(ContractError(f"{where}.decoded_anchor", "split·encoded·obfuscated만"))
    if decoded == item.get("anchor"):
        errors.append(ContractError(f"{where}.decoded_anchor", "anchor와 같음"))


def check_targets_semantics(
    targets: Mapping[str, Json], repo_root: Path = REPO_ROOT
) -> list[ContractError]:
    """대상 목록 뜻 규칙(2.9·2.10, F-B05): ID 고유, 저장소 대상은 `bench/bundles/<id>`·
    `bench/answers/<id>.json`, 내 앱은 드라이브 절대 경로이고 풀어 본 뒤에도 저장소 밖."""
    errors: list[ContractError] = []
    seen: set[str] = set()
    for i, entry in enumerate(_objects(targets.get("targets"))):
        where = f"$.targets[{i}]"
        target_id = entry.get("id")
        if isinstance(target_id, str):
            if target_id in seen:
                errors.append(ContractError(f"{where}.id", "id 겹침"))
            seen.add(target_id)
        if entry.get("kind") in _REPO_KINDS:
            _check_repo_target(entry, where, errors)
        else:
            _check_mine_target(entry, where, repo_root, errors)
    return errors


def _check_repo_target(entry: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    target_id = entry.get("id")
    if entry.get("bundle") != f"{_BUNDLES_DIR}/{target_id}":
        errors.append(ContractError(f"{where}.bundle", "bench/bundles/<id>"))
    if entry.get("answers") != f"{_ANSWERS_DIR}/{target_id}.json":
        errors.append(ContractError(f"{where}.answers", "bench/answers/<id>.json"))


def _check_mine_target(
    entry: Mapping[str, Json], where: str, repo_root: Path, errors: list[ContractError]
) -> None:
    bundle, answers = entry.get("bundle"), entry.get("answers")
    if not (isinstance(bundle, str) and _is_outside_drive_path(bundle, repo_root)):
        errors.append(ContractError(f"{where}.bundle", "mine은 저장소 밖 드라이브 절대 경로"))
    if answers is not None and not (
        isinstance(answers, str) and _is_outside_drive_path(answers, repo_root)
    ):
        errors.append(
            ContractError(f"{where}.answers", "mine은 null 또는 저장소 밖 드라이브 절대 경로")
        )


def _is_outside_drive_path(path: str, repo_root: Path) -> bool:
    """`C:\\…` 꼴만(UNC `\\\\server`·`\\\\?\\`·`\\\\.\\` 거절), 그리고 풀어 본 뒤 저장소 밖."""
    pure = PureWindowsPath(path)
    if not (pure.is_absolute() and _DRIVE.fullmatch(pure.drive)):
        return False
    resolved = Path(path).resolve()
    return not resolved.is_relative_to(repo_root.resolve())


def _objects(value: Json) -> list[dict[str, Json]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []
