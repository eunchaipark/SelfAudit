"""F-B02 규칙 2 `encoded`: 가짜 값 걸러내기 base64(표준 글자, `=` 채움)·16진(소문자).

`build.py` '더하는 변환'의 꼴이다. 원본 `plan.json` `plugins`에 `"encode"`를 적으면 빌드가 읽고,
원본 자리 `{{v:<정답 ID>|base64}}`·`{{v:<정답 ID>|hex}}`를 채운다. 정답지 닻도 같은 걸러내기로
만든다(`answers.in.json` `{"value": "<정답 ID>", "chain": "base64"}`, `locate._anchor`).

인코딩 글은 F-B07 10(규칙 5㉮·㉰)을 받는다 — 걸리면 F-B07이 실패로 내고 접두어를 바꾼다
(F-B02 예외). 여기서는 걸러내지 않는다: 같은 검사를 두 곳에 두면 기준이 갈린다.
오류 글에는 값을 싣지 않는다(걸러내기 이름만).
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Final

from sources.build_tools.build import Filter

__all__ = ["FILTERS", "to_base64", "to_hex"]


def to_base64(value: str, args: Sequence[str]) -> str:
    """F-B02 규칙 2 `encoded` base64: UTF-8 바이트의 표준 base64(`+`·`/`, `=` 채움)."""
    _no_args("base64", args)
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def to_hex(value: str, args: Sequence[str]) -> str:
    """F-B02 규칙 2 `encoded` 16진: UTF-8 바이트의 16진 소문자(바이트마다 2자)."""
    _no_args("hex", args)
    return value.encode("utf-8").hex()


def _no_args(name: str, args: Sequence[str]) -> None:
    # 인자가 붙은 자리(`|base64:2`)는 꼴을 틀리게 쓴 것이다. 조용히 버리면 틀린 원본이 지나간다
    if args:
        raise ValueError(f"{name}는 인자를 받지 않음")


FILTERS: Final[Mapping[str, Filter]] = {"base64": to_base64, "hex": to_hex}
