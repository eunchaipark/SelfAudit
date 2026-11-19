"""F-C01 발견 지문 — 기능명세 예시를 그대로 옮긴다."""

from __future__ import annotations

import hashlib
import hmac
import random
import time

import pytest

from app.compare import engine, fingerprint
from app.contracts.engine import Finding, Location, Severity
from tests.conftest import TEST_KEY

EVIDENCE_KEY_LEN = 12  # 증거키 = HMAC 앞 12자 (D-014)
LARGE_NAME_LEN = 300_000  # 수백 KB 이름에서도 선형인지 본다
TIME_LIMIT_S = 1.0


def hmac_test_key(raw: str) -> str:
    """테스트 키로 증거키를 만든다 (명세 '로컬 키', F-S01 7)."""
    digest = hmac.new(TEST_KEY, raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:EVIDENCE_KEY_LEN]


def make_finding(
    rule_id: str,
    path: str,
    evidence_key: str,
    location: Location | None = None,
    count: int = 1,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.HIGH,
        path=path,
        location=location,
        count=count,
        value="****",
        snippet="",
        evidence_key=evidence_key,
        fix="",
    )


# ---- 정규화 경로 (처리 규칙 1) ----


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("assets/index-BmR2x9Qa.js", "assets/index.js"),
        ("assets/index-Bm-2x9Qa.js", "assets/index.js"),
        ("assets/index-abcdefgh.js", "assets/index.js"),
        ("assets/chunk-12345678.js", "assets/chunk.js"),
    ],
)
def test_F_C01_vite해시_제거(path: str, expected: str) -> None:
    assert engine.normalize_path(path) == expected


def test_F_C01_webpack_map_정규화() -> None:
    assert engine.normalize_path("static/js/main.3f9a1c2b.js.map") == "static/js/main.js.map"


def test_F_C01_react는_그대로() -> None:
    assert engine.normalize_path("assets/vendor-react.js") == "assets/vendor-react.js"


def test_F_C01_알려진한계_reactdom() -> None:
    assert engine.normalize_path("assets/vendor-reactdom.js") == "assets/vendor.js"


def test_F_C01_app_js는_그대로() -> None:
    assert engine.normalize_path("app.js") == "app.js"


def test_F_C01_폴더부분은_그대로() -> None:
    # 폴더 이름이 해시처럼 생겨도 파일 이름(마지막 조각)에만 적용한다
    assert engine.normalize_path("x-abcdefgh.js/y.3f9a1c2b.js/app.js") == (
        "x-abcdefgh.js/y.3f9a1c2b.js/app.js"
    )
    assert engine.normalize_path("x-abcdefgh.js/index-BmR2x9Qa.js") == "x-abcdefgh.js/index.js"


def test_F_C01_webpack이_먼저_하나만() -> None:
    # ①이 맞으면 ②는 적용하지 않는다
    assert engine.normalize_path("app-abcdefgh.3f9a1c2b.js") == "app-abcdefgh.js"


# ---- 지문 (처리 규칙 2·3) ----


def test_F_C01_S01AWS_지문() -> None:
    key = hmac_test_key("AKIAIOSFODNN7EXAMPLE")
    assert key == "ce01f31bef88"
    finding = make_finding("S01-AWS", "assets/index-BmR2x9Qa.js", key, Location(3, 15))
    assert fingerprint(finding) == "S01-AWS|assets/index.js|ce01f31bef88"


def test_F_C01_S04_지문() -> None:
    finding = make_finding("S04-VULNLIB", "assets/vendor-Ab12Cd34.js", "jquery@3.4.1")
    assert fingerprint(finding) == "S04-VULNLIB|assets/vendor.js|jquery@3.4.1"


def test_F_C01_위치와_횟수는_지문에_없다() -> None:
    a = make_finding("S01-AWS", "assets/index-BmR2x9Qa.js", "ce01f31bef88", Location(3, 15), 1)
    b = make_finding("S01-AWS", "assets/index-Xy98Zw76.js", "ce01f31bef88", None, 3)
    assert fingerprint(a) == fingerprint(b)


# ---- 성능 (정규식이 입력 길이에 선형) ----


def spec_normalize_name(name: str) -> str:
    """명세 정규식을 이름 전체에 그대로 건 결과 (짧은 이름에서 비교용)."""
    for pattern in (engine.WEBPACK_HASH, engine.VITE_HASH):
        m = pattern.match(name)
        if m is not None:
            return m.group(1) + m.group(2)
    return name


def test_F_C01_좁힌창이_명세정규식과_같다() -> None:
    rng = random.Random(20261119)  # noqa: S311 - 보안 용도가 아닌 고정 씨앗 테스트 데이터
    alphabet = "ab0f9Z.-_!x"
    for _ in range(20_000):
        name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        assert engine.normalize_path(name) == spec_normalize_name(name), name


@pytest.mark.parametrize(
    "name",
    [
        ("." + "0" * 8) * (LARGE_NAME_LEN // 9) + "!",
        ("-" + "a" * 8) * (LARGE_NAME_LEN // 9) + "!",
        ("-" + "a" * 8 + ".") * (LARGE_NAME_LEN // 10) + "!",
        "a" * LARGE_NAME_LEN,
        "." * LARGE_NAME_LEN,
        "-" * LARGE_NAME_LEN + ".js",
    ],
)
def test_F_C01_긴이름_정규식_폭주없음(name: str) -> None:
    start = time.perf_counter()
    engine.normalize_path("assets/" + name)
    assert time.perf_counter() - start < TIME_LIMIT_S
