"""F-B02 규칙 2 `obfuscated`: 직접 만든 난독화 — 문자열 배열·배열 돌리기·글자 코드 (설계 2.7).

`build.py` '더하는 변환'의 꼴이다. 원본 `plan.json`에 `"plugins": ["obfuscate"]`와
`"steps": [{"step": "obfuscate", "files": ["assets/index.js"]}]`를 적으면,
빌드가 가짜 값·경로 자리를 채운 뒤 압축(`minify`) 전에 그 파일을 바꾼다.

하는 일 — 흔한 난독화 도구(javascript-obfuscator)의 문자열 배열·배열 돌리기·글자 코드 이스케이프
묶음을 흉내 낸다. 그 도구는 새 라이브러리라 들이지 않는다(설계 2.7 '난독화를 직접 만드는 근거'):
1. **문자열 배열**: 글(`"…"`·`'…'`), 이름 접근(`a.b`의 `b`), 객체 열쇠(`{b: 1}`·`{"b": 1}`의 `b`)를
   모두 배열 하나로 옮기고, 그 자리에는 찾기 함수 부름(`_0x3f2a(0x7)`, 접근·열쇠는
   `[_0x3f2a(0x7)]`)을 둔다. 같은 글은 한 칸이다. 글만 옮기면 이름 접근(`cfg.debugDump`)으로
   설정 이름이 글 그대로 남아, 숨긴 글과 숨기지 않은 글이 겉모양으로 갈린다.
2. **배열 돌리기**: 배열을 시드로 고른 k칸만큼 오른쪽으로 돌려 적고, 실행할 때 `push(shift())`를
   k번 해 되돌린다. 적힌 차례로 세면 찾기 번호와 글이 어긋난다.
3. **글자 코드**: 배열의 글은 글자마다 16진 글자 코드(`\\x7a`, 0xff 위는 `\\uXXXX`, BMP 밖은
   UTF-16 두 칸)로 적는다. 그래서 옮긴 글은 결과물에 글 그대로 없다.
이름(변수·함수)은 여기서 바꾸지 않는다 — 명세의 세 방법 밖이다. 이름 줄이기(F-B01 6)는 빌드가
이 변환 전에 `rename.py`로 한다.

받는 원본이 좁다(시험 번들 원본은 우리가 쓰므로 이 꼴에 맞춰 쓴다. 밖이면 멈추고 원본 줄을 알린다):
템플릿 글(`` `…` ``), 정적 `import … from "…"`·`export … from "…"`(그 자리의 글은 식이 될 수 없다),
글 안 줄바꿈, 모르는 글 이스케이프. 압축(`minify`)과 같은 토큰 규칙(정규식 글 가르기)을 쓴다.

정답지 닻은 같은 글자 코드 꼴로 만든다: 걸러내기 `charcode`(`{"value": "<정답 ID>",
"chain": "charcode:16"}` — 앞 16자의 글자 코드). 오류 글에는 값을 싣지 않는다(원본 줄·규칙만).
"""

from __future__ import annotations

import io
import random
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from sources.build_tools.build import Filter, Step, StepContext
from sources.build_tools.minify import REGEX_AFTER_PUNCT, REGEX_AFTER_WORDS, WORD

__all__ = [
    "FILTERS",
    "STEPS",
    "ObfuscateError",
    "char_codes",
    "obfuscate_js",
    "to_charcode",
]

_LF: Final = chr(0x0A)
_SPACE: Final = frozenset(" \t" + _LF)
_QUOTES: Final = frozenset("'\"")
_BACKTICK: Final = "`"
_BACKSLASH: Final = "\\"
# 이스케이프 글자 → 글자(우리 원본에 쓰는 것만. 그 밖은 멈춘다 — 조용히 바꾸면 값이 달라진다)
_SIMPLE_ESCAPES: Final[Mapping[str, str]] = {
    _BACKSLASH: _BACKSLASH,
    "'": "'",
    '"': '"',
    "n": _LF,
    "t": chr(0x09),
}
_HEX: Final = re.compile(r"[0-9a-fA-F]+")
_HEX_ESCAPE_DIGITS: Final = 2  # `\xHH`
_UNICODE_ESCAPE_DIGITS: Final = 4  # `\uHHHH`
_BYTE_MAX: Final = 0xFF
_BMP_MAX: Final = 0xFFFF
_SURROGATE_BASE: Final = 0x10000
_HIGH_SURROGATE: Final = 0xD800
_LOW_SURROGATE: Final = 0xDC00
_SURROGATE_BITS: Final = 10
_SURROGATE_MASK: Final = (1 << _SURROGATE_BITS) - 1
# 이 뒤의 글은 식 자리가 아니라 모듈 이름 자리다(바꾸면 문법이 깨진다)
_STATIC_IMPORT_WORDS: Final = frozenset({"import", "from"})
# 객체 열쇠 자리: `{`·`,` 다음, `:` 앞. `{default:`는 switch 안의 default다
_KEY_BEFORE: Final = frozenset({"{", ","})
_NOT_KEY_WORDS: Final = frozenset({"default", "case"})
# 이름 접근 `.b`를 `[…]`로 바꿀 수 있는 앞 토큰: 이름·글·정규식 글·`)`·`]`.
# `import.meta`·`new.target`은 대괄호로 쓸 수 없다
_MEMBER_AFTER_PUNCT: Final = frozenset({")", "]"})
_NO_MEMBER_WORDS: Final = frozenset({"import", "new"})
# 배열·찾기 함수 이름: 흔한 난독화 결과의 꼴 `_0x` + 16진 4자.
# 원본에 이미 있는 이름이면 다시 고른다.
# 16진 4자는 65,536가지라 두 이름이 원본 이름과 겹칠 확률은 원본 이름 수 ÷ 65,536쯤이다.
# 20번은 끝없는 되풀이를 막는 울타리다(원본 이름 100개면 20번 모두 겹칠 확률 (100/65536)^20)
NAME_PREFIX: Final = "_0x"
NAME_HEX_CHARS: Final = 4
MAX_NAME_DRAWS: Final = 20
# 글자 코드를 이만큼씩 만들어 버퍼에 쓴다: 글자마다 조각을 한 목록에 다 모으면 메모리가 입력의
# 수십 배가 된다(T21 반려 1과 같은 처지). 4096자면 목록은 늘 작고 쓰기 횟수는 입력 ÷ 4096
CHUNK_CHARS: Final = 4096
MIN_ENTRIES: Final = 2  # 돌리기는 두 칸 이상에서만 뜻이 있다(1칸 배열은 돌려도 같다)


class ObfuscateError(ValueError):
    """이 난독화가 받지 않는 원본. 글에는 원본 줄 번호(1부터)·규칙만 있다(값은 싣지 않는다)."""


@dataclass(frozen=True, slots=True)
class _Tok:
    kind: str  # str·regex·word·punct
    text: str
    gap: (
        str  # 이 토큰 앞의 공백·주석(그대로 옮긴다 — 줄바꿈이 압축의 자동 세미콜론 검사에 필요하다)
    )
    line: int  # 원본 줄, 1부터


# --- 글자 코드 -------------------------------------------------------------------------------


def char_codes(text: str) -> str:
    """F-B02 `obfuscated` 글자 코드: 글자마다 `\\xHH`(0xff까지)·`\\uHHHH`, 16진 소문자.

    BMP 밖 글자는 UTF-16 두 칸(`\\ud83c\\udf31`)으로 — JS 글 이스케이프는 UTF-16 단위다.
    """
    out = io.StringIO()
    _write_char_codes(out, text)
    return out.getvalue()


def _write_char_codes(out: io.StringIO, text: str) -> None:
    for start in range(0, len(text), CHUNK_CHARS):
        out.write("".join(map(_char_code, text[start : start + CHUNK_CHARS])))


def _char_code(ch: str) -> str:
    code = ord(ch)
    if code <= _BYTE_MAX:
        return f"\\x{code:02x}"
    if code <= _BMP_MAX:
        return f"\\u{code:04x}"
    rest = code - _SURROGATE_BASE
    high = _HIGH_SURROGATE + (rest >> _SURROGATE_BITS)
    low = _LOW_SURROGATE + (rest & _SURROGATE_MASK)
    return f"\\u{high:04x}\\u{low:04x}"


def to_charcode(value: str, args: Sequence[str]) -> str:
    """걸러내기 `charcode` · `charcode:<n>`: 값(앞 n자)의 글자 코드 — 정답지 닻을 만들 때 쓴다.

    배열 안 글은 값 전체의 글자 코드이고, 글자마다 따로 바꾸므로 앞 n자의 글자 코드는 그 앞부분이다.
    """
    if not args:
        return char_codes(value)
    if len(args) != 1 or not args[0].isdigit() or not 1 <= int(args[0]) <= len(value):
        raise ValueError("charcode는 charcode 또는 charcode:<1~값 길이>")
    return char_codes(value[: int(args[0])])


# --- 진입 ------------------------------------------------------------------------------------


def obfuscate_step(code: str, ctx: StepContext) -> str:
    """빌드 변환 `obfuscate`(파일 하나).

    같은 원본·같은 시드(`<대상 ID>/<src 안 경로>`)면 같은 결과.
    """
    if ctx.options:
        raise ObfuscateError("obfuscate는 options를 받지 않음")
    return obfuscate_js(code, ctx.seed)


def obfuscate_js(source: str, seed: str) -> str:
    """F-B02 `obfuscated`: JS 원본 → 문자열 배열 머리 한 줄 + 바꾼 원본(압축 전, 줄바꿈 남음).

    토큰을 흘려 보내며 바로 버퍼에 쓴다(토큰 목록을 쌓지 않는다 — 메모리가 결과 크기 정도).
    """
    if chr(0x0D) in source:
        raise ObfuscateError("원본에 CR이 있음(줄바꿈은 LF만)")
    rng = random.Random(seed)  # noqa: S311 — 같은 시드면 같은 결과(F-B01 3). 암호용이 아니다
    array_name, lookup_name = _names(rng, source)
    scanner = _Scanner(source)
    table = _Table(lookup_name)
    body = io.StringIO()
    _rewrite(scanner.tokens(), table, body)
    body.write(scanner.tail)
    if len(table.values) < MIN_ENTRIES:
        raise ObfuscateError(f"옮길 글이 {MIN_ENTRIES}개보다 적음(돌릴 배열이 없음)")
    turns = rng.randrange(1, len(table.values))
    out = io.StringIO()
    _write_header(out, table.values, array_name, lookup_name, turns)
    out.write(_LF)
    out.write(body.getvalue())
    return out.getvalue()


def _names(rng: random.Random, source: str) -> tuple[str, str]:
    """배열·찾기 함수 이름. 원본에 이미 있는 글이면 다시 고른다(원본만 보면 되어 먼저 고른다)."""
    names: list[str] = []
    for _ in range(MAX_NAME_DRAWS):
        name = NAME_PREFIX + "".join(rng.choice("0123456789abcdef") for _ in range(NAME_HEX_CHARS))
        if name not in source and name not in names:
            names.append(name)
        if len(names) == MIN_ENTRIES:
            return names[0], names[1]
    raise ObfuscateError("배열·찾기 함수 이름을 원본과 겹치지 않게 고를 수 없음")


def _write_header(
    out: io.StringIO, values: Sequence[str], array_name: str, lookup_name: str, turns: int
) -> None:
    """배열(오른쪽으로 `turns`칸 돌려 적음) · 되돌리는 즉시 실행 함수 · 찾기 함수."""
    n = len(values)
    out.write(f"const {array_name}=[")
    for i in range(n):
        out.write("," if i else "")
        out.write('"')
        _write_char_codes(out, values[(i - turns) % n])
        out.write('"')
    out.write(
        "];"
        f"(function(a,n){{while(n--){{a.push(a.shift());}}}})({array_name},{turns:#x});"
        f"function {lookup_name}(i){{return {array_name}[i];}}"
    )


# --- 바꾸기 ----------------------------------------------------------------------------------


class _Table:
    """옮긴 글의 배열(처음 나온 차례). 같은 글은 같은 번호."""

    def __init__(self, lookup_name: str) -> None:
        self.lookup_name = lookup_name
        self.values: list[str] = []
        self._index: dict[str, int] = {}

    def call(self, value: str) -> str:
        index = self._index.get(value)
        if index is None:
            index = len(self.values)
            self._index[value] = index
            self.values.append(value)
        return f"{self.lookup_name}({index:#x})"


def _rewrite(tokens: Iterator[_Tok], table: _Table, out: io.StringIO) -> None:
    """토큰을 하나씩 바꿔 쓴다. 앞·뒤 토큰 하나씩만 들고 있다.

    이름 접근을 바꿀 때 `.` 앞뒤 공백을 버린다: 줄 첫머리의 `.then`이 `[…]`가 되면 앞 줄의 `)`와
    줄바꿈으로 떨어져 압축이 자동 세미콜론 위험으로 멈춘다.
    버린 자리에 주석이 있었어도 압축이 지운다.
    """
    prev: _Tok | None = None
    cur = next(tokens, None)
    while cur is not None:
        nxt = next(tokens, None)
        if cur.kind == "punct" and cur.text == "." and nxt is not None and _is_member(prev, nxt):
            out.write(f"[{table.call(nxt.text)}]")
            prev, cur = nxt, next(tokens, None)
            continue
        out.write(cur.gap)
        out.write(_render(cur, prev, nxt, table))
        prev, cur = cur, nxt


def _render(tok: _Tok, prev: _Tok | None, nxt: _Tok | None, table: _Table) -> str:
    if tok.kind == "str":
        if prev is not None and prev.kind == "word" and prev.text in _STATIC_IMPORT_WORDS:
            raise ObfuscateError(f"원본 {tok.line}줄: 정적 import·export from은 받지 않음")
        call = table.call(_unquote(tok))
        return f"[{call}]" if _is_key(prev, nxt) else call
    if (
        tok.kind == "word"
        and _is_identifier(tok.text)
        and tok.text not in _NOT_KEY_WORDS
        and _is_key(prev, nxt)
    ):
        return f"[{table.call(tok.text)}]"
    return tok.text


def _is_identifier(text: str) -> bool:
    return not text[0].isdigit()


def _is_key(prev: _Tok | None, nxt: _Tok | None) -> bool:
    return (
        prev is not None
        and prev.kind == "punct"
        and prev.text in _KEY_BEFORE
        and nxt is not None
        and nxt.text == ":"
    )


def _is_member(prev: _Tok | None, nxt: _Tok | None) -> bool:
    if nxt is None or nxt.kind != "word" or not _is_identifier(nxt.text) or prev is None:
        return False
    if prev.kind == "word":
        return _is_identifier(prev.text) and prev.text not in _NO_MEMBER_WORDS
    if prev.kind in {"str", "regex"}:
        return True
    return prev.kind == "punct" and prev.text in _MEMBER_AFTER_PUNCT


def _unquote(tok: _Tok) -> str:
    """글 토큰(따옴표 포함)의 값. 우리 원본에 쓰는 이스케이프만 푼다."""
    inner = tok.text[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch != _BACKSLASH:
            out.append(ch)
            i += 1
            continue
        mark = inner[i + 1 : i + 2]
        if mark in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[mark])
            i += 2
        elif mark in {"x", "u"}:
            digits = _HEX_ESCAPE_DIGITS if mark == "x" else _UNICODE_ESCAPE_DIGITS
            hexed = inner[i + 2 : i + 2 + digits]
            if len(hexed) != digits or not _HEX.fullmatch(hexed):
                raise ObfuscateError(f"원본 {tok.line}줄: 글 이스케이프 꼴이 틀림")
            out.append(chr(int(hexed, 16)))
            i += 2 + digits
        else:
            raise ObfuscateError(f"원본 {tok.line}줄: 받지 않는 글 이스케이프")
    return "".join(out)


# --- 토큰 ------------------------------------------------------------------------------------


class _Scanner:
    """원본을 한 번 훑으며 토큰(앞 공백·주석을 붙인 채)을 하나씩 내놓는다(입력 길이에 선형).

    다 훑은 뒤 `tail`에 끝 공백·주석이 남는다.
    """

    def __init__(self, source: str) -> None:
        self.src = source
        self.pos = 0
        self.line = 1
        self.gap_start = 0
        self.last: _Tok | None = None  # 정규식 글 가르기(압축과 같은 규칙)
        self.tail = ""

    def tokens(self) -> Iterator[_Tok]:
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch in _SPACE:
                if ch == _LF:
                    self.line += 1
                self.pos += 1
                continue
            if self.src.startswith("//", self.pos):
                end = self.src.find(_LF, self.pos)
                self.pos = len(self.src) if end < 0 else end
                continue
            if self.src.startswith("/*", self.pos):
                self.block_comment()
                continue
            start = self.pos
            kind = self.token_kind(ch)
            yield self.emit(kind, start)
        self.tail = self.src[self.gap_start :]

    def token_kind(self, ch: str) -> str:
        """토큰 하나를 지나가며(`pos`를 옮기며) 그 종류를 돌려준다."""
        if ch == _BACKTICK:
            raise ObfuscateError(f"원본 {self.line}줄: 템플릿 글은 받지 않음")
        if ch in _QUOTES:
            self.quoted(ch)
            return "str"
        if ch == "/" and self.regex_allowed():
            self.regex()
            return "regex"
        if ch in WORD:
            while self.pos < len(self.src) and self.src[self.pos] in WORD:
                self.pos += 1
            return "word"
        self.pos += 1
        return "punct"

    def emit(self, kind: str, start: int) -> _Tok:
        gap = self.src[self.gap_start : start]
        tok = _Tok(kind, self.src[start : self.pos], gap, self.line)
        self.gap_start = self.pos
        self.last = tok
        return tok

    def regex_allowed(self) -> bool:
        prev = self.last
        if prev is None:
            return True
        if prev.kind == "punct":
            return prev.text in REGEX_AFTER_PUNCT
        return prev.kind == "word" and prev.text in REGEX_AFTER_WORDS

    def block_comment(self) -> None:
        end = self.src.find("*/", self.pos + 2)
        if end < 0:
            raise ObfuscateError(f"원본 {self.line}줄: 닫히지 않은 주석")
        self.line += self.src.count(_LF, self.pos, end)
        self.pos = end + 2

    def quoted(self, quote: str) -> None:
        self.pos += 1
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise ObfuscateError(f"원본 {self.line}줄: 글 안에 줄바꿈")
            if ch == _BACKSLASH:
                self.pos += 2
                continue
            self.pos += 1
            if ch == quote:
                return
        raise ObfuscateError(f"원본 {self.line}줄: 닫히지 않은 글")

    def regex(self) -> None:
        self.pos += 1
        in_class = False
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise ObfuscateError(f"원본 {self.line}줄: 정규식 글 안에 줄바꿈")
            if ch == _BACKSLASH:
                self.pos += 2
                continue
            self.pos += 1
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                while (
                    self.pos < len(self.src)
                    and self.src[self.pos].isascii()
                    and (self.src[self.pos].isalpha())
                ):
                    self.pos += 1
                return
        raise ObfuscateError(f"원본 {self.line}줄: 닫히지 않은 정규식 글")


STEPS: Final[Mapping[str, Step]] = {"obfuscate": obfuscate_step}
FILTERS: Final[Mapping[str, Filter]] = {"charcode": to_charcode}
