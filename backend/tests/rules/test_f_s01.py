"""F-S01 비밀값 노출 — 기능명세 예시를 그대로 옮긴다. 증거키는 테스트 키로 계산한 값."""

from __future__ import annotations

import json
import random
import re
import time
import tracemalloc

from app.contracts.engine import Finding, Location, Severity
from app.rules import secrets, text

KEY = b"selfaudit-test-key"  # 명세 '로컬 키'의 테스트 키 (가상)
AWS = "AKIAIOSFODNN7EXAMPLE"
RAW_VALUES = (AWS, "hunter2hunter2", "pw1234567", "s3cr3tPassw0rd")


def scan(content: str, path: str = "assets/index.js") -> list[Finding]:
    return list(secrets.scan_file(path, content, KEY).findings)


def only(content: str, path: str = "assets/index.js") -> Finding:
    found = scan(content, path)
    assert len(found) == 1, found
    return found[0]


# ---- 규칙 표와 예시 ----


def test_F_S01_AWS_위치3_15_가린값_증거키() -> None:
    f = only("\n\n" + " " * 13 + f'"{AWS}"')
    assert f.rule_id == "S01-AWS"
    assert f.severity is Severity.HIGH
    assert f.location == Location(3, 15)
    assert f.value == "AKIA****LE"
    assert f.evidence_key == "ce01f31bef88"
    assert f.count == 1


def test_F_S01_GENERIC_password_콜론() -> None:
    f = only('password:"hunter2hunter2"')
    assert (f.rule_id, f.severity, f.value) == ("S01-GENERIC", Severity.MEDIUM, "****")
    assert f.evidence_key == "08b236ad37f8"


def test_F_S01_GENERIC_DB_PASSWORD() -> None:
    f = only('DB_PASSWORD="s3cr3tPassw0rd"')
    assert (f.rule_id, f.value) == ("S01-GENERIC", "****")
    assert f.evidence_key == "fcbead8b6d92"


def test_F_S01_값에_공백이면_발견없음() -> None:
    assert scan('passwordHint:"Enter your password"') == []


def test_F_S01_apiKey_AKIA는_AWS하나만() -> None:
    f = only(f'apiKey:"{AWS}"')
    assert f.rule_id == "S01-AWS"


def test_F_S01_같은키3번_횟수3() -> None:
    f = only(f'a="{AWS}";\nb="{AWS}";\nc="{AWS}"')
    assert f.count == 3
    assert f.location == Location(1, 4)


def test_F_S01_자리표시값_발견없음() -> None:
    assert scan('password:"changeme"') == []
    assert scan('api_key:"xxxxxxxx"') == []
    for v in ("your-api-key-here", "placeholder", "example-secret", "<your-secret>", "${SECRET_X}"):
        assert scan(f'secret:"{v}"') == [], v
    assert scan('secret:"process.env.SECRET_VALUE"') == []


def test_F_S01_5자_비밀번호_발견없음() -> None:
    assert scan('password:"abc12"') == []


def test_F_S01_열은_코드포인트() -> None:
    assert only(f'가가"{AWS}"').location == Location(1, 4)


def test_F_S01_CRLF_2줄1열() -> None:
    f = only(f"x;\r\n{AWS}")
    assert f.location == Location(2, 1)


def test_F_S01_BOM은_열에_세지_않는다() -> None:
    assert only(f"﻿{AWS}").location == Location(1, 1)


def test_F_S01_개인키2블록() -> None:
    a = "-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----"
    b = "-----BEGIN RSA PRIVATE KEY-----\nBBBB\n-----END RSA PRIVATE KEY-----"
    found = scan(f"{a}\n{b}")
    assert [f.rule_id for f in found] == ["S01-PKEY", "S01-PKEY"]
    assert {f.value for f in found} == {"-----BEGIN RSA PRIVATE KEY-----"}
    assert found[0].evidence_key != found[1].evidence_key


def test_F_S01_개인키_END없으면_4096자까지() -> None:
    head = "-----BEGIN PRIVATE KEY-----\n"
    body = "A" * 5000
    f = only(head + body)
    assert f.rule_id == "S01-PKEY"
    expected = text.evidence_key(KEY, (head + body)[:4096])
    assert f.evidence_key == expected


def test_F_S01_URLCRED() -> None:
    f = only('"https://admin:pw1234567@internal.myapp.kr"')
    assert (f.rule_id, f.severity, f.value) == ("S01-URLCRED", Severity.HIGH, "****")
    assert f.evidence_key == "a0897d252337"


def test_F_S01_나머지_규칙표() -> None:
    cases = {
        "S01-STRIPE": ("sk_live_" + "a1B2" * 6, Severity.HIGH),
        "S01-GHTOKEN": ("ghp_" + "a1B2c3" * 6, Severity.HIGH),
        "S01-JWT": ("eyJhbGciOi.eyJzdWIiOiIx.abcdefghij12", Severity.MEDIUM),
        "S01-GAPI": ("AIza" + "A" * 35, Severity.LOW),
        "S01-STRIPE-PK": ("pk_live_" + "a1B2" * 6, Severity.INFO),
    }
    for rule, (raw, sev) in cases.items():
        f = only(f'x="{raw}"')
        assert (f.rule_id, f.severity) == (rule, sev), rule
        assert f.value == raw[:4] + "****" + raw[-2:]
        assert f.fix


def test_F_S01_가린값_8자_미만은_별표() -> None:
    assert text.mask_known("abcdefg") == "****"
    assert text.mask_known("abcdefgh") == "abcd****gh"


def test_F_S01_옆의_긴덩어리도_가린다() -> None:
    f = only(f'x:"{AWS}",y:"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"')
    assert f.rule_id == "S01-AWS"
    assert f.snippet == 'x:"AKIA****LE",y:"wJal****"'


def test_F_S01_근거조각_앞뒤40자와_줄바꿈() -> None:
    f = only("a " * 25 + "\n" + f'"{AWS}"' + "\n" + "b " * 40)
    assert f.snippet == ("a " * 25)[-38:] + ' "' + "AKIA****LE" + '" ' + ("b " * 40)[:38]


def test_F_S01_근거조각_원문이_다른_걸림도_가린다() -> None:
    f = scan(f'password:"hunter2hunter2",k:"{AWS}"')
    assert len(f) == 2
    for x in f:
        assert "hunter2" not in x.snippet
        assert AWS not in x.snippet


def test_F_S01_근거조각_대상글의_사설영역_글자는_그대로() -> None:
    # 예전 구현은 U+E000·U+E001을 표시 문자로 써서 이 입력에서 자르는 기준이 틀어졌다
    f = only(f' zz  x="{AWS}" tail')
    assert f.snippet == ' zz  x="AKIA****LE" tail'


def test_F_S01_근거조각_긴덩어리는_걸린곳에서_끊긴다() -> None:
    # 명세가 정하지 않은 부분(③이 걸린 곳을 덮을 때). 지금 동작을 지킨다(검증 T5 '고치지 않을 것')
    f = only(f"abcdefghijklmnopqrstu-{AWS}")
    assert f.snippet == "abcd****AKIA****LE"


# ---- GENERIC 다시 찾기 ----


def test_F_S01_GENERIC_버린값_안의_키워드도_찾는다() -> None:
    # 앞 키워드의 값(`pwd=`, `pwd:`)이 8자 미만이라 버려도, 그 안의 키워드부터 다시 본다
    for content, span in (
        ('password:"pwd="abcdefghij"', (15, 25)),
        ('k:"x" password:"pwd:"abcdefghij"', (21, 31)),
    ):
        got = [(c.start, c.end) for c in secrets._generic_candidates(content)]
        assert got == [span], content
        assert only(content).rule_id == "S01-GENERIC"


# 명세 규칙 표의 S01-GENERIC 정규식 그대로 (값 = 둘째 묶음)
SPEC_GENERIC = re.compile(
    r"(?i)[A-Za-z0-9_]*(password|passwd|pwd|secret|api_?key|access_?token|auth_?token|client_?secret)"
    r"[A-Za-z0-9_]*[\"']?\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']"
)


def generic_like(rng: random.Random) -> str:
    """`키 이름 + 구분자 + 값` 꼴을 흔든다. 값 안에 다른 키워드·구분자가 들고, 대소문자 무시로
    [A-Za-z]에 드는 특수 글자(K 켈빈·ı·ſ)도 넣어 걸림과 빗나감이 섞이게 한다."""

    def pick(*xs: str) -> str:
        return rng.choice(xs)

    def value() -> str:
        parts = ("abcd", "abcdefgh", "pwd", "secret", "=", ":", '"', "'", " ", "-", "x")
        return "".join(rng.choice(parts) for _ in range(rng.randint(0, 5)))

    def assignment() -> str:
        return (
            pick("", "DB_", "x", "K", "ı", "é")
            + pick("password", "PWD", "secret", "api_key", "apikey", "client_secret", "ſecret")
            + pick("", "Hint", "_1", "K")
            + pick("", '"', "'")
            + pick("", " ", "\t")
            + pick(":", "=", ":", " ")
            + pick("", " ")
            + pick('"', "'", '"', "")
            + value()
            + pick('"', "'", "", " ")
        )

    return pick("", " ", ";").join(assignment() for _ in range(rng.randint(1, 4)))


def test_F_S01_GENERIC_명세_정규식과_같은_범위() -> None:
    # 암호용이 아니라 시험 입력을 만드는 고정 씨앗 난수다
    rng = random.Random(7)  # noqa: S311
    hits = 0
    for _ in range(5000):
        s = generic_like(rng)
        spec = [(m.start(2), m.end(2)) for m in SPEC_GENERIC.finditer(s)]
        expected = [sp for sp in spec if not secrets.is_placeholder(s[sp[0] : sp[1]])]
        got = [(c.start, c.end) for c in secrets._generic_candidates(s)]
        assert got == expected, s
        hits += bool(expected)
    assert hits > 100


# ---- 겹침과 묶기 ----


def test_F_S01_겹침은_값_범위로_판정한다() -> None:
    # GENERIC의 키 이름(secret)과 값(AWS 키)이 아니라, 값 범위가 AWS와 같아 AWS만 남는다
    assert only(f'client_secret:"{AWS}"').rule_id == "S01-AWS"
    # 앞 규칙의 값 범위와 겹치지 않으면 둘 다 남는다
    found = scan(f'{AWS} password:"hunter2hunter2"')
    assert sorted(f.rule_id for f in found) == ["S01-AWS", "S01-GENERIC"]


def test_F_S01_같은_원문은_키이름이_달라도_하나로_묶는다() -> None:
    found = scan('password:"hunter2hunter2";\nsecret:"hunter2hunter2"')
    assert len(found) == 1 and found[0].count == 2


# ---- .map ----


def map_text(content: str) -> str:
    return json.dumps({"version": 3, "sources": ["src/api.ts"], "sourcesContent": [content]})


def test_F_S01_map_sourcesContent_경로() -> None:
    f = only(map_text('const x = {\n  password: "hunter2hunter2"\n}'), "assets/index.js.map")
    assert f.rule_id == "S01-GENERIC"
    assert f.path == "assets/index.js.map"
    assert f.location is None
    assert f.snippet.startswith("[src/api.ts] ")


def test_F_S01_map_JS와_map_둘다면_발견2() -> None:
    js = scan(f'k="{AWS}"', "a.js")
    mp = scan(map_text(f'k="{AWS}"'), "a.js.map")
    assert len(js) == 1 and len(mp) == 1
    assert js[0].evidence_key == mp[0].evidence_key


def test_F_S01_map이_JSON이_아니면_발견없음() -> None:
    assert scan(f"not json {AWS}", "a.js.map") == []
    assert text.parse_sourcemap("[1,2]") is None


def test_F_S01_map_항목_이름_없거나_null_항목() -> None:
    raw = json.dumps({"sources": ["a.ts"], "sourcesContent": [None, f'k="{AWS}"']})
    f = only(raw, "x.map")
    assert f.snippet.startswith("[] ")


# ---- 원문 ----


def test_F_S01_원문이_결과에_없다() -> None:
    content = (
        f'a="{AWS}";password:"hunter2hunter2";'
        'u="https://admin:pw1234567@internal.myapp.kr";DB_PASSWORD="s3cr3tPassw0rd"'
    )
    dump = repr(scan(content)) + repr(scan(map_text(content), "x.map"))
    for raw in RAW_VALUES:
        assert raw not in dump


# ---- 성능 ----


def test_F_S01_원문이_다른_걸림_많아도_선형() -> None:
    # 검증 T5 재검증 재현: 근거 조각마다 시작 목록을 다시 만들어 AWS 2만 개(420KB)에 24초였다
    # 기대값 변경 (CR-003): AWS 20,000개는 걸림 상한(F-S01 11)으로 발견 10,000 + 멈춤
    aws = " ".join(f"AKIA{i:016d}" for i in range(20_000))
    generic = " ".join(f"password='x{i:07d}abc'" for i in range(10_000))
    for content, n, stopped in ((aws, 10_000, True), (generic, 10_000, False)):
        t0 = time.perf_counter()
        result = secrets.scan_file("assets/index.js", content, KEY)
        assert time.perf_counter() - t0 < 3.0, n
        assert len(result.findings) == n
        assert result.stopped is stopped


def test_F_S01_긴식별자_정규식_폭주없음() -> None:
    cases = [
        "a" * 2_000_000,
        "password" * 200_000,
        'password="' + "-password" * 200_000,
        "https://" + "a" * 1_000_000,
        "-----BEGIN RSA PRIVATE KEY-----\n" * 50_000,
        "secret" + " " * 1_000_000,
    ]
    for c in cases:
        t0 = time.perf_counter()
        scan(c)
        assert time.perf_counter() - t0 < 5.0, c[:20]


# 명세 규칙 표의 S01-JWT 정규식 그대로 (구현은 같은 뜻을 선형으로 찾는다)
SPEC_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}")
JWT = "eyJhbGciOi.eyJzdWIiOiIx.abcdefghij12"  # 가상 토큰


def test_F_S01_JWT_eyJ반복_폭주없음() -> None:
    # 검증 b1 재현: 80KB에서 4.97초였다. 선형이면 800KB도 1초 안팎
    for n in (80_000, 800_000):
        t0 = time.perf_counter()
        assert scan("eyJ-" * (n // 4)) == []
        assert time.perf_counter() - t0 < 2.0, n


def test_F_S01_JWT_덩어리_안의_경계에서_시작() -> None:
    # 앞 `aeyJ`는 단어 경계가 아니고, `-` 뒤의 `eyJ`부터 토큰이다
    f = only(f"aeyJxx-{JWT}")
    assert (f.rule_id, f.value) == ("S01-JWT", JWT[:4] + "****" + JWT[-2:])
    # 첫 자리에서 실패한 덩어리 뒤에 나온 토큰도 찾는다
    assert only(f"eyJ-eyJ-eyJabc. {JWT}").rule_id == "S01-JWT"


def jwt_like(rng: random.Random) -> str:
    """토큰과 닮은 조각: 경계·구간 길이·점·`eyJ` 위치를 흔들어 걸림과 빗나감이 섞이게 한다."""

    def run() -> str:
        return "".join(rng.choice(["a", "-", "_", "eyJ"]) for _ in range(rng.randint(0, 12)))

    return (
        rng.choice(["", "a", "-", "é", " ", "."])
        + rng.choice(["eyJ", "eyJ", "x"])
        + run()
        + rng.choice([".", ".", " "])
        + rng.choice(["eyJ", "eyJ", ""])
        + run()
        + rng.choice([".", "-"])
        + run()
    )


def test_F_S01_JWT_명세_정규식과_같은_범위() -> None:
    # 암호용이 아니라 시험 입력을 만드는 고정 씨앗 난수다. 3000개 중 약 600개가 걸린다
    rng = random.Random(5)  # noqa: S311
    hits = 0
    for _ in range(3000):
        s = "".join(jwt_like(rng) for _ in range(rng.randint(1, 4)))
        expected = [(m.start(), m.end()) for m in SPEC_JWT.finditer(s)]
        got = [(c.start, c.end) for c in secrets._jwt_candidates(s)]
        assert got == expected, s
        hits += bool(expected)
    assert hits > 100


def peak_memory(content: str) -> int:
    tracemalloc.start()
    try:
        scan(content)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_F_S01_개인키_BEGIN반복_메모리() -> None:
    # 검증 b1 재현: 270KB에서 최대 44MB(입력의 약 160배)였다. 후보마다 원문을 복사하지 않는다
    content = "-----BEGIN PRIVATE KEY-----" * 10_000
    assert peak_memory(content) < 4 * len(content)


def test_F_S01_개인키_BEGIN여러개_END하나() -> None:
    content = "-----BEGIN PRIVATE KEY-----\n" * 32_000 + "-----END PRIVATE KEY-----"
    t0 = time.perf_counter()
    found = scan(content)
    assert time.perf_counter() - t0 < 2.0
    # 같은 END에 묶이는 뒤쪽 BEGIN은 첫 블록과 겹쳐 버려진다
    assert len(found) == 1 and found[0].count == 1
    assert found[0].evidence_key == text.evidence_key(KEY, content)
    assert peak_memory(content) < 4 * len(content)


# ---- 근거 조각 ㉠㉡ (CR-003) ----

AWS2 = "AKIAI44QH8DHBEXAMPLE"


def test_F_S01_근거조각_키워드꼴_짧은값_가림() -> None:
    # 예시 205·206: 발견이 되지 않는 짧은 값도 근거 조각에서는 가린다
    f = only(f'password:"abc12";k="{AWS}"')
    assert (f.rule_id, f.snippet) == ("S01-AWS", 'password:"****";k="AKIA****LE"')
    f = only(f'password = abc12345xyz; k="{AWS}"')
    assert f.snippet == 'password = ****; k="AKIA****LE"'


def test_F_S01_근거조각_백틱도_따옴표() -> None:
    assert only(f'secret:`abc`;k="{AWS}"').snippet == 'secret:`****`;k="AKIA****LE"'


def test_F_S01_근거조각_빈값은_그대로() -> None:
    assert only(f'password:"";k="{AWS}"').snippet == 'password:"";k="AKIA****LE"'


def test_F_S01_근거조각_S01가린뒤_키워드꼴이_덮음() -> None:
    found = scan(f'apiKey:"{AWS2}" k="{AWS}"')
    assert [f.rule_id for f in found] == ["S01-AWS", "S01-AWS"]
    assert found[1].snippet == 'apiKey:"****" k="AKIA****LE"'


def test_F_S01_근거조각_URL_사용자정보_가림() -> None:
    f = only(f'"https://abcdef123@git.example.kr/x.git";k="{AWS}"')
    assert f.snippet == '"https://****@git.example.kr/x.git";k="AKIA****LE"'
    # URLCRED가 비밀번호를 가린 뒤 남은 사용자 이름도 ㉡이 덮는다
    found = scan(f'k="{AWS}" u="https://admin:pw1234567@internal.myapp.kr"')
    assert found[0].rule_id == "S01-AWS"
    assert found[0].snippet == 'k="AKIA****LE" u="https://****@internal.myapp.kr"'


def test_F_S01_근거조각_키워드아닌이름_남음_알려진한계() -> None:
    f = only(f"var pw='hunter2';var k=\"{AWS}\"")
    assert f.snippet == "var pw='hunter2';var k=\"AKIA****LE\""


def test_F_S01_근거조각_걸린곳은_바꾸지않고_뒤도_가림() -> None:
    # 걸린 곳 자체(GENERIC 값)는 ㉠으로 다시 바꾸지 않고, 뒤쪽의 키워드 꼴은 가린다
    f = only('password:"hunter2hunter2" secret=abc;')
    assert f.snippet == 'password:"****" secret=****;'
    # 닫히지 않은 따옴표는 그 부분 끝까지 가린다
    f = only(f'k="{AWS}" token:1 password:"abc')
    assert f.snippet == 'k="AKIA****LE" token:1 password:"****'


# 명세 1절 '근거 조각' ㉠을 그대로 옮긴 정규식 (구현은 같은 뜻을 키워드 먼저 찾아 선형으로)
SPEC_SNIPPET_KV = re.compile(
    r"(?i)[A-Za-z0-9_]*(?:password|passwd|pwd|secret|api_?key|access_?token|auth_?token|client_?secret)"
    r"[A-Za-z0-9_]*[\"']?\s*[:=]\s*(?:([\"'`])(.*?)(?:\1|\Z)|([^\s\"'`,;)}\]]*))",
    re.DOTALL,
)


def spec_mask_assignments(part: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for m in SPEC_SNIPPET_KV.finditer(part):
        group = 2 if m.group(1) is not None else 3
        if m.start(group) == m.end(group):
            continue
        pieces.append(part[cursor : m.start(group)])
        pieces.append(text.MASKED)
        cursor = m.end(group)
    pieces.append(part[cursor:])
    return "".join(pieces)


def snippet_like(rng: random.Random) -> str:
    """키워드 꼴 대입을 흔든다: 따옴표 셋·없음·닫히지 않음·빈 값·끝 글자·특수 글자를 섞는다."""

    def pick(*xs: str) -> str:
        return rng.choice(xs)

    def value() -> str:
        parts = ("ab", "pwd", "=", ":", '"', "'", "`", " ", ",", ";", ")", "}", "]", "\n", "x")
        return "".join(rng.choice(parts) for _ in range(rng.randint(0, 5)))

    def assignment() -> str:
        return (
            pick("", "DB_", "x", "K", "ı", "é", "-")
            + pick("password", "PWD", "secret", "api_key", "apikey", "ſecret", "pw", "token")
            + pick("", "Hint", "_1", "K")
            + pick("", '"', "'")
            + pick("", " ", "\t", "\n")
            + pick(":", "=", ":", " ")
            + pick("", " ", "\n")
            + pick('"', "'", "`", "", "")
            + value()
            + pick('"', "'", "`", "", " ", ",")
        )

    return pick("", " ", ";").join(assignment() for _ in range(rng.randint(1, 4)))


def test_F_S01_근거조각_키워드꼴_명세와_같다() -> None:
    # 암호용이 아니라 시험 입력을 만드는 고정 씨앗 난수다
    rng = random.Random(11)  # noqa: S311
    masked = 0
    for _ in range(5000):
        s = snippet_like(rng)
        expected = spec_mask_assignments(s)
        assert text.mask_assignments(s) == expected, s
        masked += expected != s
    assert masked > 1000


# ---- .map 이름 (CR-003) ----


def map_named(name: object, content: str = 'password:"hunter2hunter2"') -> str:
    return json.dumps({"sources": [name], "sourcesContent": [content]})


def test_F_S01_map_이름_줄바꿈_탭_CRLF_DEL은_공백() -> None:
    for name in (
        "a\nb.ts",
        "a\tb.ts",
        "a\r\nb.ts",
        "a\rb.ts",
        "a\x7fb.ts",
        "a\x00b.ts",
        "a\x1bb.ts",
    ):
        assert only(map_named(name), "x.js.map").snippet == '[a b.ts] password:"****"', name
    # 글자 하나마다 공백 하나 (`\r\n`만 둘이 하나)
    assert only(map_named("a\n\nb"), "x.map").snippet.startswith("[a  b] ")


def test_F_S01_map_이름_101자는_말줄임_뒤100자() -> None:
    f = only(map_named("a" + "b" * 100), "x.map")
    assert f.snippet == "[…" + "b" * 100 + '] password:"****"'
    # 꼭 100자면 그대로이고, 이름에는 ③(긴 덩어리 가리기)을 하지 않는다
    f = only(map_named("c" * 100), "x.map")
    assert f.snippet.startswith("[" + "c" * 100 + "] ")
    # 길이는 코드 포인트로, 제어 문자를 바꾼 뒤에 센다
    f = only(map_named("가" * 99 + "\r\n"), "x.map")
    assert f.snippet.startswith("[" + "가" * 99 + " ] ")


# ---- 걸림 상한 (CR-003, CR-005) ----


def distinct_aws(n: int, start: int = 0) -> str:
    return " ".join(f"AKIA{i:016d}" for i in range(start, start + n))


def test_F_S01_걸림10000개_건너뜀없음() -> None:
    result = secrets.scan_file("a.js", distinct_aws(10_000), KEY)
    assert len(result.findings) == 10_000
    assert result.stopped is False


def test_F_S01_걸림10001개_발견10000_멈춤() -> None:
    result = secrets.scan_file("a.js", distinct_aws(10_001), KEY)
    assert len(result.findings) == 10_000
    assert result.stopped is True
    # 10,001번째(마지막 키)는 받지 않는다
    assert result.findings[-1].evidence_key == text.evidence_key(KEY, f"AKIA{9_999:016d}")


def test_F_S01_같은키20000번_횟수10000_멈춤() -> None:
    result = secrets.scan_file("a.js", " ".join([AWS] * 20_000), KEY)
    assert [(f.rule_id, f.count) for f in result.findings] == [("S01-AWS", 10_000)]
    assert result.stopped is True


def test_F_S01_걸림상한은_파일의_F_S01_전체를_멈춘다() -> None:
    # 규칙 표 차례로 보므로 AWS가 10,001번째에서 멈추면 뒤 규칙(GENERIC)은 보지 않는다
    content = distinct_aws(10_001) + ' password:"hunter2hunter2"'
    result = secrets.scan_file("a.js", content, KEY)
    assert {f.rule_id for f in result.findings} == {"S01-AWS"}
    assert result.stopped is True
    # 겹쳐 버려지는 걸림(AWS와 값이 같은 GENERIC)은 세지 않는다
    content = distinct_aws(9_999) + f' client_secret:"{AWS}"'
    result = secrets.scan_file("a.js", content, KEY)
    assert (len(result.findings), result.stopped) == (10_000, False)


def sourcemap(*items: str) -> str:
    return json.dumps(
        {"sources": [f"s{i}.ts" for i in range(len(items))], "sourcesContent": list(items)}
    )


def test_F_S01_map_항목합쳐_10001번째에서_멈춤() -> None:
    two = sourcemap(distinct_aws(5_000), distinct_aws(5_000, 5_000))
    result = secrets.scan_file("a.js.map", two, KEY)
    assert (len(result.findings), result.stopped) == (10_000, False)
    three = sourcemap(distinct_aws(5_000), distinct_aws(5_000, 5_000), distinct_aws(1, 10_000))
    result = secrets.scan_file("a.js.map", three, KEY)
    assert (len(result.findings), result.stopped) == (10_000, True)
    assert all(f.snippet.startswith(("[s0.ts] ", "[s1.ts] ")) for f in result.findings)


def test_F_S01_근거조각_키워드창_많아도_선형() -> None:
    # CR-003 기술 검토의 측정 꼴: 200자 창마다 키워드 꼴이 여럿 든 원문이 다른 걸림 1만 개
    unit = 'password:"a" pwd=b, secret:`c` api_key = d; access_token:"e" passwordpassword '
    cases = (
        "".join(f"{unit * 3}AKIA{i:016d} " for i in range(10_000)),
        "".join(f"{'password' * 25}=AKIA{i:016d} " for i in range(10_000)),
        "".join(f"{'https://' * 25}AKIA{i:016d}@ " for i in range(10_000)),
    )
    for content in cases:
        t0 = time.perf_counter()
        result = secrets.scan_file("a.js", content, KEY)
        assert time.perf_counter() - t0 < 5.0, content[:20]
        assert (len(result.findings), result.stopped) == (10_000, False)


# ---- T6·T8에 넘기는 출력 ----


def test_F_S01_출력_걸림범위는_글마다() -> None:
    content = f'k="{AWS}" password:"hunter2hunter2"'
    result = secrets.scan_file("a.js", content, KEY)
    assert [[(s.start, s.end, s.masked) for s in spans] for spans in result.spans] == [
        [(3, 23, "AKIA****LE"), (35, 49, "****")]
    ]
    raw = json.dumps({"sources": ["a.ts", "b.ts"], "sourcesContent": [f'k="{AWS}"', "x", None]})
    result = secrets.scan_file("a.js.map", raw, KEY)
    assert [[(s.start, s.end) for s in spans] for spans in result.spans] == [[(3, 23)], []]
    assert secrets.scan_file("a.js.map", "[1]", KEY).spans == ()
