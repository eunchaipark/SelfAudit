"""번들 지문 시험 (기능명세 F-B04, 실험구조 2.2 `bundle_manifest_sha256`, 2.9)."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from common.fingerprint import (
    ManifestError,
    bundle_manifest_sha256,
    format_manifest,
    manifest_lines,
)
from tests.conftest import MakeBundle

LF = bytes([0x0A])
CRLF = bytes([0x0D, 0x0A])
FILES = {
    "index.html": b"<html></html>" + LF,
    "assets/a.js": b"console.log(1)" + LF,
    "assets/B.js": b"B",
    "assets-x/z.js": b"",
    "한글.txt": "가짜 값".encode(),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_F_B04_예시_두파일_지문(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(
        {"index.html": b"<!doctype html>" + LF, "assets/app.js": b"console.log(1)" + LF}
    )
    assert manifest_lines(bundle) == [
        "assets/app.js\t3879a5d930ae1999b278a3a498f7de3fd83ba8dae59330fcfa2db31c103ac21d\n",
        "index.html\t335fca8574f060eea24ebcdae6b78f32414f5de03da1084fd0e73d710768e3a9\n",
    ]
    expected = "bc0d66f7f304129e1ccb817e6a3b5cfe4fe53e031c08703e76da0634446946ed"
    assert bundle_manifest_sha256(bundle) == expected


def test_F_B04_예시_줄바꿈만_바뀌면_다른지문(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(
        {"index.html": b"<!doctype html>" + LF, "assets/app.js": b"console.log(1)" + CRLF}
    )
    expected = "a9ac53474d219871fe2158df818a3c75eec3438faf3e36f0410d287b543f20fb"
    assert bundle_manifest_sha256(bundle) == expected


def test_F_B04_예시_경로_차례() -> None:
    names = ["index.html", "assets/app.js.map", "assets/app.js", "Assets/x.js", "assets/app-2.js"]
    lines = format_manifest(dict.fromkeys(names, "0" * 64))
    assert [line.split("\t")[0] for line in lines] == [
        "Assets/x.js",
        "assets/app-2.js",
        "assets/app.js",
        "assets/app.js.map",
        "index.html",
    ]


def test_F_B04_빈폴더는_멈춤(tmp_path: Path) -> None:
    # 기능명세 예시는 빈 글의 지문이지만 총괄 판단(T20 반려 1)으로 멈춘다 — 실험구조 2.9
    (tmp_path / "bundle" / "empty").mkdir(parents=True)
    with pytest.raises(ManifestError, match="파일이 하나도 없는 번들"):
        bundle_manifest_sha256(tmp_path / "bundle")


def test_common_지문_경로순_탭_줄바꿈_sha256(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(FILES)
    (bundle / "empty").mkdir()
    # 코드 포인트 차례: '-'(2D) < '/'(2F), 'B'(42) < 'a'(61), ASCII < 한글. 빈 폴더는 넣지 않는다
    expected_lines = [
        f"assets-x/z.js\t{sha(b'')}\n",
        f"assets/B.js\t{sha(b'B')}\n",
        f"assets/a.js\t{sha(b'console.log(1)' + LF)}\n",
        f"index.html\t{sha(b'<html></html>' + LF)}\n",
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
    with pytest.raises(ManifestError, match="jlink"):
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


def test_common_지문_하드링크_멈춤(make_bundle: MakeBundle, tmp_path: Path) -> None:
    outside = tmp_path / "outside.js"
    outside.write_bytes(b"x")
    bundle = make_bundle(FILES)
    os.link(outside, bundle / "hard.js")
    with pytest.raises(ManifestError, match=r"하드링크: 'hard\.js'"):
        bundle_manifest_sha256(bundle)


def test_F_B04_읽을수없는_파일_경로알림(
    make_bundle: MakeBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle(FILES)
    real_open = Path.open

    def deny(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "B.js":
            raise PermissionError("가짜 거절")
        return real_open(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(ManifestError, match=r"읽을 수 없는 파일: 'assets/B\.js'"):
        bundle_manifest_sha256(bundle)


def test_common_지문_허용꼴밖_이름_멈춤(make_bundle: MakeBundle) -> None:
    bundle = make_bundle(FILES)
    try:
        (bundle / "a.js ").write_bytes(b"x")  # 끝 공백: Windows는 지워서 만든다
    except OSError:
        pytest.skip("이 파일 시스템은 그 이름을 받지 않는다")
    if not (bundle / "a.js ").exists() or "a.js " not in os.listdir(bundle):
        pytest.skip("Windows가 끝 공백을 지워 만들었다")
    with pytest.raises(ManifestError, match="허용 꼴"):
        bundle_manifest_sha256(bundle)


def test_F_B04_읽을수없는_폴더_경로알림(
    make_bundle: MakeBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = make_bundle({"assets/sub/a.js": b"x", "index.html": b"y"})
    real_scandir = os.scandir

    def deny(path: str) -> object:
        if Path(path).name == "sub":
            raise PermissionError(13, "가짜 거절", str(path))
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", deny)
    with pytest.raises(ManifestError, match=r"번들 폴더를 읽을 수 없음: 'assets/sub'"):
        bundle_manifest_sha256(bundle)
