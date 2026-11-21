"""번들 지문 시험 (실험구조 2.2 `bundle_manifest_sha256`, 2.9)."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from common.fingerprint import ManifestError, bundle_manifest_sha256, manifest_lines
from tests.conftest import MakeBundle

FILES = {
    "index.html": b"<html></html>\n",
    "assets/a.js": b"console.log(1)\n",
    "assets/B.js": b"B",
    "assets-x/z.js": b"",
    "한글.txt": "가짜 값".encode(),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_common_지문_경로순_탭_줄바꿈_sha256(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(FILES)
    (bundle / "empty").mkdir()
    # 코드 포인트 차례: '-'(2D) < '/'(2F), 'B'(42) < 'a'(61), ASCII < 한글. 빈 폴더는 넣지 않는다
    expected_lines = [
        f"assets-x/z.js\t{sha(b'')}\n",
        f"assets/B.js\t{sha(b'B')}\n",
        f"assets/a.js\t{sha(b'console.log(1)' + bytes([10]))}\n",
        f"index.html\t{sha(b'<html></html>' + bytes([10]))}\n",
        f"한글.txt\t{sha('가짜 값'.encode())}\n",
    ]
    assert manifest_lines(bundle) == expected_lines
    assert bundle_manifest_sha256(bundle) == sha("".join(expected_lines).encode())


def test_common_지문_한글자_바뀌면_다름(make_bundle: MakeBundle) -> None:
    before = bundle_manifest_sha256(make_bundle(FILES, name="before"))
    changed = {**FILES, "assets/B.js": b"C"}
    renamed = {("assets/b2.js" if k == "assets/B.js" else k): v for k, v in FILES.items()}
    assert bundle_manifest_sha256(make_bundle(changed, name="changed")) != before
    assert bundle_manifest_sha256(make_bundle(renamed, name="renamed")) != before
    assert bundle_manifest_sha256(make_bundle(FILES, name="same")) == before


def test_common_지문_빈번들_멈춤(tmp_path: Path) -> None:
    (tmp_path / "bundle" / "empty").mkdir(parents=True)
    with pytest.raises(ManifestError):
        bundle_manifest_sha256(tmp_path / "bundle")


def test_common_지문_폴더아님_멈춤(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        bundle_manifest_sha256(tmp_path / "없음")


def test_common_지문_정션_멈춤(make_bundle: MakeBundle, tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("정션은 Windows에만 있다")
    import _winapi  # Windows에서만 있는 모듈이라 여기서 부른다

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.js").write_bytes(b"x")
    bundle = make_bundle(FILES)
    _winapi.CreateJunction(str(outside), str(bundle / "jlink"))
    with pytest.raises(ManifestError):
        bundle_manifest_sha256(bundle)


def test_common_지문_심볼릭링크_멈춤(make_bundle: MakeBundle, tmp_path: Path) -> None:
    outside = tmp_path / "outside.js"
    outside.write_bytes(b"x")
    bundle = make_bundle(FILES)
    try:
        os.symlink(outside, bundle / "link.js")
    except OSError:
        pytest.skip("이 PC는 심볼릭 링크를 만들 권한이 없다(Windows 개발자 모드 꺼짐)")
    with pytest.raises(ManifestError):
        bundle_manifest_sha256(bundle)


def test_common_지문_탭든_이름_멈춤(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(FILES)
    try:
        (bundle / ("a" + chr(9) + "b.js")).write_bytes(b"x")
    except OSError:
        pytest.skip("이 파일 시스템은 이름에 탭을 받지 않는다(Windows)")
    with pytest.raises(ManifestError):
        bundle_manifest_sha256(bundle)
