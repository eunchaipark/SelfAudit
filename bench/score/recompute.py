"""F-G05 다시 계산 검사 (R1·R5): 원자료에서 F-G01~G04를 다시 돌리고 보고서 표와 글자까지 댄다.

- `score_results`: 원자료 폴더 → 읽기(F-G01) → 짝짓기·지표(F-G02·G03) → 모으기. 실행 폴더는 이름
  차례로 읽지만 모으기는 받는 차례와 상관없이 같은 값을 낸다(5).
- `check_report`: 보고서의 `<!-- 표:<이름> -->` … `<!-- /표 -->` 사이 글(앞뒤 줄바꿈 하나씩 뺌)과
  새로 만든 표 글이 글자까지 같은지(2). 다르면 표 이름과 보고서의 첫 다른 줄 번호(3), 만들 수 없는
  이름이면 실패(4). 표식이 하나도 없으면 통과하되 검사한 표 0개(예외).

알림에는 표 이름·줄 번호·까닭만 싣는다(보고서·원자료의 글을 옮기지 않는다).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from common.contracts import (
    REPO_ROOT,
    ContractJsonError,
    ContractViolationError,
    Json,
    read_contract,
)
from score.aggregate import Report, build_report
from score.match import DEFAULT_RULES, Rules
from score.metrics import RunScore, score_run
from score.read import ReadSummary, ScoreError, read_runs

__all__ = [
    "Failure",
    "ReportCheck",
    "Scored",
    "check_report",
    "check_report_file",
    "load_answers",
    "run_dirs",
    "score_results",
]

_START: Final = re.compile(r"<!-- 표:(?P<name>[^<>]{1,60}) -->")
_END: Final = "<!-- /표 -->"
_MARK_HINT: Final = re.compile(r"<!--\s*/?\s*표")  # 표식처럼 보이는 줄(꼴이 틀린 것을 잡는다)
_CR: Final = "\r"  # Windows 줄바꿈의 앞 글자
_CRLF: Final = "줄 끝이 CRLF — LF로 저장(.gitattributes eol=lf)"
_REPORT_LIMIT_BYTES: Final = 4 * 1024 * 1024  # 보고서 글 상한 — 큰 파일을 통째로 들이지 않게


@dataclass(frozen=True)
class Scored:
    """원자료 한 벌을 채점한 것: 읽기 요약(F-G01), 실행별 지표, 모은 숫자(F-G03)."""

    summary: ReadSummary
    scores: tuple[RunScore, ...]
    report: Report


@dataclass(frozen=True)
class Failure:
    name: str
    line: int  # 보고서의 줄 번호(1부터)
    why: str

    def __str__(self) -> str:
        return f"표 {self.name}: {self.line}줄 — {self.why}"


@dataclass(frozen=True)
class ReportCheck:
    checked: tuple[str, ...]  # 글자까지 같았던 표 이름(나온 차례, 같은 이름이 둘이면 둘)
    failures: tuple[Failure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


# --- 다시 돌리기 (바깥과 닿는 곳) --------------------------------------------------------------


def run_dirs(results: Iterable[Path]) -> list[Path]:
    """원자료 폴더(`bench/results/<날짜>`)마다 실행 폴더를 이름 차례로. 없으면 `ScoreError`."""
    out: list[Path] = []
    for root in results:
        if not root.is_dir():
            raise ScoreError(f"원자료 폴더가 없음: {root.name}")
        out.extend(sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name))
    if not out:
        raise ScoreError("원자료 없음 (실행 폴더가 하나도 없음)")
    return out


def load_answers(
    targets_files: Iterable[Path], repo_root: Path = REPO_ROOT
) -> dict[str, dict[str, Json] | None]:
    """대상 목록(계약 `targets`) → 대상 ID → 정답지(계약 `answers`, 없는 대상은 `None`).

    저장소 대상의 정답지 경로는 뜻 규칙이 `bench/answers/<id>.json`으로 묶어 둔다(저장소 맨 위
    기준).
    같은 ID가 두 목록에 있으면 `ScoreError`(어느 정답지로 채점했는지 모호해지지 않게).
    """
    out: dict[str, dict[str, Json] | None] = {}
    for path in targets_files:
        try:
            targets = read_contract("targets", path)
        except (ContractJsonError, ContractViolationError) as e:
            raise ScoreError(f"대상 목록을 읽지 못함: {e}") from None
        entries = targets["targets"]
        assert isinstance(entries, list)  # 계약을 지난 값
        for entry in entries:
            assert isinstance(entry, dict)
            target_id, answers = entry["id"], entry["answers"]
            assert isinstance(target_id, str) and (answers is None or isinstance(answers, str))
            if target_id in out:
                raise ScoreError(f"{target_id}: 대상 목록 둘에 같은 ID")
            out[target_id] = None if answers is None else _read_answers(repo_root, answers)
    return out


def score_results(
    results: Iterable[Path],
    answers_by_target: Mapping[str, Mapping[str, Json] | None],
    rules: Rules = DEFAULT_RULES,
) -> Scored:
    """F-G05 1: 원자료에서 F-G01~G03을 다시 돌린다(모델을 부르지 않는다, 설계 3.9)."""
    summary = read_runs(run_dirs(results), answers_by_target)
    scores = tuple(score_run(r, answers_by_target[r.target_id], rules) for r in summary.runs)
    return Scored(summary=summary, scores=scores, report=build_report(scores, summary.rerun))


def check_report_file(path: Path, tables: Mapping[str, str]) -> ReportCheck:
    """보고서 파일을 UTF-8로 읽어 `check_report`. 없거나 너무 크면 `ScoreError`."""
    try:
        with path.open("rb") as f:
            data = f.read(_REPORT_LIMIT_BYTES + 1)
    except OSError as e:
        raise ScoreError(f"보고서를 읽지 못함: {path.name} ({type(e).__name__})") from None
    if len(data) > _REPORT_LIMIT_BYTES:
        raise ScoreError(f"보고서가 너무 큼: {path.name}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ScoreError(f"보고서가 UTF-8이 아님: {path.name}") from None
    return check_report(text, tables)


# --- 대 보기 (순수 계산) ---------------------------------------------------------------------


def check_report(text: str, tables: Mapping[str, str]) -> ReportCheck:
    """F-G05 다시 계산 검사 (R1·R5): 보고서 글의 표 사이 글을 새로 만든 표 글과 글자까지 댄다."""
    lines = text.split("\n")
    checked: list[str] = []
    failures: list[Failure] = []
    open_at: tuple[str, int] | None = None  # (이름, 여는 표식 줄 차례 0부터)
    for i, line in enumerate(lines):
        start = _START.fullmatch(line)
        if start is not None:
            if open_at is not None:
                failures.append(Failure(open_at[0], i + 1, "끝 표식 전에 새 표식"))
            open_at = (start.group("name"), i)
            continue
        if line == _END:
            if open_at is None:
                failures.append(Failure("-", i + 1, "여는 표식 없는 끝 표식"))
                continue
            name, begin = open_at
            open_at = None
            failure = _compare(name, lines[begin + 1 : i], begin + 2, i + 1, tables)
            if failure is None:
                checked.append(name)
            else:
                failures.append(failure)
            continue
        if _MARK_HINT.search(line):
            failures.append(Failure("-", i + 1, _why_crooked(line)))
    if open_at is not None:
        failures.append(Failure(open_at[0], open_at[1] + 1, "끝 표식 없음"))
    return ReportCheck(checked=tuple(checked), failures=tuple(failures))


def _compare(
    name: str, got: Sequence[str], first_line: int, end_line: int, tables: Mapping[str, str]
) -> Failure | None:
    """같으면 `None`. 다르면 보고서에서 첫 다른 줄 번호(보고서 쪽 줄이 모자라면 끝 표식 줄)."""
    if name not in tables:
        return Failure(name, first_line - 1, "만들 수 없는 표 이름")
    want = tables[name].split("\n")
    for k, (a, b) in enumerate(zip(got, want, strict=False)):
        if a != b:
            why = _CRLF if a == b + _CR else "새로 만든 표와 글자가 다름"
            return Failure(name, first_line + k, why)
    if len(got) != len(want):
        line = first_line + len(want) if len(got) > len(want) else end_line
        return Failure(name, line, "새로 만든 표와 줄 수가 다름")
    return None


def _why_crooked(line: str) -> str:
    return _CRLF if line.endswith(_CR) else "표식 꼴이 다름(한 줄에 표식 하나만, 띄어쓰기까지)"


def _read_answers(repo_root: Path, relpath: str) -> dict[str, Json]:
    path = (repo_root / relpath).resolve()
    if not path.is_relative_to(repo_root.resolve()):
        raise ScoreError("정답지 경로가 저장소 밖")  # 뜻 규칙이 막지만 열기 전에 한 번 더
    try:
        return read_contract("answers", path)
    except (ContractJsonError, ContractViolationError) as e:
        raise ScoreError(f"정답지를 읽지 못함: {e}") from None
