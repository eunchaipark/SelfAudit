"""DB 첫 모델 (단계 2). 비밀값 원문을 담는 칸은 두지 않는다 (NFR-03, D-014).

바꾸려면 마이그레이션으로만 (코드규칙 4.2). 레인은 요청한다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AwareDateTime, Base


class App(Base):
    """F-P01 앱."""

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    name_key: Mapped[str] = mapped_column(String(160), unique=True)  # NFC + casefold, 중복 검사용
    kind: Mapped[str] = mapped_column(String(16))  # mine | practice
    source_url: Mapped[str | None] = mapped_column(String(2000))
    consent_version: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(AwareDateTime())

    scans: Mapped[list[Scan]] = relationship(back_populates="app", cascade="all, delete-orphan")


class Scan(Base):
    """점검 한 번 (F-I01, F-S06). 상태: running | done | no_target | failed."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(AwareDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(AwareDateTime())
    input_name: Mapped[str] = mapped_column(String(260))
    rules_version: Mapped[str | None] = mapped_column(String(40))
    fail_reason: Mapped[str | None] = mapped_column(Text)  # 화면 문구 (F-I01 예외 B)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    target_files: Mapped[int] = mapped_column(Integer, default=0)
    unpacked_bytes: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int | None] = mapped_column(Integer)
    high: Mapped[int] = mapped_column(Integer, default=0)
    medium: Mapped[int] = mapped_column(Integer, default=0)
    low: Mapped[int] = mapped_column(Integer, default=0)
    info: Mapped[int] = mapped_column(Integer, default=0)
    notices: Mapped[str] = mapped_column(Text, default="[]")  # JSON 문자열 목록 (F-S04 안내 등)

    app: Mapped[App] = relationship(back_populates="scans")
    findings: Mapped[list[FindingRow]] = relationship(cascade="all, delete-orphan")
    skipped: Mapped[list[SkippedRow]] = relationship(cascade="all, delete-orphan")
    rea: Mapped[ReaRow | None] = relationship(cascade="all, delete-orphan")


class FindingRow(Base):
    """발견 하나 (F-S01~S04). value·snippet에는 가린 값만 들어간다."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)  # F-S06 정렬 순서
    rule_id: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))  # high | medium | low | info
    path: Mapped[str] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    column: Mapped[int | None] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text)
    evidence_key: Mapped[str] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(Text, index=True)
    fix: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)  # F-S04 식별자·summary


class SkippedRow(Base):
    """건너뛴 파일 (F-I01 8)."""

    __tablename__ = "skipped"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(32))


class ReaRow(Base):
    """REA 참고 (F-S05). 원본 JSON은 저장하지 않는다."""

    __tablename__ = "rea_refs"

    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16))  # used | absent | failed
    version: Mapped[str | None] = mapped_column(String(32))
    modules: Mapped[int | None] = mapped_column(Integer)
    sourcemaps: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
