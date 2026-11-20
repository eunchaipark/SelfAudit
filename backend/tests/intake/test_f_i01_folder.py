"""F-I01 B 1·4~10 폴더 받기와 공통 분류·제한 — 기능명세 예시를 옮긴다.

번들은 테스트 안에서 임시 폴더에 만든다(합성 파일만). 개수·크기 합 제한은 `core/limits` 값을
기본값으로 쓰는 `IntakeLimits`에 작은 값을 넣어 시험한다(파일 2만 개를 만들지 않는다).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from app.contracts.engine import IntakeFailed, Skipped, SkipReason
from app.core import limits
from app.intake import engine, receive_folder
from app.intake.engine import Entry, EntryKind, IntakeLimits
from app.intake.service import make_quarantine, write_bundle

MSG_TOO_LARGE = "번들이 너무 큽니다 (최대 200MB, 20,000개)"
MSG_OTHER = "점검 중 오류가 나서 멈췄습니다"


def make_bundle(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def sized_file(path: Path, size: int) -> None:
    """내용은 상관없고 크기만 필요한 파일 (0으로 채워진다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)


def listing(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---- 예시 ----


def test_F_I01_png는_디스크에_쓰지_않음(tmp_path: Path) -> None:
    files = {
        "index.html": b"<html></html>",
        "assets/index-BmR2x9Qa.js": b"console.log(1)",
        "assets/logo.png": b"\x89PNG....",
    }
    src = make_bundle(tmp_path / "dist", files)
    before = listing(src)

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.total_files == 3
    assert result.targets == ("assets/index-BmR2x9Qa.js", "index.html")
    assert result.skipped == (Skipped("assets/logo.png", SkipReason.NOT_TARGET),)
    assert result.unpacked_bytes == sum(len(v) for v in files.values())
    assert listing(result.root) == ["assets/index-BmR2x9Qa.js", "index.html"]
    assert not (result.root / "assets" / "logo.png").exists()
    assert listing(src) == before  # 원본 폴더에는 쓰지 않는다 (보안규칙 5장)


def test_F_I01_APP대문자_대상(tmp_path: Path) -> None:
    src = make_bundle(tmp_path / "dist", {"APP.JS": b"a", "Style.CSS": b"b", "x.Map": b"{}"})

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.targets == ("APP.JS", "Style.CSS", "x.Map")
    assert result.skipped == ()
    assert (result.root / "APP.JS").read_bytes() == b"a"


def test_F_I01_png만5개_대상없음(tmp_path: Path) -> None:
    src = make_bundle(tmp_path / "dist", {f"img{i}.png": b"p" for i in range(5)})

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.total_files == 5
    assert result.targets == ()
    assert [s.reason for s in result.skipped] == [SkipReason.NOT_TARGET] * 5
    assert listing(result.root) == []


def test_F_I01_52428800바이트_대상_52428801_건너뜀(tmp_path: Path) -> None:
    src = tmp_path / "dist"
    sized_file(src / "vendor.js", 52_428_800)
    sized_file(src / "vendor2.js", 52_428_801)

    result = receive_folder(src, tmp_path / "work" / "1")

    assert limits.MAX_FILE_BYTES == 52_428_800
    assert result.targets == ("vendor.js",)
    assert result.skipped == (Skipped("vendor2.js", SkipReason.TOO_LARGE),)
    assert (result.root / "vendor.js").stat().st_size == 52_428_800
    assert not (result.root / "vendor2.js").exists()
    assert result.unpacked_bytes == 52_428_800 + 52_428_801


def test_F_I01_20000개_통과_20001개_실패(tmp_path: Path) -> None:
    assert engine.DEFAULT_LIMITS.max_files == limits.MAX_FILES == 20_000
    small = IntakeLimits(max_files=3)
    ok = make_bundle(tmp_path / "ok", {f"{i}.js": b"x" for i in range(3)})
    over = make_bundle(tmp_path / "over", {f"{i}.png": b"x" for i in range(4)})

    assert receive_folder(ok, tmp_path / "work" / "1", limits=small).total_files == 3
    with pytest.raises(IntakeFailed) as err:
        receive_folder(over, tmp_path / "work" / "2", limits=small)
    assert err.value.reason == MSG_TOO_LARGE


def test_F_I01_심볼릭링크_건너뜀_정션(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("정션은 Windows에만 있다")
    import _winapi

    outside = make_bundle(tmp_path / "outside", {"secret.js": b"s"})
    src = make_bundle(tmp_path / "dist", {"a.js": b"a"})
    _winapi.CreateJunction(str(outside), str(src / "linked"))

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.targets == ("a.js",)
    assert result.skipped == (Skipped("linked", SkipReason.SYMLINK),)
    assert result.total_files == 2
    assert listing(result.root) == ["a.js"]


def test_F_I01_심볼릭링크_건너뜀(tmp_path: Path) -> None:
    outside = make_bundle(tmp_path / "outside", {"secret.js": b"s"})
    src = make_bundle(tmp_path / "dist", {"a.js": b"a"})
    try:
        os.symlink(outside / "secret.js", src / "b.js")
        os.symlink(outside, src / "dir", target_is_directory=True)
    except OSError:
        pytest.skip("이 PC에서는 심볼릭 링크를 만들 권한이 없다 (정션 테스트가 대신한다)")

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.targets == ("a.js",)
    assert result.skipped == (
        Skipped("b.js", SkipReason.SYMLINK),
        Skipped("dir", SkipReason.SYMLINK),
    )
    assert listing(result.root) == ["a.js"]


# ---- 경계와 공통 제한 ----


def test_F_I01_크기합_한도까지_통과_넘으면_실패(tmp_path: Path) -> None:
    assert engine.DEFAULT_LIMITS.max_unpacked_bytes == limits.MAX_UNPACKED_BYTES == 209_715_200
    small = IntakeLimits(max_unpacked_bytes=10)
    ok = make_bundle(tmp_path / "ok", {"a.js": b"x" * 6, "b.png": b"y" * 4})
    over = make_bundle(tmp_path / "over", {"a.js": b"x" * 6, "b.png": b"y" * 5})

    assert receive_folder(ok, tmp_path / "work" / "1", limits=small).unpacked_bytes == 10
    with pytest.raises(IntakeFailed) as err:
        receive_folder(over, tmp_path / "work" / "2", limits=small)
    assert err.value.reason == MSG_TOO_LARGE


def test_F_I01_건너뛴_큰파일도_크기합에_든다(tmp_path: Path) -> None:
    small = IntakeLimits(max_unpacked_bytes=10, max_file_bytes=4)
    src = make_bundle(tmp_path / "dist", {"a.js": b"x" * 3, "big.js": b"y" * 8})

    with pytest.raises(IntakeFailed) as err:
        receive_folder(src, tmp_path / "work" / "1", limits=small)
    assert err.value.reason == MSG_TOO_LARGE


def test_F_I01_크기초과가_종류보다_먼저() -> None:
    small = IntakeLimits(max_file_bytes=4)
    assert engine.skip_reason(Entry("big.png", 5), small) is SkipReason.TOO_LARGE
    assert engine.skip_reason(Entry("ok.png", 4), small) is SkipReason.NOT_TARGET
    assert engine.skip_reason(Entry("ok.js", 4), small) is None
    assert engine.skip_reason(Entry("l.js", 0, EntryKind.LINK), small) is SkipReason.SYMLINK


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("a.js", True),
        ("a.mjs", True),
        ("a.cjs", True),
        ("a.css", True),
        ("a.html", True),
        ("a.htm", True),
        ("a.json", True),
        ("a.js.map", True),
        ("A.HTM", True),
        ("a.ts", False),
        ("a.js.txt", False),
        ("js", False),
        ("assets.js/readme", False),
    ],
)
def test_F_I01_대상_확장자(path: str, target: bool) -> None:
    assert engine.is_target(path) is target


def test_F_I01_바이트를_바꾸지_않고_쓴다(tmp_path: Path) -> None:
    """9: BOM·깨진 바이트는 읽을 때(규칙) 다룬다. 받기는 바이트 그대로 둔다."""
    data = b"\xef\xbb\xbfconst a = '\xff\xfe';\r\n"
    src = make_bundle(tmp_path / "dist", {"a.js": data})

    result = receive_folder(src, tmp_path / "work" / "1")

    assert (result.root / "a.js").read_bytes() == data


def test_F_I01_하위폴더_경로는_슬래시(tmp_path: Path) -> None:
    src = make_bundle(tmp_path / "dist", {"b/c/d.js": b"d", "a.css": b"a", "b/a.json": b"{}"})

    result = receive_folder(src, tmp_path / "work" / "1")

    assert result.targets == ("a.css", "b/a.json", "b/c/d.js")


# ---- 격리 폴더 (1·7) ----


def test_F_I01_격리폴더가_이미있으면_실패(tmp_path: Path) -> None:
    src = make_bundle(tmp_path / "dist", {"a.js": b"a"})
    dest = tmp_path / "work" / "1"
    dest.mkdir(parents=True)

    with pytest.raises(IntakeFailed) as err:
        receive_folder(src, dest)
    assert err.value.reason == MSG_OTHER


@contextmanager
def opener_from(data: dict[str, bytes], path: str) -> Iterator[BinaryIO]:
    yield BytesIO(data[path])


def test_F_I01_격리폴더에_같은파일_있으면_덮어쓰지않고_실패(tmp_path: Path) -> None:
    root = make_quarantine(tmp_path / "work" / "1")
    entries = (Entry("a.js", 5), Entry("a.js", 5))
    contents = iter([b"first", b"second"])

    @contextmanager
    def opener(_: str) -> Iterator[BinaryIO]:
        yield BytesIO(next(contents))

    with pytest.raises(IntakeFailed) as err:
        write_bundle(entries, opener, root, engine.DEFAULT_LIMITS)
    assert err.value.reason == MSG_OTHER
    assert (root / "a.js").read_bytes() == b"first"


def test_F_I01_풀다가_크기합을_넘으면_그자리에서_멈춘다(tmp_path: Path) -> None:
    """5: 적힌 크기(폴더는 stat)보다 실제 바이트가 많아도 실제 바이트로 지킨다."""
    root = make_quarantine(tmp_path / "work" / "1")
    data = {"a.js": b"x" * 4, "b.js": b"y" * 20}
    entries = (Entry("a.js", 4), Entry("b.js", 1))  # b.js가 적힌 것보다 크다

    with pytest.raises(IntakeFailed) as err:
        write_bundle(
            entries,
            lambda p: opener_from(data, p),
            root,
            IntakeLimits(max_unpacked_bytes=10),
        )
    assert err.value.reason == MSG_TOO_LARGE


def test_F_I01_풀다가_파일하나_한도를_넘으면_그파일만_건너뜀(tmp_path: Path) -> None:
    root = make_quarantine(tmp_path / "work" / "1")
    data = {"a.js": b"x" * 4, "b.js": b"y" * 6}
    entries = (Entry("a.js", 4), Entry("b.js", 1))

    result = write_bundle(
        entries, lambda p: opener_from(data, p), root, IntakeLimits(max_file_bytes=5)
    )

    assert result.targets == ("a.js",)
    assert result.skipped == (Skipped("b.js", SkipReason.TOO_LARGE),)
    assert not (root / "b.js").exists()
