"""Alembic 실행 환경. 설정은 app.db.migrate가 넘긴다."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import models  # noqa: F401  모델을 메타데이터에 올린다
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def run() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


run()
