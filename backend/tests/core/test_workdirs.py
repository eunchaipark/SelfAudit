"""격리 폴더 지우기 (F-I01 11, F-P03 2, 보안규칙 5장). 공용 `core/workdirs.py`."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.core.workdirs import remove_work_dir, remove_work_dirs


def make_work(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    return work


def test_F_P03_2_점검_폴더를_지운다(tmp_path: Path) -> None:
    work = make_work(tmp_path)
    (work / "7" / "assets").mkdir(parents=True)
    (work / "7" / "assets" / "app.js").write_text("var a=1;", encoding="utf-8")
    assert remove_work_dir(work, 7) is True
    assert not (work / "7").exists()


def test_F_P03_2_없는_폴더는_그냥_넘어간다(tmp_path: Path) -> None:
    work = make_work(tmp_path)
    assert remove_work_dir(work, 8) is False


def test_F_P03_2_고른_점검만_지운다(tmp_path: Path) -> None:
    work = make_work(tmp_path)
    for scan_id in (1, 2, 3):
        (work / str(scan_id)).mkdir()
    remove_work_dirs(work, [1, 3])
    assert sorted(p.name for p in work.iterdir()) == ["2"]


def test_보안_정션은_따라가_지우지_않는다(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("정션은 Windows만")
    import _winapi  # 표준 라이브러리 (Windows)

    work = make_work(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("남아야 함", encoding="utf-8")
    _winapi.CreateJunction(str(outside), str(work / "9"))
    assert remove_work_dir(work, 9) is False
    assert (outside / "keep.txt").exists()


def test_보안_파일이면_지우지_않는다(tmp_path: Path) -> None:
    work = make_work(tmp_path)
    (work / "5").write_text("폴더가 아님", encoding="utf-8")
    assert remove_work_dir(work, 5) is False
    assert (work / "5").exists()
