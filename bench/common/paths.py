"""번들 경로 꼴과 결과 경로 정규화 (실험구조 2.2 '경로 꼴', 2.5 조건 2, 근거는 2.9)."""

from __future__ import annotations

from functools import cache
from pathlib import PureWindowsPath
from typing import Final

from common.contracts import Json, load_schema, validate

_DOT_SLASH: Final = "./"
_DRIVE_COLON: Final = 1  # `C:`에서 `:`의 자리


@cache
def _relpath_schema() -> tuple[dict[str, Json], dict[str, Json]]:
    root = load_schema("answers")
    defs = root["$defs"]
    assert isinstance(defs, dict)
    relpath = defs["relpath"]
    assert isinstance(relpath, dict)
    return relpath, root


def is_bundle_relpath(path: str) -> bool:
    """번들 안 경로 꼴(2.2): 맨 위 기준 상대, `/` 구분, 앞의 `/`·`./`, `.`·`..` 마디, `\\` 없음.

    꼴은 계약 `answers.schema.json`의 `$defs.relpath`에서 읽는다(두 곳에 두지 않는다).
    """
    relpath, root = _relpath_schema()
    return not validate(path, relpath, root)


def normalize_finding_path(file: str, target_root: str | None) -> str:
    """결과의 `file`을 정답지 경로 꼴에 맞춘다(2.5 조건 2, F-R06·F-G02 공통).

    ① `\\` → `/` ② `target_root`(대상 폴더 절대 경로)로 시작하고 바로 뒤가 `/`면 그 부분을 지움
    ③ 앞의 `./`를 남지 않을 때까지 지움. `..`·대소문자·앞의 `/`는 바꾸지 않는다(글자 그대로 비교).
    `target_root`가 None이면 ②를 건너뛴다. 절대 경로가 아니면 ValueError.
    """
    path = file.replace("\\", "/")
    if target_root is not None:
        path = _strip_root(path, _absolute_root(target_root))
    while path.startswith(_DOT_SLASH):
        path = path.removeprefix(_DOT_SLASH)
    return path


def _absolute_root(target_root: str) -> str:
    root = target_root.replace("\\", "/").rstrip("/")
    if not (root.startswith("/") or PureWindowsPath(target_root).is_absolute()):
        raise ValueError("대상 폴더는 절대 경로여야 한다")
    return root


def _strip_root(path: str, root: str) -> str:
    prefix = root + "/"
    if _fold_drive(path).startswith(_fold_drive(prefix)):
        return path[len(prefix) :]
    return path


def _fold_drive(path: str) -> str:
    """드라이브 글자 한 글자만 소문자로(2.9: 도구마다 `C:`·`c:`가 다르다). 그 밖은 그대로."""
    if (
        len(path) > _DRIVE_COLON
        and path[_DRIVE_COLON] == ":"
        and path[0].isascii()
        and path[0].isalpha()
    ):
        return path[0].lower() + path[1:]
    return path
