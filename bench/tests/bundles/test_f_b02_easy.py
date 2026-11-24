"""쉬움 번들 easy-1·easy-2 (기능명세 F-B02·F-B03·F-B04·F-B07, 설계 2.7 표 easy 줄).

값은 모두 가짜다.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from sources.build_tools import fake
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, build
from sources.build_tools.locate import SHORT_MIN, write_answers
from sources.build_tools.verify import (
    HIDING_BY_DIFFICULTY,
    REPO_ROOT,
    check_target,
    repo_target,
)
from tests.bundles.conftest import bundle_texts, expected_short

EASY = ("easy-1", "easy-2")
ALL_CATEGORIES = 8
# F-B02 예시 값(명세 그대로): easy-1의 E1-01 키·E1-02 토큰·E1-07 비밀번호
SPEC_KEY = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
SPEC_PASSWORD = "Q0HQvzBsuZJRMH46"
SPEC_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1LTQ4MjEzIiwicm9sZSI6InN0YWZmIiwiaWF0IjoxNzYzNjAwMDAwfQ"
    ".CIGvPrG9Eh50XRQy_a-fJJhyPFfaSLRAkpSPO61n8TI"
)
# F-B02 6: 내부 주소는 RFC 1918 세 네트워크만(is_private는 127/8·169.254/16 등도 참이라 쓰지 않는다)
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
# 예약 이름(RFC 2606)은 정답·미끼 한쪽에만 쓰지 않는다(T22 반려 1 1).
# 쉬움 번들은 어느 쪽에도 쓰지 않는다
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
# 번들 글에 나오는 바깥 호스트: 미끼 E1-D3의 공개 이미지 CDN 하나뿐
PUBLIC_HOSTS = frozenset({"res.cloudinary.com"})
IPV4 = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
URL_HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")


def _answers(bundle_id: str) -> dict[str, Json]:
    return read_contract("answers", REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json")


def _entries(answers: dict[str, Json], group: str) -> list[dict[str, Json]]:
    value = answers[group]
    assert isinstance(value, list)
    return [e for e in value if isinstance(e, dict)]


def _files(entry: dict[str, Json]) -> list[str]:
    locations = entry["locations"]
    assert isinstance(locations, list)
    return [str(loc["file"]) for loc in locations if isinstance(loc, dict)]


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B02_easy_plain·comment·config_모두있음(bundle_id: str) -> None:
    """F-B02 3: easy 줄의 방법(plain·comment·config)이 모두 한 번 이상, 그 밖은 none만."""
    hidings = [str(item["hiding"]) for item in _entries(_answers(bundle_id), "items")]
    assert set(hidings) - {"none"} == HIDING_BY_DIFFICULTY["easy"]


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B03_easy_정답마다_js와_map_두위치(bundle_id: str) -> None:
    """easy는 소스맵에 원본을 넣으므로(설계 2.7) 정답마다 결과물 JS와 맵 두 곳에 위치가 있다."""
    for item in _entries(_answers(bundle_id), "items"):
        files = _files(item)
        assert any(f.endswith(".js") for f in files), item["id"]
        assert any(f.endswith(".js.map") for f in files), item["id"]


def _generated(bundle_id: str) -> dict[str, str]:
    """심기 계획(plan.json values)으로 만든 가짜 값 {값: form} — 꼴이 아니라 계획으로 가른다
    (16자 영숫자 닻 `enableDebugTools`가 비밀번호 꼴과 같다)."""
    plan = json.loads((SOURCES_DIR / bundle_id / "plan.json").read_text(encoding="utf-8"))
    return {
        fake.make_value(bundle_id, entry_id, spec): str(spec["form"])
        for entry_id, spec in plan["values"].items()
    }


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B03_easy_planted에_가짜생성(bundle_id: str) -> None:
    """F-B02 7: 규칙 4로 만든 값(키·토큰·비밀번호)이 든 정답은 planted에 '가짜(생성)'.

    그 밖의 정답에는 없다. 규칙 4로 만든 값이 든 정답의 닻은 그 값과 같다 — 값이 64자를 넘고
    줄로 가를 수 없는 위치가 있을 때만 F-B03 5의 앞 조각(`expected_short`)과 같다.
    """
    plan = json.loads((SOURCES_DIR / bundle_id / "plan.json").read_text(encoding="utf-8"))
    answers = _answers(bundle_id)
    texts = bundle_texts(BUNDLES_DIR / bundle_id)
    generated = _generated(bundle_id)
    forms: set[str] = set()
    for item in _entries(answers, "items"):
        entry_id = str(item["id"])
        spec = plan["values"].get(entry_id)
        assert ("가짜(생성)" in str(item["planted"])) == (spec is not None), entry_id
        if spec is None:
            assert item["anchor"] not in generated, entry_id
            continue
        value = fake.make_value(bundle_id, entry_id, spec)
        expected = expected_short(value, item, answers, texts, decoded=False)
        assert item["anchor"] == expected, entry_id
        forms.add(str(spec["form"]))
    assert forms == {"key", "token", "password"}


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B03_easy_미끼_자리표시값(bundle_id: str) -> None:
    """미끼 2~3개, 그 가운데 하나는 채우지 않은 자리표시값(대문자·밑줄 글)."""
    decoys = _entries(_answers(bundle_id), "decoys")
    assert 2 <= len(decoys) <= 3
    placeholders = [
        d
        for d in decoys
        if str(d["why"]).startswith("자리표시값")
        and str(d["anchor"]).replace("_", "").isalpha()
        and str(d["anchor"]).isupper()
    ]
    assert len(placeholders) == 1


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B04_easy_지문같음(bundle_id: str, tmp_path: Path) -> None:
    """정답지·빌드 기록의 지문 = 저장소 번들의 지문 = 원본을 다시 빌드한 지문(F-B01 3)."""
    expected = _answers(bundle_id)["bundle_manifest_sha256"]
    assert bundle_manifest_sha256(BUNDLES_DIR / bundle_id) == expected
    record = json.loads((SOURCES_DIR / bundle_id / "build.json").read_text(encoding="utf-8"))
    assert record["bundle_manifest_sha256"] == expected
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    rebuilt = build(bundle_id, sources, tmp_path / "bundles")
    assert rebuilt.bundle_manifest_sha256 == expected


def test_F_B07_easy1_구성통과() -> None:
    report = check_target(repo_target("easy-1"))
    assert report.problems == ()


def test_F_B07_easy2_구성통과() -> None:
    report = check_target(repo_target("easy-2"))
    assert report.problems == ()


def test_F_B07_쉬움_두번들합쳐_범주8개() -> None:
    """F-B07 4: 난이도마다(번들 둘을 합쳐) 8개 모두. 번들 하나에 모두 넣지 않는다(설계 2.7)."""
    reports = [check_target(repo_target(bundle_id)) for bundle_id in EASY]
    for report in reports:
        assert 6 <= len(report.categories) < ALL_CATEGORIES, report.bundle_id
    assert len(reports[0].categories | reports[1].categories) == ALL_CATEGORIES


def test_F_B02_easy1_명세예시값() -> None:
    """F-B02 예시의 시드(`easy-1/E1-01`·`E1-02`·`E1-07`)로 만든 값이 easy-1 정답의 닻이다.

    E1-02 토큰(147자)은 맵 위치가 줄로 가를 수 없어 닻이 앞 16자다(F-B03 5 예시 — CR-008).
    """
    generated = _generated("easy-1")
    assert {SPEC_KEY, SPEC_TOKEN, SPEC_PASSWORD} <= set(generated)
    anchors = {str(i["id"]): i["anchor"] for i in _entries(_answers("easy-1"), "items")}
    assert anchors["E1-01"] == SPEC_KEY
    assert anchors["E1-02"] == SPEC_TOKEN[:SHORT_MIN] == "eyJhbGciOiJIUzI1"
    assert anchors["E1-07"] == SPEC_PASSWORD


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B02_easy_가짜주소(bundle_id: str) -> None:
    """F-B02 6 + T22 반려 1 6: 번들 글 전체의 IP는 RFC 1918 세 네트워크 안.

    주소의 호스트는 그 IP나 정해 둔 공개 CDN뿐이고, 예약 이름은 쓰지 않는다.
    """
    ips: set[str] = set()
    for path in sorted((BUNDLES_DIR / bundle_id).rglob("*")):
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8")
        assert not any(s in text for s in RESERVED_SUFFIXES), path.name
        for ip in IPV4.findall(text):
            ips.add(ip)
            assert any(ipaddress.ip_address(ip) in net for net in PRIVATE_NETWORKS), ip
        for host in URL_HOST.findall(text):
            assert IPV4.fullmatch(host) or host in PUBLIC_HOSTS, host
    assert ips  # 내부 주소 정답이 번들마다 있다


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B03_easy_정답지_명령으로_다시만들면_같음(bundle_id: str, tmp_path: Path) -> None:
    """T22 반려 1 3: 정답지는 원본 + 명령 하나로 같은 바이트가 다시 나온다."""
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    path, _ = write_answers(bundle_id, sources, tmp_path / "bundles", tmp_path / "answers")
    assert path.read_bytes() == (REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json").read_bytes()


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B02_easy_펼친코드_소스맵원본(bundle_id: str) -> None:
    """설계 2.7 easy 줄: 펼친 코드(줄바꿈 있음), 소스맵에 원본 포함."""
    bundle = BUNDLES_DIR / bundle_id
    maps = sorted((bundle / "assets").glob("*.js.map"))
    assert maps
    for map_path in maps:
        js = map_path.with_suffix("")
        assert count_lines(js.read_bytes()) > 10
        source_map = json.loads(map_path.read_text(encoding="utf-8"))
        assert source_map["sourcesContent"][0].count(chr(0x0A)) > 10
