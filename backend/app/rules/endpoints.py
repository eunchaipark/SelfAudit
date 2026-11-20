"""F-S03 내부 주소·엔드포인트 (FR-05). 순수 함수: 파일 하나의 글과 그 파일의 S01 걸림 범위를 받는다.

URL(1~5번)과 관리 경로(6번)를 글의 앞에서부터 차례로 받고, 파일 하나에서 받은 걸림이 상한을 넘으면
멈춘다(9번). 근거 조각은 S01과 같은 도구에 그 글의 S01 걸림을 넣어 만든다(②, CR-003).
정규식은 먹보 한정자로 읽어 되돌아가기 폭주를 피한다 (코드규칙 3장).
"""

from __future__ import annotations

import heapq
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from app.contracts.engine import Finding, Location, Severity
from app.core.limits import HIT_LIMIT
from app.rules import text

MAP_SUFFIX = ".map"
USERINFO_MASKED = text.MASKED + "@"

# 1번 정규식과 같은 뜻. 묶음: 스킴, 사용자 정보(`…@`), 호스트(포트 포함), 경로
_URL = re.compile(
    r"(https?://)((?:[^\s/@\"'`<>]++@)?)([A-Za-z0-9.\-_:\[\]]++)((?:/[^\s\"'`<>\\)]*+)?)"
)
_QUERY_OR_FRAGMENT = re.compile(r"[?#]")
_IPV4 = re.compile(r"([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})")
IPV4_MAX = 255
LOOPBACK_FIRST = 127  # 5번 ② `127.*`
# 5번 ③ (첫 숫자, 둘째 숫자 아래, 위): `10.*`, `172.16.*~172.31.*`, `192.168.*`, `169.254.*`
PRIVATE_RANGES = ((10, 0, IPV4_MAX), (172, 16, 31), (192, 168, 168), (169, 254, 254))
_LABEL_SPLIT = re.compile(r"[.\-]")

IGNORED_HOSTS = frozenset(
    {"www.w3.org", "w3.org", "schemas.xmlsoap.org", "react.dev", "reactjs.org"}
    | {"example.com", "example.org"}
)
LOCAL_HOSTS = frozenset({"localhost", "[::1]", "0.0.0.0"})  # noqa: S104 - 찾는 값이다
DEV_LABELS = frozenset({"dev", "staging", "stage", "test", "qa", "internal", "local"})

# 6번: 따옴표로 감싼 문자열 전체 (`^`·`$` 대신 fullmatch(글, 시작, 끝)를 쓴다)
_ADMIN_WORDS = r"(?:admin|internal|debug|actuator|swagger|graphql-playground)"
# 후보: 따옴표 + `/<낱말>` 다음이 `/`이거나 같은 따옴표. 후보가 같은 줄에서 닫히면 늘 맞으므로
# 후보마다 도는 일이 걸림 상한만큼으로 묶인다
_ADMIN_OPEN = re.compile(rf"([\"'`])/{_ADMIN_WORDS}(?=/|\1)")
_ADMIN_PATH = re.compile(rf"/{_ADMIN_WORDS}(?:/.*)?")


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    severity: Severity
    fix: str


# 규칙 표 순서 = 파일 안 발견 차례
RULES: tuple[Rule, ...] = (
    Rule("S03-PRIVATE-IP", Severity.MEDIUM, "내부망 주소가 드러납니다. 배포 설정에서 빼세요"),
    Rule("S03-LOCAL", Severity.LOW, "개발용 주소가 남았습니다. 환경별 설정으로 나누세요"),
    Rule(
        "S03-DEVHOST",
        Severity.LOW,
        "개발·스테이징 서버 주소가 드러납니다. 배포 번들에서 빼세요",
    ),
    Rule(
        "S03-ADMINPATH",
        Severity.LOW,
        "관리·디버그 경로가 보입니다. 서버에서 인증으로 막혀 있는지 확인하세요",
    ),
    Rule("S03-URL", Severity.INFO, "(엔드포인트 목록. 점수에 들어가지 않음)"),
)
_RULE_ORDER = {r.rule_id: i for i, r in enumerate(RULES)}
_RULE_BY_ID = {r.rule_id: r for r in RULES}


@dataclass(frozen=True, slots=True)
class EndpointsScan:
    """F-S03 파일 하나의 결과. stopped: 걸림 상한(F-S03 9)으로 멈췄다 → 건너뜀 `TOO_MANY_HITS`."""

    findings: tuple[Finding, ...]
    stopped: bool


@dataclass(frozen=True, slots=True)
class _Hit:
    """받아들인 걸림 하나.

    [start, end)는 근거 조각의 걸린 곳, edits는 걸린 곳을 값 모양으로 바꾸는 곳.
    """

    rule_id: str
    start: int
    end: int
    value: str
    edits: tuple[text.MaskedSpan, ...]


def _hit_start(hit: _Hit) -> int:
    return hit.start


def _host_of(host_port: str) -> str:
    """4번: 소문자로, 포트를 뗀다. `[::1]:8080` → `[::1]`."""
    host = host_port.lower()
    if host.startswith("["):
        close = host.find("]")
        return host[: close + 1] if close != -1 else host
    return host.split(":", 1)[0]


def _ipv4(host: str) -> tuple[int, int, int, int] | None:
    """0~255 숫자 네 개인 IPv4 주소면 그 숫자들."""
    m = _IPV4.fullmatch(host)
    if m is None:
        return None
    a, b, c, d = (int(g) for g in m.groups())
    if max(a, b, c, d) > IPV4_MAX:
        return None
    return a, b, c, d


def _is_private(ip: tuple[int, int, int, int]) -> bool:
    """5번 ③: 첫 두 숫자가 사설·링크 로컬 범위 안인가."""
    return any(a == ip[0] and lo <= ip[1] <= hi for a, lo, hi in PRIVATE_RANGES)


def classify(host: str) -> str | None:
    """5번: 호스트 하나의 규칙ID. 무시 호스트면 None (버림)."""
    if host in IGNORED_HOSTS:
        return None
    ip = _ipv4(host)
    if host in LOCAL_HOSTS or (ip is not None and ip[0] == LOOPBACK_FIRST):
        return "S03-LOCAL"
    if ip is not None and _is_private(ip):
        return "S03-PRIVATE-IP"
    head = host.rsplit(".", 1)[0] if "." in host else ""  # 최상위 도메인을 뺀 호스트
    if head and any(label in DEV_LABELS for label in _LABEL_SPLIT.split(head)):
        return "S03-DEVHOST"
    return "S03-URL"


def _url_hits(content: str) -> Iterator[_Hit]:
    """1~5번. 무시 호스트는 내지 않는다(받아들인 걸림이 아니다)."""
    for m in _URL.finditer(content):
        rule_id = classify(_host_of(m.group(3)))
        if rule_id is None:
            continue
        start, end = m.start(), m.end()
        host_start = m.start(3)
        edits: list[text.MaskedSpan] = []
        value_head = m.group(1)
        if m.group(2):
            edits.append(text.MaskedSpan(m.end(1), host_start, USERINFO_MASKED))
            value_head += USERINFO_MASKED
        cut = _QUERY_OR_FRAGMENT.search(content, host_start, end)
        value_end = cut.start() if cut else end
        if value_end < end:
            edits.append(text.MaskedSpan(value_end, end, ""))
        value = value_head + content[host_start:value_end]
        yield _Hit(rule_id, start, end, value, tuple(edits))


def _admin_hits(content: str) -> Iterator[_Hit]:
    """6번. 따옴표 + 관리 경로로 여는 문자열마다 같은 따옴표까지(같은 줄)를 본다.

    닫히면 그 문자열 뒤부터, 줄 안에서 닫히지 않으면 다음 글자부터 다시 찾는다. 닫히지 않은 따옴표
    뒤로는 그 줄에 같은 따옴표가 없으므로 줄마다 따옴표 종류당 한 번만 끝까지 읽는다(선형).
    `"`·`'`는 줄을 넘지 못하고, 넘는 글은 `.`이 줄바꿈을 받지 않아 어차피 맞지 않는다.
    """
    pos = 0
    line_end = -1  # 지금 줄의 끝. 줄마다 한 번만 찾는다(한 줄 50MB에서도 선형)
    while (m := _ADMIN_OPEN.search(content, pos)) is not None:
        quote = m.start()
        if quote > line_end:
            line_end = content.find("\n", quote)
            if line_end == -1:
                line_end = len(content)
        close = content.find(content[quote], quote + 1, line_end)
        if close == -1:
            pos = quote + 1
            continue
        pos = close + 1
        start = quote + 1
        if _ADMIN_PATH.fullmatch(content, start, close) is None:
            continue
        cut = _QUERY_OR_FRAGMENT.search(content, start, close)
        value_end = cut.start() if cut else close
        edits = (text.MaskedSpan(value_end, close, ""),) if value_end < close else ()
        yield _Hit("S03-ADMINPATH", start, close, content[start:value_end], edits)


def _hits(content: str) -> Iterator[_Hit]:
    """URL과 관리 경로를 글의 앞에서부터 차례로 낸다(상한을 세는 차례)."""
    return heapq.merge(_url_hits(content), _admin_hits(content), key=_hit_start)


@dataclass(slots=True)
class _Group:
    rule_id: str
    value: str
    first_snippet: str
    first_location: Location | None
    count: int


def _texts(path: str, content: str) -> Iterator[tuple[str | None, str]]:
    """(`.map` 항목 이름 또는 None, BOM을 뗀 글).

    `secrets._texts`와 같은 차례로 낸다(S01 걸림과 짝).
    """
    if not path.lower().endswith(MAP_SUFFIX):
        yield None, text.strip_bom(content)
        return
    for name, item in text.parse_sourcemap(content) or []:
        yield name, text.strip_bom(item)


def scan_file(
    path: str, content: str, *, s01_spans: Sequence[Sequence[text.MaskedSpan]]
) -> EndpointsScan:
    """F-S03 내부 주소·엔드포인트 (FR-05). `.map`은 `sourcesContent` 항목마다 본다(F-S01처럼).

    s01_spans: 같은 파일의 `secrets.scan_file(...).spans`(글마다 S01 걸림). S01이 멈춘 파일도 받은
    것까지 근거 조각 ②에 넣는다 (CR-003). 걸림 상한(9번)은 파일 하나(`.map`은 항목을 합쳐)에서 S01과
    따로 센다. 10,001번째가 나오면 그것은 받지 않고 남은 항목도 보지 않는다 (CR-005).
    """
    groups: dict[tuple[str, str], _Group] = {}
    accepted = 0
    stopped = False
    for i, (name, item) in enumerate(_texts(path, content)):
        spans = s01_spans[i] if i < len(s01_spans) else ()
        accepted, stopped = _collect(groups, item, spans, name, accepted)
        if stopped:
            break
    ordered = sorted(groups.values(), key=lambda g: _RULE_ORDER[g.rule_id])
    findings = tuple(
        Finding(
            rule_id=g.rule_id,
            severity=_RULE_BY_ID[g.rule_id].severity,
            path=path,
            location=g.first_location,
            count=g.count,
            value=g.value,
            snippet=g.first_snippet,
            evidence_key=g.value,  # 8번: 증거키 = 3번까지 거친 값
            fix=_RULE_BY_ID[g.rule_id].fix,
        )
        for g in ordered
    )
    return EndpointsScan(findings=findings, stopped=stopped)


def _collect(
    groups: dict[tuple[str, str], _Group],
    content: str,
    spans: Sequence[text.MaskedSpan],
    map_name: str | None,
    accepted: int,
) -> tuple[int, bool]:
    """글 하나의 걸림을 받아 묶는다 (7번). (지금까지 받은 수, 멈췄나)를 돌려준다.

    날글(map_name None)만 위치를 세고, `.map` 항목은 접두를 붙인다.
    근거 조각은 묶음의 첫 걸림에만 만든다.
    """
    cursor = text.LineCursor(content) if map_name is None else None
    prefix: str | None = None
    for hit in _hits(content):
        if accepted >= HIT_LIMIT:
            return accepted, True
        accepted += 1
        group = groups.get((hit.rule_id, hit.value))
        if group is not None:
            group.count += 1
            continue
        if prefix is None:
            prefix = "" if map_name is None else text.map_prefix(map_name)
        groups[(hit.rule_id, hit.value)] = _Group(
            rule_id=hit.rule_id,
            value=hit.value,
            first_snippet=prefix + text.hit_snippet(content, spans, hit.start, hit.end, hit.edits),
            first_location=cursor.locate(hit.start) if cursor else None,
            count=1,
        )
    return accepted, False
