"""현재 시각은 여기서만 만든다. 엔진은 시각을 인자로 받는다 (코드규칙 1장)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

# 한국은 일광 절약 시간이 없어 고정 오프셋으로 충분하다 (Windows에 tz 데이터가 없어도 된다)
KST = timezone(timedelta(hours=9), "KST")

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


def fixed_clock(at: datetime) -> Clock:
    if at.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 쓰지 않는다")
    return lambda: at
