"""쉬움 번들 easy-1·easy-2 (기능명세 F-B02·F-B03·F-B04·F-B07, 설계 2.7 표 easy 줄).

값은 모두 가짜다.
"""

from __future__ import annotations

import ipaddress
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from common.contracts import Json, read_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from sources.build_tools import fake
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, build
from sources.build_tools.verify import (
    HIDING_BY_DIFFICULTY,
    REPO_ROOT,
    check_target,
    repo_target,
)

EASY = ("easy-1", "easy-2")
ALL_CATEGORIES = 8
# F-B02 예시 값(명세 그대로): easy-1의 E1-01 키·E1-02 토큰·E1-07 비밀번호
SPEC_KEY = "zelto_b0C4frYzt4BKOBGR0EOcliebprppDYO8"
SPEC_PASSWORD = "Q0HQvzBsuZJRMH46"
SPEC_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJ1LTQ4MjEzIiwicm9sZSI6InN0YWZmIiwiaWF0IjoxNzYzNjAwMDAwfQ"
    ".CIGvPrG9Eh50XRQy_a-fJJhyPFfaSLRAkpSPO61n8TJ"
)
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")  # F-B02 6 (RFC 2606)


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


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B03_easy_planted에_가짜생성(bundle_id: str) -> None:
    """F-B02 7: 규칙 4로 만든 값(키·토큰·비밀번호)이 든 정답은 planted에 '가짜(생성)'."""
    generated = 0
    for item in _entries(_answers(bundle_id), "items"):
        anchor = item["anchor"]
        if isinstance(anchor, str) and fake.rule4_form(anchor) in {"key", "token"}:
            generated += 1
            assert "가짜(생성)" in str(item["planted"]), item["id"]
        if "가짜(생성)" in str(item["planted"]):
            assert isinstance(anchor, str) and fake.rule4_form(anchor), item["id"]
    assert generated >= 2


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
    """F-B02 예시의 시드(`easy-1/E1-01`·`E1-02`·`E1-07`)로 만든 값이 easy-1 정답의 닻이다."""
    anchors = {str(i["id"]): i["anchor"] for i in _entries(_answers("easy-1"), "items")}
    assert anchors["E1-01"] == SPEC_KEY
    assert anchors["E1-02"] == SPEC_TOKEN
    assert anchors["E1-07"] == SPEC_PASSWORD


@pytest.mark.parametrize("bundle_id", EASY)
def test_F_B02_easy_가짜주소(bundle_id: str) -> None:
    """F-B02 6: 내부 주소는 사설 주소(RFC 1918)나 예약 이름만. 미끼 주소도 예약 이름."""
    answers = _answers(bundle_id)
    urls = [
        str(e["anchor"])
        for e in _entries(answers, "items") + _entries(answers, "decoys")
        if str(e["anchor"]).startswith(("http://", "https://"))
    ]
    assert urls
    for url in urls:
        host = urlsplit(url).hostname or ""
        if host.replace(".", "").isdigit():
            assert ipaddress.ip_address(host).is_private, url
        else:
            assert host.endswith(RESERVED_SUFFIXES), url


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
