"""API 스키마를 backend/openapi.json으로 쓴다. 화면 타입은 이 파일에서 만든다.

`uv run python -m app.contracts.export_openapi` (확인만: `--check`, 다르면 종료 코드 1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.core.config import DataPaths, Settings
from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[2] / "openapi.json"
MODULE = "app.contracts.export_openapi"


def render() -> str:
    # 스키마만 만들므로 데이터 폴더는 쓰지 않는다 (lifespan을 돌리지 않음)
    app = create_app(Settings(data=DataPaths(Path("unused"))))
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"openapi.json이 코드와 다릅니다. 다시 만드세요: uv run python -m {MODULE}")
            return 1
        print("openapi.json 최신")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"썼습니다: {OUTPUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
