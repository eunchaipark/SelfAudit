"""F-R01 실행 계획: 대상 목록·계획 파일 읽기, 섞은 차례, 배치 ID·실행 ID (실험구조 2.4·3.6·3.9).

계획 파일 꼴 (`bench/run/plans/<이름>.json`, 칸 이름은 이 모듈이 정했다 —
계획 만들기 명령 T34도 이 꼴로 쓴다)::

    {"name": "first24", "targets": [{"id": "easy-1", "n": 2}, {"id": "easy-2"}],
     "default_n": 2, "conditions": ["A", "B"], "model": "<모델 전체 ID>", "effort": "high",
     "timeout_s": 780, "max_budget_usd": 2.52, "order_seed": 20261123,
     "first_repeat": 1, "source": {...}}

`first_repeat`(없으면 1)·`source`(배치는 읽지 않는다)·대상의 `n`(없으면 `default_n`)만 빠질 수 있다.
칸 이름은 `run.json` `settings`(`timeout_s`·`max_budget_usd`·`order_seed`·`effort`)와 같게 했다.
"""

from __future__ import annotations

import hashlib
import itertools
import random
import re
import secrets
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from common.contracts import Json, read_contract, read_json

__all__ = [
    "CONDITIONS",
    "MAX_RUN_ID_CHARS",
    "Plan",
    "PlanError",
    "PlanTarget",
    "PlannedRun",
    "ScheduledRun",
    "Target",
    "assign_run_ids",
    "batch_id",
    "existing_run_names",
    "expand_runs",
    "load_targets",
    "parse_plan",
    "read_plan",
    "run_id",
]

CONDITIONS: Final = ("A", "B")  # 섞기 전 차례도 이 차례(계획 파일에 적힌 차례가 아니라)
MAX_RUN_ID_CHARS: Final = 80  # 실험구조 2.4, run.schema.json run_id
HASH_CHARS: Final = 8
MINE_PREFIX: Final = "mine-"
# 8자가 겹쳐 다시 뽑는 횟수 상한. 2³²개 가운데 지난 실행 수백 개와 겹칠 확률은 1천만분의 1쯤이라
# 100번 연달아 겹치면 난수가 고장 난 것이다(같은 값만 내는 주입 함수 등)
MAX_TOKEN_TRIES: Final = 100
_NAME: Final = re.compile(r"[a-z0-9]{4,12}")
_HEX8: Final = re.compile(r"[0-9a-f]{8}")
_RUN_ID: Final = re.compile(r"[a-z0-9][a-z0-9-]{3,79}")
_RUN_NAME_TAIL: Final = re.compile(r".+-([0-9a-f]{8})")
_REQUIRED: Final = frozenset(
    {"name", "targets", "default_n", "conditions", "model", "effort", "timeout_s"}
    | {"max_budget_usd", "order_seed"}
)
_OPTIONAL: Final = frozenset({"first_repeat", "source"})
_TARGET_KEYS: Final = frozenset({"id", "n"})
_REPO_KINDS: Final = frozenset({"planted", "practice"})
_MINE: Final = "mine"


class PlanError(ValueError):
    """계획·대상 목록을 받을 수 없다 → 배치를 시작하지 않는다. 글에는 칸 위치와 규칙만(값 없음)."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("계획을 받을 수 없음: " + "; ".join(self.problems))


@dataclass(frozen=True)
class Target:
    """대상 목록(F-B05) 한 줄. `bundle`·`answers`는 디스크 경로(저장소 대상은 저장소 기준)."""

    id: str
    kind: str
    bundle: Path
    answers: Path | None


@dataclass(frozen=True)
class PlanTarget:
    id: str
    n: int


@dataclass(frozen=True)
class Plan:
    name: str
    targets: tuple[PlanTarget, ...]
    conditions: tuple[str, ...]
    model: str
    effort: str
    timeout_s: int
    max_budget_usd: float
    order_seed: int
    first_repeat: int
    sha256: str  # 계획 파일 바이트의 sha256 (`run.json` `versions.plan_sha256`)


@dataclass(frozen=True)
class PlannedRun:
    target_id: str
    condition: str
    repeat: int


@dataclass(frozen=True)
class ScheduledRun:
    run_id: str
    target_id: str
    target_kind: str
    condition: str
    repeat: int


# --- 대상 목록 --------------------------------------------------------------------------------


def load_targets(repo_root: Path, private_list: Path | None) -> dict[str, Target]:
    """F-B05 두 목록(`bench/targets.json`, 저장소 밖 내 앱 목록)을 합친다.

    ID는 두 목록을 합쳐서 겹치지 않는다.

    계약·뜻 규칙은 `common.contracts`가 본다. 여기서는 목록마다 종류(저장소 안은 planted·practice,
    밖은 mine만)와 두 목록 사이 겹침만 더 본다. 내 앱 목록 파일이 없으면 내 앱 대상이 없는 것이다.
    """
    targets: dict[str, Target] = {}
    problems: list[str] = []
    repo_doc = read_contract("targets", repo_root / "bench" / "targets.json")
    _merge(targets, _entries(repo_doc), "bench/targets.json", _REPO_KINDS, repo_root, problems)
    if private_list is not None and private_list.is_file():
        private_doc = read_contract("targets", private_list)
        _merge(targets, _entries(private_doc), "내 앱 목록", {_MINE}, repo_root, problems)
    if problems:
        raise PlanError(problems)
    return targets


def _entries(doc: Mapping[str, Json]) -> list[dict[str, Json]]:
    value = doc.get("targets")
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def _merge(
    targets: dict[str, Target],
    entries: Iterable[Mapping[str, Json]],
    where: str,
    kinds: Iterable[str],
    repo_root: Path,
    problems: list[str],
) -> None:
    allowed = frozenset(kinds)
    for i, entry in enumerate(entries):
        tid, kind, bundle, answers = (entry.get(k) for k in ("id", "kind", "bundle", "answers"))
        # 계약을 지난 값이라 꼴은 맞다. 타입만 좁힌다
        if not (isinstance(tid, str) and isinstance(kind, str) and isinstance(bundle, str)):
            problems.append(f"{where} $.targets[{i}]: 칸 타입")
            continue
        if kind not in allowed:
            problems.append(f"{where} $.targets[{i}].kind: 이 목록에 둘 수 없는 종류")
            continue
        if tid in targets:
            problems.append(f"{where} $.targets[{i}].id: 두 목록 사이 ID 겹침")
            continue
        base = repo_root if kind in _REPO_KINDS else None
        targets[tid] = Target(
            id=tid,
            kind=kind,
            bundle=_target_path(bundle, base),
            answers=_target_path(answers, base) if isinstance(answers, str) else None,
        )


def _target_path(text: str, base: Path | None) -> Path:
    return base.joinpath(*text.split("/")) if base is not None else Path(text)


# --- 계획 파일 --------------------------------------------------------------------------------


def read_plan(path: Path, targets: Mapping[str, Target]) -> Plan:
    """F-R01 계획 파일을 엄격한 JSON으로 읽어 검사한다. 어긋나면 `PlanError`(시작하지 않음)."""
    before = _file_sha256(path)
    value = read_json(path)
    # 검사한 바이트와 sha256을 적는 바이트가 같아야 `plan_sha256`이 그 계획을 가리킨다
    if _file_sha256(path) != before:
        raise PlanError(["$: 읽는 동안 계획 파일이 바뀜"])
    return parse_plan(value, targets, before)


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise PlanError([f"$: 계획 파일을 읽을 수 없음 ({type(e).__name__})"]) from None


def parse_plan(value: Json, targets: Mapping[str, Target], sha256: str) -> Plan:
    """F-R01 입력·예외: 칸 꼴, `name` 꼴, 대상이 목록에 있음, 조건 A·B,
    대상마다 1 ≤ first_repeat ≤ N."""
    if not isinstance(value, dict):
        raise PlanError(["$: 객체가 아님"])
    problems: list[str] = []
    keys = set(value)
    problems += [f"$.{k}: 꼭 있어야 함" for k in sorted(_REQUIRED - keys)]
    problems += [f"$.{k}: 모르는 칸" for k in sorted(keys - _REQUIRED - _OPTIONAL)]
    name = value.get("name")
    if not (isinstance(name, str) and _NAME.fullmatch(name)):
        problems.append("$.name: 소문자·숫자 4~12자")
    default_n = _positive_int(value.get("default_n"), "$.default_n", problems)
    first_repeat = _positive_int(value.get("first_repeat", 1), "$.first_repeat", problems)
    plan_targets = _plan_targets(value.get("targets"), default_n, first_repeat, targets, problems)
    conditions = _conditions(value.get("conditions"), problems)
    model = _text(value.get("model"), "$.model", problems)
    effort = _text(value.get("effort"), "$.effort", problems)
    timeout_s = _positive_int(value.get("timeout_s"), "$.timeout_s", problems)
    budget = _positive_number(value.get("max_budget_usd"), "$.max_budget_usd", problems)
    seed = value.get("order_seed")
    if not _is_int(seed):
        problems.append("$.order_seed: 정수")
    if problems:
        raise PlanError(problems)
    assert isinstance(name, str) and isinstance(seed, int)
    return Plan(
        name=name,
        targets=plan_targets,
        conditions=conditions,
        model=model,
        effort=effort,
        timeout_s=timeout_s,
        max_budget_usd=budget,
        order_seed=seed,
        first_repeat=first_repeat,
        sha256=sha256,
    )


def _plan_targets(
    value: Json,
    default_n: int,
    first_repeat: int,
    known: Mapping[str, Target],
    problems: list[str],
) -> tuple[PlanTarget, ...]:
    if not (isinstance(value, list) and value):
        problems.append("$.targets: 대상이 하나 이상인 목록")
        return ()
    out: list[PlanTarget] = []
    seen: set[str] = set()
    for i, entry in enumerate(value):
        where = f"$.targets[{i}]"
        if not isinstance(entry, dict) or set(entry) - _TARGET_KEYS or "id" not in entry:
            problems.append(f"{where}: {{id, n}} 꼴")
            continue
        tid = entry["id"]
        if not isinstance(tid, str) or tid not in known:
            problems.append(f"{where}.id: 대상 목록(F-B05)에 없음")
            continue
        if tid in seen:
            problems.append(f"{where}.id: 계획 안에서 겹침")
            continue
        seen.add(tid)
        n = _positive_int(entry.get("n", default_n), f"{where}.n", problems)
        if not 1 <= first_repeat <= n:
            problems.append(f"{where}: 1 ≤ first_repeat ≤ N 아님")
        out.append(PlanTarget(id=tid, n=n))
    return tuple(out)


def _conditions(value: Json, problems: list[str]) -> tuple[str, ...]:
    if not (isinstance(value, list) and value):
        problems.append("$.conditions: 조건이 하나 이상인 목록")
        return ()
    if any(c not in CONDITIONS for c in value):
        problems.append("$.conditions: A·B 밖의 조건")
        return ()
    if len(set(map(str, value))) != len(value):
        problems.append("$.conditions: 겹침")
        return ()
    return tuple(c for c in CONDITIONS if c in value)


def _is_int(value: Json) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Json, where: str, problems: list[str]) -> int:
    if _is_int(value) and isinstance(value, int) and value >= 1:
        return value
    problems.append(f"{where}: 1 이상 정수")
    return 1


def _positive_number(value: Json, where: str, problems: list[str]) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
        return float(value)
    problems.append(f"{where}: 0보다 큰 수")
    return 1.0


def _text(value: Json, where: str, problems: list[str]) -> str:
    if isinstance(value, str) and value.strip():
        return value
    problems.append(f"{where}: 빈 글이 아닌 글")
    return ""


# --- 차례·ID ---------------------------------------------------------------------------------


def expand_runs(plan: Plan) -> list[PlannedRun]:
    """F-R01 1: 대상(계획 차례) × 조건(A, B) × 반복 차례(first_repeat~N)를 시드로 섞는다."""
    runs = [
        PlannedRun(target_id=t.id, condition=c, repeat=r)
        for t in plan.targets
        for c, r in itertools.product(plan.conditions, range(plan.first_repeat, t.n + 1))
    ]
    # 암호 용도가 아니다: 같은 시드면 같은 차례가 나와야 하는 섞기(F-R01 1 근거)
    random.Random(plan.order_seed).shuffle(runs)  # noqa: S311
    return runs


def batch_id(started_at: datetime, name: str) -> str:
    """F-R01 2: 배치를 시작한 로컬 시각 `YYYYMMDD-HHMM` + `-` + `name`.

    `started_at`은 부르는 쪽이 로컬 시간대로 준 시각이다(그 벽시계 값을 그대로 쓴다).
    """
    if started_at.tzinfo is None:
        raise ValueError("시작 시각에 시간대가 없음")
    if not _NAME.fullmatch(name):
        raise PlanError(["name: 소문자·숫자 4~12자"])
    return f"{started_at:%Y%m%d-%H%M}-{name}"


def run_id(target_id: str, condition: str, repeat: int, token: str, *, mine: bool) -> str:
    """F-R01 3: `[mine-]<대상 ID>-<a·b>-<반복 차례>-<16진 8자>`, 80자까지(빈·문지기는 대상 ID 자리에
    예약 ID `empty`·`gate`)."""
    if condition not in CONDITIONS:
        raise PlanError(["condition: A·B 밖"])
    if not _HEX8.fullmatch(token):
        raise PlanError(["token: 16진 소문자 8자"])
    if repeat < 1:
        raise PlanError(["repeat: 1 이상"])
    prefix = MINE_PREFIX if mine else ""
    rid = f"{prefix}{target_id}-{condition.lower()}-{repeat}-{token}"
    if len(rid) > MAX_RUN_ID_CHARS or not _RUN_ID.fullmatch(rid):
        raise PlanError([f"run_id: {MAX_RUN_ID_CHARS}자 넘음 또는 꼴 아님"])
    return rid


def existing_run_names(results_root: Path) -> set[str]:
    """`bench/results/<날짜>/<실행 ID>/` 아래 지난 실행 폴더 이름들(8자 겹침을 피하려고)."""
    if not results_root.is_dir():
        return set()
    return {run.name for day in results_root.iterdir() if day.is_dir() for run in day.iterdir()}


def assign_run_ids(
    runs: Sequence[PlannedRun],
    targets: Mapping[str, Target],
    existing_names: Iterable[str],
    token: Callable[[], str] = lambda: secrets.token_hex(HASH_CHARS // 2),
) -> list[ScheduledRun]:
    """F-R01 3: 차례마다 실행 ID를 붙인다.

    8자는 이 배치 안과 지난 실행 폴더 이름의 8자와 겹치지 않는다.
    """
    used = {m.group(1) for name in existing_names if (m := _RUN_NAME_TAIL.fullmatch(name))}
    out: list[ScheduledRun] = []
    for run in runs:
        target = targets[run.target_id]
        hex8 = _fresh_token(token, used)
        used.add(hex8)
        rid = run_id(run.target_id, run.condition, run.repeat, hex8, mine=target.kind == _MINE)
        out.append(ScheduledRun(rid, run.target_id, target.kind, run.condition, run.repeat))
    return out


def _fresh_token(token: Callable[[], str], used: set[str]) -> str:
    for _ in range(MAX_TOKEN_TRIES):
        value = token()
        if value not in used:
            return value
    raise PlanError([f"run_id: 겹치지 않는 8자를 {MAX_TOKEN_TRIES}번 안에 못 뽑음"])
