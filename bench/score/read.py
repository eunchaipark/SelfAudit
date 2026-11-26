"""F-G01 결과 읽기 (R5): 실행 폴더를 원본 계약으로 읽고 '채점할 상태'를 정한다.

- `run.json`(계약 `run`)이 없거나 어긋나면 그 실행 폴더는 '읽지 못함' — 채점에서 뺀다.
- `condition_mismatch`·`error`는 채점하지 않고 '다시 돌릴 실행'(실험 장치 문제, 설계 2.5).
- `ok`는 `findings.json`을 원본 계약 `findings`로 다시 본다(실행기가 넘긴 사본은 키워드를 뺐을 수
  있다, 설계 2.3 '형식 강제'). 없거나 어긋나면 `format_failure`.
- `timeout`·`budget_exceeded`·`format_failure`는 결과 없이 채점한다(F-G03 3).
- 정답지 지문이 `run.json`과 다르면 그 대상의 채점을 멈춘다(F-B04).

오류·문제 글에는 값을 싣지 않는다(위치와 규칙만, 보안코딩 '실험').
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from common.contracts import ContractError, ContractJsonError, Json, read_json, validate_contract

__all__ = [
    "FINDINGS_JSON",
    "NO_RESULT_STATUSES",
    "RERUN_STATUSES",
    "RUN_JSON",
    "Finding",
    "ManifestMismatchError",
    "ReadSummary",
    "RunRead",
    "RunUnreadableError",
    "ScoreError",
    "Unreadable",
    "read_run",
    "read_runs",
]

RUN_JSON: Final = "run.json"
FINDINGS_JSON: Final = "findings.json"
STATUS_OK: Final = "ok"
STATUS_FORMAT_FAILURE: Final = "format_failure"
RERUN_STATUSES: Final = frozenset({"condition_mismatch", "error"})  # F-G01 2
NO_RESULT_STATUSES: Final = frozenset({"timeout", "budget_exceeded", STATUS_FORMAT_FAILURE})
_SHOWN_ERRORS: Final = 5  # 읽지 못함 까닭에 싣는 어긋난 곳 수(나머지는 수만)


class ScoreError(RuntimeError):
    """채점을 멈춰야 하는 일(정답지가 그 대상의 것이 아님, 정답지를 받지 못함)."""


class ManifestMismatchError(ScoreError):
    """F-G01 5: `run.json`의 번들 지문이 정답지 지문과 다르다 — 그 대상의 채점을 멈춘다."""

    def __init__(self, target_id: str) -> None:
        self.target_id = target_id
        super().__init__(f"{target_id}: 실행의 번들 지문이 정답지 지문과 다름 (F-B04)")


class RunUnreadableError(ValueError):
    """F-G01 예외: `run.json`이 없거나 계약에 어긋난다. `reason`에는 위치와 규칙만 있다."""

    def __init__(self, run_dir: Path, reason: str) -> None:
        self.run_dir = run_dir
        self.reason = reason
        super().__init__(f"{run_dir.name}: 읽지 못함 — {reason}")


@dataclass(frozen=True)
class Finding:
    """결과 하나(계약 `findings`의 칸 가운데 채점에 쓰는 것). `index`는 결과 차례(0부터)."""

    index: int
    category: str
    file: str
    line: int | None
    evidence: str


@dataclass(frozen=True)
class RunRead:
    """F-G01 출력: 실행 하나의 (상태, 결과 목록 또는 없음).

    `record`는 계약을 지난 `run.json` 그대로다(F-G03이 `run_kind`·`metrics`를 읽는다).
    `problems`는 `format_failure`로 본 까닭(값 없는 위치·규칙)이다.
    """

    run_dir: Path
    record: Mapping[str, Json]
    status: str
    findings: tuple[Finding, ...] | None
    problems: tuple[ContractError, ...] = ()

    @property
    def run_id(self) -> str:
        return _text(self.record, "run_id")

    @property
    def condition(self) -> str:
        return _text(self.record, "condition")

    @property
    def target_id(self) -> str:
        return _text(self.record, "target_id")

    @property
    def scored(self) -> bool:
        """채점에 넣는가(F-G01 2·4). `condition_mismatch`·`error`는 넣지 않는다."""
        return self.status not in RERUN_STATUSES


@dataclass(frozen=True)
class Unreadable:
    run_dir: Path
    reason: str


@dataclass(frozen=True)
class ReadSummary:
    """실행 여럿을 읽은 결과.

    - `runs`: 채점할 실행(`ok`·`timeout`·`budget_exceeded`·`format_failure`), 받은 차례대로
    - `rerun`: 다시 돌릴 실행(`condition_mismatch`·`error`)
    - `unreadable`: 읽지 못한 실행 폴더
    - `stopped_targets`: 지문이 달라 채점을 멈춘 대상(그 대상의 실행은 위 셋 어디에도 없다)
    - `counts`: (조건, 대상) → 상태 → 실행 수(F-G01 6, 멈춘 대상은 빼고)
    """

    runs: tuple[RunRead, ...]
    rerun: tuple[RunRead, ...]
    unreadable: tuple[Unreadable, ...]
    stopped_targets: tuple[str, ...]
    counts: Mapping[tuple[str, str], Mapping[str, int]]


def read_run(run_dir: Path, answers: Mapping[str, Json] | None) -> RunRead:
    """F-G01 결과 읽기 (R5): 실행 폴더 하나를 읽어 채점할 상태를 정한다.

    `answers`는 그 대상의 정답지(계약을 지난 값)다. 정답지가 없는 대상(내 앱, F-B05 3)은 `None`
    — 그때는 지문을 대지 않는다. 정답지가 다른 대상의 것이면 `ScoreError`, 지문이 다르면
    `ManifestMismatchError`, `run.json`을 읽지 못하면 `RunUnreadableError`.
    """
    record = _read_record(run_dir)
    if answers is not None:
        _check_answers_for(record, answers)
    status = _text(_object(record, "outcome"), "status")
    if status != STATUS_OK:
        return RunRead(run_dir, record, status, None)
    findings, problems = _read_findings(run_dir / FINDINGS_JSON)
    if problems:
        return RunRead(run_dir, record, STATUS_FORMAT_FAILURE, None, problems)
    return RunRead(run_dir, record, STATUS_OK, findings)


def read_runs(
    run_dirs: Iterable[Path], answers_by_target: Mapping[str, Mapping[str, Json] | None]
) -> ReadSummary:
    """F-G01 결과 읽기 (R5): 실행 폴더 여럿을 읽어 채점할 것·다시 돌릴 것·상태별 수로 나눈다.

    `answers_by_target`에는 실행에 나오는 대상마다 정답지(없는 대상은 `None`)가 있어야 한다.
    빠진 대상이 있으면 `ScoreError` — 정답지를 잊고 지문 대기를 건너뛰지 않게(안전한 쪽).
    """
    read: list[RunRead] = []
    unreadable: list[Unreadable] = []
    stopped: list[str] = []
    for run_dir in run_dirs:
        try:
            record = _read_record(run_dir)
        except RunUnreadableError as e:
            unreadable.append(Unreadable(run_dir, e.reason))
            continue
        target_id = _text(record, "target_id")
        if target_id in stopped:
            continue
        if target_id not in answers_by_target:
            raise ScoreError(f"{target_id}: 정답지를 받지 못함 (정답지가 없는 대상은 None)")
        try:
            read.append(read_run(run_dir, answers_by_target[target_id]))
        except ManifestMismatchError:
            stopped.append(target_id)
    kept = [run for run in read if run.target_id not in stopped]
    return ReadSummary(
        runs=tuple(run for run in kept if run.scored),
        rerun=tuple(run for run in kept if not run.scored),
        unreadable=tuple(unreadable),
        stopped_targets=tuple(stopped),
        counts=_count(kept),
    )


# --- 읽기 (바깥과 닿는 곳) -------------------------------------------------------------------


def _read_record(run_dir: Path) -> dict[str, Json]:
    path = run_dir / RUN_JSON
    if not path.is_file():
        raise RunUnreadableError(run_dir, f"{RUN_JSON} 없음")
    try:
        value = read_json(path)
    except ContractJsonError:
        raise RunUnreadableError(run_dir, f"{RUN_JSON}을 JSON으로 읽을 수 없음") from None
    errors = validate_contract("run", value)
    if errors:
        raise RunUnreadableError(run_dir, f"{RUN_JSON} 계약에 어긋남 — {_where(errors)}")
    assert isinstance(value, dict)  # 계약 `run`의 맨 위는 객체다
    return value


def _read_findings(path: Path) -> tuple[tuple[Finding, ...], tuple[ContractError, ...]]:
    """F-G01 3·예외: 원본 계약으로 본다. 문제가 있으면 (빈 결과, 문제)."""
    if not path.is_file():
        return (), (ContractError(f"{FINDINGS_JSON}", "없음"),)
    try:
        value = read_json(path)
    except ContractJsonError:
        return (), (ContractError(f"{FINDINGS_JSON}", "JSON으로 읽을 수 없음"),)
    errors = validate_contract("findings", value)
    if errors:
        return (), tuple(errors)
    assert isinstance(value, dict)  # 계약 `findings`의 맨 위는 객체다
    items = value["findings"]
    assert isinstance(items, list)
    return tuple(_finding(i, item) for i, item in enumerate(items)), ()


# --- 순수 계산 -------------------------------------------------------------------------------


def _check_answers_for(record: Mapping[str, Json], answers: Mapping[str, Json]) -> None:
    target_id = _text(record, "target_id")
    if answers.get("bundle_id") != target_id:
        raise ScoreError(f"{target_id}: 받은 정답지가 이 대상의 것이 아님")
    if answers.get("bundle_manifest_sha256") != record.get("bundle_manifest_sha256"):
        raise ManifestMismatchError(target_id)


def _finding(index: int, item: Json) -> Finding:
    assert isinstance(item, dict)  # 계약을 지난 결과 항목
    line = item["line"]
    # 계약 검증은 JSON 뜻이라 `12.0`도 정수로 지난다(README '공통 함수') — int로 바꿔 쓴다
    return Finding(
        index=index,
        category=_text(item, "category"),
        file=_text(item, "file"),
        line=None if line is None else int(_number(line)),
        evidence=_text(item, "evidence"),
    )


def _count(runs: Iterable[RunRead]) -> dict[tuple[str, str], dict[str, int]]:
    counters: dict[tuple[str, str], Counter[str]] = {}
    for run in runs:
        counters.setdefault((run.condition, run.target_id), Counter())[run.status] += 1
    return {key: dict(sorted(counter.items())) for key, counter in sorted(counters.items())}


def _where(errors: list[ContractError]) -> str:
    shown = ", ".join(str(e) for e in errors[:_SHOWN_ERRORS])
    more = len(errors) - _SHOWN_ERRORS
    return shown + (f" … 외 {more}곳" if more > 0 else "")


def _object(value: Mapping[str, Json], key: str) -> Mapping[str, Json]:
    inner = value[key]
    assert isinstance(inner, dict)  # 계약을 지난 값
    return inner


def _text(value: Mapping[str, Json], key: str) -> str:
    text = value[key]
    assert isinstance(text, str)  # 계약을 지난 값
    return text


def _number(value: Json) -> int | float:
    assert isinstance(value, int | float) and not isinstance(value, bool)
    return value
