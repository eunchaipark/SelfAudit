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
    "FakeValueError",
    "binary_suffixes",
    "check_prefix",
    "fake_value_problems",
    "make_key",
    "make_password",
    "make_token",
    "make_value",
    "seed_for",
    "service_shape_names",
    "split_piece",
    "split_value",
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
PREFIX: Final = re.compile(r"[a-z]{4,6}_")  # ⓐ 지어낸 서비스 이름 소문자 4~6자 + `_`
# 규칙 5 ㉯ 실제 서비스 접두어, ㉰ 미끼(자리표시값)의 신호 낱말 — 대소문자 무시
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
# ㉰에 걸리면 시드 끝에 `#1`, `#2`…를 붙여 다시 만든다.
# 한 번 걸릴 확률이 약 0.1%(32자 안에 낱말 6개,
# 대소문자 섞임 — 추정)라 100번은 사실상 끝이 없는 되풀이를 막는 울타리다
MAX_RESEED: Final = 100
# 나눔 조각 하나는 닻이 될 수 있어야 한다(계약 anchor 4자 이상).
# 8조각은 키 38자를 4자 넘게 나누는 끝
SPLIT_MIN_PIECE_CHARS: Final = 4
SPLIT_MAX_PARTS: Final = 8

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


def fake_value_problems(value: str) -> list[str]:
    """F-B02 규칙 5: 걸린 항목(㉮ 꼴 이름, ㉯, ㉰). 빈 목록이면 지킨다."""
    problems = [f"㉮ 서비스 꼴({name})" for name in service_shape_names(value)]
    lowered = value.lower()
    if lowered.startswith(REAL_PREFIXES):
        problems.append("㉯ 실제 서비스 접두어로 시작")
    if any(word in lowered for word in DECOY_WORDS):
        problems.append("㉰ 미끼 신호 낱말")
    return problems


def check_prefix(prefix: str) -> None:
    """ⓐ 접두어 꼴과 ㉯·㉰. 걸리면 접두어를 바꿔야 한다(시드를 바꿔도 고쳐지지 않는다)."""
    if not PREFIX.fullmatch(prefix):
        raise FakeValueError("접두어는 소문자 4~6자 + '_'")
    problems = [p for p in fake_value_problems(prefix) if not p.startswith("㉮")]
    if problems:
        raise FakeValueError(f"접두어가 규칙 5에 걸림: {', '.join(problems)}")


# --- 만들기 (규칙 4) ---------------------------------------------------------------------------


def seed_for(bundle_id: str, entry_id: str) -> str:
    """F-B02 규칙 4 시드 `<대상 ID>/<정답 ID>`."""
    return f"{bundle_id}/{entry_id}"


def _draw(seed: str, alphabet: str, count: int) -> str:
    # 같은 시드면 같은 값이어야 해서(F-B02 근거 5) 시드를 주는 random.Random을 쓴다. 암호용이 아니다
    rng = random.Random(seed)  # noqa: S311
    return "".join(rng.choice(alphabet) for _ in range(count))


def _reseeded(seed: str, fixed: str, make: Callable[[str], str]) -> str:
    """규칙 5에 걸리면 시드 끝에 `#n`을 붙여 다시 만든다.

    `fixed`(바뀌지 않는 앞부분)가 걸리면 시드로 고칠 수 없어 멈춘다.
    """
    if fake_value_problems(fixed):
        raise FakeValueError("고정 부분이 규칙 5에 걸림")
    for attempt in range(MAX_RESEED):
        value = make(seed if attempt == 0 else f"{seed}#{attempt}")
        if not fake_value_problems(value):
            return value
    raise FakeValueError(f"{MAX_RESEED}번 다시 만들어도 규칙 5에 걸림")


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
    return _reseeded(seed, fixed, lambda s: fixed + _draw(s, BASE64URL, TOKEN_SIGNATURE_CHARS))


def _b64url_json(value: Mapping[str, Json]) -> str:
    text = json.dumps(value, separators=(",", ":"))
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


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
