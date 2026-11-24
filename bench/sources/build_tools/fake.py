"""F-B02 가짜 값 만들기(규칙 4)·가짜 값 규칙(규칙 5)·나눔(`split`, 규칙 2).

값은 `random.Random("<대상 ID>/<정답 ID>")`로 차례로 고른다.
같은 ID면 늘 같은 값이 나와 다시 빌드해도
지문(F-B04)이 같다(F-B02 근거 5). 암호용 난수가 아니다 — 이 값은 공개 저장소에 올라가는 가짜 값이다.
오류 글에는 값을 싣지 않는다(정답 ID·규칙만).
"""

from __future__ import annotations

import base64
import functools
import importlib.util
import json
import random
import re
import string
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Final

from common.contracts import Json

__all__ = [
    "BASE62",
    "BASE64URL",
    "FAKE_PREFIXES",
    "FakeValueError",
    "binary_suffixes",
    "check_prefix",
    "check_unique_prefixes",
    "fake_value_problems",
    "has_decoy_word",
    "key_prefix",
    "make_key",
    "make_password",
    "make_token",
    "make_value",
    "rule4_form",
    "seed_for",
    "service_shape_names",
    "split_piece",
    "split_value",
    "token_problems",
]

# F-B02 규칙 4: 본문·비밀번호는 base62(`0-9A-Za-z`), 서명은 base64url 글자.
# 차례는 글자표 차례 그대로
# (예시 값 `zelto_b0C4…`·`Q0HQvzBs…`·`CIGvPrG9…`가 이 차례로 나온다)
BASE62: Final = string.digits + string.ascii_uppercase + string.ascii_lowercase
BASE64URL: Final = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"
KEY_BODY_CHARS: Final = 32  # ⓐ 본문 32자
PASSWORD_CHARS: Final = 16  # ⓒ 16자
TOKEN_SIGNATURE_CHARS: Final = 43  # ⓑ 서명 43자(HS256 서명 32바이트의 base64url 길이)
TOKEN_MAX_CHARS: Final = 200  # ⓑ 200자 안(닻 상한, 설계 2.2)
JWT_HEADER: Final[Mapping[str, str]] = {"alg": "HS256", "typ": "JWT"}
# 서명 끝 글자(T22 반려 1 2, 총괄 대리): 32바이트 = 256비트를 base64url 43자(258비트)로 쓰면
# 끝 글자의 아래 2비트는 쓰지 않으므로 표준 꼴에서는 0이다 —
# 글자표에서 4의 배수 자리 16글자(A E I M … 0 4 8)만 된다.
# 무작위로 고르면 4개 중 3개가 엄격한 디코더에서 '깨진 토큰'이 되어 정답이 미끼처럼 보일 수 있다
SIGNATURE_LAST_CHARS: Final = BASE64URL[::4]
PREFIX: Final = re.compile(r"[a-z]{4,6}_")  # ⓐ 지어낸 서비스 이름 소문자 4~6자 + `_`
# 규칙 4로 만든 값의 꼴(F-B07 10이 '규칙 4 값이 든 정답·미끼'를 가를 때 쓴다, 반려 1 9 총괄 대리).
# 토큰 머리는 늘 같은 글(JWT_HEADER의 base64url)이다
KEY_FORM: Final = re.compile(r"([a-z]{4,6}_)[0-9A-Za-z]{32}")
# 몸 119자까지 = 200 − 머리 36 − 점 2 − 서명 43
TOKEN_FORM: Final = re.compile(
    r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{1,119}\.[A-Za-z0-9_-]{43}"
)
PASSWORD_FORM: Final = re.compile(r"[0-9A-Za-z]{16}")
# ㉯ 접두어는 허용 목록이다(반려 1 5): 실제 서비스 접두어는 계속 늘어 차단 목록은 늘 빠지고
# (`whsec_` 등), 우리가 지어내는 접두어는 번들 6개 × 키 3~4개 = 약 20개라 미리 적어 두는 값이 싸다.
# 30개는 그 1.5배. 늘릴 때는 `test_F_B02_허용접두어_규칙5_지킴`이
# 아래 REAL_PREFIXES·DECOY_WORDS로 본다
FAKE_PREFIXES: Final = frozenset(
    f"{name}_"
    for name in (
        "zelto",  # 명세 F-B02 예시
        "korvel",  # 시험 번들 mini-1
        "quvar",
        "mirtak",
        "bramu",
        "tolvin",
        "yarek",
        "fenzo",
        "lumac",
        "drovik",
        "wexla",
        "nuvor",
        "cablo",
        "jirmo",
        "vantor",
        "oskel",
        "trimba",
        "zunap",
        "felko",
        "morvi",
        "quilo",
        "gralo",
        "ivmok",
        "tazen",
        "kelvo",
        "numra",
        "ulbek",
        "vroda",
        "ezmir",
        "plavek",
    )
)
# 규칙 5 ㉯가 이름을 든 실제 서비스 접두어(허용 목록의 이름이 이것으로 시작하지 않는지 시험이 본다),
# ㉰ 미끼(자리표시값)의 신호 낱말 — 대소문자 무시
REAL_PREFIXES: Final = (
    "gh",
    "github",
    "glpat",
    "npm",
    "pypi",
    "hf",
    "sk",
    "rk",
    "pk",
    "xox",
    "akia",
    "asia",
    "aiza",
    "shp",
    "dop",
    "sq0",
)
DECOY_WORDS: Final = ("fake", "test", "dummy", "example", "sample", "demo")
# ㉰에 걸리면 시드 끝에 `#1`, `#2`…를 붙여 다시 만든다. 한 번 걸릴 확률(직접 계산, 합집합 상한):
# 낱말마다 (들어갈 자리 수) × (2/글자 수)^(낱말 길이) — 글자마다 대소문자 둘이 맞는다.
# 키 본문 32자(base62) 0.0095%, 비밀번호 16자 0.0043%, 토큰 서명 43자(base64url) 0.012%.
# 10번 모두 걸릴 확률은 0.00012^10 ≈ 10^-39라, 10은 끝없는 되풀이를 막는 울타리일 뿐이다.
# 확인: `test_F_B02_다시만들기_드묾`이 키 1만 개에서 다시 만든 수를 센다(기댓값 약 1)
MAX_RESEED: Final = 10
# 나눔 조각 하나는 닻이 될 수 있어야 한다(계약 anchor 4자 이상). 조각 수 상한 9 =
# 가장 짧은 키(37자, ⓐ)를 조각마다 4자 이상으로 나눌 수 있는 끝(37 // 4). 더 짧은 값(비밀번호 16자는
# 4조각까지)은 '4자 이상' 검사가 막는다
SPLIT_MIN_PIECE_CHARS: Final = 4
SPLIT_MAX_PARTS: Final = 9

_CHECK_BENCH: Final = Path(__file__).resolve().parents[3] / "ops" / "scripts" / "check_bench.py"
_OPENAI_NAME: Final = "OpenAI 키"


class FakeValueError(ValueError):
    """가짜 값을 만들 수 없다(접두어 꼴·규칙 5·나눔 수). 값은 싣지 않는다."""


# --- 규칙 5 ----------------------------------------------------------------------------------


@functools.cache
def _check_bench() -> ModuleType:
    """서비스 꼴 목록은 검사 '실험자료'(`check_bench.py`)의 것을 그대로 쓴다.

    F-B07 9 '같은 꼴 목록'.
    """
    spec = importlib.util.spec_from_file_location("selfaudit_check_bench", _CHECK_BENCH)
    if spec is None or spec.loader is None:
        raise FakeValueError("검사 check_bench.py를 읽을 수 없음")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def service_shape_names(text: str) -> list[str]:
    """글 한 줄에 든 서비스 꼴 키의 이름(㉮). 값은 돌려주지 않는다."""
    bench = _check_bench()
    names: list[str] = [name for name, pattern in bench.SECRET_SHAPES if pattern.search(text)]
    if bench.openai_shape(text):
        names.append(_OPENAI_NAME)
    return names


def binary_suffixes() -> frozenset[str]:
    """검사 '실험자료'가 글 파일로 읽지 않는 확장자(서비스 꼴을 같은 파일에서 찾으려고)."""
    suffixes: set[str] = set(_check_bench().BINARY_SUFFIXES)
    return frozenset(suffixes)


def rule4_form(value: str) -> str | None:
    """값이 규칙 4로 만든 꼴(`key`·`token`·`password`)인지. 아니면 None."""
    if KEY_FORM.fullmatch(value):
        return "key"
    if TOKEN_FORM.fullmatch(value):
        return "token"
    if PASSWORD_FORM.fullmatch(value):
        return "password"
    return None


def key_prefix(value: str) -> str | None:
    """키 꼴 값의 접두어(`zelto_`). 키 꼴이 아니면 None — ㉯는 접두어가 있는 값에만 건다."""
    m = KEY_FORM.fullmatch(value)
    return m.group(1) if m else None


def has_decoy_word(value: str) -> bool:
    """㉰: `fake`·`test`·`dummy`·`example`·`sample`·`demo`가 대소문자 무시로 들어 있다."""
    lowered = value.lower()
    return any(word in lowered for word in DECOY_WORDS)


def fake_value_problems(value: str) -> list[str]:
    """F-B02 규칙 5: 걸린 항목(㉮ 꼴 이름, ㉯, ㉰). 빈 목록이면 지킨다.

    ㉯는 접두어가 있는 값(키 꼴)에만: 접두어가 허용 목록(`FAKE_PREFIXES`)에 있어야 한다.
    """
    problems = [f"㉮ 서비스 꼴({name})" for name in service_shape_names(value)]
    prefix = key_prefix(value)
    if prefix is not None and prefix not in FAKE_PREFIXES:
        problems.append("㉯ 허용 목록에 없는 접두어")
    if has_decoy_word(value):
        problems.append("㉰ 미끼 신호 낱말")
    return problems


def token_problems(value: str) -> list[str]:
    """F-B02 4ⓑ: 토큰 꼴 값의 서명 끝 글자가 표준 꼴(쓰지 않는 끝 2비트가 0)인지.

    토큰 꼴이 아닌 값(앞 조각 닻 등)은 보지 않는다 — 끝 글자가 서명 끝이 아니다.
    """
    if TOKEN_FORM.fullmatch(value) and value[-1] not in SIGNATURE_LAST_CHARS:
        return ["4ⓑ 토큰 서명 끝 글자가 표준 꼴이 아님"]
    return []


def check_prefix(prefix: str) -> None:
    """ⓐ 접두어 꼴과 ㉯(허용 목록). 걸리면 접두어를 바꿔야 한다(시드로는 고쳐지지 않는다)."""
    if not PREFIX.fullmatch(prefix):
        raise FakeValueError("접두어는 소문자 4~6자 + '_'")
    if prefix not in FAKE_PREFIXES:
        raise FakeValueError("㉯ 접두어가 허용 목록(FAKE_PREFIXES)에 없음")


# --- 만들기 (규칙 4) ---------------------------------------------------------------------------


def seed_for(bundle_id: str, entry_id: str) -> str:
    """F-B02 규칙 4 시드 `<대상 ID>/<정답 ID>`."""
    return f"{bundle_id}/{entry_id}"


def _draw(seed: str, alphabet: str, count: int) -> str:
    # 같은 시드면 같은 값이어야 해서(F-B02 근거 5) 시드를 주는 random.Random을 쓴다. 암호용이 아니다
    rng = random.Random(seed)  # noqa: S311
    return "".join(rng.choice(alphabet) for _ in range(count))


def _reseeded(seed: str, fixed: str, make: Callable[[str], str]) -> str:
    """F-B02 예외: ㉰에 걸리면 시드 끝에 `#n`을 붙여 다시 만든다(㉰만 — ㉯는 접두어를 바꾸고,
    ㉮는 F-B07이 실패로 낸다). `fixed`(바뀌지 않는 앞부분)가 ㉰에 걸리면 시드로 고칠 수 없어 멈춘다.
    """
    if has_decoy_word(fixed):
        raise FakeValueError("고정 부분(접두어·토큰 머리·몸)이 ㉰에 걸림")
    for attempt in range(MAX_RESEED):
        value = make(seed if attempt == 0 else f"{seed}#{attempt}")
        if not has_decoy_word(value):
            return value
    raise FakeValueError(f"{MAX_RESEED}번 다시 만들어도 ㉰에 걸림")


def make_key(bundle_id: str, entry_id: str, prefix: str) -> str:
    """ⓐ 키 꼴: 접두어 + base62 32자(합 37~39자)."""
    check_prefix(prefix)
    seed = seed_for(bundle_id, entry_id)
    return _reseeded(seed, prefix, lambda s: prefix + _draw(s, BASE62, KEY_BODY_CHARS))


def make_password(bundle_id: str, entry_id: str) -> str:
    """ⓒ 비밀번호 꼴: base62 16자."""
    seed = seed_for(bundle_id, entry_id)
    return _reseeded(seed, "", lambda s: _draw(s, BASE62, PASSWORD_CHARS))


def make_token(bundle_id: str, entry_id: str, claims: Mapping[str, Json]) -> str:
    """ⓑ 토큰 꼴(JWT 꼴): `<머리>.<몸>.<서명>`, 서명은 base64url 글자 43자. 200자 안."""
    fixed = f"{_b64url_json(JWT_HEADER)}.{_b64url_json(claims)}."
    if len(fixed) + TOKEN_SIGNATURE_CHARS > TOKEN_MAX_CHARS:
        raise FakeValueError(f"토큰이 {TOKEN_MAX_CHARS}자를 넘음(클레임을 줄인다)")
    seed = seed_for(bundle_id, entry_id)
    return _reseeded(seed, fixed, lambda s: fixed + _signature(s))


def _signature(seed: str) -> str:
    """서명 43자: 앞 42자는 base64url 글자, 끝 글자는 표준 꼴(쓰지 않는 끝 비트 0)."""
    # 같은 시드면 같은 값이어야 해서(F-B02 근거 5) 시드를 주는 random.Random을 쓴다. 암호용이 아니다
    rng = random.Random(seed)  # noqa: S311
    head = "".join(rng.choice(BASE64URL) for _ in range(TOKEN_SIGNATURE_CHARS - 1))
    return head + rng.choice(SIGNATURE_LAST_CHARS)


def _b64url_json(value: Mapping[str, Json]) -> str:
    text = json.dumps(value, separators=(",", ":"))
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def check_unique_prefixes(values: Mapping[str, Json]) -> None:
    """ⓐ 한 번들 안 정답마다 다른 접두어(같은 접두어 하나가 검색 표식이 되지 않게, F-B02 근거 4②).

    `values`는 심기 계획의 `{정답 ID: {"form": "key", "prefix": …}}`. 겹치면 뒤 정답 ID를 알린다.
    """
    seen: dict[str, str] = {}
    for entry_id, spec in values.items():
        if not isinstance(spec, dict) or spec.get("form") != "key":
            continue
        prefix = str(spec.get("prefix"))
        if prefix in seen:
            raise FakeValueError(f"{entry_id}: 접두어가 {seen[prefix]}와 같음(정답마다 다르게)")
        seen[prefix] = entry_id


def make_value(bundle_id: str, entry_id: str, spec: Mapping[str, Json]) -> str:
    """심기 계획(`plan.json` `values`)의 한 칸: `{"form": "key", "prefix": "zelto_"}` ·
    `{"form": "token", "claims": {…}}` · `{"form": "password"}`."""
    form = spec.get("form")
    if form == "key":
        prefix = spec.get("prefix")
        if not isinstance(prefix, str):
            raise FakeValueError(f"{entry_id}: 키 꼴에는 prefix 글이 필요")
        return make_key(bundle_id, entry_id, prefix)
    if form == "token":
        claims = spec.get("claims")
        if not isinstance(claims, dict) or not claims:
            raise FakeValueError(f"{entry_id}: 토큰 꼴에는 claims 객체가 필요")
        return make_token(bundle_id, entry_id, claims)
    if form == "password":
        return make_password(bundle_id, entry_id)
    raise FakeValueError(f"{entry_id}: form은 key·token·password")


# --- 나눔 (`split`) --------------------------------------------------------------------------


def split_value(value: str, parts: int) -> list[str]:
    """F-B02 규칙 2 `split`: 값을 앞에서부터 거의 같은 길이의 `parts`조각으로.

    앞 조각이 한 자 길 수 있다.

    이어 붙이면 원값이다. 조각마다 닻이 될 수 있게 4자 이상이어야 한다.
    """
    if not 2 <= parts <= SPLIT_MAX_PARTS:
        raise FakeValueError(f"조각 수는 2~{SPLIT_MAX_PARTS}")
    size, extra = divmod(len(value), parts)
    if size < SPLIT_MIN_PIECE_CHARS:
        raise FakeValueError(f"조각이 {SPLIT_MIN_PIECE_CHARS}자보다 짧아짐")
    pieces: list[str] = []
    start = 0
    for i in range(parts):
        end = start + size + (1 if i < extra else 0)
        pieces.append(value[start:end])
        start = end
    return pieces


def split_piece(value: str, args: Sequence[str]) -> str:
    """자리 걸러내기 `split:<조각 수>:<차례 0부터>` — 빌드가 부른다."""
    if len(args) != 2 or not all(a.isdigit() for a in args):
        raise FakeValueError("split은 split:<조각 수>:<차례>")
    parts, index = int(args[0]), int(args[1])
    pieces = split_value(value, parts)
    if index >= parts:
        raise FakeValueError("split 차례가 조각 수보다 큼")
    return pieces[index]
