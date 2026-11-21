"""번들 경로 허용 꼴·번들 안 열기·결과 경로 정규화 시험 (실험구조 2.2, 2.5 조건 2, 2.9, F-G02 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from common.contracts import ContractError, validate_contract
from common.paths import (
    BundlePathError,
    is_bundle_relpath,
    normalize_finding_path,
    resolve_in_bundle,
)
from tests.common.examples import answers_example, first_item, first_location
from tests.conftest import MakeBundle

# 가상 실행 폴더 (실험구조 1절 '저장소 밖' 꼴)
ROOT = (
    "C:\\Users\\fake\\AppData\\Local\\SelfAudit-bench-runs"
    "\\20261122-0900-abcd\\easy-1-a-1-3f2a9c10\\target"
)
ROOT_SLASH = ROOT.replace("\\", "/")

REJECTED = [
    "assets\\index.js",  # 역슬래시
    "/assets/index.js",  # 앞 슬래시(빈 마디)
    "./assets/index.js",
    "../index.js",
    "assets/../index.js",
    "assets/./index.js",
    "assets/..",
    "assets/.",
    ".",
    "..",
    "",
    "a//b.js",  # 빈 마디
    "assets/",
    "C:/Windows/win.ini",  # 드라이브
    "a/D:/x",
    "C:x",
    "a.js:s",  # NTFS 대체 데이터 흐름
    "a.js.",  # 끝 점(Windows가 지운다)
    "a.js ",  # 끝 공백
    " a.js",  # 앞 공백
    "CON",  # 장치 이름
    "con.txt",
    "assets/NUL.js",
    "COM1",
    "LPT9.txt",
    "COM" + chr(0xB9) + ".js",
    "CON .txt",
    "a*b.js",
    "a?b.js",
    "a|b.js",
    "a<b.js",
    'a"b.js',
    "a" + chr(0x09) + "b.js",  # 제어 글자(탭)
    "assets/index.js" + chr(0x0A),
    "assets/a" + chr(0x0D) + ".js",
    "a" + chr(0x01) + ".js",
    "a" + chr(0x200B) + ".js",  # 폭 없는 공백
    "a" + chr(0x202E) + "sj.js",  # 방향 뒤집기
    "a" + chr(0xD800) + ".js",  # 짝 없는 서로게이트
    "a" + chr(0xE000) + ".js",  # 사용자 정의 글자
    "a" + chr(0x2028) + ".js",  # 줄 구분
    "a" * 256,  # 마디 하나 255자 넘음
    ("a" * 200 + "/") + "b" * 100,  # 전체 301자
]
ACCEPTED = [
    "assets/index-3f2a.js",
    "index.html",
    ".well-known/a.txt",
    "a..b/c.js",
    "...js",
    "a b.js",  # 가운데 공백
    "CONSOLE.js",
    "COM10.txt",
    "con-1.js",
    "uploads/" + chr(0x14DA) + chr(0x160F) + "-#zatschi.jpg",  # 다른 문자 체계
    "uploads/" + chr(0x1F63C) + "-#zatschi.jpg",  # 그림 글자(서로게이트 쌍이 아닌 한 글자)
    "a" * 255,
    ("a" * 200 + "/") + "b" * 99,  # 전체 300자
]


@pytest.mark.parametrize("path", REJECTED)
def test_common_경로꼴_역슬래시·앞슬래시·점점_거절(path: str) -> None:
    assert not is_bundle_relpath(path)


@pytest.mark.parametrize("path", ACCEPTED)
def test_common_경로꼴_통과(path: str) -> None:
    assert is_bundle_relpath(path)


def test_common_경로꼴_정답지계약도_같음() -> None:
    data = answers_example()
    first_location(first_item(data))["file"] = "assets\\index-3f2a.js"
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0].file", "format bundle-relpath")
    ]


def test_common_번들안_열기(make_bundle: MakeBundle) -> None:
    bundle = make_bundle({"assets/a.js": b"x"})
    assert resolve_in_bundle(bundle, "assets/a.js") == (bundle / "assets" / "a.js").resolve()
    with pytest.raises(BundlePathError):
        resolve_in_bundle(bundle, "../a.js")
    with pytest.raises(BundlePathError):
        resolve_in_bundle(bundle, "C:/Windows/win.ini")


def test_common_번들안_열기_정션은_밖(make_bundle: MakeBundle, tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("정션은 Windows에만 있다")
    import _winapi  # Windows에서만 있는 모듈이라 여기서 부른다

    outside = tmp_path / "outside"
    outside.mkdir()
    bundle = make_bundle({"a.js": b"x"})
    _winapi.CreateJunction(str(outside), str(bundle / "jlink"))
    with pytest.raises(BundlePathError, match="번들 밖"):
        resolve_in_bundle(bundle, "jlink/x.js")


def test_common_시험번들_만들기도_허용꼴만(make_bundle: MakeBundle) -> None:
    with pytest.raises(BundlePathError):
        make_bundle({"../escape.js": b"x"})


@pytest.mark.parametrize(
    ("file", "root", "expected"),
    [
        # 기능명세 F-G02 예시 두 줄 그대로
        ("C:\\RUN\\target\\assets\\m-9c1e.js", "C:\\RUN\\target", "assets/m-9c1e.js"),
        ("c:/run/target/assets/m-9c1e.js", "C:\\RUN\\target", "c:/run/target/assets/m-9c1e.js"),
    ],
)
def test_common_결과경로_F_G02_예시(file: str, root: str, expected: str) -> None:
    assert normalize_finding_path(file, root) == expected


@pytest.mark.parametrize(
    ("file", "expected"),
    [
        (ROOT + "\\assets\\index-3f2a.js", "assets/index-3f2a.js"),
        (ROOT_SLASH + "/assets/index-3f2a.js", "assets/index-3f2a.js"),
        ("c" + ROOT[1:] + "\\assets\\x.js", "c" + ROOT_SLASH[1:] + "/assets/x.js"),  # 글자 그대로
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
