"""보통 번들 normal-1·normal-2 (기능명세 F-B01·F-B02·F-B03·F-B07, 설계 2.7 표 normal 줄).

normal 줄: 압축(한 줄)·파일 이름에 해시, 숨기는 방법 `split`·`encoded`(base64·16진)·`config`.
인코딩 걸러내기는 `build_tools/encode.py`(T23). 값은 모두 가짜다.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import shutil
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from sources.build_tools import encode, fake
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, build
from sources.build_tools.locate import write_answers
from sources.build_tools.verify import (
    HIDING_BY_DIFFICULTY,
    REPO_ROOT,
    check_target,
    repo_target,
)

NORMAL = ("normal-1", "normal-2")
ALL_CATEGORIES = 8
HIDDEN = frozenset({"split", "encoded", "obfuscated"})
# F-B02 예시(명세 그대로): 키 `zelto_…`의 base64(52자)와 16진(76자)
SPEC_KEY = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
SPEC_BASE64 = "emVsdG9fYjBDNGZyWXp0NEJLT0JHUjBFT2NsaWVicHJwcERZTzg="
SPEC_HEX_LENGTH = 76
# 해시 이름: Vite 꼴 `<이름>-<16진 8자>.<확장자>`(build.HASH_CHARS)
HASHED = re.compile(r"[a-z]+-[0-9a-f]{8}\.(?:js|css)")
MAP_LINE = re.compile(r"//# sourceMappingURL=[a-z]+-[0-9a-f]{8}\.js\.map")
# F-B02 6: 내부 주소는 RFC 1918 세 네트워크만
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
# 예약 이름(RFC 2606)은 정답·미끼 한쪽에만 쓰지 않는다(F-B02 6). 보통 번들은 어느 쪽에도 쓰지 않는다
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
# 번들 글에 나오는 바깥 호스트: 미끼(공개 CDN)뿐
PUBLIC_HOSTS = frozenset({"d2q7m4x9k1w8ze.cloudfront.net", "res.cloudinary.com"})
IPV4 = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
URL_HOST = re.compile(r"(?:https?|wss?)://([A-Za-z0-9.-]+)")
# 코드가 실행 중에 푸는 자리(압축 꼴, 빈칸 없음). 닻이 바로 뒤에 온다
DECODE_CALLS = ('atob("', 'fromHex("')
CONFIG_START =re.compile(r"window\.__APP_CONFIG__ ?= ?\{")


# --- 읽기 ------------------------------------------------------------------------------------


def _answers(bundle_id: str) -> dict[str, Json]:
    return read_contract("answers", REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json")


def _entries(answers: dict[str, Json], group: str) -> list[dict[str, Json]]:
    value = answers[group]
    assert isinstance(value, list)
    return [e for e in value if isinstance(e, dict)]


def _items(bundle_id: str, hiding: str | None = None) -> list[dict[str, Json]]:
    items = _entries(_answers(bundle_id), "items")
    return [i for i in items if hiding is None or i["hiding"] == hiding]


def _location_files(entry: dict[str, Json]) -> set[str]:
    locations = entry["locations"]
    assert isinstance(locations, list)
    return {str(loc["file"]) for loc in locations if isinstance(loc, dict)}


def _texts(bundle_id: str) -> dict[str, str]:
    """번들의 글 파일(모두 UTF-8 글이다) {번들 안 경로: 글}."""
    bundle = BUNDLES_DIR / bundle_id
    return {
        path.relative_to(bundle).as_posix(): path.read_bytes().decode("utf-8")
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }


def _occurrences(text: str, needle: str) -> int:
    """나오는 곳 수(겹쳐 나와도 시작 자리마다 하나, F-B07 6)."""
    count, start = 0, text.find(needle)
    while start >= 0:
        count += 1
        start = text.find(needle, start + 1)
    return count


def _generated(bundle_id: str) -> set[str]:
    """심기 계획(plan.json values)으로 만든 가짜 값."""
    plan = json.loads((SOURCES_DIR / bundle_id / "plan.json").read_text(encoding="utf-8"))
    return {fake.make_value(bundle_id, eid, spec) for eid, spec in plan["values"].items()}


def _is_base64(anchor: str, decoded: str) -> bool:
    try:
        raw = base64.b64decode(anchor, validate=True)
    except binascii.Error:
        return False
    return raw == decoded.encode("utf-8") and base64.b64encode(raw).decode() == anchor


def _is_hex(anchor: str, decoded: str) -> bool:
    return anchor == decoded.encode("utf-8").hex()


# --- 인코딩 도구 (encode.py) ------------------------------------------------------------------


def test_F_B02_인코딩_명세예시_base64_16진() -> None:
    """F-B02 예시: 키를 base64로 52자(`=` 채움), 16진으로 76자(소문자)."""
    assert encode.to_base64(SPEC_KEY, []) == SPEC_BASE64
    hexed = encode.to_hex(SPEC_KEY, [])
    assert len(hexed) == SPEC_HEX_LENGTH
    assert hexed.startswith("7a656c746f5f")
    assert hexed.endswith("594f38")
    assert hexed == hexed.lower()


def test_F_B02_인코딩_걸러내기_이름과_인자() -> None:
    """빌드가 읽는 이름은 `base64`·`hex`이고, 인자는 받지 않는다(오류 글에 값 없음)."""
    assert set(encode.FILTERS) == {"base64", "hex"}
    for name, func in encode.FILTERS.items():
        with pytest.raises(ValueError, match=name) as err:
            func(SPEC_KEY, ["2"])
        assert SPEC_KEY not in str(err.value)


# --- 숨기는 방법 (F-B02 2·3) ------------------------------------------------------------------


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_split_두조각_따로있음(bundle_id: str) -> None:
    """`split` 정답: 닻은 번들에 있는 조각 하나, 풀어낸 값은 통째로는 번들에 없다.

    풀어낸 값에서 닻을 뺀 앞·뒤 조각도 번들에 따로 있다(둘이 이어 붙은 글로는 없다).
    """
    items = _items(bundle_id, "split")
    assert items
    texts = list(_texts(bundle_id).values())
    for item in items:
        anchor, decoded = str(item["anchor"]), str(item["decoded_anchor"])
        before, found, after = decoded.partition(anchor)
        assert found and anchor != decoded, item["id"]
        assert not any(decoded in t for t in texts), item["id"]
        rest = [piece for piece in (before, after) if piece]
        assert all(any(piece in t for t in texts) for piece in rest), item["id"]


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_encoded_base64(bundle_id: str) -> None:
    """`encoded` 정답 가운데 base64(표준 글자, `=` 채움)가 있다. 풀어낸 값은 번들에 글로 없다."""
    texts = _texts(bundle_id)
    found = [
        i
        for i in _items(bundle_id, "encoded")
        if _is_base64(str(i["anchor"]), str(i["decoded_anchor"]))
    ]
    assert found
    for item in found:
        assert not any(str(item["decoded_anchor"]) in t for t in texts.values()), item["id"]


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_encoded_16진(bundle_id: str) -> None:
    """`encoded` 정답 가운데 16진(소문자)이 있고, 모든 `encoded` 정답은 base64 아니면 16진이다."""
    texts = _texts(bundle_id)
    items = _items(bundle_id, "encoded")
    hexed = [i for i in items if _is_hex(str(i["anchor"]), str(i["decoded_anchor"]))]
    assert hexed
    for item in hexed:
        assert not any(str(item["decoded_anchor"]) in t for t in texts.values()), item["id"]
    for item in items:
        anchor, decoded = str(item["anchor"]), str(item["decoded_anchor"])
        assert _is_base64(anchor, decoded) or _is_hex(anchor, decoded), item["id"]


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_config(bundle_id: str) -> None:
    """`config` 정답의 닻은 설정 객체 `window.__APP_CONFIG__ = {…}` 안에 있다."""
    items = _items(bundle_id, "config")
    assert items
    spans = [span for text in _texts(bundle_id).values() for span in _config_spans(text)]
    assert len(spans) == 1  # 설정 객체는 번들에 하나
    for item in items:
        assert str(item["anchor"]) in spans[0], item["id"]


def _config_spans(text: str) -> list[str]:
    """`window.__APP_CONFIG__ = {`부터 짝이 맞는 `}`까지(설정 값에 중괄호를 두지 않는다)."""
    spans: list[str] = []
    for m in CONFIG_START.finditer(text):
        depth = 0
        for i in range(m.end() - 1, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                spans.append(text[m.end() - 1 : i + 1])
                break
    return spans


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_split·encoded·config_모두있음(bundle_id: str) -> None:
    """F-B02 3: normal 줄의 방법이 모두 한 번 이상, 그 밖은 none만."""
    hidings = {str(item["hiding"]) for item in _items(bundle_id)}
    assert hidings - {"none"} == HIDING_BY_DIFFICULTY["normal"]


# --- 결과물 꼴 (F-B01, 설계 2.7) ----------------------------------------------------------------


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B01_normal_한줄_해시이름(bundle_id: str) -> None:
    """압축(한 줄): JS는 코드 한 줄(+ 소스맵이 있으면 `//# sourceMappingURL=` 한 줄).

    HTML·CSS·맵은 한 줄(반려 1 3·4). JS·CSS 이름에는 해시가 붙는다.
    남기는 주석은 `/*!` 배너뿐이다.
    """
    bundle = BUNDLES_DIR / bundle_id
    scripts = sorted((bundle / "assets").glob("*.js"))
    assert scripts
    for path in sorted((bundle / "assets").iterdir()):
        if path.suffix in {".js", ".css"}:
            assert HASHED.fullmatch(path.name), path.name
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.suffix in {".html", ".css", ".map"}:
            assert count_lines(path.read_bytes()) == 1, path.name
    for path in scripts:
        data = path.read_bytes()
        lines = data.decode("utf-8").split(chr(0x0A))
        assert count_lines(data) <= 2, path.name
        has_map = path.with_name(path.name + ".map").is_file()
        assert count_lines(data) == (2 if has_map else 1), path.name
        if has_map:
            assert MAP_LINE.fullmatch(lines[1]), path.name
        code = lines[0].replace("/*!", "")
        assert "/*" not in code and "//" not in code.replace("://", ""), path.name


# --- 정답지 (F-B03) ---------------------------------------------------------------------------


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B03_normal_닻_번들에서_한곳만(bundle_id: str) -> None:
    """압축 파일은 한 줄이라 F-B07 6(줄 범위)으로는 정답끼리 가르지 못한다(설계 2.5).

    그래서 더 본다: ㉮ 닻이 나오는 파일은 모두 그 정답(미끼)의 위치 파일
    ㉯ 숨긴 정답의 닻(조각·인코딩 글)은 나오는 파일마다 꼭 한 번
    ㉰ 닻이 다른 정답·미끼의 닻 안에 들지 않는다(결과 하나가 둘을 맞히지 않게).
    """
    answers = _answers(bundle_id)
    entries = _entries(answers, "items") + _entries(answers, "decoys")
    texts = _texts(bundle_id)
    anchors = {str(e["id"]): str(e["anchor"]) for e in entries if e["anchor"] is not None}
    assert len(anchors) == len(entries)  # 보통 번들은 모든 정답·미끼에 닻이 있다
    for entry in entries:
        entry_id, anchor = str(entry["id"]), anchors[str(entry["id"])]
        counts = {rel: _occurrences(t, anchor) for rel, t in texts.items()}
        found_in = {rel for rel, n in counts.items() if n}
        assert found_in and found_in <= _location_files(entry), entry_id
        if entry.get("hiding") in HIDDEN:
            assert all(counts[rel] == 1 for rel in found_in), entry_id
        for other_id, other in anchors.items():
            assert other_id == entry_id or anchor not in other, (entry_id, other_id)


def test_F_B03_normal1_소스맵_닻은_맵이름() -> None:
    """반려 1 1: 줄로 못 가르는 위치라 닻으로만 맞는다. `sourcesContent` 낱말은 맵 JSON을
    날것으로 읽는 쪽에만 evidence에 들어가므로, 번들에 한 번만 나오는 맵 파일 이름을 닻으로 쓴다."""
    (item,) = [i for i in _items("normal-1") if i["categories"] == ["source_map"]]
    anchor = str(item["anchor"])
    texts = _texts("normal-1")
    assert anchor.endswith(".js.map") and f"assets/{anchor}" in texts
    assert sum(_occurrences(t, anchor) for t in texts.values()) == 1


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B03_normal_숨긴정답만_풀어낸값(bundle_id: str) -> None:
    """F-B03 6: 숨긴 정답(split·encoded)에는 풀어낸 값, 그 밖(config·none)은 null."""
    for item in _items(bundle_id):
        hidden = item["hiding"] in HIDDEN
        assert (item["decoded_anchor"] is not None) == hidden, item["id"]


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B03_normal_planted에_가짜생성(bundle_id: str) -> None:
    """F-B02 7: 규칙 4로 만든 값이 닻이나 풀어낸 값인 정답만 planted에 '가짜(생성)'."""
    generated = _generated(bundle_id)
    used: set[str] = set()
    for item in _items(bundle_id):
        values = {item["anchor"], item["decoded_anchor"]} & generated
        used |= {str(v) for v in values}
        assert ("가짜(생성)" in str(item["planted"])) == bool(values), item["id"]
    assert used == generated  # 만든 값은 모두 정답에 쓰인다


def test_F_B03_normal_두번들합쳐_키·토큰·비밀번호() -> None:
    forms = {fake.rule4_form(v) for bundle_id in NORMAL for v in _generated(bundle_id)}
    assert forms == {"key", "token", "password"}


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B03_normal_정답지_명령으로_다시만들면_같음(bundle_id: str, tmp_path: Path) -> None:
    """정답지는 원본 + 명령 하나(`answers <id>`)로 같은 바이트가 다시 나온다(T22 반려 1 3)."""
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    path, _ = write_answers(bundle_id, sources, tmp_path / "bundles", tmp_path / "answers")
    assert path.read_bytes() == (REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json").read_bytes()


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B04_normal_지문같음(bundle_id: str, tmp_path: Path) -> None:
    """정답지·빌드 기록의 지문 = 저장소 번들의 지문 = 원본을 다시 빌드한 지문(F-B01 3)."""
    expected = _answers(bundle_id)["bundle_manifest_sha256"]
    assert bundle_manifest_sha256(BUNDLES_DIR / bundle_id) == expected
    record = json.loads((SOURCES_DIR / bundle_id / "build.json").read_text(encoding="utf-8"))
    assert record["bundle_manifest_sha256"] == expected
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    assert build(bundle_id, sources, tmp_path / "bundles").bundle_manifest_sha256 == expected


# --- 공정성 (겉모양으로 정답·미끼를 가르지 않게) ---------------------------------------------


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_가짜주소(bundle_id: str) -> None:
    """F-B02 6: 번들 글과 풀어낸 값의 IP는 RFC 1918 세 네트워크 안.

    호스트는 그 IP나 정해 둔 공개 CDN뿐이고, 예약 이름은 쓰지 않는다.
    """
    texts = list(_texts(bundle_id).values())
    texts += [str(i["decoded_anchor"]) for i in _items(bundle_id) if i["decoded_anchor"]]
    ips: set[str] = set()
    for text in texts:
        assert not any(s in text for s in RESERVED_SUFFIXES)
        for ip in IPV4.findall(text):
            ips.add(ip)
            assert any(ipaddress.ip_address(ip) in net for net in PRIVATE_NETWORKS), ip
        for host in URL_HOST.findall(text):
            assert IPV4.fullmatch(host) or host in PUBLIC_HOSTS, host
    assert ips  # 내부 주소 정답이 번들마다 있다


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_미끼낱말_번들에없음(bundle_id: str) -> None:
    """F-B02 5㉰의 낱말(fake·test·demo…)이 번들 글 어디에도 없다 — 미끼에만 있으면 단서가 된다."""
    for rel, text in _texts(bundle_id).items():
        assert not fake.has_decoy_word(text), rel


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_미끼도_인코딩꼴(bundle_id: str) -> None:
    """숨긴 정답과 같은 겉모양(base64·16진 글)인 미끼가 있다.

    '인코딩된 글이면 문제'라는 겉모양 규칙으로 정답을 고를 수 없게 한다.
    """
    decoys = _entries(_answers(bundle_id), "decoys")
    shaped = [d for d in decoys if _looks_encoded(str(d["anchor"]))]
    assert shaped


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B02_normal_푸는함수마다_미끼(bundle_id: str) -> None:
    """반려 1 2: 코드가 실행 중에 푸는 글(`atob("…")`·`fromHex("…")`)은 함수마다 정답과 미끼가 다 있다.

    '푸는 글은 다 신고'로는 정밀도를 지킬 수 없게 — 풀어 본 뒤 내용으로 가르는지를 잰다.
    """
    text = "".join(_texts(bundle_id).values())
    answers = _answers(bundle_id)
    for call in DECODE_CALLS:
        if call not in text:
            continue
        for group in ("items", "decoys"):
            anchors = [str(e["anchor"]) for e in _entries(answers, group)]
            assert any(call + a in text for a in anchors), (call, group)


def _looks_encoded(anchor: str) -> bool:
    hex_like = re.fullmatch(r"[0-9a-f]{12,}", anchor) is not None
    try:
        base64.b64decode(anchor, validate=True)
    except binascii.Error:
        return hex_like
    return hex_like or (len(anchor) % 4 == 0 and len(anchor) >= 16)


# --- 구성 검사 (F-B07) ------------------------------------------------------------------------


def test_F_B07_normal1_구성통과() -> None:
    report = check_target(repo_target("normal-1"))
    assert report.problems == ()


def test_F_B07_normal2_구성통과() -> None:
    report = check_target(repo_target("normal-2"))
    assert report.problems == ()


def test_F_B07_보통_범주8개() -> None:
    """F-B07 4: 난이도마다(번들 둘을 합쳐) 8개 모두. 번들 하나에 모두 넣지 않는다(설계 2.7)."""
    reports = [check_target(repo_target(bundle_id)) for bundle_id in NORMAL]
    for report in reports:
        assert 6 <= len(report.categories) < ALL_CATEGORIES, report.bundle_id
    assert len(reports[0].categories | reports[1].categories) == ALL_CATEGORIES


@pytest.mark.parametrize("bundle_id", NORMAL)
def test_F_B07_normal_줄허용범위_기록(bundle_id: str) -> None:
    """F-B07 13 확인 기록: 압축 JS·맵의 위치는 모두 줄 허용 범위가 파일을 덮는다(T = 2)."""
    report = check_target(repo_target(bundle_id))
    assert report.cover_rows
    for row in report.cover_rows:
        if row.file.endswith((".js", ".js.map")):
            assert row.covers, (row.entry_id, row.file)
