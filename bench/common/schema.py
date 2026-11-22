"""JSON Schema 2020-12의 일부만 다루는 검증기 (실험구조 2.9 — 범위·뜻·상한의 근거).

세 계약이 쓰는 키워드만 안다. 모르는 키워드·잘못된 키워드 값·순환 `$ref`는 계약을 읽을 때 멈춘다.
오류 글에는 값을 싣지 않는다 — 결과·정답지에는 대상 안의 글(비밀값일 수 있다)이 그대로 있다.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Hashable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from functools import cache
from typing import Final

from common.paths import is_bundle_relpath

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None
type Schema = Mapping[str, Json]

MAX_DEPTH: Final = 64  # 계약의 가장 깊은 값은 6단(정답지 → items → 정답 → locations → 위치 → 칸)
MAX_ERRORS: Final = 100  # 오류 목록 상한. 넘으면 앞 100곳과 '생략' 한 줄

_ANNOTATIONS: Final = frozenset({"$schema", "$id", "title", "description"})
_NON_NEGATIVE_INT_KEYWORDS: Final = frozenset({"minLength", "maxLength", "minItems", "maxItems"})
_NUMBER_KEYWORDS: Final = frozenset({"minimum", "exclusiveMinimum", "maximum"})
_OTHER_KEYWORDS: Final = frozenset({
    "$defs", "type", "enum", "const", "properties", "required", "additionalProperties", "items",
    "uniqueItems", "pattern", "format", "$ref",
})  # fmt: skip
_KEYWORDS: Final = _ANNOTATIONS | _NON_NEGATIVE_INT_KEYWORDS | _NUMBER_KEYWORDS | _OTHER_KEYWORDS
_TYPES: Final = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})
_REF_PREFIX: Final = "#/$defs/"
_SAFE_KEY: Final = re.compile(r"[A-Za-z0-9_]{1,40}")
_HIDDEN_KEY: Final = "<키>"

# ECMA-262 뜻 (2.9): `.`은 줄 끝 글자를 받지 않고, `$`는 글 끝에서만, `\d`·`\w`는 ASCII
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


@dataclass(frozen=True)
class ContractError:
    """계약에 어긋난 곳 하나. `where`는 `$.items[0].anchor` 꼴, `rule`은 걸린 규칙과 기준."""

    where: str
    rule: str

    def __str__(self) -> str:
        return f"{self.where}: {self.rule}"


class _TooManyErrorsError(Exception):
    """오류가 MAX_ERRORS를 채웠다. 검사를 멈춘다."""


class _Errors:
    def __init__(self) -> None:
        self.items: list[ContractError] = []

    def add(self, where: str, rule: str) -> None:
        self.items.append(ContractError(where, rule))
        if len(self.items) >= MAX_ERRORS:
            raise _TooManyErrorsError


# --- 계약 훑기 -------------------------------------------------------------------------------


def check_schema(schema: Schema) -> None:
    """계약 전체(쓰이지 않는 갈래 포함)를 훑어 모르는 키워드·잘못된 값·순환 `$ref`면 멈춘다."""
    for where, node in _subschemas(schema, "#"):
        unknown = set(node) - _KEYWORDS
        if unknown:
            raise SchemaUnsupportedError(f"{where}: 모르는 키워드 {sorted(unknown)}")
        for key, value in node.items():
            _check_keyword_value(schema, where, key, value)


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


def _check_keyword_value(root: Schema, where: str, key: str, value: Json) -> None:
    def bad(expected: str) -> SchemaUnsupportedError:
        return SchemaUnsupportedError(f"{where}: {key} 값은 {expected}여야 한다")

    if key in _ANNOTATIONS or key == "format":
        if not isinstance(value, str):
            raise bad("글")
        if key == "format" and value not in _FORMATS:
            raise SchemaUnsupportedError(f"{where}: 모르는 format {value!r}")
    elif key in _NON_NEGATIVE_INT_KEYWORDS:
        if type(value) is not int or value < 0:
            raise bad("0 이상 정수")
    elif key in _NUMBER_KEYWORDS:
        if _number(value) is None:
            raise bad("수")
    elif key == "type":
        names = value if isinstance(value, list) else [value]
        if not names or any(not isinstance(n, str) or n not in _TYPES for n in names):
            raise bad(f"{sorted(_TYPES)} 가운데 하나 또는 그 목록")
    elif key == "enum":
        if not isinstance(value, list) or not value:
            raise bad("비지 않은 목록")
    elif key == "required":
        if not isinstance(value, list) or any(not isinstance(k, str) for k in value):
            raise bad("글 목록")
        if len(set(value)) != len(value):
            raise bad("겹치지 않는 글 목록")
    elif key in ("properties", "$defs"):
        if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
            raise bad("스키마 사전")
    elif key == "items":
        if not isinstance(value, dict):
            raise bad("스키마 하나")
    elif key == "additionalProperties":
        if not isinstance(value, bool | dict):
            raise bad("true·false 또는 스키마")
    elif key == "uniqueItems":
        if not isinstance(value, bool):
            raise bad("true·false")
    elif key == "pattern":
        if not isinstance(value, str):
            raise bad("글")
        _ecma_regex(value)
    elif key == "$ref":
        _check_ref_chain(root, value)


def _check_ref_chain(root: Schema, ref: Json) -> None:
    """`$ref`가 `$ref`만 가리키며 돌면 검사가 끝나지 않는다. 그런 순환을 막는다."""
    seen: set[str] = set()
    while isinstance(ref, str):
        if ref in seen:
            raise SchemaUnsupportedError(f"$ref 순환: {ref}")
        seen.add(ref)
        ref = _resolve_ref(root, ref).get("$ref")
    if ref is not None:
        raise SchemaUnsupportedError("$ref 값은 글이어야 한다")


def _resolve_ref(root: Schema, ref: Json) -> Schema:
    if not isinstance(ref, str) or not ref.startswith(_REF_PREFIX):
        raise SchemaUnsupportedError(f"$ref는 {_REF_PREFIX}… 꼴만 다룬다")
    defs = root.get("$defs")
    target = defs.get(ref.removeprefix(_REF_PREFIX)) if isinstance(defs, dict) else None
    if not isinstance(target, dict):
        raise SchemaUnsupportedError(f"$ref가 가리키는 정의가 없음: {ref}")
    return target


# --- 값 검사 ---------------------------------------------------------------------------------


def validate(instance: Json, schema: Schema, root: Schema | None = None) -> list[ContractError]:
    """`instance`를 `schema`로 검사한다. `root`는 `$ref`를 찾는 계약 전체(없으면 `schema`).

    맞으면 빈 목록. 차례는 늘 같다(계약의 칸 차례, 그다음 값의 차례). 100곳을 채우면 멈추고
    '생략' 한 줄을 붙인다. MAX_DEPTH보다 깊은 값은 검사하지 않고 그 한 줄만 낸다.
    """
    if is_too_deep(instance):
        return [ContractError("$", f"depth {MAX_DEPTH}")]
    errors = _Errors()
    try:
        _check(instance, schema, root if root is not None else schema, "$", errors)
    except _TooManyErrorsError:
        errors.items.append(ContractError("$", f"오류 {MAX_ERRORS}곳에서 멈춤, 나머지 생략"))
    return errors.items


def is_too_deep(value: Json, limit: int = MAX_DEPTH) -> bool:
    """값의 깊이(글·수는 1, 목록·객체는 안의 것 + 1)가 limit을 넘는지. 되부름 없이 센다."""
    stack: list[tuple[Json, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            return True
        if isinstance(current, list):
            stack.extend((v, depth + 1) for v in current)
        elif isinstance(current, dict):
            stack.extend((v, depth + 1) for v in current.values())
    return False


def _check(value: Json, schema: Schema, root: Schema, where: str, errors: _Errors) -> None:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        _check(value, _resolve_ref(root, ref), root, where, errors)
    expected = schema.get("type")
    if expected is not None and not _type_matches(value, expected):
        names = expected if isinstance(expected, list) else [expected]
        errors.add(where, "type " + "|".join(map(str, names)))
        return
    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or not any(_json_equal(value, o) for o in options):
            errors.add(where, "enum")
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.add(where, "const")
    if isinstance(value, str):
        _check_string(value, schema, where, errors)
    elif (number := _number(value)) is not None:
        _check_number(number, schema, where, errors)
    elif isinstance(value, list):
        _check_array(value, schema, root, where, errors)
    elif isinstance(value, dict):
        _check_object(value, schema, root, where, errors)


def _check_string(value: str, schema: Schema, where: str, errors: _Errors) -> None:
    low, high = schema.get("minLength"), schema.get("maxLength")
    # 코드 포인트 수 = JSON Schema의 글 길이
    if isinstance(low, int) and len(value) < low:
        errors.add(where, f"minLength {low}")
    if isinstance(high, int) and len(value) > high:
        errors.add(where, f"maxLength {high}")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and not _ecma_regex(pattern).search(value):
        errors.add(where, "pattern")
    fmt = schema.get("format")
    if isinstance(fmt, str) and not _FORMATS[fmt](value):
        errors.add(where, f"format {fmt}")


def _check_number(value: int | float, schema: Schema, where: str, errors: _Errors) -> None:
    low, above = _number(schema.get("minimum")), _number(schema.get("exclusiveMinimum"))
    high = _number(schema.get("maximum"))
    if low is not None and value < low:
        errors.add(where, f"minimum {low}")
    if above is not None and value <= above:
        errors.add(where, f"exclusiveMinimum {above}")
    if high is not None and value > high:
        errors.add(where, f"maximum {high}")


def _check_array(
    value: list[Json], schema: Schema, root: Schema, where: str, errors: _Errors
) -> None:
    low, high = schema.get("minItems"), schema.get("maxItems")
    if isinstance(low, int) and len(value) < low:
        errors.add(where, f"minItems {low}")
    if isinstance(high, int) and len(value) > high:
        # 상한을 넘은 목록의 원소는 보지 않는다(쏟아 낸 결과 10만 개를 하나씩 검사하지 않게)
        errors.add(where, f"maxItems {high}")
        return
    if schema.get("uniqueItems") is True and _has_duplicates(value):
        errors.add(where, "uniqueItems")
    items = schema.get("items")
    if isinstance(items, dict):
        for i, element in enumerate(value):
            _check(element, items, root, f"{where}[{i}]", errors)


def _check_object(
    value: dict[str, Json], schema: Schema, root: Schema, where: str, errors: _Errors
) -> None:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                errors.add(where, f"required {key}")
    properties = schema.get("properties")
    known = properties if isinstance(properties, dict) else {}
    for key, sub in known.items():
        if key in value and isinstance(sub, dict):
            _check(value[key], sub, root, f"{where}.{key}", errors)
    extra = schema.get("additionalProperties")
    for key, element in value.items():
        if key in known:
            continue
        child = f"{where}.{safe_key(key)}"
        if extra is False:
            errors.add(child, "additionalProperties false")
        elif isinstance(extra, dict):
            _check(element, extra, root, child, errors)


def safe_key(key: str) -> str:
    """오류 글에 실을 키 이름. 영문·숫자·밑줄 40자 안이 아니면 `<키>`(결과 쪽이 정한 글)."""
    return key if _SAFE_KEY.fullmatch(key) else _HIDDEN_KEY


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
    return _canonical(a) == _canonical(b)


def _canonical(value: Json) -> Hashable:
    """JSON 뜻으로 같은 값이면 같은(해시도 같은) 열쇠. 1과 1.0은 Python에서 같고 해시도 같다."""
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, int | float):
        return ("n", value)
    if isinstance(value, list):
        return ("l", tuple(_canonical(v) for v in value))
    if isinstance(value, dict):
        return ("o", frozenset((k, _canonical(v)) for k, v in value.items()))
    return ("s" if isinstance(value, str) else "z", value)


def _has_duplicates(values: list[Json]) -> bool:
    """O(N): 열쇠 집합으로 센다(N²로 비교하지 않는다)."""
    keys = {_canonical(v) for v in values}
    return len(keys) != len(values)


@cache
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


# 계약이 쓰는 format. `bundle-relpath`는 이 프로젝트 꼴(2.9: ECMA 정규식으로 글자 종류를 못 쓴다)
_FORMATS: Final[Mapping[str, Callable[[str], bool]]] = {
    "date-time": _is_date_time,
    "bundle-relpath": is_bundle_relpath,
}
