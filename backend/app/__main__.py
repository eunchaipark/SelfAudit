"""실행: `uv run python -m app` (화면 개발 서버와 함께 쓰면 `--dev`)."""

from __future__ import annotations

import argparse

import uvicorn

from app.core.config import LOOPBACK_HOST, load_settings
from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="SelfAudit 로컬 서버 (127.0.0.1 전용)")
    parser.add_argument("--dev", action="store_true", help="Vite 개발 서버(5173)의 요청을 받는다")
    args = parser.parse_args()
    settings = load_settings(dev=args.dev)
    uvicorn.run(
        create_app(settings),
        host=LOOPBACK_HOST,
        port=settings.port,
        server_header=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
