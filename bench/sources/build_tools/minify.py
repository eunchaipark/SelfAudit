"""F-B01 압축(한 줄): 직접 쓴 JS 원본을 주석·공백·줄바꿈 없이 한 줄로.

압축 도구(terser·esbuild)는 새 라이브러리라 쓰지 않는다
(설계 2.7 '난독화를 직접 만드는 근거'와 같은 까닭).
그래서 받는 원본이 좁다 — 시험 번들 원본은 우리가 쓰므로 이 꼴에 맞춰 쓴다:
- 문장마다 `;`로 끝낸다(줄바꿈으로 문장을 끝내는 자동 세미콜론에 기대지 않는다).
  줄바꿈이 자동 세미콜론을 부를 수 있는 자리(앞이 이름·글·`)`·`]`, 뒤가 이름·글·`(`·`[`)는
  멈추고 원본 줄을 알린다.
- 글(`'…'`·`"…"`·`` `…` ``)과 정규식 글에 줄바꿈을 두지 않는다.
  템플릿 글의 `${…}` 안에 `` ` ``를 두지 않는다.
- `/*! … */`(라이선스·버전 배너)는 남기고 한 줄이어야 한다. 그 밖의 주석은 지운다.
식 줄이기는 하지 않는다(심은 글이 그대로 남아야 닻이 번들에 있다). 이름 줄이기는 빌드가
압축 전에 `rename.py`로 한다(F-B01 6).
토큰 상수 `WORD`·`REGEX_AFTER_*`는 `rename`·`obfuscate`도 쓴다(공개 이름, 설계 8.4 9).
"""

from __future__ import annotations

import io
import string
from dataclasses import dataclass
from typing import Final

__all__ = [
    "REGEX_AFTER_PUNCT",
    "REGEX_AFTER_WORDS",
    "WORD",
    "Minified",
    "MinifyError",
    "minify_js",
]

WORD: Final = frozenset(string.ascii_letters + string.digits + "_$")
_SPACE: Final = frozenset(" \t" + chr(0x0A))
_LF: Final = chr(0x0A)
_QUOTES: Final = frozenset("'\"")
_BACKTICK: Final = "`"
_BACKSLASH: Final = "\\"
# 앞 토큰이 이것이면 `/`는 나눗셈이 아니라 정규식 글의 시작이다
REGEX_AFTER_PUNCT: Final = frozenset("(,=:[!&|?{};+-*%<>~^")
REGEX_AFTER_WORDS: Final = frozenset(
    {"return", "typeof", "case", "do", "else", "in", "instanceof", "new", "delete", "void"}
    | {"throw", "yield", "await", "of"}
)
# 줄바꿈 뒤에 문장이 이어져도 자동 세미콜론이 생기지 않는 낱말(블록·식이 뒤따른다)
_CONTINUING_WORDS: Final = frozenset(
    {"else", "do", "try", "finally", "in", "of", "new", "typeof", "void", "delete"}
    | {"instanceof", "case", "const", "let", "var", "function", "class", "if", "for", "while"}
    | {"switch", "catch", "async", "export", "import", "extends", "static", "get", "set"}
)
_STATEMENT_END_PUNCT: Final = frozenset(")]")
_STATEMENT_START_PUNCT: Final = frozenset("([")


class MinifyError(ValueError):
    """이 압축이 받지 않는 원본. 글에는 원본 줄 번호(1부터)만 있다."""


@dataclass(frozen=True)
class Minified:
    """압축 결과: 한 줄 코드(끝 줄바꿈 없음)와 소스맵 조각 `(결과물 열, 원본 줄 0부터)`."""

    code: str
    segments: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class _Token:
    text: str
    kind: str  # word·str·regex·keep(남기는 주석)·punct
    line: int  # 원본 줄, 0부터
    newline_before: bool
    space_before: bool


def minify_js(source: str) -> Minified:
    """F-B01 압축 모드: JS 원본 → 한 줄."""
    return _Scanner(source).run()


def _needs_space(left: str, right: str) -> bool:
    if left[-1] in WORD and right[0] in WORD:
        return True
    return left[-1] in "+-" and right[0] == left[-1]  # `a + +b`, `a - -b`


def _asi_risk(prev: _Token, tok: _Token) -> bool:
    ends = (prev.kind in {"word", "str", "regex"} and prev.text not in _CONTINUING_WORDS) or (
        prev.text in _STATEMENT_END_PUNCT
    )
    starts = tok.kind in {"word", "str"} or tok.text in _STATEMENT_START_PUNCT
    return ends and starts


class _Scanner:
    """원본을 한 번 훑으며 토큰을 바로 결과에 잇는다.

    토큰 목록을 쌓지 않아 메모리가 결과 크기 정도다(반려 1 4).
    """

    def __init__(self, source: str) -> None:
        if chr(0x0D) in source:
            raise MinifyError("원본에 CR이 있음(줄바꿈은 LF만)")
        self.src = source
        self.pos = 0
        self.line = 0
        self.newline = False
        self.space = False
        self.out = io.StringIO()
        self.col = 0
        self.segments: list[tuple[int, int]] = []
        self.prev: _Token | None = None
        self.significant: _Token | None = None  # 남기는 주석이 아닌 마지막 토큰(정규식 가르기)

    def emit(self, text: str, kind: str, line: int) -> None:
        tok = _Token(text, kind, line, self.newline, self.space)
        self.newline = self.space = False
        prev = self.prev
        if prev is not None:
            if tok.newline_before and _asi_risk(prev, tok):
                raise MinifyError(f"원본 {tok.line + 1}줄: 앞 줄 끝에 ';'가 없음(자동 세미콜론)")
            if tok.space_before and _needs_space(prev.text, tok.text):
                self.out.write(" ")
                self.col += 1
        if not self.segments or self.segments[-1][1] != tok.line:
            self.segments.append((self.col, tok.line))
        self.out.write(tok.text)
        self.col += len(tok.text)
        self.prev = tok
        if kind != "keep":
            self.significant = tok

    def regex_allowed(self) -> bool:
        prev = self.significant
        if prev is None:
            return True
        if prev.kind == "punct":
            return prev.text in REGEX_AFTER_PUNCT
        return prev.kind == "word" and prev.text in REGEX_AFTER_WORDS

    def run(self) -> Minified:
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch in _SPACE:
                self.skip_space(ch)
            elif self.src.startswith("//", self.pos):
                self.skip_line_comment()
            elif self.src.startswith("/*", self.pos):
                self.block_comment()
            elif ch in _QUOTES or ch == _BACKTICK:
                self.quoted(ch, "str")
            elif ch == "/" and self.regex_allowed():
                self.regex()
            elif ch in WORD:
                self.word()
            else:
                self.emit(ch, "punct", self.line)
                self.pos += 1
        return Minified(self.out.getvalue(), tuple(self.segments))

    def skip_space(self, ch: str) -> None:
        self.space = True
        if ch == _LF:
            self.newline = True
            self.line += 1
        self.pos += 1

    def skip_line_comment(self) -> None:
        end = self.src.find(_LF, self.pos)
        self.pos = len(self.src) if end < 0 else end
        self.space = True

    def block_comment(self) -> None:
        end = self.src.find("*/", self.pos + 2)
        if end < 0:
            raise MinifyError(f"원본 {self.line + 1}줄: 닫히지 않은 주석")
        text = self.src[self.pos : end + 2]
        if text.startswith("/*!"):
            if _LF in text:
                raise MinifyError(f"원본 {self.line + 1}줄: 남기는 주석(/*!)이 여러 줄")
            self.emit(text, "keep", self.line)
        else:
            self.line += text.count(_LF)
            self.newline = self.newline or _LF in text
            self.space = True
        self.pos = end + 2

    def quoted(self, quote: str, kind: str) -> None:
        start = self.pos
        self.pos += 1
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise MinifyError(f"원본 {self.line + 1}줄: 글 안에 줄바꿈")
            if ch == _BACKSLASH:
                self.pos += 2
                continue
            self.pos += 1
            if ch == quote:
                self.emit(self.src[start : self.pos], kind, self.line)
                return
        raise MinifyError(f"원본 {self.line + 1}줄: 닫히지 않은 글")

    def regex(self) -> None:
        start = self.pos
        self.pos += 1
        in_class = False
        while self.pos < len(self.src):
            ch = self.src[self.pos]
            if ch == _LF:
                raise MinifyError(f"원본 {self.line + 1}줄: 정규식 글 안에 줄바꿈")
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
                self.emit(self.src[start : self.pos], "regex", self.line)
                return
        raise MinifyError(f"원본 {self.line + 1}줄: 닫히지 않은 정규식 글")

    def word(self) -> None:
        start = self.pos
        while self.pos < len(self.src) and self.src[self.pos] in WORD:
            self.pos += 1
        self.emit(self.src[start : self.pos], "word", self.line)
