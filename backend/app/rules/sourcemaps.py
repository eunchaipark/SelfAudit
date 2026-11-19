"""F-S02 소스맵 노출 (FR-04). 순수 함수: 파일 하나의 글과 번들 경로 목록을 받아 발견을 돌려준다.

`.map` 파일은 내용(1번), JS·CSS 파일은 마지막 sourceMappingURL(2~4번)을 본다.
건너뛴 `.map` 안내(6번)는 F-I01 건너뜀 목록으로 정한다. 증거키는 `-`이다(5번).
"""

from __future__ import annotations

import re
from collections.abc import Container, Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import unquote

from app.contracts.engine import Finding, Location, Severity, Skipped, SkipReason
from app.rules import text

MAP_SUFFIX = ".map"
REFERENCE_SUFFIXES = (".js", ".mjs", ".cjs", ".css")
NO_EVIDENCE = "-"
INLINE_KEEP = 30  # data: 값은 앞 30자 + `…` (F-S02 출력)
_MARKERS = ("//# sourceMappingURL=", "//@ sourceMappingURL=", "/*# sourceMappingURL=")
_BLOCK_MARKER = "/*#"
_BLOCK_END = "*/"
_VALUE = re.compile(r"\S*+")
_DATA_PREFIX = "data:"
# '주소 형식'(F-S02 4): `http:` `file:` 같은 스킴, 또는 `//`로 시작하는 주소
_ADDRESS = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:|//")
_QUERY_OR_FRAGMENT = re.compile(r"[?#]")

NOTICE_SKIPPED_MAPS = (
    "건너뛴 소스맵 {n}개는 내용을 점검하지 않았습니다. 배포에서 .map을 뺐는지 확인하세요"
)


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    severity: Severity
    fix: str


MAP_CONTENT = Rule(
    "S02-MAP-CONTENT",
    Severity.HIGH,
    "배포 빌드에서 소스맵을 끄거나(.map 빼기), 오류 추적 서비스에만 따로 올리세요",
)
INLINE = Rule("S02-INLINE", Severity.HIGH, "인라인 소스맵을 끄세요 (배포 빌드 설정)")
MAP_PATHS = Rule(
    "S02-MAP-PATHS", Severity.LOW, "원본 폴더 구조가 드러납니다. 배포에서 .map을 빼세요"
)
DANGLING = Rule(
    "S02-DANGLING",
    Severity.LOW,
    "번들에는 없지만 서버에 .map이 따로 올라갔는지 확인하세요",
)


@dataclass(frozen=True, slots=True)
class SourcemapScan:
    """F-S02 파일 하나의 결과.

    not_sourcemap이면 건너뜀 `NOT_SOURCEMAP`이고 F-S01·S03도 보지 않는다.
    """

    findings: tuple[Finding, ...]
    not_sourcemap: bool


def bundle_paths(targets: Iterable[str], skipped: Iterable[Skipped]) -> frozenset[str]:
    """F-S02 3 '번들에 있음'의 경로: 점검 대상과 F-I01 건너뜀 목록 (CR-004).

    글자 그대로 비교한다 (CR-005).
    """
    return frozenset(targets) | {s.path for s in skipped}


def skipped_notice(skipped: Iterable[Skipped]) -> str | None:
    """F-S02 6 건너뛴 소스맵 안내 (CR-004). 확장자 `.map`(대소문자 무시)인 건너뜀 n개.

    이 규칙이 낸 `소스맵 형식 아님`은 세지 않는다.
    """
    n = sum(
        1
        for s in skipped
        if s.reason is not SkipReason.NOT_SOURCEMAP and s.path.lower().endswith(MAP_SUFFIX)
    )
    return NOTICE_SKIPPED_MAPS.format(n=n) if n else None


def scan_file(
    path: str,
    content: str,
    *,
    in_bundle: Container[str],
    s01_spans: Sequence[Sequence[text.MaskedSpan]],
) -> SourcemapScan:
    """F-S02 소스맵 노출 (FR-04). `.map`은 1번, `.js .mjs .cjs .css`는 2~4번, 그 밖은 발견 없음.

    in_bundle: `bundle_paths`의 결과. s01_spans: 같은 파일의 `secrets.scan_file(...).spans`
    (JS·CSS의 근거 조각 ②에 쓴다).
    """
    lower = path.lower()
    if lower.endswith(MAP_SUFFIX):
        return _scan_map(path, content)
    if not lower.endswith(REFERENCE_SUFFIXES):
        return SourcemapScan((), not_sourcemap=False)
    spans = s01_spans[0] if s01_spans else ()
    finding = _scan_reference(path, text.strip_bom(content), in_bundle, spans)
    return SourcemapScan((finding,) if finding else (), not_sourcemap=False)


def _scan_map(path: str, content: str) -> SourcemapScan:
    """F-S02 1. `sourcesContent`에 빈 문자열·null이 아닌 항목이 있으면 MAP-CONTENT.

    그렇지 않고 `sources`가 1개 이상이면 MAP-PATHS. JSON 객체가 아니면 건너뜀 (예외, CR-002).
    """
    data = text.load_sourcemap(content)
    if data is None:
        return SourcemapScan((), not_sourcemap=True)
    contents = data.get("sourcesContent")
    sources = data.get("sources")
    n_content = (
        sum(1 for item in contents if item is not None and item != "")
        if isinstance(contents, list)
        else 0
    )
    n_sources = len(sources) if isinstance(sources, list) else 0
    if n_content:
        rule = MAP_CONTENT
    elif n_sources:
        rule = MAP_PATHS
    else:
        return SourcemapScan((), not_sourcemap=False)
    value = f"sourcesContent {n_content}개 / sources {n_sources}개"
    finding = _finding(rule, path, None, value, snippet="")
    return SourcemapScan((finding,), not_sourcemap=False)


def _last_reference(content: str) -> tuple[int, int] | None:
    """마지막 sourceMappingURL 값의 범위. 세 꼴 중 가장 뒤에 나온 것 (F-S02 2)."""
    best = -1
    marker = ""
    for m in _MARKERS:
        at = content.rfind(m)
        if at > best:
            best, marker = at, m
    if best == -1:
        return None
    start = best + len(marker)
    value = _VALUE.match(content, start)
    end = value.end() if value else start
    if marker.startswith(_BLOCK_MARKER):
        close = content.find(_BLOCK_END, start, end)
        if close != -1:
            end = close
    return (start, end) if end > start else None


def resolve_reference(path: str, value: str) -> str | None:
    """F-S02 3. `?`·`#` 뒤를 떼고 %-디코딩한 뒤 경로로 푼다.

    `/`로 시작하면 번들 맨 위, 아니면 파일의 폴더 기준. 번들 밖으로 나가면 None.
    `\\`는 구분자로 보지 않는다(번들 경로의 구분자는 `/`).
    """
    cut = _QUERY_OR_FRAGMENT.search(value)
    decoded = unquote(value[: cut.start()] if cut else value)
    parts: list[str] = [] if decoded.startswith("/") else path.split("/")[:-1]
    for seg in decoded.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def _scan_reference(
    path: str, content: str, in_bundle: Container[str], spans: Sequence[text.MaskedSpan]
) -> Finding | None:
    """F-S02 2~4. data: 값이면 INLINE, 풀어 낸 `.map`이 번들에 없거나 밖이거나 주소면 DANGLING."""
    found = _last_reference(content)
    if found is None:
        return None
    start, end = found
    value = content[start:end]
    if value[: len(_DATA_PREFIX)].lower() == _DATA_PREFIX:
        rule = INLINE
        edits: tuple[text.MaskedSpan, ...] = ()
        if len(value) > INLINE_KEEP:
            edits = (text.MaskedSpan(start + INLINE_KEEP, end, text.ELLIPSIS),)
            value = value[:INLINE_KEEP] + text.ELLIPSIS
    else:
        if _ADDRESS.match(value) is None:
            resolved = resolve_reference(path, value)
            if resolved is not None and resolved in in_bundle:
                return None
        rule = DANGLING
        edits = ()
    location = text.LineCursor(content).locate(start)
    snippet = text.hit_snippet(content, spans, start, end, edits)
    return _finding(rule, path, location, value, snippet)


def _finding(rule: Rule, path: str, location: Location | None, value: str, snippet: str) -> Finding:
    return Finding(
        rule_id=rule.rule_id,
        severity=rule.severity,
        path=path,
        location=location,
        count=1,
        value=value,
        snippet=snippet,
        evidence_key=NO_EVIDENCE,
        fix=rule.fix,
    )
