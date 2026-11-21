"""번들 경로 꼴(허용 꼴)·번들 안 파일 열기·결과 경로 정규화 (실험구조 2.2·2.5·2.9).

이 모듈은 다른 common 모듈을 부르지 않는다(계약 검증기가 `bundle-relpath` 꼴로 이것을 부른다).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PureWindowsPath
from typing import Final

MAX_RELPATH_CHARS: Final = 300  # 2.2 길이 상한
MAX_SEGMENT_CHARS: Final = 255  # NTFS 이름 하나의 한도
# 마디 안에 둘 수 없는 ASCII 글자: 구분자 `\`, 드라이브·ADS의 `:`, Windows 금지 `*?"<>|`
_FORBIDDEN_CHARS: Final = frozenset('\\:*?"<>|')
# 둘 수 없는 글자 종류: 제어(Cc), 서식(Cf: 방향·폭 없는 글자), 서로게이트(Cs), 사용자 정의(Co),
# 배정 안 됨(Cn), 줄·문단 구분(Zl·Zp)
_FORBIDDEN_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_SUPERSCRIPT_DIGITS: Final = chr(0xB9) + chr(0xB2) + chr(0xB3)  # COM¹ 등도 장치 이름이다
_RESERVED_STEMS: Final = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"{dev}{d}" for dev in ("COM", "LPT") for d in "0123456789" + _SUPERSCRIPT_DIGITS}
)
_SEPARATOR: Final = "/"
_DOT_SLASH: Final = "./"


class BundlePathError(ValueError):
    """번들 안 경로가 허용 꼴이 아니거나, 풀어 보니 번들 밖을 가리킨다."""


def is_bundle_relpath(path: str) -> bool:
    """번들 안 경로 허용 꼴(2.2·2.9). 계약의 `format: bundle-relpath`가 이 함수다.

    전체 1~300자, `/`로 나눈 마디마다: 비어 있지 않음, 255자까지, 앞뒤 공백 없음, 끝이 `.` 아님
    (그래서 `.`·`..` 마디도 없음), `\\ : * ? " < > |`와 제어·서식·서로게이트·배정 안 된 글자 없음,
    확장자 앞 이름이 Windows 장치 이름(`CON`·`NUL`·`COM1`…, 대소문자 무시)이 아님.
    """
    if not 1 <= len(path) <= MAX_RELPATH_CHARS:
        return False
    return all(_is_segment(segment) for segment in path.split(_SEPARATOR))


def _is_segment(segment: str) -> bool:
    if not 1 <= len(segment) <= MAX_SEGMENT_CHARS:
        return False
    if segment[0] == " " or segment[-1] in " .":
        return False
    if any(ch in _FORBIDDEN_CHARS or _is_forbidden_category(ch) for ch in segment):
        return False
    stem = segment.split(".", 1)[0].rstrip(" ").upper()
    return stem not in _RESERVED_STEMS


def _is_forbidden_category(ch: str) -> bool:
    return unicodedata.category(ch) in _FORBIDDEN_CATEGORIES


def resolve_in_bundle(bundle_dir: Path, rel: str) -> Path:
    """번들 안 경로를 디스크 경로로. 허용 꼴이 아니거나 풀어 보니(링크·정션 포함) 밖이면 멈춘다.

    번들 안 파일을 여는 쪽은 모두 이 함수를 거친다(보안코딩 '허용 폴더 안').
    """
    if not is_bundle_relpath(rel):
        raise BundlePathError(f"번들 안 경로가 허용 꼴(2.2)이 아님: {rel!r}")
    root = bundle_dir.resolve()
    path = root.joinpath(*rel.split(_SEPARATOR)).resolve()
    if not path.is_relative_to(root):
        raise BundlePathError(f"번들 밖을 가리킴: {rel!r}")
    return path


def normalize_finding_path(file: str, target_root: str | None) -> str:
    """결과의 `file`을 정답지 경로 꼴에 맞춘다(2.5 조건 2, F-G02 1, F-R06 4 공통).

    ① `\\` → `/` ② 대상 폴더 절대 경로(①을 하고 끝에 `/`)로 글자 그대로 시작하면 지움
    ③ 앞의 `./`를 남지 않을 때까지 지움. `..`·대소문자(드라이브 글자 포함)·앞의 `/`는 바꾸지 않는다.
    `target_root`가 None이면 ②를 건너뛴다. 절대 경로가 아니면 ValueError.
    """
    path = file.replace("\\", _SEPARATOR)
    if target_root is not None:
        path = path.removeprefix(_root_prefix(target_root))
    while path.startswith(_DOT_SLASH):
        path = path.removeprefix(_DOT_SLASH)
    return path


def _root_prefix(target_root: str) -> str:
    root = target_root.replace("\\", _SEPARATOR).rstrip(_SEPARATOR)
    if not (root.startswith(_SEPARATOR) or PureWindowsPath(target_root).is_absolute()):
        raise ValueError("대상 폴더는 절대 경로여야 한다")
    return root + _SEPARATOR
