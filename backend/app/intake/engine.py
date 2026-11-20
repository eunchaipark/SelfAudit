"""F-I01 번들 받기의 판정 (순수). 폴더·zip이 같이 쓰는 분류와 공통 제한. 디스크를 보지 않는다."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from app.contracts.engine import IntakeFailed, SkipReason
from app.core.limits import MAX_FILE_BYTES, MAX_FILES, MAX_UNPACKED_BYTES, TARGET_EXTENSIONS

MSG_TOO_LARGE = "번들이 너무 큽니다 (최대 200MB, 20,000개)"
MSG_OTHER = "점검 중 오류가 나서 멈췄습니다"


@dataclass(frozen=True, slots=True)
class IntakeLimits:
    """F-I01 5·6 제한. 기본값은 `core/limits`이고, 테스트만 작은 값을 넣는다."""

    max_files: int = MAX_FILES
    max_unpacked_bytes: int = MAX_UNPACKED_BYTES
    max_file_bytes: int = MAX_FILE_BYTES


DEFAULT_LIMITS = IntakeLimits()


class EntryKind(StrEnum):
    FILE = "file"
    LINK = "link"  # 심볼릭 링크·정션 (따라가지 않는다)
    OTHER = "other"  # 보통 파일도 폴더도 아닌 것 (장치·파이프 등). 열지 않는다


@dataclass(frozen=True, slots=True)
class Entry:
    """번들 항목 하나. path는 번들 경로('/' 구분), size는 적힌 크기(폴더는 stat, zip은 적힌 값)."""

    path: str
    size: int
    kind: EntryKind = EntryKind.FILE


def is_target(path: str) -> bool:
    """F-I01 7 확장자(대소문자 무시)가 점검 대상인가."""
    return PurePosixPath(path).suffix.lower() in TARGET_EXTENSIONS


def skip_reason(entry: Entry, limits: IntakeLimits) -> SkipReason | None:
    """F-I01 4·6·7 건너뛸 이유. 대상이면 None.

    6(크기)을 7(종류)보다 먼저 본다: 명세 차례이고, F-S02 6이 큰 `.map`을 `크기 초과`로 센다.
    """
    if entry.kind is EntryKind.LINK:
        return SkipReason.SYMLINK
    if entry.kind is EntryKind.OTHER:
        return SkipReason.NOT_TARGET
    if entry.size > limits.max_file_bytes:
        return SkipReason.TOO_LARGE
    if not is_target(entry.path):
        return SkipReason.NOT_TARGET
    return None


def check_totals(files: int, unpacked_bytes: int, limits: IntakeLimits) -> None:
    """F-I01 5 공통 제한: 파일 수와 풀린 크기 합. 넘으면 실패(크기 초과)."""
    if files > limits.max_files or unpacked_bytes > limits.max_unpacked_bytes:
        raise IntakeFailed(MSG_TOO_LARGE)
