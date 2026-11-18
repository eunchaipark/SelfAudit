"""로컬 키: 증거키 HMAC에만 쓰는 무작위 32바이트 (용어 '로컬 키', D-014).

화면·내보내기·로그·오류에 내지 않는다. 값은 이 모듈 밖으로 bytes로만 넘긴다.
"""

from __future__ import annotations

import secrets
from pathlib import Path

KEY_BYTES = 32


class LocalKeyError(Exception):
    """키 파일이 깨졌다. 내용은 메시지에 넣지 않는다."""


def load_or_create(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        data = secrets.token_bytes(KEY_BYTES)
        try:
            with path.open("xb") as f:
                f.write(data)
        except FileExistsError:
            data = path.read_bytes()
    if len(data) != KEY_BYTES:
        raise LocalKeyError("로컬 키 파일의 길이가 맞지 않습니다")
    return data
