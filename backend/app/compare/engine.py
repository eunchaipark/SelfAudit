"""F-C01 발견 지문과 F-C02 두 점검 비교 (FR-10). 순수 계산: DB·네트워크·시각을 쓰지 않는다."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.contracts.engine import Finding, Location, Severity

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


# ---- F-C02 두 점검 비교 ----

# F-S06 3 정렬: 심각도는 높음 → 정보
_SEVERITY_RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}


@dataclass(frozen=True, slots=True)
class ScanSide:
    """비교할 점검 하나. findings는 그 점검의 발견 전부(정렬 순서)."""

    scan_id: int
    started_at: datetime
    score: int
    rules_version: str | None
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class ComparedFinding:
    """묶음에 든 발견 하나. path는 정규화 경로, 남음이면 후의 발견 (F-C02 3)."""

    rule_id: str
    severity: Severity
    path: str
    location: Location | None
    value: str
    severity_changed: bool


@dataclass(frozen=True, slots=True)
class Comparison:
    """F-C02 출력. 묶음마다 F-S06 정렬."""

    before: ScanSide
    after: ScanSide
    score_change: int
    fixed: tuple[ComparedFinding, ...]
    remaining: tuple[ComparedFinding, ...]
    new: tuple[ComparedFinding, ...]
    rules_version_differs: bool


def order_sides(x: ScanSide, y: ScanSide) -> tuple[ScanSide, ScanSide]:
    """F-C02 1: 시작 시각이 앞선 쪽이 전, 같으면 점검 ID가 작은 쪽이 전."""
    if (x.started_at, x.scan_id) <= (y.started_at, y.scan_id):
        return x, y
    return y, x


def _compared(finding: Finding, *, severity_changed: bool = False) -> ComparedFinding:
    return ComparedFinding(
        rule_id=finding.rule_id,
        severity=finding.severity,
        path=normalize_path(finding.path),
        location=finding.location,
        value=finding.value,
        severity_changed=severity_changed,
    )


def _sort_key(item: ComparedFinding) -> tuple[int, str, str, int, int, int]:
    # F-S06 3: 심각도 → 규칙ID → 경로 → 위치(줄, 열, `-`는 맨 뒤). 경로는 화면에 보이는 정규화 경로
    loc = item.location
    no_location = 1 if loc is None else 0
    line = 0 if loc is None else loc.line
    column = 0 if loc is None else loc.column
    return (_SEVERITY_RANK[item.severity], item.rule_id, item.path, no_location, line, column)


def _sorted(items: list[ComparedFinding]) -> tuple[ComparedFinding, ...]:
    return tuple(sorted(items, key=_sort_key))


def _group_by_fingerprint(findings: tuple[Finding, ...]) -> dict[str, list[Finding]]:
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[fingerprint(finding)].append(finding)
    return groups


def compare_scans(x: ScanSide, y: ScanSide) -> Comparison:
    """F-C02 두 점검 비교 (FR-10). 고른 순서와 상관없이 같은 결과를 낸다."""
    before, after = order_sides(x, y)
    before_groups = _group_by_fingerprint(before.findings)
    after_groups = _group_by_fingerprint(after.findings)
    fixed: list[ComparedFinding] = []
    remaining: list[ComparedFinding] = []
    new: list[ComparedFinding] = []
    for key, olds in before_groups.items():
        news = after_groups.get(key, [])
        kept = min(len(olds), len(news))
        for old, cur in zip(olds[:kept], news[:kept], strict=True):
            remaining.append(_compared(cur, severity_changed=old.severity != cur.severity))
        fixed.extend(_compared(old) for old in olds[kept:])
    for key, news in after_groups.items():
        kept = min(len(before_groups.get(key, [])), len(news))
        new.extend(_compared(cur) for cur in news[kept:])
    return Comparison(
        before=before,
        after=after,
        score_change=after.score - before.score,
        fixed=_sorted(fixed),
        remaining=_sorted(remaining),
        new=_sorted(new),
        rules_version_differs=before.rules_version != after.rules_version,
    )
