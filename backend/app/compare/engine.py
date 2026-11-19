"""F-C01 발견 지문 (FR-10). 순수 계산: DB·네트워크·시각을 쓰지 않는다."""

from __future__ import annotations

import re

from app.contracts.engine import Finding

# 명세 F-C01 처리 규칙 1의 정규식 그대로. ①이 안 맞을 때만 ②.
WEBPACK_HASH = re.compile(r"^(.*)\.[0-9a-f]{8,32}(\.[A-Za-z0-9.]+)$")
VITE_HASH = re.compile(r"^(.*)-[A-Za-z0-9_-]{8}(\.[A-Za-z0-9.]+)$")

# 확장자 묶음 `[A-Za-z0-9.]`에 드는 글자
_EXT_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.")
# Vite 해시 조각(`-` + 8자)은 확장자 묶음 밖의 글자(`-`, `_`)를 가질 수 있다
_VITE_PIECE_LEN = 9
_FIELD_SEP = "|"


def _match_window_start(name: str) -> int:
    """정규식이 걸릴 수 있는 가장 앞 자리.

    두 정규식 모두 이름 끝의 `(\\.[A-Za-z0-9.]+)$`와, 그 바로 앞의 해시 조각(webpack은 확장자
    글자뿐, Vite는 `-` + 8자)만 본다. 그래서 끝에서부터 확장자 글자가 이어지는 구간과 그 앞
    9자만 보면 결과가 같다. 이름 전체에 `(.*)`을 걸면 `.`이 많은 긴 이름에서 되짚기가
    제곱으로 늘어난다(30,000자 0.5초). 창을 좁혀 입력 길이에 선형으로 만든다.
    """
    run_start = len(name)
    while run_start > 0 and name[run_start - 1] in _EXT_CHARS:
        run_start -= 1
    return max(0, run_start - _VITE_PIECE_LEN)


def _normalize_name(name: str) -> str:
    # `(.*)`의 `.`은 줄바꿈을 건너지 못한다. 줄바꿈이 든 이름은 전체 정규식과 같게 그대로 둔다
    if "\n" in name:
        return name
    start = _match_window_start(name)
    head, tail = name[:start], name[start:]
    for pattern in (WEBPACK_HASH, VITE_HASH):
        m = pattern.match(tail)
        if m is not None:
            return head + m.group(1) + m.group(2)
    return name


def normalize_path(path: str) -> str:
    """F-C01 정규화 경로: 파일 이름(마지막 조각)의 빌드 해시만 지운다. 폴더 부분은 그대로."""
    folder, sep, name = path.rpartition("/")
    return folder + sep + _normalize_name(name)


def fingerprint(finding: Finding) -> str:
    """F-C01 발견 지문 (FR-10): `<규칙ID>|<정규화 경로>|<증거키>`. 위치·횟수는 넣지 않는다."""
    return _FIELD_SEP.join((finding.rule_id, normalize_path(finding.path), finding.evidence_key))
