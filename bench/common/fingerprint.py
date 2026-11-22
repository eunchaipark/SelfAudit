"""번들 지문 `bundle_manifest_sha256` (실험구조 2.2, F-B04. 정한 것과 근거는 2.9).

번들 폴더 아래 모든 파일을 `<번들 안 경로>\\t<sha256>\\n` 줄로 경로의 코드 포인트 차례로 잇고,
그 글을 UTF-8로 바꾼 바이트의 sha256(소문자 16진 64자). 빈 폴더는 넣지 않는다. 파일 바이트는 그대로.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from common.paths import is_bundle_relpath

_TAB: Final = chr(0x09)
_LINE_END: Final = chr(0x0A)
_HASH: Final = "sha256"


class ManifestError(ValueError):
    """지문을 낼 수 없는 번들. 글에 번들 안 경로(또는 폴더 이름)가 있다."""


def bundle_manifest_sha256(bundle_dir: Path) -> str:
    """F-B04 번들 폴더의 지문. 번들이 한 글자라도 바뀌면 다른 값이 된다."""
    text = "".join(manifest_lines(bundle_dir))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_lines(bundle_dir: Path) -> list[str]:
    """F-B04 지문을 내는 줄들을 차례대로(어긋난 번들을 가려 볼 때 쓴다)."""
    files = _bundle_files(bundle_dir)
    if not files:
        raise ManifestError(f"파일이 하나도 없는 번들: {bundle_dir.name!r}")
    return format_manifest({rel: _file_sha256(path, rel) for rel, path in files.items()})


def format_manifest(digests: Mapping[str, str]) -> list[str]:
    """F-B04 2·3 `{번들 안 경로: sha256}` → 코드 포인트 차례의 `<경로>\\t<sha256>\\n` 줄들."""
    return [f"{rel}{_TAB}{digests[rel]}{_LINE_END}" for rel in sorted(digests)]


def _bundle_files(bundle_dir: Path) -> dict[str, Path]:
    if _is_link(bundle_dir) or not bundle_dir.is_dir():
        raise ManifestError(f"번들 폴더가 없거나 폴더가 아님: {bundle_dir.name!r}")
    files: dict[str, Path] = {}

    def walk_failed(error: OSError) -> None:
        _walk_failed(bundle_dir, error)

    for current, dirnames, filenames in os.walk(bundle_dir, onerror=walk_failed):
        base = Path(current)
        for name in dirnames:
            if _is_link(base / name):
                raise ManifestError(f"번들 안에 바로가기 폴더: {_rel(bundle_dir, base / name)!r}")
        for name in filenames:
            path = base / name
            rel = _rel(bundle_dir, path)
            _check_file(path, rel)
            files[rel] = path
    return files


def _check_file(path: Path, rel: str) -> None:
    if _is_link(path) or not path.is_file():
        raise ManifestError(f"번들 안에 일반 파일이 아닌 것: {rel!r}")
    if not is_bundle_relpath(rel):
        raise ManifestError(f"번들 안 경로가 허용 꼴(2.2)이 아님: {rel!r}")
    try:
        links = path.stat().st_nlink
    except OSError as e:
        raise ManifestError(f"읽을 수 없는 파일: {rel!r} ({type(e).__name__})") from None
    if links > 1:
        # 하드링크는 번들 밖의 같은 파일과 내용을 나눈다. 밖에서 고치면 번들이 소리 없이 바뀐다
        raise ManifestError(f"번들 안에 하드링크: {rel!r}")


def _walk_failed(bundle_dir: Path, error: OSError) -> None:
    # os.walk는 읽지 못한 폴더를 조용히 건너뛴다. 건너뛰면 다른 번들이 같은 지문을 낸다
    raise ManifestError(
        f"번들 폴더를 읽을 수 없음: {_error_rel(bundle_dir, error)!r} ({type(error).__name__})"
    ) from error


def _error_rel(bundle_dir: Path, error: OSError) -> str:
    """오류가 난 폴더의 번들 안 경로. 번들 맨 위 자신이면 `.`, 알 수 없으면 `?`."""
    if not error.filename:
        return "?"
    path = Path(str(error.filename))
    try:
        return path.relative_to(bundle_dir).as_posix()
    except ValueError:
        return "?"


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _rel(bundle_dir: Path, path: Path) -> str:
    return path.relative_to(bundle_dir).as_posix()


def _file_sha256(path: Path, rel: str) -> str:
    try:
        with path.open("rb") as f:
            return hashlib.file_digest(f, _HASH).hexdigest()
    except OSError as e:
        raise ManifestError(f"읽을 수 없는 파일: {rel!r} ({type(e).__name__})") from None
