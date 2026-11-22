"""F-B05 대상 목록 `bench/targets.json` (기능명세 F-B05 예시, 설계 2.7 표, 4절 ⑶).

계약 뜻 규칙(경로 꼴·ID 겹침·내 앱 경로)의 시험은 공통(`tests/common/test_semantics.py`)에 있다.
여기서는 저장소의 목록 자체와, 저장소 목록의 `mine`을 검사 '실험자료'가 막는지를 본다.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

from common.contracts import Json, read_contract, validate_contract
from sources.build_tools.verify import REPO_ROOT, TARGETS_PATH, check_target, repo_target
from tests.bundles.conftest import Mini

PLANTED = ["easy-1", "easy-2", "normal-1", "normal-2", "hard-1", "hard-2"]  # 설계 2.7 표


def _check_bench() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_bench_for_test", REPO_ROOT / "ops" / "scripts" / "check_bench.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _OneFile:
    """check_bench `Files`의 두 메서드만 흉내 낸다(저장소·색인을 건드리지 않고 목록 하나만 보게)."""

    def __init__(self, value: Json) -> None:
        self.value = value

    def paths(self) -> list[str]:
        return ["bench/targets.json"]

    def json_versions(self, path: str) -> list[tuple[str, object]]:
        return [("작업 폴더", self.value)]


def _load_targets(value: Json) -> tuple[dict[str, str], list[str]]:
    problems: list[str] = []
    kinds: dict[str, str] = _check_bench().load_targets(_OneFile(value), problems)
    return kinds, problems


def test_F_B05_종류_planted_practice만() -> None:
    targets = read_contract("targets", TARGETS_PATH)
    entries = targets["targets"]
    assert isinstance(entries, list)
    kinds = {str(e["id"]): e["kind"] for e in entries if isinstance(e, dict)}
    assert list(kinds) == PLANTED
    assert set(kinds.values()) <= {"planted", "practice"}
    checked, problems = _load_targets(json.loads(TARGETS_PATH.read_text(encoding="utf-8")))
    assert problems == []
    assert checked == kinds


def test_F_B05_mine_거절() -> None:
    value: Json = {
        "schema": "selfaudit-bench/targets@1",
        "targets": [
            {
                "id": "mine-blog",
                "kind": "mine",
                "bundle": "bench/bundles/mine-blog",
                "answers": "bench/answers/mine-blog.json",
            }
        ],
    }
    kinds, problems = _load_targets(value)
    assert kinds == {}
    assert len(problems) == 1
    assert "mine" in problems[0]
    # 저장소 안 경로를 가리키는 mine은 계약 뜻 규칙에서도 걸린다(드라이브 절대 경로·저장소 밖만)
    assert [e.where for e in validate_contract("targets", value)] == [
        "$.targets[0].bundle",
        "$.targets[0].answers",
    ]


def test_F_B05_번들경로는_bench_bundles_id만() -> None:
    value: Json = {
        "schema": "selfaudit-bench/targets@1",
        "targets": [
            {
                "id": "easy-1",
                "kind": "planted",
                "bundle": "bench/bundles/easy-2",
                "answers": "bench/answers/easy-1.json",
            }
        ],
    }
    assert [e.where for e in validate_contract("targets", value)] == ["$.targets[0].bundle"]


def test_F_B05_종류와_정답지origin_다르면_멈춤(mini_bundle: Mini, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    bundle = root / "bench" / "bundles" / "mini-1"
    shutil.copytree(mini_bundle.bundle_dir, bundle)
    answers_path = root / "bench" / "answers" / "mini-1.json"
    answers_path.parent.mkdir(parents=True)
    answers_path.write_text(json.dumps(mini_bundle.answers), encoding="utf-8")
    targets_path = root / "bench" / "targets.json"
    entry = {
        "id": "mini-1",
        "bundle": "bench/bundles/mini-1",
        "answers": "bench/answers/mini-1.json",
    }
    for kind, expected in (("planted", []), ("practice", [("F-B05 4", "$.origin")])):
        value = {"schema": "selfaudit-bench/targets@1", "targets": [{**entry, "kind": kind}]}
        targets_path.write_text(json.dumps(value), encoding="utf-8")
        target = repo_target("mini-1", targets_path, root)
        assert target.bundle_dir == bundle
        report = check_target(target)
        assert [(p.rule, p.where) for p in report.problems] == expected


def test_F_B05_목록에_없는_대상_멈춤() -> None:
    with pytest.raises(LookupError, match="juice-shop-17"):
        repo_target("juice-shop-17")
