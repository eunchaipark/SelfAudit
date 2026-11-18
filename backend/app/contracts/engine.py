"""레인끼리 주고받는 엔진 타입 (설계). 바꾸려면 설계에 요청한다.

흐름 (scans 레인이 잇는다):
  intake.receive_zip / receive_folder  → IntakeResult       (F-I01, 실패는 IntakeFailed)
  rules.run_rules                      → RuleRun            (F-S01~S04)
  rules.score                          → ScoreResult        (F-S06)
  rea.analyze                          → ReaRef             (F-S05)
  compare.fingerprint / compare_scans  → 지문, Comparison  (F-C01·C02)
  export.to_json / to_markdown         → bytes              (F-E01·E02)
엔진은 DB·네트워크·현재 시각·전역 난수를 쓰지 않는다. 로컬 키는 인자로 받는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    """심각도. API·DB·내보내기에는 영어 값, 화면에는 SEVERITY_LABEL."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_LABEL = {
    Severity.HIGH: "높음",
    Severity.MEDIUM: "중간",
    Severity.LOW: "낮음",
    Severity.INFO: "정보",
}


class ScanStatus(StrEnum):
    RUNNING = "running"  # 진행 중
    DONE = "done"  # 완료
    NO_TARGET = "no_target"  # 대상 없음
    FAILED = "failed"  # 실패


class SkipReason(StrEnum):
    """건너뛴 이유. 값이 화면 문구다 (F-I01, F-S02)."""

    SYMLINK = "심볼릭 링크"
    NAME_CLASH = "이름 겹침"
    TOO_LARGE = "크기 초과"
    NOT_TARGET = "점검 안 하는 종류"
    NOT_SOURCEMAP = "소스맵 형식 아님"


class ReaStatus(StrEnum):
    USED = "used"  # 사용함
    ABSENT = "absent"  # 없음
    FAILED = "failed"  # 실패


@dataclass(frozen=True, slots=True)
class Location:
    """줄:열, 둘 다 1부터 (용어 '위치')."""

    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class Skipped:
    path: str
    reason: SkipReason


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """F-I01 출력. root는 격리 폴더, targets는 root 기준 상대 경로('/' 구분)."""

    root: Path
    total_files: int
    targets: tuple[str, ...]
    skipped: tuple[Skipped, ...]
    unpacked_bytes: int


class IntakeFailed(Exception):
    """F-I01 B의 실패. reason은 화면 문구 그대로 (점검의 실패 이유로 저장)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Finding:
    """발견 하나. value·snippet에는 가린 값만 넣는다 (NFR-03). 원문은 어디에도 담지 않는다."""

    rule_id: str
    severity: Severity
    path: str
    location: Location | None
    count: int
    value: str
    snippet: str
    evidence_key: str
    fix: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RuleRun:
    """F-S01~S04를 한 번에 돌린 결과."""

    findings: tuple[Finding, ...]
    notices: tuple[str, ...]  # 점검 안내 (F-S04 목록 없음 등)
    skipped: tuple[Skipped, ...]  # F-S02 소스맵 형식 아님
    rules_version: str  # r1+vulndb.<8자> | r1+vulndb.none


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """F-S06 출력. findings는 정렬된 순서."""

    score: int
    high: int
    medium: int
    low: int
    info: int
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class ReaRef:
    status: ReaStatus
    version: str | None = None
    modules: int | None = None
    sourcemaps: int | None = None
    message: str | None = None
