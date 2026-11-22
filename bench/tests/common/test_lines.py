"""줄 세기·'줄로 가를 수 있는 위치' 시험 (실험구조 2.2 `file_lines`, 2.5 ㉢)."""

from __future__ import annotations

import pytest

from common.lines import count_lines, window_covers_file

LF = bytes([0x0A])
CR = bytes([0x0D])


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"a", 1),
        (b"a" + LF, 1),  # 끝의 줄바꿈 하나는 새 줄을 만들지 않는다
        (b"a" + LF + b"b", 2),
        (b"a" + LF + b"b" + LF, 2),
        (b"a" + LF + LF, 2),  # 빈 줄 하나 + 끝 줄바꿈
        (b"", 1),
        (LF, 1),
        (b"a" + CR + LF + b"b" + CR + LF, 2),  # CRLF도 LF에서 한 번
        (b"a" + CR + b"b", 1),  # CR만은 나누지 않는다
        (b"x" * 1000 + LF + b"//# sourceMappingURL=a.js.map" + LF, 2),  # 압축 결과물의 흔한 꼴
    ],
)
def test_common_줄수_셈(data: bytes, expected: int) -> None:
    assert count_lines(data) == expected


@pytest.mark.parametrize(
    ("line_start", "line_end", "file_lines", "expected"),
    [
        (1, 1, 1, True),  # 한 줄 파일
        (1, 1, 2, True),  # 코드 한 줄 + sourceMappingURL 한 줄
        (3, 3, 5, True),  # 1~5줄을 [1, 5]가 덮는다
        (1, 1, 5, False),  # [−1, 3]은 4·5줄을 덮지 않는다
        (2, 2, 4, True),
        (3, 3, 6, False),
        (40, 40, 120, False),  # 펼친 번들
    ],
)
def test_common_줄허용범위가_파일을_덮는지(
    line_start: int, line_end: int, file_lines: int, expected: bool
) -> None:
    assert window_covers_file(line_start, line_end, file_lines, tolerance=2) is expected


def test_common_줄허용_0이면_한줄파일만() -> None:
    assert window_covers_file(1, 1, 1, tolerance=0)
    assert not window_covers_file(1, 1, 2, tolerance=0)
