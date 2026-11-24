"""F-B01 6 이름 줄이기 (normal·hard): 원본에서 쓴 이름을 '줄일 이름 표'대로 짧은 이름으로.

실제 압축기(esbuild `minifyIdentifiers`, terser `mangle`)처럼 지역·모듈 이름을 줄이고 속성 이름은
남긴다(설계 8.4 1). 범위 분석기는 새 라이브러리라 쓰지 않고, 바꿀 이름을 원본마다 빌드 설정
(`plan.json` `rename`)에 사람이 적는다. 빌드는 빠진 것을 잡아 멈춘다.

바꾸는 방법: 표의 이름을 **한 파일 안에서 모두 같은 짧은 이름으로** 바꾼다(그 파일에 없는 이름으로).
범위가 달라도 같은 이름을 같은 새 이름으로 바꾸면 뜻이 같다 — 그래서 범위를 가를 필요가 없다.
바꾸지 않는 자리: `.`·`?.` 뒤 이름(속성), 객체 열쇠(`{`·`,` 뒤, `:` 앞), 글·주석·정규식 글,
`export` 선언 이름(덩어리 사이에 부르는 이름, 설계 8.8 4 ㉡).

멈추는 꼴(원본 파일·줄·이름을 알린다. 이름은 값이 아니다):
- 선언 이름(`const`·`let`·`var`·`function` 뒤 이름, `function` 매개변수) 가운데
  표에 없는 2자 넘는 것
- 구조 분해 선언(`const {a} =`·`const [a] =`)과 구조 분해 매개변수
- 단축 속성(`{payKey}`·`{a, payKey}`)에 표의 이름(㉠ — 원본에 `payKey: payKey`로 풀어 쓴다)
- 표에 있는 `export` 선언 이름(㉡), `export {…}`·`export *`·정적 `import`(㉢)
- `class`(본문의 메서드 이름 자리를 토큰으로 가를 수 없다 — 설계 8.8 4 '같이 본 것', 지금 0곳),
  `${…}`가 든 템플릿 글(안의 이름을 바꿀 수 없다)

토큰 규칙(글·정규식 글 가르기)은 압축(`minify`)과 같다. 두 번 훑는다: 한 번은 검사와 파일 안 이름
모으기, 한 번은 바꿔 쓰기. 토큰 목록을 쌓지 않는다(메모리는 결과 크기 + 이름 모음 정도).
"""

from __future__ import annotations

import io
import itertools
import string
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Final

from sources.build_tools.minify import REGEX_AFTER_PUNCT, REGEX_AFTER_WORDS, WORD

__all__ = ["RESERVED", "RenameError", "Renamed", "check_table", "rename_js"]

_LF: Final = chr(0x0A)
_SPACE: Final = frozenset(" \t" + _LF)
_QUOTES: Final = frozenset("'\"`")
_BACKTICK: Final = "`"
_BACKSLASH: Final = "\\"
_OPEN: Final = {"(": ")", "[": "]", "{": "}"}
_CLOSE: Final = frozenset(_OPEN.values())
# 이름으로 쓸 수 없거나 뜻이 따로 있는 낱말(예약어와 문맥 낱말).
# 표에 둘 수 없고 짧은 이름으로 고르지 않는다
RESERVED: Final = frozenset(
    {"break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete"}
    | {"do", "else", "enum", "export", "extends", "false", "finally", "for", "function", "if"}
    | {"import", "in", "instanceof", "new", "null", "return", "super", "switch", "this"}
    | {"throw", "true", "try", "typeof", "var", "void", "while", "with", "yield", "let"}
    | {"static", "implements", "interface", "package", "private", "protected", "public"}
    | {"await", "async", "of", "as", "from", "get", "set", "arguments", "eval", "undefined"}
    | {"NaN", "Infinity"}
)
_DECLARE: Final = frozenset({"const", "let", "var"})
_EXPORTABLE: Final = frozenset({"function", "async", "const", "let", "var", "class", "default"})
_AFTER_IMPORT: Final = frozenset({"(", "."})  # 동적 import(`import("…")`)·`import.meta`만
_RENAMABLE: Final = frozenset({"ident", "declared"})
# 표에 없어도 되는 선언 이름의 길이(F-B01 6 '2자 넘는 이름이면 멈춤')
KEEP_MAX_CHARS: Final = 2
# 짧은 이름 글자: 실제 압축기처럼 한 글자(a~z, A~Z)부터, 모자라면 두 글자
_FIRST: Final = string.ascii_lowercase + string.ascii_uppercase
_REST: Final = _FIRST + string.digits


class RenameError(ValueError):
    """이름 줄이기가 받지 않는 원본. 글에는 원본 파일·줄·이름·규칙만(값은 싣지 않는다)."""


@dataclass(frozen=True)
class Renamed:
    """바꾼 원본(줄바꿈·주석은 그대로 — 압축이 지운다)과 이 파일에서 바꾼 이름."""

    code: str
    used: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Tok:
    kind: str  # word·str·regex·punct
    text: str
    start: int
    line: int  # 1부터


def check_table(names: Collection[str]) -> None:
    """표의 이름 꼴: 이름 글자(`A-Z a-z 0-9 _ $`, 숫자로 시작하지 않음)이고 예약어가 아니다."""
    for name in sorted(names):
        if not name or name[0].isdigit() or any(ch not in WORD for ch in name):
            raise RenameError(f"줄일 이름 표에 이름 꼴이 아닌 것: {name[:40]!r}")
        if name in RESERVED:
            raise RenameError(f"줄일 이름 표에 예약어: {name}")


def rename_js(source: str, table: Collection[str], file: str) -> Renamed:
    """F-B01 6: 원본 JS 하나의 표 이름을 짧은 이름으로(같은 원본·같은 표면 같은 결과)."""
    table = frozenset(table)
    words = _check(source, table, file)
    fresh = _fresh_names(words)
    mapping: dict[str, str] = {}
    out = io.StringIO()
    pos = 0
    for tok, role in _classify(source, file):
        if role not in _RENAMABLE or tok.text not in table:
            continue
        short = mapping.get(tok.text)
        if short is None:
            short = mapping[tok.text] = next(fresh)
        out.write(source[pos : tok.start])
        out.write(short)
        pos = tok.start + len(tok.text)
    out.write(source[pos:])
    return Renamed(out.getvalue(), frozenset(mapping))


def _fresh_names(words: Collection[str]) -> Iterator[str]:
    """그 파일에 이름 토큰으로 나오지 않고 예약어가 아닌 짧은 이름을 차례로."""
    singles = iter(_FIRST)
    pairs = ("".join(p) for p in itertools.product(_FIRST, _REST))
    for name in itertools.chain(singles, pairs):
        if name not in words and name not in RESERVED:
            yield name
    raise RenameError("짧은 이름이 모자람(두 글자 이름을 모두 씀)")


def _check(source: str, table: frozenset[str], file: str) -> set[str]:
    """검사(선언·단축 속성·export)하고 그 파일의 이름 토큰 글을 모은다(새 이름이 겹치지 않게)."""
    words: set[str] = set()
    for tok, role in _classify(source, file):
        if tok.kind != "word":
            continue
        words.add(tok.text)
        if role == "shorthand" and tok.text in table:
            raise RenameError(f"원본 {file} {tok.line}줄: 단축 속성에 줄일 이름 {tok.text}")
        if role == "export" and tok.text in table:
            raise RenameError(f"원본 {file} {tok.line}줄: export 이름은 줄이지 않음 {tok.text}")
        if role == "declared" and tok.text not in table and len(tok.text) > KEEP_MAX_CHARS:
            raise RenameError(f"원본 {file} {tok.line}줄: 줄일 이름 표에 없는 선언 {tok.text}")
    return words


def _classify(source: str, file: str) -> Iterator[tuple[_Tok, str]]:
    """토큰마다 자리: `ident`(이름)·`declared`(선언 이름)·`export`(내보내는 선언 이름)·
    `prop`(속성·열쇠)·`shorthand`(단축 속성)·`other`. 바꾸는 것은 `ident`·`declared`."""
    state = _State(file)
    tokens = _Lexer(source, file).tokens()
    cur = next(tokens, None)
    while cur is not None:
        nxt = next(tokens, None)
        yield cur, state.role(cur, nxt)
        state.advance(cur)
        cur = nxt


class _State:
    """괄호 쌓기와 선언 자리를 따라간다(앞 토큰 둘·다음 토큰 하나만 본다)."""

    def __init__(self, file: str) -> None:
        self.file = file
        self.stack: list[str] = []
        self.prev: _Tok | None = None
        self.prev2: _Tok | None = None
        self.expect_declarator = False  # const·let·var 또는 선언 목록의 `,` 다음
        self.decl_depth: int | None = None  # 선언 목록이 열린 괄호 깊이
        self.after_function = False  # `function` 뒤, `(` 전
        self.function_exported = False
        self.declarator_exported = False  # `export const` 뒤 이름
        self.param_depths: set[int] = set()

    def fail(self, tok: _Tok, rule: str) -> RenameError:
        return RenameError(f"원본 {self.file} {tok.line}줄: {rule}")

    def role(self, tok: _Tok, nxt: _Tok | None) -> str:
        if tok.kind == "punct":
            self.check_punct(tok)
            return "other"
        if tok.kind != "word" or tok.text[0].isdigit():
            return "other"
        if tok.text in RESERVED:
            self.check_keyword(tok, nxt)
            return "other"
        return self.word_role(tok, nxt)

    def word_role(self, tok: _Tok, nxt: _Tok | None) -> str:
        prev, prev2 = self.prev, self.prev2
        if prev is not None and prev.text == "." and not (prev2 is not None and prev2.text == "."):
            return "prop"
        in_object = bool(self.stack) and self.stack[-1] == "{"
        after_open = prev is not None and prev.text in {"{", ","}
        if in_object and after_open and nxt is not None and nxt.text == ":":
            return "prop"
        if self.expect_declarator:
            self.expect_declarator = False
            return "export" if self.declarator_exported else "declared"
        if self.after_function and prev is not None and prev.text == "function":
            return "export" if self.function_exported else "declared"
        if self.is_param(prev):
            return "declared"
        if in_object and after_open and nxt is not None and nxt.text in {",", "}"}:
            return "shorthand"
        return "ident"

    def is_param(self, prev: _Tok | None) -> bool:
        depth = len(self.stack)
        return (
            depth in self.param_depths
            and self.stack[-1] == "("
            and prev is not None
            and prev.text in {"(", ","}
        )

    def check_keyword(self, tok: _Tok, nxt: _Tok | None) -> None:
        text, after = tok.text, (nxt.text if nxt is not None else "")
        if text == "class":
            raise self.fail(tok, "class는 받지 않음(본문 이름 자리를 가를 수 없음)")
        if text == "export" and after not in _EXPORTABLE:
            raise self.fail(tok, "export는 선언 꼴(function·const 등)과 default만")
        if text == "import" and after not in _AFTER_IMPORT:
            raise self.fail(tok, "정적 import는 받지 않음(동적 import()만)")
        if text in _DECLARE:
            if after in {"{", "["}:
                raise self.fail(tok, "구조 분해 선언은 받지 않음")
            self.expect_declarator = True
            self.decl_depth = len(self.stack)
            self.declarator_exported = self.prev is not None and self.prev.text == "export"
        if text == "function":
            self.after_function = True
            self.function_exported = self.exported_function()

    def exported_function(self) -> bool:
        prev, prev2 = self.prev, self.prev2
        if prev is not None and prev.text == "export":
            return True
        return (
            prev is not None
            and prev.text == "async"
            and prev2 is not None
            and (prev2.text == "export")
        )

    def check_punct(self, tok: _Tok) -> None:
        text, prev = tok.text, self.prev
        if text in {"{", "["} and self.is_param(prev):
            raise self.fail(tok, "구조 분해 매개변수는 받지 않음")
        if text in {"{", "["} and self.expect_declarator:
            raise self.fail(tok, "구조 분해 선언은 받지 않음")
        if text == "," and self.decl_depth == len(self.stack):
            self.expect_declarator = True
        if text == ";" and self.decl_depth == len(self.stack):
            self.decl_depth = None

    def advance(self, tok: _Tok) -> None:
        if tok.kind == "punct":
            self.move_brackets(tok)
        self.prev2, self.prev = self.prev, tok

    def move_brackets(self, tok: _Tok) -> None:
        text = tok.text
        if text in _OPEN:
            self.stack.append(text)
            if text == "(" and self.after_function:
                self.param_depths.add(len(self.stack))
                self.after_function = False
            return
        if text not in _CLOSE:
            return
        if not self.stack or _OPEN[self.stack[-1]] != text:
            raise self.fail(tok, "괄호 짝이 맞지 않음")
        self.param_depths.discard(len(self.stack))
        self.stack.pop()
        if self.decl_depth is not None and len(self.stack) < self.decl_depth:
            self.decl_depth = None


class _Lexer:
    """원본을 한 번 훑으며 토큰을 하나씩 내놓는다(공백·주석은 건너뜀, 입력 길이에 선형)."""

    def __init__(self, source: str, file: str) -> None:
        if chr(0x0D) in source:
            raise RenameError(f"원본 {file}에 CR이 있음(줄바꿈은 LF만)")
        self.src = source
        self.file = file
        self.pos = 0
        self.line = 1
        self.last: _Tok | None = None

    def fail(self, rule: str) -> RenameError:
        return RenameError(f"원본 {self.file} {self.line}줄: {rule}")

    def tokens(self) -> Iterator[_Tok]:
        src = self.src
        while self.pos < len(src):
            ch = src[self.pos]
            if ch in _SPACE:
                self.line += ch == _LF
                self.pos += 1
            elif src.startswith("//", self.pos):
                end = src.find(_LF, self.pos)
                self.pos = len(src) if end < 0 else end
            elif src.startswith("/*", self.pos):
                self.block_comment()
            else:
                yield self.token(ch)

    def token(self, ch: str) -> _Tok:
        start = self.pos
        if ch in _QUOTES:
            self.quoted(ch)
            kind = "str"
        elif ch == "/" and self.regex_allowed():
            self.regex()
            kind = "regex"
        elif ch in WORD:
            while self.pos < len(self.src) and self.src[self.pos] in WORD:
                self.pos += 1
            kind = "word"
        else:
            self.pos += 1
            kind = "punct"
        tok = _Tok(kind, self.src[start : self.pos], start, self.line)
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
            raise self.fail("닫히지 않은 주석")
        self.line += self.src.count(_LF, self.pos, end)
        self.pos = end + 2

    def quoted(self, quote: str) -> None:
        self.pos += 1
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise self.fail("글 안에 줄바꿈")
            if ch == _BACKSLASH:
                self.pos += 2
                continue
            if quote == _BACKTICK and self.src.startswith("${", self.pos):
                raise self.fail("템플릿 글의 ${…}는 받지 않음")
            self.pos += 1
            if ch == quote:
                return
        raise self.fail("닫히지 않은 글")

    def regex(self) -> None:
        self.pos += 1
        in_class = False
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise self.fail("정규식 글 안에 줄바꿈")
            if ch == _BACKSLASH:
                self.pos += 2
                continue
            self.pos += 1
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                while self.pos < len(self.src) and self.src[self.pos] in string.ascii_letters:
                    self.pos += 1
                return
        raise self.fail("닫히지 않은 정규식 글")
