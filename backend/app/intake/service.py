"""F-I01 번들 받기의 흐름: 격리 폴더 만들기, 폴더 읽기, 대상만 격리 폴더에 쓰기. DB는 없다."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from io import BufferedWriter
from pathlib import Path
from typing import Protocol

from app.contracts.engine import IntakeFailed, IntakeResult, Skipped, SkipReason
from app.intake import engine
from app.intake.engine import DEFAULT_LIMITS, Entry, EntryKind, IntakeLimits

CHUNK_BYTES = 1 << 20  # 흘려 쓰는 단위. 파일 하나를 통째로 메모리에 올리지 않는다
BAD_NAMES = frozenset({"", ".", ".."})


class Source(Protocol):
    def read(self, size: int, /) -> bytes: ...


Opener = Callable[[str], AbstractContextManager[Source]]


def receive_folder(
    source: Path, dest: Path, *, limits: IntakeLimits = DEFAULT_LIMITS
) -> IntakeResult:
    """F-I01 B 1·4~10 폴더 받기. 고른 폴더가 맨 위이고, 대상만 dest(격리 폴더)에 쓴다.

    source는 점검 흐름이 A에서 절대 경로·있음을 확인한 폴더다. dest는 새로 만든다
    (`<데이터 폴더>/work/<점검ID>`). 지우는 것은 점검 흐름이 한다(11).
    실패는 IntakeFailed(화면 문구). 그 밖의 OSError는 올린다(점검 흐름이 '그 밖의 오류'로 바꾼다).
    """
    root = make_quarantine(dest)
    entries = scan_folder(source, limits)
    return write_bundle(entries, lambda path: _open_in(source, path), root, limits)


def make_quarantine(dest: Path) -> Path:
    """F-I01 B 1 격리 폴더를 새로 만든다. 이미 있으면 남의 파일을 섞지 않으려고 실패한다."""
    try:
        dest.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise IntakeFailed(engine.MSG_OTHER) from exc
    return dest.resolve()


def scan_folder(source: Path, limits: IntakeLimits) -> tuple[Entry, ...]:
    """F-I01 4·5 폴더를 훑는다. 링크·정션은 따라가지 않는다. 파일은 열지 않고 크기만 본다.

    개수·크기 합은 훑는 동안 세어, 넘는 순간 멈춘다(큰 폴더를 끝까지 훑지 않는다).
    차례는 경로 글자 차례(같은 폴더면 같은 결과, NFR-04).
    """
    entries: list[Entry] = []
    total = 0
    folders: list[tuple[str, str]] = [(os.fspath(source), "")]
    while folders:
        folder, prefix = folders.pop()
        with os.scandir(folder) as items:
            for item in items:
                entry = _classify(item, prefix + item.name)
                if entry is None:
                    folders.append((item.path, prefix + item.name + "/"))
                    continue
                entries.append(entry)
                total += entry.size
                engine.check_totals(len(entries), total, limits)
    return tuple(sorted(entries, key=lambda e: e.path))


def _classify(item: os.DirEntry[str], path: str) -> Entry | None:
    """폴더면 None(더 들어간다). 정션은 is_dir()가 참이라 링크부터 본다."""
    if item.is_symlink() or item.is_junction():
        return Entry(path, 0, EntryKind.LINK)
    if item.is_dir(follow_symlinks=False):
        return None
    if item.is_file(follow_symlinks=False):
        return Entry(path, item.stat(follow_symlinks=False).st_size)
    return Entry(path, 0, EntryKind.OTHER)


def write_bundle(
    entries: Sequence[Entry], open_source: Opener, root: Path, limits: IntakeLimits
) -> IntakeResult:
    """F-I01 5~8 분류하고 대상만 root에 흘려 쓴다. 폴더·zip이 같이 쓴다.

    크기 합은 적힌 크기로 먼저 보고, 쓰는 동안 실제 바이트로 다시 지킨다(5). 파일 하나가
    쓰는 동안 한도를 넘으면 그 파일만 지우고 건너뛴다(6). 이미 있는 파일은 덮어쓰지 않는다(7).
    """
    total = sum(e.size for e in entries)
    engine.check_totals(len(entries), total, limits)
    targets: list[str] = []
    skipped: list[Skipped] = []
    folders: set[Path] = set()  # 안인지 확인하고 만든 폴더
    for entry in entries:
        reason = engine.skip_reason(entry, limits)
        if reason is None:
            out = _inside(root, entry.path, folders)
            budget = limits.max_unpacked_bytes - (total - entry.size)
            written = _write_target(open_source, entry.path, out, limits.max_file_bytes, budget)
            total += written - entry.size
            if written <= limits.max_file_bytes:
                targets.append(entry.path)
                continue
            reason = SkipReason.TOO_LARGE
            engine.check_totals(len(entries), total, limits)
        skipped.append(Skipped(entry.path, reason))
    return IntakeResult(
        root=root,
        total_files=len(entries),
        targets=tuple(targets),
        skipped=tuple(skipped),
        unpacked_bytes=total,
    )


def _write_target(open_source: Opener, path: str, out: Path, file_max: int, budget: int) -> int:
    """대상 하나를 out에 흘려 쓰고 읽은 바이트 수를 돌려준다.

    file_max를 넘으면 그 자리에서 멈추고 쓴 파일을 지운다(돌려준 수가 file_max보다 크다).
    budget(남은 크기 합)을 넘으면 그 자리에서 실패한다.
    """
    read = 0
    with open_source(path) as src, _create_new(out) as dst:
        while chunk := src.read(CHUNK_BYTES):
            read += len(chunk)
            if read > file_max:
                break
            if read > budget:
                raise IntakeFailed(engine.MSG_TOO_LARGE)
            dst.write(chunk)
    if read > file_max:
        out.unlink()
    return read


def _inside(root: Path, path: str, folders: set[Path]) -> Path:
    """번들 경로를 격리 폴더 안 경로로 바꾸고 그 폴더를 만든다 (보안규칙 5장).

    resolve()는 파일마다 하면 느려서(Windows에서 한 번에 수 ms) 폴더마다 한 번 하고,
    마지막 조각은 맨 이름인지만 본다. 밖으로 나가면 만들기 전에 실패한다.
    """
    out = root.joinpath(*path.split("/"))
    folder = out.parent
    if out.name in BAD_NAMES or out.name != path.rsplit("/", 1)[-1]:
        raise IntakeFailed(engine.MSG_OTHER)
    if folder not in folders:
        if not folder.resolve().is_relative_to(root):
            raise IntakeFailed(engine.MSG_OTHER)
        folder.mkdir(parents=True, exist_ok=True)
        folders.add(folder)
    return out


def _create_new(out: Path) -> BufferedWriter:
    """`xb`로 연다. NTFS 짧은 이름(8.3)이 앞 파일을 가리켜도 덮어쓰지 않는다 (F-I01 7)."""
    try:
        return out.open("xb")
    except FileExistsError as exc:
        raise IntakeFailed(engine.MSG_OTHER) from exc


def _open_in(source: Path, path: str) -> AbstractContextManager[Source]:
    return source.joinpath(*path.split("/")).open("rb")
