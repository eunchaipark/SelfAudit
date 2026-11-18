"""로컬 키: 증거키 HMAC에만 쓰는 무작위 32바이트 (용어 '로컬 키', D-014).

화면·내보내기·로그·오류에 내지 않는다. 값은 이 모듈 밖으로 bytes로만 넘긴다.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

KEY_BYTES = 32
OWNER_ONLY = 0o600  # POSIX에서만 뜻이 있다. Windows는 %LOCALAPPDATA%의 사용자 전용 권한을 따른다


class LocalKeyError(Exception):
    """키 파일이 깨졌다. 내용은 메시지에 넣지 않는다."""


def load_or_create(path: Path) -> bytes:
    if not path.exists():
        _create(path)
    data = path.read_bytes()
    if len(data) != KEY_BYTES:
        raise LocalKeyError("로컬 키 파일의 길이가 맞지 않습니다")
    return data


def _create(path: Path) -> None:
    """임시 파일에 다 쓰고 나서 한 번에 이름을 붙인다. 쓰다 죽어도 반쯤 쓴 키가 남지 않는다."""
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), OWNER_ONLY)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(KEY_BYTES))
            f.flush()
            os.fsync(f.fileno())
        # 하드 링크는 이미 있으면 실패한다: 동시에 시작해도 먼저 만든 키 하나만 남는다
        with contextlib.suppress(FileExistsError):
            os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
