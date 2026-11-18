"""시작할 때 마이그레이션을 끝까지 적용한다."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def alembic_config(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", MIGRATIONS.as_posix())
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def upgrade(db_url: str) -> None:
    command.upgrade(alembic_config(db_url), "head")
