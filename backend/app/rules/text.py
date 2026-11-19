"""규칙이 함께 쓰는 글 도구 (순수): 위치·가린 값·근거 조각·증거키·소스맵 풀기·걸림 상한.

원문(비밀값)은 이 모듈의 함수 안에서만 쓰고 결과에 담지 않는다 (NFR-03, D-014).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from typing import overload

from app.contracts.engine import Location

MASKED = "****"
EVIDENCE_LEN = 12
BOM = "﻿"
KNOWN_MASK_MIN = 8  # 형식이 정해진 키는 이 길이 이상일 때만 앞 4자·뒤 2자를 남긴다

# 근거 조각 (용어 '근거 조각')
SNIPPET_WINDOW = 200
SNIPPET_SIDE = 40
LONG_RUN_MIN = 20
LONG_RUN_KEEP = 4
_LONG_RUN = re.compile(rf"[A-Za-z0-9+/=_-]{{{LONG_RUN_MIN},}}")
_NEWLINE = re.compile(r"\r\n|\r|\n")

# 파일 하나에서 받아들이는 걸림 수 (F-S01 11, F-S03 9). 10,001번째가 나오면 멈춘다
HIT_LIMIT = 10_000

# S01-GENERIC 키워드. 규칙(F-S01)과 근거 조각 ㉠이 같은 목록을 쓴다 (CR-003)
GENERIC_KEYWORD = re.compile(
    r"password|passwd|pwd|secret|api_?key|access_?token|auth_?token|client_?secret",
    re.IGNORECASE,
)
# 명세 정규식 전체에 (?i)가 걸려 있어 `[A-Za-z]`도 K(켈빈)·ſ·İ·ı를 받는다. 같게 맞춘다.
IDENT_RUN = re.compile(r"[A-Za-z0-9_]*+", re.IGNORECASE)

# 근거 조각 ㉠: 키워드가 든 식별자 + `["']?\s*[:=]\s*` 뒤의 값 (CR-003)
_ASSIGN_TAIL = re.compile(r"[\"']?\s*+[:=]\s*+")
_ASSIGN_BARE = re.compile(r"[^\s\"'`,;)}\]]*+")
_SNIPPET_QUOTES = "\"'`"
# 근거 조각 ㉡: `http(s)://` 바로 뒤의 사용자 정보 (CR-003)
_URL_USERINFO = re.compile(r"(https?://)[^\s/@\"'`<>]++@")
_URL_USERINFO_MASKED = r"\g<1>" + MASKED + "@"

# `.map` 이름 접두 (F-S01 9, CR-003)
MAP_NAME_MAX = 100
_MAP_NAME_CONTROL = re.compile(r"\r\n|[\x00-\x1f\x7f]")
ELLIPSIS = "…"


def evidence_key(key: bytes, raw: str) -> str:
    """증거키 = HMAC-SHA-256(로컬 키, 원문) 16진수 앞 12자 (F-S01 7)."""
    digest = hmac.new(key, raw.encode("utf-8", "surrogatepass"), hashlib.sha256)
    return digest.hexdigest()[:EVIDENCE_LEN]


def mask_known(raw: str) -> str:
    """형식이 정해진 키의 가린 값: 8자 이상이면 앞 4자 + `****` + 뒤 2자, 아니면 `****`."""
    if len(raw) < KNOWN_MASK_MIN:
        return MASKED
    return raw[:4] + MASKED + raw[-2:]


def strip_bom(content: str) -> str:
    return content[1:] if content.startswith(BOM) else content


class LineIndex:
    """글자 위치(0부터) → 줄:열(1부터). 줄은 `\\n`으로만 나눈다. BOM은 미리 뗀 글에 쓴다."""

    def __init__(self, content: str) -> None:
        self._breaks = [i for i, ch in enumerate(content) if ch == "\n"]

    def locate(self, offset: int) -> Location:
        line = bisect_left(self._breaks, offset)  # offset 앞의 줄바꿈 수
        line_start = self._breaks[line - 1] + 1 if line else 0
        return Location(line + 1, offset - line_start + 1)


def map_prefix(name: str) -> str:
    """F-S01 9 `.map` 근거 조각 앞의 `[<이름>] ` (CR-003).

    제어 문자 하나(`\\r\\n`은 둘이 하나)를 공백 하나로 바꾸고, 코드 포인트 100자를 넘으면
    `…` + 뒤 100자로 줄인다(경로는 끝에 파일 이름이 있다). 이름에는 ③을 하지 않는다.
    """
    clean = _MAP_NAME_CONTROL.sub(" ", name)
    if len(clean) > MAP_NAME_MAX:
        clean = ELLIPSIS + clean[-MAP_NAME_MAX:]
    return f"[{clean}] "


class LineCursor:
    """앞으로만 가는 위치 세기. 자리가 커지는 차례로 물으면 글을 한 번만 읽는다.

    줄바꿈 목록을 만들지 않으므로 줄이 아주 많은 글에서도 메모리가 늘지 않는다.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self._pos = 0
        self._line = 1
        self._line_start = 0

    def locate(self, offset: int) -> Location:
        if offset < self._pos:
            raise ValueError("LineCursor는 앞으로만 간다")
        breaks = self._content.count("\n", self._pos, offset)
        if breaks:
            self._line += breaks
            self._line_start = self._content.rfind("\n", self._pos, offset) + 1
        self._pos = offset
        return Location(self._line, offset - self._line_start + 1)


def load_sourcemap(content: str) -> dict[str, object] | None:
    """`.map` 글을 JSON 객체로 읽는다. JSON 객체가 아니면 None (F-S02 예외, CR-002).

    BOM은 떼고 읽는다(규칙 함수가 BOM을 뗀다, RunRules). F-S01·S02·S03이 같은 판정을 쓴다.
    """
    try:
        data = json.loads(strip_bom(content))
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def parse_sourcemap(content: str) -> list[tuple[str, str]] | None:
    """`.map`의 (sources 이름, sourcesContent 글) 목록. JSON 객체가 아니면 None.

    글이 아닌 항목(null 등)과 빈 글은 건너뛴다. 이름이 없으면 빈 문자열.
    """
    data = load_sourcemap(content)
    if data is None:
        return None
    sources = data.get("sources")
    names = sources if isinstance(sources, list) else []
    contents = data.get("sourcesContent")
    if not isinstance(contents, list):
        return []
    out: list[tuple[str, str]] = []
    for i, item in enumerate(contents):
        if not isinstance(item, str) or not item:
            continue
        name = names[i] if i < len(names) and isinstance(names[i], str) else ""
        out.append((name, item))
    return out


@dataclass(frozen=True, slots=True)
class MaskedSpan:
    """한 글 안에서 최종으로 남은 S01 걸림: 원문 범위와 가린 값."""

    start: int
    end: int
    masked: str


def _span_start(span: MaskedSpan) -> int:
    return span.start


def _mask_long_runs(part: str) -> str:
    return _LONG_RUN.sub(lambda m: m.group()[:LONG_RUN_KEEP] + MASKED, part)


def _assigned_value(part: str, start: int) -> tuple[int, int, int]:
    """㉠의 (값 시작, 값 끝, 다시 찾을 자리). 따옴표로 열리면 같은 따옴표 앞까지(없으면 끝까지)."""
    if start < len(part) and part[start] in _SNIPPET_QUOTES:
        close = part.find(part[start], start + 1)
        if close == -1:
            return start + 1, len(part), len(part)
        return start + 1, close, close + 1
    bare = _ASSIGN_BARE.match(part, start)
    end = bare.end() if bare else start
    return start, end, end


def mask_assignments(part: str) -> str:
    """근거 조각 ㉠ (CR-003): 키워드 꼴 대입의 값을 길이·자리표시값과 상관없이 `****`로.

    빈 값은 그대로 둔다(`****`를 넣으면 값이 있었던 것처럼 보인다).

    S01-GENERIC처럼 키워드를 먼저 찾고, 값이 정해지는 식별자 덩어리 끝에서 꼬리를 본다(선형).
    실패하면 덩어리 끝부터, 가리면 값 뒤(닫는 따옴표 뒤)부터 다시 찾는다(명세 finditer와 같다).
    """
    pieces: list[str] = []
    cursor = 0
    pos = 0
    while (kw := GENERIC_KEYWORD.search(part, pos)) is not None:
        run = IDENT_RUN.match(part, kw.end())
        run_end = run.end() if run else kw.end()
        tail = _ASSIGN_TAIL.match(part, run_end)
        if tail is None:
            pos = run_end
            continue
        start, end, pos = _assigned_value(part, tail.end())
        if end > start:
            pieces.append(part[cursor:start])
            pieces.append(MASKED)
            cursor = end
    pieces.append(part[cursor:])
    return "".join(pieces)


def mask_url_userinfo(part: str) -> str:
    """근거 조각 ㉡ (CR-003): `http(s)://` 바로 뒤의 `사용자 정보@`를 `****@`로."""
    return _URL_USERINFO.sub(_URL_USERINFO_MASKED, part)


def _mask_side(part: str) -> str:
    """걸린 곳 앞·뒤 한쪽에 ㉠ → ㉡ → ③ (②는 이미 한 글)."""
    return _mask_long_runs(mask_url_userinfo(mask_assignments(part)))


def _masked_text(content: str, spans: Sequence[MaskedSpan], lo: int, hi: int, rng: range) -> str:
    """content[lo:hi]에서 spans[rng]를 가린 값으로 바꾼 글 (②)."""
    pieces: list[str] = []
    cursor = lo
    for i in rng:
        pieces.append(content[cursor : spans[i].start])
        pieces.append(spans[i].masked)
        cursor = spans[i].end
    pieces.append(content[cursor:hi])
    return "".join(pieces)


def build_snippet(content: str, spans: Sequence[MaskedSpan], target: int) -> str:
    """근거 조각 (용어 '근거 조각' ①~⑤). spans는 시작 순서이고 겹치지 않는다. target은 그 인덱스.

    걸린 곳 앞·걸린 곳·뒤를 따로 만들고 따로 ③을 하므로, 긴 덩어리는 걸린 곳 경계에서 끊긴다.
    ㉠㉡은 ②(S01 가리기)를 한 앞·뒤에만 하고 걸린 곳 자체는 바꾸지 않는다 (CR-003).
    글 안에 표시 문자를 넣지 않는다(대상 글에 어떤 글자가 있어도 자르는 기준이 틀어지지 않는다).
    """
    hit = spans[target]
    lo_text = max(0, hit.start - SNIPPET_WINDOW)
    hi_text = min(len(content), hit.end + SNIPPET_WINDOW)
    first = max(bisect_right(spans, lo_text, key=_span_start) - 1, 0)
    if spans[first].end <= lo_text:
        first += 1
    last = bisect_left(spans, hi_text, key=_span_start)  # 범위 안에서 시작하는 걸림의 다음
    first = min(first, target)
    last = max(last, target + 1)
    lo_text = min(lo_text, spans[first].start)  # 걸림이 잘리지 않게 범위를 넓힌다
    hi_text = max(hi_text, spans[last - 1].end)

    before = _masked_text(content, spans, lo_text, hit.start, range(first, target))
    after = _masked_text(content, spans, hit.end, hi_text, range(target + 1, last))
    snippet = (
        _mask_side(before)[-SNIPPET_SIDE:]
        + _mask_long_runs(hit.masked)
        + _mask_side(after)[:SNIPPET_SIDE]
    )
    return _NEWLINE.sub(" ", snippet)


class _Spliced(Sequence[MaskedSpan]):
    """spans[lo:hi]를 hit 하나로 바꾼 보기.

    복사하지 않으므로 발견마다 걸림 목록 길이만큼 들지 않는다.
    """

    def __init__(self, spans: Sequence[MaskedSpan], lo: int, hi: int, hit: MaskedSpan) -> None:
        self._spans = spans
        self._lo = lo
        self._shift = hi - lo - 1
        self._hit = hit
        self._len = len(spans) - self._shift

    def __len__(self) -> int:
        return self._len

    @overload
    def __getitem__(self, index: int) -> MaskedSpan: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[MaskedSpan]: ...
    def __getitem__(self, index: int | slice) -> MaskedSpan | Sequence[MaskedSpan]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self._len))]
        if index < 0:
            index += self._len
        if not 0 <= index < self._len:
            raise IndexError(index)
        if index < self._lo:
            return self._spans[index]
        if index == self._lo:
            return self._hit
        return self._spans[index + self._shift]


def _span_end(span: MaskedSpan) -> int:
    return span.end


def _render_hit(content: str, lo: int, hi: int, pieces: list[MaskedSpan]) -> str:
    """content[lo:hi]에서 pieces를 바꾼 글.

    앞의 것 안에 든 조각은 버리고, 걸친 조각은 이어 붙인다.
    """
    pieces.sort(key=lambda p: (p.start, -p.end))
    out: list[str] = []
    cursor = lo
    for p in pieces:
        if p.start < cursor:
            if p.end <= cursor:
                continue
            out.append(p.masked)
            cursor = p.end
            continue
        out.append(content[cursor : p.start])
        out.append(p.masked)
        cursor = p.end
    out.append(content[cursor:hi])
    return "".join(out)


def hit_snippet(
    content: str,
    spans: Sequence[MaskedSpan],
    start: int,
    end: int,
    edits: Sequence[MaskedSpan] = (),
) -> str:
    """S01이 아닌 걸림(F-S02·S03)의 근거 조각 (용어 '근거 조각' ①~⑤, CR-003).

    spans는 같은 글의 S01 걸림(시작 순서, 겹치지 않음). 걸린 곳 [start, end)은 그 규칙의 값 모양
    (edits: 걸린 곳 안에서 바꿀 범위와 글, 예: 사용자 정보 → `****@`)에 걸린 곳과 겹치는 S01 걸림을
    가린 값으로 바꾼 글(②)로 보인다. S01 걸림이 걸린 곳 밖으로 걸치면 걸린 곳을 그 끝까지 넓힌다
    (S01 원문의 조각이 남지 않게). 그다음은 S01과 같은 `build_snippet`이다(㉠㉡은 앞·뒤에만).
    """
    lo_i = bisect_right(spans, start, key=_span_end)  # 끝이 start 뒤인 첫 걸림
    hi_i = bisect_left(spans, end, key=_span_start)  # 시작이 end 이상인 첫 걸림 (늘 lo_i 이상)
    overlapping = [spans[i] for i in range(lo_i, hi_i)]
    lo = min(start, overlapping[0].start) if overlapping else start
    hi = max(end, overlapping[-1].end) if overlapping else end
    hit = MaskedSpan(lo, hi, _render_hit(content, lo, hi, [*overlapping, *edits]))
    return build_snippet(content, _Spliced(spans, lo_i, hi_i, hit), lo_i)
