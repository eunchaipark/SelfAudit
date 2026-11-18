"""F-S01 비밀값 노출 (FR-03). 순수 함수: 파일 텍스트와 로컬 키를 받아 발견을 돌려준다.

정규식은 대상(최대 50MB 한 줄)에 돌리므로 되돌아가기 폭주를 피한다 (코드규칙 3장).
S01-GENERIC은 키워드를 먼저 찾고 양옆으로 넓히며, 값은 먹보 한정자(possessive)로 읽는다.
"""

from __future__ import annotations

import re
from bisect import bisect_left, insort
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.contracts.engine import Finding, Location, Severity
from app.rules import text

MAP_SUFFIX = ".map"
PKEY_MAX = 4096  # END가 없을 때 BEGIN부터 읽는 글자 수


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    severity: Severity
    fix: str


# 규칙 표 순서 = 겹칠 때의 우선순위 (F-S01 2)
RULES: tuple[Rule, ...] = (
    Rule("S01-PKEY", Severity.HIGH, "개인키를 번들에서 빼고, 키를 새로 만들어 바꾸세요"),
    Rule("S01-AWS", Severity.HIGH, "키를 즉시 비활성화하고, AWS 호출은 서버로 옮기세요"),
    Rule("S01-STRIPE", Severity.HIGH, "비밀 키를 다시 발급하고, 결제 호출은 서버로 옮기세요"),
    Rule("S01-GHTOKEN", Severity.HIGH, "토큰을 폐기하고 번들에서 빼세요"),
    Rule(
        "S01-URLCRED",
        Severity.HIGH,
        "주소에 박힌 비밀번호를 바꾸고, 주소에서 계정 정보를 빼세요",
    ),
    Rule("S01-JWT", Severity.MEDIUM, "번들에 박힌 토큰을 빼고, 로그인 후 받아 쓰게 하세요"),
    Rule("S01-GENERIC", Severity.MEDIUM, "비밀값을 서버 환경 변수로 옮기세요"),
    Rule(
        "S01-GAPI",
        Severity.LOW,
        "공개용 키라면 키 제한(HTTP 리퍼러·API 제한)이 걸려 있는지 확인하세요",
    ),
    Rule(
        "S01-STRIPE-PK",
        Severity.INFO,
        "공개용 키입니다. 비밀 키(sk_)와 섞이지 않았는지만 확인하세요",
    ),
)
_RULE_ORDER = {r.rule_id: i for i, r in enumerate(RULES)}
_RULE_BY_ID = {r.rule_id: r for r in RULES}

# (규칙ID, 정규식, 값 묶음 번호). 묶음 0 = 전체 매치
_SIMPLE: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("S01-AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), 0),
    ("S01-STRIPE", re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b"), 0),
    ("S01-GHTOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), 0),
    ("S01-URLCRED", re.compile(r"https?://[^\s/:@\"'`<>]+:([^\s/@\"'`<>]++)@"), 1),
    (
        "S01-JWT",
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}"),
        0,
    ),
    ("S01-GAPI", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), 0),
    ("S01-STRIPE-PK", re.compile(r"\bpk_live_[0-9A-Za-z]{24,}\b"), 0),
)
_PKEY_BEGIN = re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")

# S01-GENERIC: 키워드 → 그 뒤 식별자·구분자 → 값. 앞쪽 `[A-Za-z0-9_]*`는 쓰지 않는다.
_GENERIC_KEYWORD = re.compile(
    r"password|passwd|pwd|secret|api_?key|access_?token|auth_?token|client_?secret",
    re.IGNORECASE,
)
_IDENT_RUN = re.compile(r"[A-Za-z0-9_]*")
_GENERIC_TAIL = re.compile(r"[A-Za-z0-9_]*[\"']?\s*[:=]\s*[\"']")
_GENERIC_VALUE = re.compile(r"[^\"'\s]*+")
GENERIC_MIN = 8
_QUOTES = "\"'"
_PLACEHOLDER_EXACT = ("changeme", "placeholder")
_PLACEHOLDER_PREFIX = ("your", "example", "process.env")


@dataclass(frozen=True, slots=True)
class _Candidate:
    rule_id: str
    start: int
    end: int
    raw: str
    masked: str


def is_placeholder(value: str) -> bool:
    """S01-GENERIC 값이 자리표시값인가 (F-S01 3). 대소문자 무시."""
    low = value.lower()
    return (
        len(set(low)) == 1
        or low in _PLACEHOLDER_EXACT
        or low.startswith(_PLACEHOLDER_PREFIX)
        or (low.startswith("<") and low.endswith(">"))
        or (low.startswith("${") and low.endswith("}"))
    )


def _simple_candidates(content: str) -> Iterator[_Candidate]:
    for rule_id, pattern, group in _SIMPLE:
        for m in pattern.finditer(content):
            raw = m.group(group)
            masked = text.MASKED if rule_id == "S01-URLCRED" else text.mask_known(raw)
            yield _Candidate(rule_id, m.start(group), m.end(group), raw, masked)


def _pkey_candidates(content: str) -> Iterator[_Candidate]:
    # 종류별로 "이 자리 이후 첫 END"를 기억해 되풀이 탐색(느려짐)을 막는다
    end_of_kind: dict[str, int] = {}
    for m in _PKEY_BEGIN.finditer(content):
        kind = m.group(1) or ""
        marker = f"-----END {kind}PRIVATE KEY-----"
        found = end_of_kind.get(kind)
        if found is None or (found != -1 and found < m.end()):
            found = content.find(marker, m.end())
            end_of_kind[kind] = found
        end = found + len(marker) if found != -1 else min(len(content), m.start() + PKEY_MAX)
        yield _Candidate("S01-PKEY", m.start(), end, content[m.start() : end], m.group(0))


def _generic_candidates(content: str) -> Iterator[_Candidate]:
    pos = 0
    while True:
        kw = _GENERIC_KEYWORD.search(content, pos)
        if kw is None:
            return
        tail = _GENERIC_TAIL.match(content, kw.end())
        if tail is None:
            ident = _IDENT_RUN.match(content, kw.end())
            pos = max(kw.end(), ident.end() if ident else 0)  # 같은 식별자 안 키워드는 건너뜀
            continue
        value = _GENERIC_VALUE.match(content, tail.end())
        if value is None:
            pos = kw.end()
            continue
        pos = max(value.end(), kw.end())
        raw = value.group()
        closed = value.end() < len(content) and content[value.end()] in _QUOTES
        if len(raw) >= GENERIC_MIN and closed and not is_placeholder(raw):
            yield _Candidate("S01-GENERIC", value.start(), value.end(), raw, text.MASKED)


def _accepted(content: str) -> list[_Candidate]:
    """규칙 표 순서로 걸림을 받고, 값 범위가 먼저 받은 것과 겹치면 버린다 (F-S01 2)."""
    sources: tuple[Callable[[str], Iterator[_Candidate]], ...] = (
        _pkey_candidates,
        _simple_candidates,
        _generic_candidates,
    )
    candidates = [c for source in sources for c in source(content)]
    candidates.sort(key=lambda c: (_RULE_ORDER[c.rule_id], c.start))
    taken: list[tuple[int, int]] = []  # 받은 범위 (시작 순서, 겹치지 않음)
    kept: list[_Candidate] = []
    for c in candidates:
        i = bisect_left(taken, (c.start, c.end))
        if i > 0 and taken[i - 1][1] > c.start:
            continue
        if i < len(taken) and taken[i][0] < c.end:
            continue
        insort(taken, (c.start, c.end))
        kept.append(c)
    kept.sort(key=lambda c: c.start)
    return kept


@dataclass(slots=True)
class _Group:
    rule_id: str
    masked: str
    evidence: str
    first_snippet: str
    first_location: Location | None
    count: int


def scan_file(path: str, content: str, key: bytes) -> list[Finding]:
    """F-S01 비밀값 노출 (FR-03). `.map`은 JSON을 풀어 `sourcesContent` 항목마다 본다 (F-S01 9).

    `.map`이 JSON이 아니면 발견 없음(건너뜀 목록은 F-S02가 맡는다).
    """
    groups: dict[tuple[str, str], _Group] = {}
    if path.lower().endswith(MAP_SUFFIX):
        for name, item in text.parse_sourcemap(content) or []:
            _collect(groups, text.strip_bom(item), key, f"[{name}] ", locate=False)
    else:
        _collect(groups, text.strip_bom(content), key, "", locate=True)
    ordered = sorted(groups.values(), key=lambda g: _RULE_ORDER[g.rule_id])
    return [
        Finding(
            rule_id=g.rule_id,
            severity=_RULE_BY_ID[g.rule_id].severity,
            path=path,
            location=g.first_location,
            count=g.count,
            value=g.masked,
            snippet=g.first_snippet,
            evidence_key=g.evidence,
            fix=_RULE_BY_ID[g.rule_id].fix,
        )
        for g in ordered
    ]


def _collect(
    groups: dict[tuple[str, str], _Group], content: str, key: bytes, prefix: str, *, locate: bool
) -> None:
    kept = _accepted(content)
    if not kept:
        return
    spans = [text.MaskedSpan(c.start, c.end, c.masked) for c in kept]
    index = text.LineIndex(content) if locate else None
    for i, c in enumerate(kept):
        group = groups.get((c.rule_id, c.raw))
        if group is not None:
            group.count += 1
            continue
        groups[(c.rule_id, c.raw)] = _Group(
            rule_id=c.rule_id,
            masked=c.masked,
            evidence=text.evidence_key(key, c.raw),
            first_snippet=prefix + text.build_snippet(content, spans, i),
            first_location=index.locate(c.start) if index else None,
            count=1,
        )
