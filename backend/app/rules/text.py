"""규칙이 함께 쓰는 글 도구 (순수): 위치·가린 값·근거 조각·증거키·소스맵 풀기.

원문(비밀값)은 이 모듈의 함수 안에서만 쓰고 결과에 담지 않는다 (NFR-03, D-014).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

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
_MARK_START = ""  # 걸린 곳 표시 (근거 조각을 자를 기준)
_MARK_END = ""


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


def parse_sourcemap(content: str) -> list[tuple[str, str]] | None:
    """`.map`의 (sources 이름, sourcesContent 글) 목록. JSON 객체가 아니면 None.

    글이 아닌 항목(null 등)과 빈 글은 건너뛴다. 이름이 없으면 빈 문자열.
    """
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
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


def build_snippet(content: str, spans: list[MaskedSpan], target: int) -> str:
    """근거 조각 (용어 '근거 조각' ①~⑤). spans는 시작 순서이고 겹치지 않는다. target은 그 인덱스."""
    hit = spans[target]
    lo_text = max(0, hit.start - SNIPPET_WINDOW)
    hi_text = min(len(content), hit.end + SNIPPET_WINDOW)
    starts = [s.start for s in spans]
    first = max(bisect_right(starts, lo_text) - 1, 0)
    if spans[first].end <= lo_text:
        first += 1
    last = bisect_left(starts, hi_text)  # 범위 안에서 시작하는 걸림의 다음
    first = min(first, target)
    last = max(last, target + 1)
    lo_text = min(lo_text, spans[first].start)  # 걸림이 잘리지 않게 범위를 넓힌다
    hi_text = max(hi_text, spans[last - 1].end)

    pieces: list[str] = []
    cursor = lo_text
    for i in range(first, last):
        span = spans[i]
        pieces.append(content[cursor : span.start])
        pieces.append(_MARK_START + span.masked + _MARK_END if i == target else span.masked)
        cursor = span.end
    pieces.append(content[cursor:hi_text])
    joined = "".join(pieces)

    joined = _LONG_RUN.sub(lambda m: m.group()[:LONG_RUN_KEEP] + MASKED, joined)
    a = joined.index(_MARK_START)
    b = joined.index(_MARK_END)
    snippet = joined[:a][-SNIPPET_SIDE:] + joined[a + 1 : b] + joined[b + 1 :][:SNIPPET_SIDE]
    return _NEWLINE.sub(" ", snippet)
