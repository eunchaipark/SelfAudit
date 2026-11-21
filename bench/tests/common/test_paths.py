"""번들 경로 꼴과 결과 경로 정규화 시험 (실험구조 2.2 '경로 꼴', 2.5 조건 2, 2.9)."""

from __future__ import annotations

import pytest

from common.contracts import ContractError, validate_contract
from common.paths import is_bundle_relpath, normalize_finding_path
from tests.common.test_contracts import answers_example, item

# 가상 실행 폴더 (실험구조 1절 '저장소 밖' 꼴)
ROOT = (
    "C:\\Users\\fake\\AppData\\Local\\SelfAudit-bench-runs"
    "\\20261122-0900-abcd\\easy-1-a-1-3f2a9c10\\target"
)
ROOT_SLASH = ROOT.replace("\\", "/")

REJECTED = [
    "assets\\index.js",  # 역슬래시
    "/assets/index.js",  # 앞 슬래시
    "./assets/index.js",
    "../index.js",
    "assets/../index.js",
    "assets/./index.js",
    "assets/..",
    "assets/.",
    ".",
    "..",
    "",
    "assets/index.js" + chr(10),  # ECMA-262 `$`는 끝 줄바꿈 앞에서 맞지 않는다
    "assets/a" + chr(13) + ".js",  # ECMA-262 `.`은 U+000D를 받지 않는다
    "a" * 301,
]
ACCEPTED = [
    "assets/index-3f2a.js",
    "index.html",
    ".well-known/a.txt",
    "a..b/c.js",
    "...js",
    "a" * 300,
]


@pytest.mark.parametrize("path", REJECTED)
def test_common_경로꼴_역슬래시·앞슬래시·점점_거절(path: str) -> None:
    assert not is_bundle_relpath(path)


@pytest.mark.parametrize("path", ACCEPTED)
def test_common_경로꼴_통과(path: str) -> None:
    assert is_bundle_relpath(path)


def test_common_경로꼴_정답지계약도_같음() -> None:
    data = answers_example()
    locations = item(data)["locations"]
    assert isinstance(locations, list)
    first = locations[0]
    assert isinstance(first, dict)
    first["file"] = "assets\\index-3f2a.js"
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0].file", "pattern")
    ]


@pytest.mark.parametrize(
    ("file", "expected"),
    [
        (ROOT + "\\assets\\index-3f2a.js", "assets/index-3f2a.js"),
        (ROOT_SLASH + "/assets/index-3f2a.js", "assets/index-3f2a.js"),
        ("c" + ROOT[1:] + "\\assets\\x.js", "assets/x.js"),  # 드라이브 글자만 대소문자 무시
        (ROOT + "2\\assets\\x.js", ROOT_SLASH + "2/assets/x.js"),  # 이름 앞부분만 같은 형제
        (ROOT.replace("Users", "USERS") + "\\x.js", ROOT_SLASH.replace("Users", "USERS") + "/x.js"),
        (ROOT, ROOT_SLASH),  # 대상 폴더 자체는 파일이 아니다
        (".\\assets\\x.js", "assets/x.js"),
        ("././assets/x.js", "assets/x.js"),
        ("assets/x.js", "assets/x.js"),
        ("assets/../x.js", "assets/../x.js"),  # `..`은 풀지 않는다(글자 그대로)
        ("/assets/x.js", "/assets/x.js"),
    ],
)
def test_common_결과경로_대상절대경로_지움(file: str, expected: str) -> None:
    assert normalize_finding_path(file, ROOT) == expected


def test_common_결과경로_대상폴더_끝슬래시_같음() -> None:
    assert normalize_finding_path(ROOT + "\\x.js", ROOT + "\\") == "x.js"
    assert normalize_finding_path("/runs/b1/target/x.js", "/runs/b1/target/") == "x.js"


def test_common_결과경로_대상폴더없음() -> None:
    assert normalize_finding_path(".\\assets\\x.js", None) == "assets/x.js"


@pytest.mark.parametrize("root", ["target", "runs\\target", "C:target", ""])
def test_common_결과경로_상대대상폴더_멈춤(root: str) -> None:
    with pytest.raises(ValueError, match="절대 경로"):
        normalize_finding_path("target/x.js", root)
