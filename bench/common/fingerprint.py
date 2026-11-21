"""번들 지문 `bundle_manifest_sha256` (실험구조 2.2, F-B04. 정한 것과 근거는 2.9).

번들 폴더 아래 모든 파일을 `<상대 경로>\\t<sha256>\\n` 줄로 상대 경로의 코드 포인트 차례로 잇고,
그 글을 UTF-8로 바꾼 바이트의 sha256(소문자 16진 64자). 빈 폴더는 넣지 않는다.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Final

from common.paths import is_bundle_relpath

_TAB: Final = chr(0x09)
_LINE_END: Final = chr(0x0A)
_HASH: Final = "sha256"


class ManifestError(ValueError):
    """지문을 낼 수 없는 번들(폴더 아님, 파일 없음, 바로가기, 경로 꼴 어긋남)."""


def bundle_manifest_sha256(bundle_dir: Path) -> str:
    """번들 폴더의 지문(2.2). 번들이 한 글자라도 바뀌면 다른 값이 된다."""
    text = "".join(manifest_lines(bundle_dir))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_lines(bundle_dir: Path) -> list[str]:
    """지문을 내는 줄들(`<상대 경로>\\t<sha256>\\n`)을 차례대로. 어긋난 번들을 가려 볼 때 쓴다."""
    files = _bundle_files(bundle_dir)
    if not files:
        raise ManifestError("파일이 하나도 없는 번들")
    return [f"{rel}{_TAB}{_file_sha256(path)}{_LINE_END}" for rel, path in sorted(files.items())]


def _bundle_files(bundle_dir: Path) -> dict[str, Path]:
    if _is_link(bundle_dir) or not bundle_dir.is_dir():
        raise ManifestError("번들 폴더가 없거나 폴더가 아님")
    files: dict[str, Path] = {}
    for current, dirnames, filenames in os.walk(
        bundle_dir, onerror=_walk_failed, followlinks=False
    ):
        base = Path(current)
        for name in dirnames:
            if _is_link(base / name):
                raise ManifestError(f"번들 안에 바로가기 폴더: {_rel(bundle_dir, base / name)!r}")
        for name in filenames:
            path = base / name
            rel = _rel(bundle_dir, path)
            if _is_link(path) or not path.is_file():
                raise ManifestError(f"번들 안에 일반 파일이 아닌 것: {rel!r}")
            if _TAB in rel or not is_bundle_relpath(rel):
                raise ManifestError(f"번들 안 경로가 2.2 꼴이 아님: {rel!r}")
            files[rel] = path
    return files


def _walk_failed(error: OSError) -> None:
    # os.walk는 읽지 못한 폴더를 조용히 건너뛴다. 건너뛰면 다른 번들이 같은 지문을 낸다
    raise ManifestError(f"번들 폴더를 읽을 수 없음 ({type(error).__name__})") from error


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _rel(bundle_dir: Path, path: Path) -> str:
    return path.relative_to(bundle_dir).as_posix()


def _file_sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, _HASH).hexdigest()
