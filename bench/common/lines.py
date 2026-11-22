"""줄 세기와 '줄로 가를 수 있는 위치' (실험구조 2.2 `file_lines`, 2.5 ㉢ — 근거는 그 절).

F-B03(`file_lines`)·F-B07(번들과 맞는지)·F-G02(줄 맞춤·위치 정확도·미끼)가 같은 셈을 쓴다.
"""

from __future__ import annotations

from typing import Final

_LF: Final = 0x0A


def count_lines(data: bytes) -> int:
    """파일의 줄 수(2.2 `file_lines`): `\\n`으로 나눈 조각 수, 끝의 `\\n` 하나는 새 줄이 아니다.

    `\\r`은 나누지 않는다(`\\r\\n`도 `\\n`에서 한 번 나뉜다). 빈 파일은 1줄(줄 1이 빈 줄).
    예: `a` → 1, `a\\n` → 1, `a\\nb` → 2, `a\\nb\\n` → 2, `a\\n\\n` → 2, 빈 파일 → 1.
    """
    newlines = data.count(_LF)
    if data and data[-1] == _LF:
        return max(newlines, 1)
    return newlines + 1


def window_covers_file(line_start: int, line_end: int, file_lines: int, tolerance: int) -> bool:
    """줄 허용 범위 `[line_start − T, line_end + T]`가 파일 전체(1~file_lines)를 덮는지(2.5 ㉢).

    덮으면 그 위치는 '줄로 가를 수 없다' — 줄 번호가 무엇이든 '같은 파일'만 말한다.
    """
    return line_start - tolerance <= 1 and line_end + tolerance >= file_lines
