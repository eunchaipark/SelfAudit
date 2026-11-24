"""번들·정답지 시험 공통 (번들 레인).

원본·결과물 폴더는 tmp_path 아래에 만든다(저장소의 번들을 건드리지 않는다).

- `write_source(bundle_id, plan, files)` → 원본 폴더 `<tmp>/sources/<id>/`(plan.json·src/)
- `mini_bundle` → 손으로 만든 작은 번들(`fixtures/mini-1/`)의 복사본과 정답지 값. F-B07 틀 시험용
값은 모두 가짜다(F-B02 4절 꼴).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest

from common.contracts import Json, read_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MINI_ID = "mini-1"


class WriteSource(Protocol):
    def __call__(
        self, bundle_id: str, plan: Mapping[str, Json], files: Mapping[str, str | bytes]
    ) -> Path: ...


@dataclass(frozen=True)
class Dirs:
    sources: Path
    bundles: Path


@dataclass(frozen=True)
class Mini:
    bundle_dir: Path
    answers: dict[str, Json]


def make_plan(bundle_id: str, **overrides: Json) -> dict[str, Json]:
    """빌드 설정(plan.json) 기본값 + 고칠 칸."""
    plan: dict[str, Json] = {
        "schema": "selfaudit-bench/plan@1",
        "bundle_id": bundle_id,
        "mode": "expanded",
        "hash_names": [],
        "sourcemaps": [],
        "sourcemap_content": False,
        "values": {},
        "plugins": [],
        "steps": [],
    }
    plan.update(overrides)
    return plan


@pytest.fixture
def dirs(tmp_path: Path) -> Dirs:
    sources, bundles = tmp_path / "sources", tmp_path / "bundles"
    sources.mkdir()
    bundles.mkdir()
    return Dirs(sources, bundles)


@pytest.fixture
def write_source(dirs: Dirs) -> WriteSource:
    def write(bundle_id: str, plan: Mapping[str, Json], files: Mapping[str, str | bytes]) -> Path:
        root = dirs.sources / bundle_id
        (root / "src").mkdir(parents=True)
        (root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        for rel, content in files.items():
            path = root / "src" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8") if isinstance(content, str) else content
            path.write_bytes(data)
        return root

    return write


@pytest.fixture
def mini_bundle(tmp_path: Path) -> Mini:
    bundle_dir = tmp_path / MINI_ID
    shutil.copytree(FIXTURES / MINI_ID / "bundle", bundle_dir)
    answers = read_json(FIXTURES / MINI_ID / "answers.json")
    assert isinstance(answers, dict)
    return Mini(bundle_dir, answers)


# --- 64자 앞 조각의 기대값 (F-B03 5, 설계 8.8 2) — 정답지 명령(`locate`)과 따로 셈 ----------------

SHORT_MAX = 64  # 줄로 가를 수 없는 위치가 있는 정답·미끼의 닻·풀어낸 값 상한
SHORT_FROM = 16  # 앞 조각의 가장 짧은 길이
COVER_T = 2  # 줄 허용 범위 T(F-G02 2㉢)
_LF_BYTE = 0x0A


def bundle_texts(bundle_dir: Path) -> dict[str, bytes]:
    """번들 파일 {번들 안 경로: 바이트}(심은 번들은 모두 글 파일이다)."""
    return {
        p.relative_to(bundle_dir).as_posix(): p.read_bytes()
        for p in sorted(bundle_dir.rglob("*"))
        if p.is_file()
    }


def _locations(entry: Mapping[str, Json]) -> list[dict[str, Json]]:
    value = entry.get("locations")
    return [loc for loc in value if isinstance(loc, dict)] if isinstance(value, list) else []


def _line(loc: Mapping[str, Json], key: str) -> int:
    value = loc[key]
    assert isinstance(value, int)
    return value


def _unsplittable(entry: Mapping[str, Json]) -> bool:
    return any(
        _line(loc, "line_start") - COVER_T <= 1
        and _line(loc, "line_end") + COVER_T >= _line(loc, "file_lines")
        for loc in _locations(entry)
    )


def _only_in_locations(piece: str, entry: Mapping[str, Json], texts: Mapping[str, bytes]) -> bool:
    """조각이 번들에 한 번 이상 나오고, 나오는 곳(시작 글자가 든 줄)이 모두 그 정답의 위치 안."""
    needle = piece.encode("utf-8")
    seen = False
    for rel, data in texts.items():
        start = data.find(needle)
        while start >= 0:
            line = data.count(_LF_BYTE, 0, start) + 1
            inside = any(
                loc["file"] == rel and _line(loc, "line_start") <= line <= _line(loc, "line_end")
                for loc in _locations(entry)
            )
            if not inside:
                return False
            seen = True
            start = data.find(needle, start + 1)
    return seen


def _anchor_texts(entry: Mapping[str, Json]) -> list[str]:
    texts = [v for v in (entry.get("anchor"), entry.get("decoded_anchor")) if isinstance(v, str)]
    texts += [str(loc["anchor"]) for loc in _locations(entry) if isinstance(loc.get("anchor"), str)]
    return texts


def expected_short(
    value: str,
    entry: Mapping[str, Json],
    answers: Mapping[str, Json],
    texts: Mapping[str, bytes],
    *,
    decoded: bool,
) -> str:
    """F-B03 5의 기대값(아래 `short_or_none`). 64자 안에 앞 조각이 없으면 시험 실패."""
    found = short_or_none(value, entry, answers, texts, decoded=decoded)
    if found is None:
        raise AssertionError(f"{entry.get('id')}: 64자 안에 앞 조각이 없음")
    return found


def short_or_none(
    value: str,
    entry: Mapping[str, Json],
    answers: Mapping[str, Json],
    texts: Mapping[str, bytes],
    *,
    decoded: bool,
) -> str | None:
    """F-B03 5의 기대값: 값이 64자 이하이거나 줄로 가를 수 없는 위치가 없으면 값 그대로.

    아니면 16자부터 한 자씩 늘려 처음 지키는 앞 조각 — 닻은 번들 안 나오는 곳이 모두 그 정답
    위치 안(F-B07 6), 풀어낸 값은 ㉠ 번들 글 어디에도 없고 ㉡ 다른 정답·미끼의 닻·풀어낸 값·위치
    닻(정답지에 적힌 값)과 어느 쪽으로도 겹치지 않음. 64자 안에 없으면 None.
    """
    if len(value) <= SHORT_MAX or not _unsplittable(entry):
        return value
    others = [
        text
        for group in ("items", "decoys")
        for other in (answers.get(group) or [])  # type: ignore[union-attr]
        if isinstance(other, dict) and other.get("id") != entry.get("id")
        for text in _anchor_texts(other)
    ]
    for length in range(SHORT_FROM, SHORT_MAX + 1):
        piece = value[:length]
        if not decoded:
            if _only_in_locations(piece, entry, texts):
                return piece
            continue
        if any(piece.encode("utf-8") in data for data in texts.values()):
            continue
        if not any(piece in other or other in piece for other in others):
            return piece
    return None
