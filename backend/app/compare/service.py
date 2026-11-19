"""비교 흐름: 두 점검 읽기 → 확인 → 엔진. 읽기만 하고 쓰지 않는다."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.compare import engine, repo
from app.contracts.engine import Finding, Location, ScanStatus, Severity
from app.core.errors import NotFound, ValidationFailed
from app.db.models import FindingRow, Scan

MSG_SAME_SCAN = "서로 다른 점검 두 개를 고르세요"
MSG_OTHER_APP = "같은 앱의 점검끼리만 비교할 수 있습니다"
MSG_NOT_DONE = "완료된 점검만 비교할 수 있습니다"
SAME_SCAN_CODE = "SAME_SCAN"
OTHER_APP_CODE = "OTHER_APP"
NOT_DONE_CODE = "SCAN_NOT_DONE"


def _load(session: Session, scan_id: int) -> Scan:
    scan = repo.get_scan(session, scan_id)
    if scan is None:
        raise NotFound
    return scan


def _to_finding(row: FindingRow) -> Finding:
    location = None if row.line is None or row.column is None else Location(row.line, row.column)
    return Finding(
        rule_id=row.rule_id,
        severity=Severity(row.severity),
        path=row.path,
        location=location,
        count=row.count,
        value=row.value,
        snippet=row.snippet,
        evidence_key=row.evidence_key,
        fix=row.fix,
        detail=row.detail,
    )


def _to_side(session: Session, scan: Scan) -> engine.ScanSide:
    if scan.score is None:
        # 완료인데 점수가 없으면 저장이 잘못된 것이다. 0으로 메우지 않고 멈춘다
        raise ValueError("완료된 점검에 점수가 없다")
    rows = repo.list_findings(session, scan.id)
    return engine.ScanSide(
        scan_id=scan.id,
        started_at=scan.started_at,
        score=scan.score,
        rules_version=scan.rules_version,
        findings=tuple(_to_finding(row) for row in rows),
    )


def compare(session: Session, a: int, b: int) -> engine.Comparison:
    """F-C02 두 점검 비교 (FR-10). 예외 문구의 차례는 명세 예외 칸의 차례를 따른다."""
    if a == b:
        raise ValidationFailed(MSG_SAME_SCAN, code=SAME_SCAN_CODE)
    first, second = _load(session, a), _load(session, b)
    if first.app_id != second.app_id:
        raise ValidationFailed(MSG_OTHER_APP, code=OTHER_APP_CODE)
    if any(scan.status != ScanStatus.DONE for scan in (first, second)):
        raise ValidationFailed(MSG_NOT_DONE, code=NOT_DONE_CODE)
    return engine.compare_scans(_to_side(session, first), _to_side(session, second))
