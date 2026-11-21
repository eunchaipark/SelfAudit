"""계약 읽기·검증: `bench/contracts/*.schema.json` (실험구조 2.2~2.4, 범위와 근거는 2.9).

JSON Schema 2020-12 가운데 세 계약이 쓰는 키워드만 검사한다. 모르는 키워드는 계약을 읽을 때 멈춘다.
오류 글에는 값을 싣지 않는다 — 결과·정답지에는 대상 안의 글(비밀값일 수 있다)이 그대로 있다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Literal

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
type Schema = Mapping[str, Json]
type ContractName = Literal["answers", "findings", "run"]

CONTRACT_NAMES: Final[tuple[ContractName, ...]] = ("answers", "findings", "run")
CONTRACTS_DIR: Final = Path(__file__).resolve().parents[1] / "contracts"

# 설명뿐인 키워드: 값 검사에 쓰지 않는다
_ANNOTATIONS: Final = frozenset({"$schema", "$id", "title", "description", "$defs"})
_CHECKS: Final = frozenset({
    "type", "enum", "const", "properties", "required", "additionalProperties", "items",
    "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "pattern",
    "minimum", "exclusiveMinimum", "format", "$ref",
})  # fmt: skip
_FORMATS: Final = frozenset({"date-time"})
_TYPES: Final = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})
_REF_PREFIX: Final = "#/$defs/"
# 오류 글에 실어도 되는 키 이름 (그 밖은 결과를 낸 쪽이 정한 글이라 싣지 않는다)
_SAFE_KEY: Final = re.compile(r"[A-Za-z0-9_]{1,40}")
_HIDDEN_KEY: Final = "<키>"

# ECMA-262 뜻 (2.9): `.`은 줄 끝 글자를 받지 않고, `$`는 글 끝에서만
_LINE_TERMINATORS: Final = chr(0x0A) + chr(0x0D) + chr(0x2028) + chr(0x2029)
_ECMA_DOT: Final = "[^" + _LINE_TERMINATORS + "]"
_ECMA_CLASS_ESCAPES: Final = {"d": "0-9", "w": "A-Za-z0-9_"}
_ECMA_ESCAPES: Final = {"d": "[0-9]", "D": "[^0-9]", "w": "[A-Za-z0-9_]", "W": "[^A-Za-z0-9_]"}
_PLAIN_LETTER_ESCAPES: Final = frozenset("nrt")

# RFC 3339 date-time. 시간대는 꼭 있어야 한다
_DATE_TIME: Final = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?"
    r"(?:([Zz])|([+-])([0-9]{2}):([0-9]{2}))"
)
_MAX_OFFSET_HOURS: Final = 23
_MAX_OFFSET_MINUTES: Final = 59


class SchemaUnsupportedError(ValueError):
    """계약이 이 검증기가 모르는 키워드·꼴을 쓴다. 계약이나 검증기를 고친다(설계)."""


class ContractJsonError(ValueError):
    """JSON으로 읽을 수 없다(깨짐, 같은 키 두 번, NaN·Infinity). 글에 값은 없다."""


@dataclass(frozen=True)
class ContractError:
    """계약에 어긋난 곳 하나. `where`는 `$.items[0].anchor` 꼴, `rule`은 걸린 키워드와 기준."""

    where: str
    rule: str

    def __str__(self) -> str:
        return f"{self.where}: {self.rule}"


class ContractViolationError(ValueError):
    """`read_contract`가 계약에 어긋난 파일을 만났다. `errors`에 어긋난 곳이 모두 있다."""

    def __init__(self, path: Path, errors: list[ContractError]) -> None:
        self.path = path
        self.errors = tuple(errors)
        super().__init__(
            f"{path.name}: 계약에 어긋남 {len(errors)}곳 — " + "; ".join(map(str, errors))
        )


def read_json(path: Path) -> Json:
    """JSON 파일 하나를 읽는다. 같은 키 두 번·NaN·Infinity는 거절한다(2.9)."""
    try:
        text = path.read_text(encoding="utf-8")
        value: Json = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_no_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ContractJsonError(
            f"{path.name}: JSON으로 읽을 수 없음 ({type(e).__name__})"
        ) from None
    return value


def _unique_keys(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    out: dict[str, Json] = {}
    for key, value in pairs:
        if key in out:
            raise json.JSONDecodeError("같은 키가 두 번 있다", "", 0)
        out[key] = value
    return out


def _no_constant(_name: str) -> Json:
    raise json.JSONDecodeError("NaN·Infinity는 JSON 값이 아니다", "", 0)


def load_schema(name: ContractName) -> dict[str, Json]:
    """계약 하나를 읽고, 이 검증기가 다 아는 키워드만 쓰는지 확인한다."""
    schema = read_json(CONTRACTS_DIR / f"{name}.schema.json")
    if not isinstance(schema, dict):
        raise SchemaUnsupportedError(f"{name}: 계약 맨 위가 객체가 아님")
    check_schema(schema)
    return schema


def check_schema(schema: Schema) -> None:
    """계약 전체(쓰이지 않는 갈래 포함)를 훑어 모르는 키워드·꼴이면 멈춘다."""
    for where, node in _subschemas(schema, "#"):
        unknown = set(node) - _ANNOTATIONS - _CHECKS
        if unknown:
            raise SchemaUnsupportedError(f"{where}: 모르는 키워드 {sorted(unknown)}")
        types = node.get("type", [])
        for name in types if isinstance(types, list) else [types]:
            if name not in _TYPES:
                raise SchemaUnsupportedError(f"{where}: 모르는 type {name!r}")
        if "items" in node and not isinstance(node["items"], dict):
            raise SchemaUnsupportedError(f"{where}: items는 스키마 하나만 다룬다")
        fmt = node.get("format")
        if fmt is not None and fmt not in _FORMATS:
            raise SchemaUnsupportedError(f"{where}: 모르는 format {fmt!r}")
        ref = node.get("$ref")
        if ref is not None:
            _resolve_ref(schema, ref)
        pattern = node.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise SchemaUnsupportedError(f"{where}: pattern이 글이 아님")
            _ecma_regex(pattern)


def _subschemas(node: Schema, where: str) -> Iterator[tuple[str, Schema]]:
    yield where, node
    children: list[tuple[str, Json]] = []
    for key in ("properties", "$defs"):
        group = node.get(key)
        if isinstance(group, dict):
            children += [(f"{where}/{key}/{k}", v) for k, v in group.items()]
    for key in ("items", "additionalProperties"):
        children.append((f"{where}/{key}", node.get(key)))
    for child_where, child in children:
        if isinstance(child, dict):
            yield from _subschemas(child, child_where)


def validate_contract(name: ContractName, instance: Json) -> list[ContractError]:
    """`instance`가 계약 `name`에 맞는지. 맞으면 빈 목록, 아니면 어긋난 곳 모두(차례는 늘 같다)."""
    return validate(instance, load_schema(name))


def read_contract(name: ContractName, path: Path) -> dict[str, Json]:
    """파일을 읽어 계약으로 검증한다. 어긋나면 `ContractViolationError`(오류 목록 포함)."""
    value = read_json(path)
    errors = validate_contract(name, value)
    if errors:
        raise ContractViolationError(path, errors)
    assert isinstance(value, dict)  # 세 계약 모두 맨 위가 type object라 검증을 지나면 객체다
    return value


def validate(instance: Json, schema: Schema, root: Schema | None = None) -> list[ContractError]:
    """`instance`를 `schema`로 검사한다. `root`는 `$ref`를 찾는 계약 전체(없으면 `schema`)."""
    errors: list[ContractError] = []
    _check(instance, schema, root if root is not None else schema, "$", errors)
    return errors


def _check(
    value: Json, schema: Schema, root: Schema, where: str, errors: list[ContractError]
) -> None:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        _check(value, _resolve_ref(root, ref), root, where, errors)
    expected = schema.get("type")
    if expected is not None and not _type_matches(value, expected):
        names = expected if isinstance(expected, list) else [expected]
        errors.append(ContractError(where, "type " + "|".join(map(str, names))))
        return
    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or not any(_json_equal(value, o) for o in options):
            errors.append(ContractError(where, "enum"))
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(ContractError(where, "const"))
    if isinstance(value, str):
        _check_string(value, schema, where, errors)
    elif (number := _number(value)) is not None:
        _check_number(number, schema, where, errors)
    elif isinstance(value, list):
        _check_array(value, schema, root, where, errors)
    elif isinstance(value, dict):
        _check_object(value, schema, root, where, errors)


def _check_string(value: str, schema: Schema, where: str, errors: list[ContractError]) -> None:
    low, high = schema.get("minLength"), schema.get("maxLength")
    # 코드 포인트 수 = JSON Schema의 글 길이
    if isinstance(low, int) and len(value) < low:
        errors.append(ContractError(where, f"minLength {low}"))
    if isinstance(high, int) and len(value) > high:
        errors.append(ContractError(where, f"maxLength {high}"))
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and not _ecma_regex(pattern).search(value):
        errors.append(ContractError(where, "pattern"))
    if schema.get("format") == "date-time" and not _is_date_time(value):
        errors.append(ContractError(where, "format date-time"))


def _check_number(
    value: int | float, schema: Schema, where: str, errors: list[ContractError]
) -> None:
    low, above = _number(schema.get("minimum")), _number(schema.get("exclusiveMinimum"))
    if low is not None and value < low:
        errors.append(ContractError(where, f"minimum {low}"))
    if above is not None and value <= above:
        errors.append(ContractError(where, f"exclusiveMinimum {above}"))


def _check_array(
    value: list[Json], schema: Schema, root: Schema, where: str, errors: list[ContractError]
) -> None:
    low, high = schema.get("minItems"), schema.get("maxItems")
    if isinstance(low, int) and len(value) < low:
        errors.append(ContractError(where, f"minItems {low}"))
    if isinstance(high, int) and len(value) > high:
        errors.append(ContractError(where, f"maxItems {high}"))
    if schema.get("uniqueItems") is True and _has_duplicates(value):
        errors.append(ContractError(where, "uniqueItems"))
    items = schema.get("items")
    if isinstance(items, dict):
        for i, element in enumerate(value):
            _check(element, items, root, f"{where}[{i}]", errors)


def _check_object(
    value: dict[str, Json], schema: Schema, root: Schema, where: str, errors: list[ContractError]
) -> None:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                errors.append(ContractError(where, f"required {key}"))
    properties = schema.get("properties")
    known = properties if isinstance(properties, dict) else {}
    for key, sub in known.items():
        if key in value and isinstance(sub, dict):
            _check(value[key], sub, root, f"{where}.{key}", errors)
    extra = schema.get("additionalProperties")
    for key, element in value.items():
        if key in known:
            continue
        child = f"{where}.{_safe_key(key)}"
        if extra is False:
            errors.append(ContractError(child, "additionalProperties false"))
        elif isinstance(extra, dict):
            _check(element, extra, root, child, errors)


def _safe_key(key: str) -> str:
    return key if _SAFE_KEY.fullmatch(key) else _HIDDEN_KEY


def _resolve_ref(root: Schema, ref: Json) -> Schema:
    if not isinstance(ref, str) or not ref.startswith(_REF_PREFIX):
        raise SchemaUnsupportedError(f"$ref는 {_REF_PREFIX}… 꼴만 다룬다")
    defs = root.get("$defs")
    target = defs.get(ref.removeprefix(_REF_PREFIX)) if isinstance(defs, dict) else None
    if not isinstance(target, dict):
        raise SchemaUnsupportedError(f"$ref가 가리키는 정의가 없음: {ref}")
    return target


def _number(value: Json) -> int | float | None:
    """JSON 수면 그 값, 아니면 None. Python에서 bool은 int지만 JSON에서는 수가 아니다."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _type_matches(value: Json, expected: Json) -> bool:
    if isinstance(expected, list):
        return any(_type_matches(value, e) for e in expected)
    match expected:
        case "null":
            return value is None
        case "boolean":
            return isinstance(value, bool)
        case "integer":
            # JSON 뜻: 소수점 아래가 0인 수는 정수다(1.0). true·false는 수가 아니다
            number = _number(value)
            return isinstance(number, int) or (number is not None and number.is_integer())
        case "number":
            return _number(value) is not None
        case "string":
            return isinstance(value, str)
        case "array":
            return isinstance(value, list)
        case "object":
            return isinstance(value, dict)
    raise SchemaUnsupportedError(f"모르는 type {expected!r}")


def _json_equal(a: Json, b: Json) -> bool:
    """JSON 뜻의 같음: 수는 값으로(1 = 1.0), true·false는 수와 다르다."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if _number(a) is not None and _number(b) is not None:
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(map(_json_equal, a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _has_duplicates(values: list[Json]) -> bool:
    return any(_json_equal(values[i], values[j]) for i in range(len(values)) for j in range(i))


def _ecma_regex(pattern: str) -> re.Pattern[str]:
    """ECMA-262 `pattern`을 같은 뜻의 Python 정규식으로 바꾼다(2.9). 모르는 이스케이프는 멈춘다."""
    out: list[str] = []
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            if i + 1 >= len(pattern):
                raise SchemaUnsupportedError("pattern이 역슬래시로 끝남")
            out.append(_ecma_escape(pattern[i + 1], in_class))
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
            out.append(ch)
        elif ch == "[":
            if pattern.startswith(("[]", "[^]"), i):
                raise SchemaUnsupportedError("빈 글자 묶음 []는 다루지 않는다")
            in_class = True
            out.append(ch)
        elif ch == ".":
            out.append(_ECMA_DOT)
        elif ch == "$":
            out.append(r"\Z")
        else:
            out.append(ch)
        i += 1
    try:
        return re.compile("".join(out))
    except re.error as e:
        raise SchemaUnsupportedError(f"pattern을 읽을 수 없음: {e}") from None


def _ecma_escape(ch: str, in_class: bool) -> str:
    if in_class and ch in _ECMA_CLASS_ESCAPES:
        return _ECMA_CLASS_ESCAPES[ch]
    if not in_class and ch in _ECMA_ESCAPES:
        return _ECMA_ESCAPES[ch]
    if ch in _PLAIN_LETTER_ESCAPES or not ch.isalnum():
        return "\\" + ch
    raise SchemaUnsupportedError(f"pattern의 이스케이프 \\{ch}는 다루지 않는다")


def _is_date_time(value: str) -> bool:
    """RFC 3339 date-time(시간대 필수). 윤초 60은 거절한다(2.9)."""
    m = _DATE_TIME.fullmatch(value)
    if m is None:
        return False
    year, month, day, hour, minute, second = (int(g) for g in m.groups()[:6])
    utc_mark, sign, off_h, off_m = m.group(8), m.group(9), m.group(10), m.group(11)
    try:
        if utc_mark:
            zone = UTC
        else:
            hours, minutes = int(off_h), int(off_m)
            if hours > _MAX_OFFSET_HOURS or minutes > _MAX_OFFSET_MINUTES:
                return False
            delta = timedelta(hours=hours, minutes=minutes)
            zone = timezone(delta if sign == "+" else -delta)
        datetime(year, month, day, hour, minute, second, tzinfo=zone)
    except ValueError:
        return False
    return True
