"""F-S03 내부 주소·엔드포인트 — 기능명세 예시를 그대로 옮긴다."""

from __future__ import annotations

import json
import random
import re
import time
import tracemalloc

from app.contracts.engine import Finding, Location, Severity
from app.rules import endpoints, secrets, text

KEY = b"selfaudit-test-key"  # 명세 '로컬 키'의 테스트 키 (가상)
AWS = "AKIAIOSFODNN7EXAMPLE"
# 1번 정규식 (명세 그대로). 다시 짠 정규식과 같은 범위를 내는지 대조한다
SPEC_URL = re.compile(r"https?://(?:[^\s/@\"'`<>]+@)?[A-Za-z0-9.\-_:\[\]]+(/[^\s\"'`<>\\)]*)?")


def run(content: str, path: str = "assets/index.js") -> endpoints.EndpointsScan:
    spans = secrets.scan_file(path, content, KEY).spans
    return endpoints.scan_file(path, content, KEY, s01_spans=spans)


def scan(content: str, path: str = "assets/index.js") -> list[Finding]:
    return list(run(content, path).findings)


def only(content: str, path: str = "assets/index.js") -> Finding:
    found = scan(content, path)
    assert len(found) == 1, found
    return found[0]


def private_ips(n: int) -> str:
    return " ".join(f'"http://10.0.{i // 256}.{i % 256}/"' for i in range(n))


def distinct_aws(n: int) -> str:
    return " ".join(f"AKIA{i:016d}" for i in range(n))


# ---- 분류 (5번)와 값 ----


def test_F_S03_localhost_LOCAL() -> None:
    f = only('"http://localhost:8080/api"')
    assert (f.rule_id, f.severity, f.value) == (
        "S03-LOCAL",
        Severity.LOW,
        "http://localhost:8080/api",
    )
    # 기대값 변경 (CR-007): 증거키는 주소 글이 아니라 HMAC 12자
    assert f.evidence_key == "8da80bd3636e"
    assert f.location == Location(1, 2)
    assert f.fix == "개발용 주소가 남았습니다. 환경별 설정으로 나누세요"


def test_F_S03_LOCAL_127_0000_IPv6() -> None:
    for url in (
        "http://127.0.0.1:3000/",
        "http://127.255.0.9/",
        "http://0.0.0.0/",
        "http://[::1]:8080/x",
    ):
        assert only(f'"{url}"').rule_id == "S03-LOCAL", url
    assert only('"http://LOCALHOST/"').rule_id == "S03-LOCAL"


def test_F_S03_사설IP_PRIVATE_IP_중간() -> None:
    f = only('"http://192.168.0.12/upload"')
    assert (f.rule_id, f.severity) == ("S03-PRIVATE-IP", Severity.MEDIUM)
    assert f.fix == "내부망 주소가 드러납니다. 배포 설정에서 빼세요"
    assert only('"http://169.254.169.254/latest/meta-data"').rule_id == "S03-PRIVATE-IP"
    for url in ("http://10.1.2.3/", "http://172.16.0.1/", "http://172.31.255.255/"):
        assert only(f'"{url}"').rule_id == "S03-PRIVATE-IP", url


def test_F_S03_172_32는_URL정보() -> None:
    f = only('"http://172.32.0.1/"')
    assert (f.rule_id, f.severity) == ("S03-URL", Severity.INFO)
    assert only('"http://172.15.0.1/"').rule_id == "S03-URL"
    # 0~255 숫자 넷이 아니면 IPv4 주소가 아니다
    assert only('"http://10.0.0.256/"').rule_id == "S03-URL"


def test_F_S03_IPv4가_아닌_호스트는_URL() -> None:
    assert only('"https://10.myhost.com/"').rule_id == "S03-URL"


def test_F_S03_DEVHOST() -> None:
    f = only('"https://api.staging.myapp.kr/v1"')
    assert (f.rule_id, f.severity) == ("S03-DEVHOST", Severity.LOW)
    assert f.fix == "개발·스테이징 서버 주소가 드러납니다. 배포 번들에서 빼세요"
    assert only('"https://dev-api.myapp.kr"').rule_id == "S03-DEVHOST"
    for host in ("stage", "test", "qa", "internal", "local"):
        assert only(f'"https://{host}.myapp.kr/"').rule_id == "S03-DEVHOST", host


def test_F_S03_devices는_dev가_아님() -> None:
    f = only('"https://devices.myapp.kr"')
    assert (f.rule_id, f.severity) == ("S03-URL", Severity.INFO)
    assert f.fix == "(엔드포인트 목록. 점수에 들어가지 않음)"


def test_F_S03_최상위도메인_dev는_빼고_봄() -> None:
    assert only('"https://vitejs.dev/guide"').rule_id == "S03-URL"


def test_F_S03_값은_물음표_샵_앞까지() -> None:
    f = only('"https://api.myapp.kr/v1/users?token=abc123&v=7"')
    assert (f.rule_id, f.value) == ("S03-URL", "https://api.myapp.kr/v1/users")
    assert f.evidence_key == "74f7616adeb1"  # 기대값 변경 (CR-007)
    assert "abc123" not in f.snippet
    assert only('"https://api.myapp.kr/v1#frag"').value == "https://api.myapp.kr/v1"


def test_F_S03_사용자정보_가림() -> None:
    found = scan('"https://admin:pw1234567@internal.myapp.kr"')
    assert [(f.rule_id, f.value) for f in found] == [
        ("S03-DEVHOST", "https://****@internal.myapp.kr")
    ]
    f = found[0]
    assert f.evidence_key == "28f9b12831d0"  # 기대값 변경 (CR-007)
    for raw in ("pw1234567", "admin"):
        assert raw not in f.value + f.snippet + f.evidence_key
    # 비밀번호는 F-S01이 따로 잡는다
    s01 = secrets.scan_file("assets/index.js", '"https://admin:pw1234567@internal.myapp.kr"', KEY)
    assert [x.rule_id for x in s01.findings] == ["S01-URLCRED"]


def test_F_S03_무시호스트는_버림() -> None:
    for host in ("www.w3.org", "w3.org", "schemas.xmlsoap.org", "react.dev", "reactjs.org"):
        assert scan(f'"http://{host}/2000/svg"') == [], host
    assert scan('"https://example.com/x" "https://EXAMPLE.org:443/"') == []


def test_F_S03_같은_규칙_값은_하나로_묶는다() -> None:
    f = only('a="http://10.0.0.1/x";\nb="http://10.0.0.1/x?v=2";\nc="http://10.0.0.1/x"')
    assert (f.count, f.location) == (3, Location(1, 4))


def test_F_S03_규칙표_차례로_낸다() -> None:
    content = '"https://api.myapp.kr" "http://localhost/" "/admin" "http://10.0.0.1/" "https://qa.myapp.kr"'
    assert [f.rule_id for f in scan(content)] == [
        "S03-PRIVATE-IP",
        "S03-LOCAL",
        "S03-DEVHOST",
        "S03-ADMINPATH",
        "S03-URL",
    ]


# ---- 관리 경로 (6번) ----


def test_F_S03_admin경로_administrator는_없음() -> None:
    f = only("'/admin/users'")
    assert (f.rule_id, f.severity, f.value) == ("S03-ADMINPATH", Severity.LOW, "/admin/users")
    assert f.fix == "관리·디버그 경로가 보입니다. 서버에서 인증으로 막혀 있는지 확인하세요"
    assert scan("'/administrator'") == []


def test_F_S03_관리경로_따옴표_셋과_목록() -> None:
    for path in (
        "/admin",
        "/internal/x",
        "/debug",
        "/actuator/health",
        "/swagger",
        "/graphql-playground",
    ):
        for q in "\"'`":
            assert only(f"{q}{path}{q}").value == path, (q, path)
    # 문자열 전체가 맞아야 한다
    for s in ('"/api/admin"', '"admin"', '"/admin?x"', "'/admin\"", '"/Admin"'):
        assert [f.rule_id for f in scan(s)] == [], s


def test_F_S03_관리경로_값도_물음표_앞까지() -> None:
    f = only('"/admin/users?token=abc123"')
    assert f.value == "/admin/users"
    assert "abc123" not in f.snippet


def test_F_S03_관리경로_닫히지_않으면_그_줄에서_다음을_본다() -> None:
    assert [f.value for f in scan("x = \"/admin\n'/debug/a'")] == ["/debug/a"]
    assert [f.value for f in scan("\"a\" + '/admin'")] == ["/admin"]


# ---- 근거 조각 (1절, CR-003) ----


def test_F_S03_근거조각_키워드꼴_URL사용자정보_가림() -> None:
    content = (
        'password:"abc12";u="https://admin:pw1234567@git.example.kr/x.git";x="http://10.0.0.1/"'
    )
    found = {f.rule_id: f for f in scan(content)}
    assert (
        found["S03-PRIVATE-IP"].snippet
        == '="https://****@git.example.kr/x.git";x="http://10.0.0.1/"'
    )
    assert found["S03-URL"].snippet == (
        'password:"****";u="https://****@git.example.kr/x.git";x="http://10.0.0.1/"'
    )


def test_F_S03_S01이_멈춘파일도_짧은값_원문없음() -> None:
    tail = ' password:"hunter2hunter2" u="https://admin:pw1234567@10.0.0.1/" secret:`abc12`'
    content = distinct_aws(10_001) + tail
    s01 = secrets.scan_file("a.js", content, KEY)
    assert s01.stopped is True
    result = endpoints.scan_file("a.js", content, KEY, s01_spans=s01.spans)
    f = next(x for x in result.findings if x.rule_id == "S03-PRIVATE-IP")
    assert f.value == "https://****@10.0.0.1/"
    for raw in ("hunter2hunter2", "pw1234567", "abc12", f"AKIA{10_000:016d}"):
        assert raw not in f.snippet, f.snippet


def test_F_S03_근거조각_걸린곳_안의_S01은_가린값() -> None:
    f = only(f'"https://files.myapp.kr/{AWS}/a.png"')
    assert AWS not in f.snippet
    assert "AKIA****LE" in f.snippet


def test_F_S03_근거조각_걸린곳을_덮는_S01이면_S01_가린값만() -> None:
    # S01-GENERIC 값이 URL을 감싸면 걸린 곳은 S01 가린 값으로 보인다
    found = scan('secret:"x-http://10.0.0.1/abcdefgh"')
    assert [f.rule_id for f in found] == ["S03-PRIVATE-IP"]
    assert found[0].snippet == 'secret:"****"'


def test_F_S03_근거조각_걸린곳에_걸친_S01도_가린다() -> None:
    # S01-JWT가 URL 머리(`https`)까지 먹어 걸린 곳 앞에 걸친다 → 걸린 곳을 넓혀 가린 값으로
    jwt = "eyJhbGciOi.eyJzdWIiOi.abcdefghij"
    f = only(f"{jwt}https://10.0.0.1/x")
    assert f.rule_id == "S03-PRIVATE-IP"
    assert f.value == "eyJh****ps://10.0.0.1/x"  # 기대값 변경 (CR-007): 값도 넓힌 걸린 곳
    assert jwt not in f.snippet and "eyJzdWIiOi" not in f.snippet
    assert f.snippet == "eyJh****ps://10.0.0.1/x"


def test_F_S03_map은_항목마다_접두와_위치없음() -> None:
    raw = json.dumps(
        {"sources": ["src/api.ts", "src/b.ts"], "sourcesContent": ['u="http://10.0.0.1/"', None]}
    )
    f = only(raw, "assets/index.js.map")
    assert (f.rule_id, f.path, f.location) == ("S03-PRIVATE-IP", "assets/index.js.map", None)
    assert f.snippet == '[src/api.ts] u="http://10.0.0.1/"'
    assert scan("not json http://10.0.0.1/", "a.js.map") == []


def test_F_S03_map_S01_걸림과_같은_항목에서_가린다() -> None:
    items = [f'k="{AWS}"', f'k2="{AWS[:-1]}Y" u="http://10.0.0.1/"']
    raw = json.dumps({"sources": ["a.ts", "b.ts"], "sourcesContent": items})
    f = only(raw, "a.js.map")
    assert f.snippet == '[b.ts] k2="AKIA****LY" u="http://10.0.0.1/"'


# ---- 값 가리기·증거키 (1절, 7·8번, CR-007) ----


def test_F_S03_값_URL속_AWS_가림_증거키HMAC() -> None:
    found = scan('u="https://files.myapp.kr/AKIAIOSFODNN7EXAMPLE/a.png"')
    assert [f.rule_id for f in found] == ["S03-URL"]
    f = found[0]
    assert f.value == "https://files.myapp.kr/AKIA****LE/a.png"
    assert f.evidence_key == "e037ba6aaca9"
    assert f.snippet == 'u="https://files.myapp.kr/AKIA****LE/a.png"'
    assert AWS not in f.value + f.snippet + f.evidence_key


def test_F_S03_키만다른_두주소_발견2() -> None:
    content = (
        'a="https://files.myapp.kr/AKIAIOSFODNN7EXAMPLE/a.png",'
        'b="https://files.myapp.kr/AKIAI44QH8DHBEXAMPLE/a.png"'
    )
    found = scan(content)
    assert [(f.rule_id, f.value, f.count) for f in found] == [
        ("S03-URL", "https://files.myapp.kr/AKIA****LE/a.png", 1),
        ("S03-URL", "https://files.myapp.kr/AKIA****LE/a.png", 1),
    ]
    assert [f.evidence_key for f in found] == ["e037ba6aaca9", "6e7c083a5d80"]


def test_F_S03_GENERIC이_덮으면_값_가림() -> None:
    f = only('secret:"x-http://10.0.0.1/abcdefgh"')
    assert (f.rule_id, f.value) == ("S03-PRIVATE-IP", "****")
    assert f.evidence_key == "c41e5cc43500"
    assert f.snippet == 'secret:"****"'


def test_F_S03_걸친_S01만큼_넓힌_값과_증거키() -> None:
    f = only("eyJhbGciOi.eyJzdWIiOi.abcdefghijhttps://10.0.0.1/x")
    assert (f.rule_id, f.value) == ("S03-PRIVATE-IP", "eyJh****ps://10.0.0.1/x")
    assert f.snippet == "eyJh****ps://10.0.0.1/x"
    assert f.evidence_key == "d7e9f900c62d"


def test_F_S03_관리경로_물음표뒤_뗌() -> None:
    f = only("'/admin/users?token=abc123'")
    assert (f.rule_id, f.value) == ("S03-ADMINPATH", "/admin/users")
    assert f.evidence_key == "4e553bf2e925"
    assert f.snippet == "'/admin/users'"


def test_F_S03_관리경로_키워드값_가림() -> None:
    f = only("'/admin/login;password=hunter2'")
    assert (f.rule_id, f.value) == ("S03-ADMINPATH", "/admin/login;password=****")
    assert f.evidence_key == "2c82ed4ee970"
    assert f.snippet == "'/admin/login;password=****'"


def test_F_S03_값_200자_넘으면_자름_증거키는_자르기전() -> None:
    url = "https://api.myapp.kr/" + "a" * 300
    assert len(url) == 321
    f = only(f'"{url}"')
    assert f.rule_id == "S03-URL"
    assert f.value == "https://api.myapp.kr/" + "a" * 179 + "…"
    assert len(f.value) == 201
    assert f.evidence_key == "e3910c4674eb"
    assert f.snippet == '"https://api.myapp.kr/a****…"'


def test_F_S03_값_자르기는_가린_뒤_200자까지_원문을_본다() -> None:
    # 가린 값이 짧아 뒤 글이 앞으로 당겨진다: 원문 앞 200자만 가리면 값이 모자란다
    keys = "/".join(f"AKIA{i:016d}" for i in range(30))
    url = f"https://x.kr/{keys}/tail"
    f = only(f'"{url}"')
    full = "https://x.kr/" + "/".join(f"AKIA****{i % 100:02d}" for i in range(30)) + "/tail"
    assert f.value == full[:200] + "…"
    assert "AKIA0000" not in f.value


def test_F_S03_묶기는_가리기_전_글로() -> None:
    # ㈀㈁만 한 글이 같으면 하나: 쿼리만 다른 두 주소는 묶이고, 경로가 다르면 값이 같아 보여도 둘
    found = scan('"http://10.0.0.1/x?a=1" "http://10.0.0.1/x#b"')
    assert [(f.value, f.count) for f in found] == [("http://10.0.0.1/x", 2)]


# ---- 걸림 상한 (9번, CR-003·005) ----


def test_F_S03_서로다른사설IP_10001개_발견10000_멈춤() -> None:
    result = run(private_ips(10_001))
    assert len(result.findings) == 10_000
    assert {f.rule_id for f in result.findings} == {"S03-PRIVATE-IP"}
    assert result.stopped is True
    assert result.findings[-1].value == f"http://10.0.{9_999 // 256}.{9_999 % 256}/"


def test_F_S03_사설IP_10000개_건너뜀없음() -> None:
    result = run(private_ips(10_000))
    assert (len(result.findings), result.stopped) == (10_000, False)


def test_F_S03_S01과_S03이_따로_세고_둘다_멈춤() -> None:
    # 예시 291: 사설 IP 10,001개와 AWS 키 10,001개 (건너뜀 한 줄로 합치는 것은 T8)
    content = private_ips(10_001) + " " + distinct_aws(10_001)
    s01 = secrets.scan_file("a.js", content, KEY)
    s03 = endpoints.scan_file("a.js", content, KEY, s01_spans=s01.spans)
    assert (len(s01.findings), s01.stopped) == (10_000, True)
    assert {f.rule_id for f in s01.findings} == {"S01-AWS"}
    assert (len(s03.findings), s03.stopped) == (10_000, True)
    assert {f.rule_id for f in s03.findings} == {"S03-PRIVATE-IP"}


def test_F_S03_묶기_전에_세고_버림은_세지_않는다() -> None:
    result = run(" ".join(['"http://10.0.0.1/"'] * 10_001))
    assert [(f.rule_id, f.count) for f in result.findings] == [("S03-PRIVATE-IP", 10_000)]
    assert result.stopped is True
    result = run(private_ips(10_000) + ' "http://www.w3.org/2000/svg"' * 100)
    assert (len(result.findings), result.stopped) == (10_000, False)


def test_F_S03_map_항목합쳐_10001번째에서_멈춤() -> None:
    def ips(lo: int, n: int) -> str:
        return " ".join(f'"http://10.1.{i // 256}.{i % 256}/"' for i in range(lo, lo + n))

    two = json.dumps({"sources": ["a", "b"], "sourcesContent": [ips(0, 5_000), ips(5_000, 5_000)]})
    assert run(two, "a.js.map").stopped is False
    three = json.dumps(
        {
            "sources": ["a", "b", "c"],
            "sourcesContent": [ips(0, 5_000), ips(5_000, 5_000), ips(10_000, 1)],
        }
    )
    result = run(three, "a.js.map")
    assert (len(result.findings), result.stopped) == (10_000, True)


# ---- 명세 정규식과 같은 범위 ----


def test_F_S03_URL_명세_정규식과_같은_범위() -> None:
    rng = random.Random(6)  # noqa: S311
    pieces = [
        "http://",
        "https://",
        "a",
        "Z",
        "9",
        ".",
        "-",
        "_",
        ":",
        "[",
        "]",
        "@",
        "/",
        "?",
        "#",
    ]
    pieces += [" ", '"', "'", "`", "<", ">", "\\", ")", "%", "\n", "가"]
    hits = 0
    for _ in range(3_000):
        s = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 40)))
        spec = [(m.start(), m.end()) for m in SPEC_URL.finditer(s)]
        mine = [(m.start(), m.end()) for m in endpoints._URL.finditer(s)]
        assert mine == spec, s
        hits += len(spec)
    assert hits > 1_000


# ---- 성능 ----


def test_F_S03_정규식_머리말_반복_폭주없음() -> None:
    cases = (
        "http://" * 100_000,
        "https://a@" * 100_000,
        "https://a:" * 100_000,
        '"/' * 200_000,
        "'/admin" * 100_000,
        "\"/admin/'`/" * 100_000,
        ("x" * 1_000 + '"/') * 500 + "\n",
        # 닫히지 않는 관리 경로 후보: 줄마다 따옴표 종류당 한 번만 줄 끝까지 읽는다
        ("'/admin/" + "x" * 50 + "\n") * 20_000,
        '"/admin/' + "`/debug/x" * 100_000,
    )
    for content in cases:
        t0 = time.perf_counter()
        run(content, "a.js")
        assert time.perf_counter() - t0 < 5.0, content[:20]


def test_F_S03_S01_걸림_많아도_근거조각_선형() -> None:
    # 발견마다 S01 걸림 목록을 복사하면 제곱이 된다(검증 T5 재검증과 같은 꼴)
    content = " ".join(f'AKIA{i:016d} "http://10.0.{i // 256}.{i % 256}/"' for i in range(10_000))
    spans = secrets.scan_file("a.js", content, KEY).spans  # S01 시간은 재지 않는다
    t0 = time.perf_counter()
    result = endpoints.scan_file("a.js", content, KEY, s01_spans=spans)
    assert time.perf_counter() - t0 < 5.0
    assert (len(result.findings), result.stopped) == (10_000, False)
    assert all("AKIA0000" not in f.snippet for f in result.findings)


def test_F_S03_map_항목많아도_쌓지_않는다() -> None:
    n = 20_000
    content = json.dumps({"sources": ["s" * 300] * n, "sourcesContent": [text.BOM + "x" * 150] * n})
    spans = secrets.scan_file("a.js.map", content, KEY).spans
    tracemalloc.start()
    try:
        result = endpoints.scan_file("a.js.map", content, KEY, s01_spans=spans)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result.findings == ()
    assert peak < 2.2 * len(content)
