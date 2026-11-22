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
