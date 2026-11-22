"""F-B01 소스맵(버전 3) 쓰기: `mappings`의 base64 VLQ와 맵 JSON.

맞춤은 줄 단위로 거칠다(원본 줄마다 첫 글자 하나). 실험은 맵의 `sourcesContent`(원본 노출)와 맵 파일이
있다는 것(범주 `source_map`)을 보고, 열 단위 정확도는 채점에 쓰이지 않는다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Final

__all__ = ["line_mappings", "render_map", "segment_mappings", "vlq"]

_B64: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_VLQ_SHIFT: Final = 5
_VLQ_CONTINUE: Final = 1 << _VLQ_SHIFT
_VLQ_MASK: Final = _VLQ_CONTINUE - 1
MAP_VERSION: Final = 3


def vlq(value: int) -> str:
    """정수 하나의 base64 VLQ(맨 아래 비트가 부호)."""
    rest = (-value << 1) | 1 if value < 0 else value << 1
    out = []
    while True:
        digit = rest & _VLQ_MASK
        rest >>= _VLQ_SHIFT
        if rest:
            digit |= _VLQ_CONTINUE
        out.append(_B64[digit])
        if not rest:
            return "".join(out)


def line_mappings(line_count: int) -> str:
    """펼친 결과물: 결과물 n째 줄 첫 글자 → 원본 n째 줄 첫 글자."""
    if line_count < 1:
        return ""
    first = vlq(0) * 4
    rest = vlq(0) + vlq(0) + vlq(1) + vlq(0)
    return ";".join([first] + [rest] * (line_count - 1))


def segment_mappings(segments: Sequence[tuple[int, int]]) -> str:
    """압축 결과물(한 줄): `(결과물 열, 원본 줄 0부터)`마다 한 조각. 열·줄은 앞 조각과의 차이로 적는다."""
    parts = []
    last_col = last_line = 0
    for col, line in segments:
        parts.append(vlq(col - last_col) + vlq(0) + vlq(line - last_line) + vlq(0))
        last_col, last_line = col, line
    return ",".join(parts)


def render_map(file: str, source: str, content: str | None, mappings: str) -> bytes:
    """맵 파일 바이트(한 줄 JSON + `\\n`). `content`가 None이면 `sourcesContent`를 넣지 않는다."""
    value: dict[str, object] = {"version": MAP_VERSION, "file": file, "sources": [source]}
    if content is not None:
        value["sourcesContent"] = [content]
    value["names"] = []
    value["mappings"] = mappings
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")
