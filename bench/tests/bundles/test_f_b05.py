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
                # 내 앱의 필수 칸(설계 실험구조 8.9 2). 있어야 아래 두 경로 거절만 남는다
                "bundle_manifest_sha256": "a" * 64,
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


def _repo_with(mini: Mini, root: Path, target_id: str, kind: str, copy_bundle: bool = True) -> Path:
    """`root` 아래에 저장소 꼴(bench/bundles·answers·targets.json)을 만든다.

    돌려주는 것은 대상 목록 경로.
    """
    bundle = root / "bench" / "bundles" / target_id
    if copy_bundle:
        shutil.copytree(mini.bundle_dir, bundle)
    answers_path = root / "bench" / "answers" / f"{target_id}.json"
    answers_path.parent.mkdir(parents=True)
    answers = {**mini.answers, "bundle_id": target_id}
    answers_path.write_text(json.dumps(answers), encoding="utf-8")
    entry = {
        "id": target_id,
        "kind": kind,
        "bundle": f"bench/bundles/{target_id}",
        "answers": f"bench/answers/{target_id}.json",
    }
    targets_path = root / "bench" / "targets.json"
    value = {"schema": "selfaudit-bench/targets@1", "targets": [entry]}
    targets_path.write_text(json.dumps(value), encoding="utf-8")
    return targets_path


@pytest.mark.parametrize(
    ("kind", "expected"), [("planted", []), ("practice", [("F-B05 4", "$.origin")])]
)
def test_F_B05_종류와_정답지origin_다르면_멈춤(
    kind: str, expected: list[tuple[str, str]], mini_bundle: Mini, tmp_path: Path
) -> None:
    """명세 예시 `juice-shop-17`: practice인데 정답지 origin이 planted → 멈춤."""
    root = tmp_path / "repo"
    targets_path = _repo_with(mini_bundle, root, "juice-shop-17", kind)
    target = repo_target("juice-shop-17", targets_path, root)
    assert target.bundle_dir == root / "bench" / "bundles" / "juice-shop-17"
    report = check_target(target)
    assert [(p.rule, p.where) for p in report.problems] == expected


def test_F_B05_번들폴더없음_멈춤(mini_bundle: Mini, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    targets_path = _repo_with(mini_bundle, root, "easy-1", "planted", copy_bundle=False)
    report = check_target(repo_target("easy-1", targets_path, root))
    assert [(p.rule, p.where) for p in report.problems] == [("F-B05", "bundle")]


def test_F_B05_목록에_없는_대상_멈춤() -> None:
    with pytest.raises(LookupError, match="juice-shop-17"):
        repo_target("juice-shop-17")
