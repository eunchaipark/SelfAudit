"""F-B02 가짜 값 만들기·규칙 5·나눔 (기능명세 F-B02 규칙 4·5 예시, 값은 가상).

서비스 꼴을 걸리게 하는 시험 값은 조각을 이어 만든다 — 이 파일 글에 그 꼴이 그대로 있으면
검사 '실험자료'가 이 파일을 막는다.
"""

from __future__ import annotations

import base64
import re

import pytest

from common.contracts import Json
from sources.build_tools import fake

KEY = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1LTQ4MjEzIiwicm9sZSI6InN0YWZmIiwiaWF0IjoxNzYzNjAwMDAwfQ"
    ".CIGvPrG9Eh50XRQy_a-fJJhyPFfaSLRAkpSPO61n8TI"
)
CLAIMS: dict[str, Json] = {"sub": "u-48213", "role": "staff", "iat": 1763600000}


def test_F_B02_가짜값_예시_키_비밀번호_토큰() -> None:
    assert fake.make_key("easy-1", "E1-01", "zelto_") == KEY
    assert len(KEY) == 38
    assert fake.make_password("easy-1", "E1-07") == "Q0HQvzBsuZJRMH46"
    token = fake.make_token("easy-1", "E1-02", CLAIMS)
    assert token == TOKEN
    assert len(token) == 147


def test_F_B02_토큰서명_표준꼴() -> None:
    """T22 반려 1 2(총괄 대리): 서명 43자는 32바이트의 표준 base64url — 풀었다 다시 쓰면 같은 글.

    명세 F-B02 예시의 끝 글자 `…61n8TJ`는 표준 꼴이 아니라 `…61n8TI`로 바뀌었다(문서가 예시를 고친다).
    """
    for i in range(50):
        sig = fake.make_token("easy-1", f"T-{i:02d}", CLAIMS).split(".")[2]
        raw = base64.urlsafe_b64decode(sig + "=")
        assert len(raw) == 32
        assert base64.urlsafe_b64encode(raw).decode().rstrip("=") == sig
        assert sig[-1] in fake.SIGNATURE_LAST_CHARS
    assert TOKEN.endswith("61n8TI")


def test_F_B02_인코딩_예시_길이() -> None:
    encoded = base64.b64encode(KEY.encode()).decode()
    assert encoded == "emVsdG9fYjBDNGZyWXp0NEJLT0JHUjBFT2NsaWVicHJwcERZTzg="
    assert len(encoded) == 52
    hexed = KEY.encode().hex()
    assert len(hexed) == 76
    assert hexed.startswith("7a656c746f5f")
    assert hexed.endswith("594f38")


def test_F_B02_가짜값_시드같으면_같음() -> None:
    assert fake.make_key("easy-1", "E1-01", "zelto_") == fake.make_key("easy-1", "E1-01", "zelto_")
    assert fake.make_password("easy-2", "E2-03") == fake.make_password("easy-2", "E2-03")
    assert fake.make_key("easy-1", "E1-01", "zelto_") != fake.make_key("easy-2", "E1-01", "zelto_")
    assert fake.make_key("easy-1", "E1-01", "zelto_") != fake.make_key("easy-1", "E1-02", "zelto_")


def test_F_B02_가짜값_서비스꼴아님() -> None:
    made = [
        fake.make_key(bundle, entry, prefix)
        for bundle in ("easy-1", "normal-1", "hard-1")
        for entry, prefix in (("A-01", "zelto_"), ("A-02", "quvar_"), ("A-03", "mirtak_"))
    ]
    made += [fake.make_password("easy-1", f"P-{i:02d}") for i in range(20)]
    made += [fake.make_token("easy-1", f"T-{i:02d}", CLAIMS) for i in range(5)]
    for value in made:
        assert fake.fake_value_problems(value) == []
        assert re.fullmatch(
            r"[a-z]{4,6}_[0-9A-Za-z]{32}|[0-9A-Za-z]{16}|[\w-]+\.[\w-]+\.[\w-]{43}", value
        )


@pytest.mark.parametrize(
    "prefix", ["sk_", "ghpx_", "demox_", "whsec_", "zel_", "zeltoqq_", "Zelto_", "zelto", "abcde_"]
)
def test_F_B02_접두어_거절(prefix: str) -> None:
    """명세 예시 `sk_`·`ghpx_`(㉯)·`demox_`(㉰), 허용 목록 밖(`whsec_`·`abcde_`), 꼴 틀림."""
    with pytest.raises(fake.FakeValueError):
        fake.make_key("easy-1", "E1-01", prefix)


def test_F_B02_허용접두어_규칙5_지킴() -> None:
    """허용 목록의 접두어마다 ⓐ 꼴, ㉯(실제 서비스 접두어로 시작 안 함), ㉰(미끼 낱말 없음)."""
    assert len(fake.FAKE_PREFIXES) == 30
    for prefix in fake.FAKE_PREFIXES:
        assert fake.PREFIX.fullmatch(prefix)
        assert not prefix.startswith(fake.REAL_PREFIXES)
        assert not fake.has_decoy_word(prefix)
        assert fake.fake_value_problems(prefix + "Q" * 32) == []


def test_F_B02_접두어없는_값에는_접두어규칙_안걸림() -> None:
    assert fake.fake_value_problems("sk3kQ0HQvzBsuZJR") == []  # 비밀번호 꼴(접두어 없음)
    assert fake.fake_value_problems("whsec_" + "Q" * 32) == ["㉯ 허용 목록에 없는 접두어"]


@pytest.mark.parametrize("word", ["fake", "TEST", "Dummy", "example", "sample", "demo"])
def test_F_B02_미끼낱말_걸림(word: str) -> None:
    assert "㉰ 미끼 신호 낱말" in fake.fake_value_problems("zelto_ab" + word + "cd")


def test_F_B02_서비스꼴_걸림_값은_싣지않음() -> None:
    aws = "AK" + "IA" + "Q7" * 8
    problems = fake.fake_value_problems(aws)
    assert any(p.startswith("㉮") for p in problems)
    assert all(aws not in p for p in problems)


def test_F_B02_시드_다시만들기(monkeypatch: pytest.MonkeyPatch) -> None:
    """㉰에 걸리면 시드 끝에 #1, #2…를 붙인다. 첫 시드 값을 걸리게 꾸며 다음 시드로 가는지 본다."""
    first = fake.make_password("easy-1", "E1-07")
    real = fake.has_decoy_word
    monkeypatch.setattr(fake, "has_decoy_word", lambda v: v == first or real(v))
    again = fake.make_password("easy-1", "E1-07")
    assert again != first
    assert again == fake._draw("easy-1/E1-07#1", fake.BASE62, fake.PASSWORD_CHARS)


def test_F_B02_다시만들기_드묾() -> None:
    """MAX_RESEED 근거의 확인: 키 1만 개에서 첫 시드가 ㉰에 걸린 수(계산 기댓값 약 0.95)."""
    first_hits = sum(
        fake.has_decoy_word(fake._draw(f"easy-1/K-{i}", fake.BASE62, fake.KEY_BODY_CHARS))
        for i in range(10_000)
    )
    assert first_hits <= 5


def test_F_B02_접두어_한번들에_겹치면_멈춤() -> None:
    """ⓐ 한 번들 안 정답마다 다른 접두어 — 계획(plan.json values)에서 막는다."""
    values: dict[str, Json] = {
        "E1-01": {"form": "key", "prefix": "zelto_"},
        "E1-02": {"form": "key", "prefix": "zelto_"},
    }
    with pytest.raises(fake.FakeValueError, match="E1-02"):
        fake.check_unique_prefixes(values)
    fake.check_unique_prefixes({**values, "E1-02": {"form": "key", "prefix": "quvar_"}})


def test_F_B02_나눔_합치면_원값() -> None:
    for parts in range(2, fake.SPLIT_MAX_PARTS + 1):
        pieces = fake.split_value(KEY, parts)
        assert len(pieces) == parts
        assert "".join(pieces) == KEY
        assert all(len(p) >= fake.SPLIT_MIN_PIECE_CHARS for p in pieces)
    assert fake.split_value(KEY, 2) == [KEY[:19], KEY[19:]]
    assert fake.split_piece(KEY, ["3", "2"]) == fake.split_value(KEY, 3)[2]
    assert len(fake.split_value("zelto_" + "Q" * 31, 9)) == 9  # 가장 짧은 키 37자도 9조각


@pytest.mark.parametrize(("parts", "value"), [(1, KEY), (10, KEY), (5, "Q0HQvzBsuZJRMH46")])
def test_F_B02_나눔_거절(parts: int, value: str) -> None:
    with pytest.raises(fake.FakeValueError):
        fake.split_value(value, parts)


def test_F_B02_토큰_200자_넘으면_거절() -> None:
    with pytest.raises(fake.FakeValueError, match="200"):
        fake.make_token("easy-1", "E1-02", {"note": "x" * 120})


def test_F_B02_규칙4_꼴_가르기() -> None:
    assert fake.rule4_form(KEY) == "key"
    assert fake.rule4_form(TOKEN) == "token"
    assert fake.rule4_form("Q0HQvzBsuZJRMH46") == "password"
    assert fake.rule4_form("/console/manage") is None
    assert fake.key_prefix(KEY) == "zelto_"
    assert fake.key_prefix(KEY[:19]) is None  # 나눈 조각은 접두어 있는 값이 아니다
