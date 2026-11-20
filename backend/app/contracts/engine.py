"""레인끼리 주고받는 엔진 타입 (설계). 바꾸려면 설계에 요청한다.

흐름 (scans 레인이 잇는다):
  intake.receive_zip / receive_folder  → IntakeResult       (F-I01, 실패는 IntakeFailed)
  rules.run_rules                      → RuleRun            (F-S01~S04, 모양은 RunRules)
  rules.score                          → ScoreResult        (F-S06, 모양은 Score)
  rea.analyze                          → ReaRef             (F-S05)
  compare.fingerprint / compare_scans  → 지문, Comparison  (F-C01·C02)
  export.to_json / to_markdown         → bytes              (F-E01·E02)
엔진은 DB·네트워크·현재 시각·전역 난수를 쓰지 않는다. 로컬 키는 인자로 받는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


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
    """건너뛴 이유. 값이 화면 문구다 (F-I01, F-S02, F-S01 11·F-S03 9)."""

    SYMLINK = "심볼릭 링크"
    NAME_CLASH = "이름 겹침"
    TOO_LARGE = "크기 초과"
    NOT_TARGET = "점검 안 하는 종류"
    NOT_SOURCEMAP = "소스맵 형식 아님"
    TOO_MANY_HITS = "걸림이 너무 많아 일부만 점검"  # CR-003


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
    notices: tuple[str, ...]  # 점검 안내 (F-S02 건너뛴 소스맵, F-S04 목록, 발견 상한)
    skipped: tuple[Skipped, ...]  # 소스맵 형식 아님, 걸림이 너무 많아 일부만 점검
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


class RunRules(Protocol):
    """`rules.run_rules`의 모양 (F-S01~S04). 규칙 레인이 만들고 점검 흐름이 부른다.

    입력:
      intake       F-I01 결과 그대로. 대상 0개면 부르지 않는다
                   (점검 흐름이 `대상 없음`으로 끝낸다).
      key          로컬 키. 증거키(HMAC)에만 쓴다. 테스트는 `b"selfaudit-test-key"`.
      vulndb_file  `DataPaths.vulndb_file`. 없을 수 있다(F-S04 예외).

    읽기:
      - `intake.targets` 차례로 `intake.root / 경로`를 한 파일씩 읽는다.
        폴더를 훑지 않고 목록만 쓴다.
      - 글은 `read_bytes().decode("utf-8", errors="replace")`(F-I01 9). BOM은 규칙 함수가 뗀다.
      - 한 번에 한 파일의 글만 들고 있는다. 모든 파일의 글을 모아 두지 않는다(합 200MB).
      - 파일마다 F-S01 → F-S02 → F-S03 → F-S04를 확장자에 맞는 것만 돌린다.
        `.map`이 JSON이 아니면 skipped에 `NOT_SOURCEMAP`을 넣고 F-S01·S03도 보지 않는다.
      - F-S02의 '번들에 있음'은 `intake.targets`와 `intake.skipped`의 경로다
        (디스크를 다시 보지 않는다, CR-004).
      - 걸림 상한(F-S01 11·F-S03 9, `core.limits.HIT_LIMIT`): 파일 하나에서 S01·S03 걸림을
        따로 세어 10,000개까지 받는다. 10,001번째 걸림이 나오면 그것은 받지 않고 그 규칙 묶음만
        멈춘다. 꼭 10,000개면 다 본 것이라 멈추지 않고 건너뜀도 없다 (CR-005).
        발견 상한(1절, `core.limits.FINDINGS_LIMIT`): 파일을 하나 마칠 때마다 발견 수를 세어
        50,000개를 넘었으면 남은 파일은 F-S01~S04를 보지 않는다 (CR-003).
      - 취약 목록은 점검마다 한 번 읽는다(캐시 없음). 쓰는 파일은 없다.

    출력 (같은 입력이면 같은 결과, NFR-04):
      findings       targets 차례, 한 파일 안에서는 규칙 차례. 정렬은 `score`가 한다.
      notices        이 차례로: F-S02 6 건너뛴 소스맵 안내(`intake.skipped`로 정하므로 발견 상한과
                     상관없이) → F-S04 안내(목록 없음·형식 오류·버린 항목 n개) → 발견 상한 안내
                     (1절 '발견 상한', 한 줄). 문구는 명세 그대로.
      skipped        targets 차례, 파일 하나에 한 줄. `소스맵 형식 아님`(F-S02 예외) 또는
                     `걸림이 너무 많아 일부만 점검`(S01·S03 중 하나라도 멈추면, 둘 다여도 한 줄).
                     F-I01의 건너뜀은 넣지 않는다. 발견 상한으로 보지 않은 파일도 넣지 않는다.
      rules_version  S04를 돌렸으면(일부 항목 버림 포함) `r1+vulndb.<파일 바이트 SHA-256 소문자
                     16진 앞 8자>`, 목록 없음·읽기 실패·형식 오류·쓸 항목 0개면 `r1+vulndb.none`
                     (CR-004).

    오류:
      - 대상 파일을 읽다 난 `OSError`는 삼키지 않고 올린다. 점검 흐름이 `실패`
        "점검 중 오류가 나서 멈췄습니다"로 바꾼다.
      - 취약 목록의 없음·읽기 실패·형식 오류는 F-S04 예외대로 안내만 남기고 다른 규칙은 계속한다.
    """

    def __call__(self, intake: IntakeResult, *, key: bytes, vulndb_file: Path) -> RuleRun: ...


class Score(Protocol):
    """`rules.score`의 모양 (F-S06 1~3). 점수·심각도별 개수·정렬된 발견을 낸다.

    `완료`인 점검에만 부른다. `대상 없음`·`실패`의 점수 `-`는 점검 흐름이 정한다
    (score를 부르지 않고 점수를 None으로 저장한다).
    """

    def __call__(self, findings: Sequence[Finding]) -> ScoreResult: ...
