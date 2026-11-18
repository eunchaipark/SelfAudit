"""F-P01 앱 등록의 판정 (순수). DB·시각을 쓰지 않는다."""

from __future__ import annotations

import unicodedata

from app.contracts.schemas import AppKind
from app.core.errors import ValidationFailed
from app.core.limits import APP_NAME_MAX

MSG_NAME_EMPTY = "앱 이름을 입력하세요"
MSG_NAME_TOO_LONG = "앱 이름은 40자까지입니다"
MSG_DUPLICATE = "같은 이름의 앱이 있습니다"
MSG_SOURCE_REQUIRED = "공개 연습앱은 출처 주소(https://…)가 필요합니다"
MSG_CONSENT_REQUIRED = "직접 만든 앱이나 분석이 허용된 연습용 앱만 점검할 수 있습니다"
HTTPS_PREFIX = "https://"


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
    """F-P01 4·5 출처 주소와 확인란. 저장할 출처 주소(없으면 None)를 돌려준다."""
    url = (source_url or "").strip() or None
    if kind == "practice" and (url is None or not url.startswith(HTTPS_PREFIX)):
        raise ValidationFailed(MSG_SOURCE_REQUIRED)
    if not consent:
        raise ValidationFailed(MSG_CONSENT_REQUIRED)
    return url
