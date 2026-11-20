"""앱 영역의 판정 (순수, F-P01~P03). DB·시각을 쓰지 않는다."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlsplit

from app.contracts.engine import ScanStatus
from app.contracts.schemas import URL_MAX, AppKind
from app.core.errors import ValidationFailed
from app.core.limits import APP_NAME_MAX

MSG_NAME_EMPTY = "앱 이름을 입력하세요"
MSG_NAME_TOO_LONG = "앱 이름은 40자까지입니다"
MSG_DUPLICATE = "같은 이름의 앱이 있습니다"
MSG_SOURCE_REQUIRED = "공개 연습앱은 출처 주소(https://…)가 필요합니다"
MSG_CONSENT_REQUIRED = "직접 만든 앱이나 분석이 허용된 연습용 앱만 점검할 수 있습니다"
HTTPS_SCHEME = "https"
ALLOWED_PORT_MAX = 65535


def is_valid_source_url(url: str) -> bool:
    """출처 주소 형식 (보안규칙 5장): https, 호스트 있음, 계정 정보 없음, 공백·제어문자 없음.

    계정 정보(`user:pw@`)는 비밀값이 평문으로 남는 길이고(NFR-03), 공백·개행은 내보내기에서
    글을 끼워 넣는 길이라(D-021) 막는다.
    """
    if not url or len(url) > URL_MAX or not url.isprintable() or any(c.isspace() for c in url):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != HTTPS_SCHEME or not parts.hostname or "@" in parts.netloc:
        return False
    return port is None or 0 < port <= ALLOWED_PORT_MAX


def normalize_name(raw: str) -> str:
    """F-P01 1·2 이름의 앞뒤 공백을 지우고 NFC로 바꾼 뒤 코드 포인트 1~40자인지 본다."""
    name = unicodedata.normalize("NFC", raw.strip())
    if not name:
        raise ValidationFailed(MSG_NAME_EMPTY)
    if len(name) > APP_NAME_MAX:
        raise ValidationFailed(MSG_NAME_TOO_LONG)
    return name


def name_key(name: str) -> str:
    """F-P01 3 중복 검사 열쇠: NFC로 바꾼 이름을 casefold한다."""
    return unicodedata.normalize("NFC", name.casefold())


def check_source_and_consent(kind: AppKind, source_url: str | None, consent: bool) -> str | None:
    """F-P01 4·5 출처 주소와 확인란. 저장할 출처 주소(없으면 None)를 돌려준다.

    `내 앱`은 출처 주소를 쓰지 않으므로(SCR-02 02-03은 공개 연습앱일 때만 보인다) 받은 값을 버린다.
    """
    url = (source_url or "").strip()
    if kind == "practice" and not is_valid_source_url(url):
        raise ValidationFailed(MSG_SOURCE_REQUIRED)
    if not consent:
        raise ValidationFailed(MSG_CONSENT_REQUIRED)
    return url if kind == "practice" else None


# ---- F-P02 점검 기록 · F-P03 앱 지우기 ----

MSG_RUNNING = "점검이 끝난 뒤 지울 수 있습니다"


@dataclass(frozen=True, slots=True)
class ScanRecord:
    """점검 기록 한 줄 (F-P02 2). 완료가 아니면 점수와 개수는 None으로 보인다."""

    id: int
    app_id: int
    started_at: datetime
    input_name: str
    status: str
    score: int | None
    high: int | None
    medium: int | None
    low: int | None


def newest_first(records: Iterable[ScanRecord]) -> list[ScanRecord]:
    """F-P02 1 시작 시각 최신순, 시각이 같으면 점검 ID가 큰 것이 위."""
    return sorted(records, key=lambda r: (r.started_at, r.id), reverse=True)


def shown(record: ScanRecord) -> ScanRecord:
    """F-P02 3 상태가 `완료`가 아니면 점수와 개수를 비운다(화면은 `-`)."""
    if record.status == ScanStatus.DONE:
        return record
    return replace(record, score=None, high=None, medium=None, low=None)


def latest_done_by_app(records: Iterable[ScanRecord]) -> dict[int, ScanRecord]:
    """F-P02 4 앱마다 가장 최근 `완료` 점검 (차례는 1번과 같다)."""
    latest: dict[int, ScanRecord] = {}
    for record in newest_first(r for r in records if r.status == ScanStatus.DONE):
        latest.setdefault(record.app_id, record)
    return latest


def check_deletable(statuses: Iterable[str]) -> None:
    """F-P03 4 `진행 중` 점검이 하나라도 있으면 그 앱은 지울 수 없다."""
    if any(status == ScanStatus.RUNNING for status in statuses):
        raise ValidationFailed(MSG_RUNNING)
