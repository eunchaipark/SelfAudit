"""F-R01 실행 계획 (R4) 시험. 기능명세 F-R01 예시를 옮겼다(값은 가상)."""

from __future__ import annotations

import gc
import hashlib
import itertools
import json
import time
import tracemalloc
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from run import plan as rp

KST = timezone(timedelta(hours=9))
EASY = ("easy-1", "easy-2")
SIX = ("easy-1", "easy-2", "normal-1", "normal-2", "hard-1", "hard-2")  # bench/targets.json 차례
# 선형 4N/N 약 4, 제곱 약 16의 가운데(부하 흔들림을 두 배까지 받아 줌, 코드규칙 6장 N·2N 비율)
LINEAR_RATIO_LIMIT = 8.0


def targets(*ids: str, kind: str = "planted") -> dict[str, rp.Target]:
    return {i: rp.Target(id=i, kind=kind, bundle=Path("C:/b") / i, answers=None) for i in ids}


def plan_value(**over: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": "first24",
        "targets": [{"id": t} for t in EASY],
        "default_n": 2,
        "conditions": ["A", "B"],
        "model": "claude-test-model-1",
        "effort": "high",
        "timeout_s": 780,
        "max_budget_usd": 2.52,
        "order_seed": 20261123,
    }
    value.update(over)
    return value


def parse(value: dict[str, Any], known: dict[str, rp.Target] | None = None) -> rp.Plan:
    return rp.parse_plan(value, known if known is not None else targets(*EASY), "0" * 64)


def labels(plan: rp.Plan) -> list[str]:
    return [f"{r.target_id}-{r.condition.lower()}-{r.repeat}" for r in rp.expand_runs(plan)]


def counter_tokens() -> Callable[[], str]:
    numbers: Iterator[int] = itertools.count()
    return lambda: f"{next(numbers):08x}"


def problems(excinfo: pytest.ExceptionInfo[rp.PlanError]) -> str:
    return " | ".join(excinfo.value.problems)


# --- 예시 ------------------------------------------------------------------------------------


def test_F_R01_같은시드_같은차례() -> None:
    first = labels(parse(plan_value()))
    assert first == [
        "easy-1-b-2",
        "easy-2-a-2",
        "easy-1-b-1",
        "easy-1-a-1",
        "easy-2-a-1",
        "easy-2-b-1",
        "easy-1-a-2",
        "easy-2-b-2",
    ]
    assert labels(parse(plan_value())) == first


def test_F_R01_다른시드_다른차례() -> None:
    assert labels(parse(plan_value(order_seed=7))) == [
        "easy-2-b-1",
        "easy-2-b-2",
        "easy-1-b-1",
        "easy-2-a-1",
        "easy-1-a-1",
        "easy-1-b-2",
        "easy-1-a-2",
        "easy-2-a-2",
    ]


def test_F_R01_조건_적힌차례와_상관없이_같은차례() -> None:
    assert labels(parse(plan_value(conditions=["B", "A"]))) == labels(parse(plan_value()))


def test_F_R01_첫실험_24번과_앞넷() -> None:
    value = plan_value(targets=[{"id": t} for t in SIX], order_seed=int("53f186825b51", 16))
    got = labels(parse(value, targets(*SIX)))
    assert value["order_seed"] == 92296808913745
    assert len(got) == 24
    assert got[:4] == ["normal-1-b-2", "normal-1-a-1", "hard-1-b-1", "normal-2-a-2"]


def test_F_R01_없는대상ID_거절() -> None:
    value = plan_value(targets=[{"id": "easy-1"}, {"id": "easy-9"}])
    with pytest.raises(rp.PlanError) as e:
        parse(value)
    assert "$.targets[1].id: 대상 목록(F-B05)에 없음" in problems(e)


@pytest.mark.parametrize("name", ["First_24", "abc", "abcdefghijklm", "first-24", "ｆｉｒｓｔ"])
def test_F_R01_name_꼴아님_거절(name: str) -> None:
    with pytest.raises(rp.PlanError) as e:
        parse(plan_value(name=name))
    assert "$.name" in problems(e)


@pytest.mark.parametrize("conditions", [["A", "C"], ["a"], [], ["A", "A"], "AB"])
def test_F_R01_조건_AB밖_거절(conditions: Any) -> None:
    with pytest.raises(rp.PlanError) as e:
        parse(plan_value(conditions=conditions))
    assert "$.conditions" in problems(e)


@pytest.mark.parametrize(
    ("first_repeat", "n", "expect"),
    [
        (None, 2, [1, 2]),
        (3, 3, [3]),
        (3, 2, None),
        (0, 2, None),
    ],
    ids=["없음_N2", "3_N3", "3_N2", "0"],
)
def test_F_R01_first_repeat(first_repeat: int | None, n: int, expect: list[int] | None) -> None:
    over: dict[str, Any] = {"default_n": n, "targets": [{"id": "easy-1"}]}
    if first_repeat is not None:
        over["first_repeat"] = first_repeat
    if expect is None:
        with pytest.raises(rp.PlanError):
            parse(plan_value(**over))
        return
    runs = rp.expand_runs(parse(plan_value(**over)))
    assert sorted({r.repeat for r in runs}) == expect
    assert len(runs) == 2 * len(expect)


def test_F_R01_대상마다_N() -> None:
    value = plan_value(targets=[{"id": "easy-1", "n": 3}, {"id": "easy-2"}], default_n=1)
    runs = rp.expand_runs(parse(value))
    assert sum(r.target_id == "easy-1" for r in runs) == 6
    assert sum(r.target_id == "easy-2" for r in runs) == 2


@pytest.mark.parametrize(
    ("over", "where"),
    [
        ({"timeout_s": 0}, "$.timeout_s"),
        ({"timeout_s": True}, "$.timeout_s"),
        ({"max_budget_usd": 0}, "$.max_budget_usd"),
        ({"order_seed": 1.5}, "$.order_seed"),
        ({"model": ""}, "$.model"),
        ({"extra": 1}, "$.extra: 모르는 칸"),
        ({"targets": [{"id": "easy-1"}, {"id": "easy-1"}]}, "계획 안에서 겹침"),
        ({"targets": [{"id": "easy-1", "n": 0}]}, "$.targets[0].n"),
        ({"targets": []}, "$.targets"),
    ],
)
def test_F_R01_칸꼴_어긋나면_거절(over: dict[str, Any], where: str) -> None:
    with pytest.raises(rp.PlanError) as e:
        parse(plan_value(**over))
    assert where in problems(e)


def test_F_R01_필수칸_빠지면_거절() -> None:
    value = plan_value()
    del value["order_seed"]
    with pytest.raises(rp.PlanError) as e:
        parse(value)
    assert "$.order_seed: 꼭 있어야 함" in problems(e)


def test_F_R01_source는_읽지_않음() -> None:
    a = parse(plan_value(source={"command": "first", "calibration_batch": "x"}))
    b = parse(plan_value())
    assert labels(a) == labels(b)


def test_F_R01_계획sha256_기록(tmp_path: Path) -> None:
    path = tmp_path / "small.json"
    data = json.dumps(plan_value(), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(data)
    got = rp.read_plan(path, targets(*EASY))
    assert got.sha256 == hashlib.sha256(data).hexdigest()
    assert (got.name, got.timeout_s, got.max_budget_usd) == ("first24", 780, 2.52)


def test_F_R01_계획파일_같은키_두번_거절(tmp_path: Path) -> None:
    path = tmp_path / "dup.json"
    path.write_text('{"name": "first24", "name": "other"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON으로 읽을 수 없음"):
        rp.read_plan(path, targets(*EASY))


def test_F_R01_배치ID() -> None:
    started = datetime(2026, 11, 23, 1, 30, 59, tzinfo=KST)
    assert rp.batch_id(started, "first24") == "20261123-0130-first24"
    with pytest.raises(rp.PlanError):
        rp.batch_id(started, "First_24")
    with pytest.raises(ValueError, match="시간대"):
        rp.batch_id(started.replace(tzinfo=None), "first24")


def test_F_R01_실행ID_꼴과_길이() -> None:
    tid = "t" * 40
    rid = rp.run_id(tid, "A", 1, "3f2a9c10", mine=False)
    assert rid == f"{tid}-a-1-3f2a9c10"
    assert len(rid) == 40 + 3 + 1 + 1 + 8 == 53
    assert rp.run_id("blog", "B", 2, "0000beef", mine=True) == "mine-blog-b-2-0000beef"
    assert rp.run_id("empty", "A", 1, "0123abcd", mine=False) == "empty-a-1-0123abcd"


def test_F_R01_실행ID_80자넘으면_거절() -> None:
    tid = "t" * 40
    ok = rp.run_id(tid, "A", 10**22, "3f2a9c10", mine=True)  # 5 + 40 + 3 + 23 + 1 + 8 = 80
    assert len(ok) == 80
    with pytest.raises(rp.PlanError, match="80자"):
        rp.run_id(tid, "A", 10**23, "3f2a9c10", mine=True)


@pytest.mark.parametrize("token", ["3F2A9C10", "3f2a9c1", "3f2a9c10a", "../../x1"])
def test_F_R01_실행ID_8자꼴아님_거절(token: str) -> None:
    with pytest.raises(rp.PlanError):
        rp.run_id("easy-1", "A", 1, token, mine=False)


def test_F_R01_mine대상_mine접두() -> None:
    known = targets("easy-1") | targets("blog", kind="mine")
    value = plan_value(targets=[{"id": "easy-1"}, {"id": "blog"}], default_n=1)
    runs = rp.assign_run_ids(rp.expand_runs(parse(value, known)), known, [], counter_tokens())
    ids = {r.run_id.rsplit("-", 1)[0]: r for r in runs}
    assert set(ids) == {"easy-1-a-1", "easy-1-b-1", "mine-blog-a-1", "mine-blog-b-1"}
    assert ids["mine-blog-a-1"].target_kind == "mine"


def test_F_R01_8자_배치안과_지난실행과_겹치지않음() -> None:
    known = targets(*EASY)
    runs = rp.expand_runs(parse(plan_value()))
    existing = ["easy-1-a-1-00000000", "easy-2-b-2-00000002", "README.md"]
    tokens = iter(
        ["00000000", "00000001", "00000001", "00000002", *(f"{i:08x}" for i in range(3, 99))]
    )
    got = rp.assign_run_ids(runs, known, existing, lambda: next(tokens))
    hexes = [r.run_id[-8:] for r in got]
    assert len(set(hexes)) == len(hexes) == 8
    assert not {"00000000", "00000002"} & set(hexes)


def test_F_R01_8자_계속겹치면_멈춤() -> None:
    known = targets(*EASY)
    runs = rp.expand_runs(parse(plan_value()))
    with pytest.raises(rp.PlanError, match="100번"):
        rp.assign_run_ids(runs, known, [], lambda: "0000aaaa")


def test_F_R01_지난실행_이름(tmp_path: Path) -> None:
    (tmp_path / "2026-11-23" / "easy-1-a-1-3f2a9c10").mkdir(parents=True)
    (tmp_path / "2026-11-24" / "easy-2-b-1-00ff00ff").mkdir(parents=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    assert rp.existing_run_names(tmp_path) == {"easy-1-a-1-3f2a9c10", "easy-2-b-1-00ff00ff"}
    assert rp.existing_run_names(tmp_path / "없음") == set()


# --- 대상 목록 -------------------------------------------------------------------------------


def write_targets(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "selfaudit-bench/targets@1", "targets": entries}
    path.write_text(json.dumps(doc), encoding="utf-8")


def repo_entry(tid: str, kind: str = "planted") -> dict[str, Any]:
    return {
        "id": tid,
        "kind": kind,
        "bundle": f"bench/bundles/{tid}",
        "answers": f"bench/answers/{tid}.json",
    }


def test_F_R01_대상목록_두목록_합침(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_targets(repo / "bench" / "targets.json", [repo_entry("easy-1")])
    private = tmp_path / "private" / "targets.json"
    write_targets(
        private, [{"id": "blog", "kind": "mine", "bundle": r"D:\apps\blog\dist", "answers": None}]
    )
    got = rp.load_targets(repo, private)
    assert got["easy-1"].bundle == repo / "bench" / "bundles" / "easy-1"
    assert got["easy-1"].answers == repo / "bench" / "answers" / "easy-1.json"
    assert (got["blog"].kind, got["blog"].bundle, got["blog"].answers) == (
        "mine",
        Path(r"D:\apps\blog\dist"),
        None,
    )
    assert set(rp.load_targets(repo, tmp_path / "없음.json")) == {"easy-1"}


def test_F_R01_대상목록_저장소안_mine_거절(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    entry = {"id": "blog", "kind": "mine", "bundle": r"D:\apps\blog\dist", "answers": None}
    write_targets(repo / "bench" / "targets.json", [repo_entry("easy-1"), entry])
    with pytest.raises(rp.PlanError, match="이 목록에 둘 수 없는 종류"):
        rp.load_targets(repo, None)


def test_F_R01_대상목록_두목록사이_겹침_거절(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_targets(repo / "bench" / "targets.json", [repo_entry("easy-1")])
    private = tmp_path / "private.json"
    write_targets(private, [{"id": "easy-1", "kind": "mine", "bundle": r"D:\a", "answers": None}])
    with pytest.raises(rp.PlanError, match="두 목록 사이 ID 겹침"):
        rp.load_targets(repo, private)


def test_F_R01_진짜대상목록_읽힘() -> None:
    repo = Path(__file__).resolve().parents[3]
    got = rp.load_targets(repo, None)
    assert tuple(got) == SIX
    assert all(t.kind == "planted" for t in got.values())


# --- 처리량 (보안규칙 5장, 실험구조 8.1 ⑤) -------------------------------------------------


def _schedule(n: int) -> list[rp.ScheduledRun]:
    """대상 하나 × A·B × N — 실행 ID의 8자는 모두 다르다(원문이 모두 다름)."""
    known = targets("easy-1")
    plan = parse(plan_value(targets=[{"id": "easy-1"}], default_n=n), known)
    return rp.assign_run_ids(rp.expand_runs(plan), known, [], counter_tokens())


def _seconds(n: int) -> float:
    best = float("inf")
    for _ in range(3):
        gc.collect()
        gc.disable()
        start = time.perf_counter()
        try:
            assert len(_schedule(n)) == 2 * n
            best = min(best, time.perf_counter() - start)
        finally:
            gc.enable()
    return best


def _peak(n: int) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        _schedule(n)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_F_R01_처리량_N_1만_2만_선형() -> None:
    t1, t4 = _seconds(10_000), _seconds(40_000)
    m1, m2 = _peak(10_000), _peak(20_000)
    assert t4 / t1 < LINEAR_RATIO_LIMIT, (t1, t4)
    assert m2 / m1 < 3.0, (m1, m2)
