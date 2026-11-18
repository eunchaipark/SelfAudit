"""F-P01 앱 등록의 판정 (순수). DB·시각을 쓰지 않는다."""

from __future__ import annotations

import unicodedata
from urllib.parse import urlsplit

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
