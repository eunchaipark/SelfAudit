"""서버 설정. 환경 변수에서 읽고, 없으면 기본값을 쓴다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
VITE_DEV_ORIGIN = "http://127.0.0.1:5173"
REPO_ROOT = Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    r"""데이터 폴더 기본 위치: %LOCALAPPDATA%\SelfAudit (저장소 밖)."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "SelfAudit"
    return Path.home() / ".selfaudit"


@dataclass(frozen=True, slots=True)
class DataPaths:
    """데이터 폴더 안의 위치. 서버는 이 폴더 밖에 쓰지 않는다 (용어 '데이터 폴더')."""

    root: Path

    @property
    def db_file(self) -> Path:
        return self.root / "selfaudit.db"

    @property
    def key_file(self) -> Path:
        return self.root / "local.key"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def vulndb_file(self) -> Path:
        return self.root / "vulndb" / "jsrepository.json"

    def ensure(self) -> None:
        for folder in (self.root, self.work, self.uploads, self.vulndb_file.parent):
            folder.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class Settings:
    data: DataPaths
    port: int = DEFAULT_PORT
    dev_origins: tuple[str, ...] = ()
    static_dir: Path | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data.db_file.as_posix()}"

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset({f"{LOOPBACK_HOST}:{self.port}", f"localhost:{self.port}"})

    @property
    def allowed_origins(self) -> frozenset[str]:
        own = {f"http://{LOOPBACK_HOST}:{self.port}", f"http://localhost:{self.port}"}
        return frozenset(own | set(self.dev_origins))


def load_settings(*, dev: bool = False) -> Settings:
    data_dir = Path(os.environ.get("SELFAUDIT_DATA_DIR") or default_data_dir()).resolve()
    port = int(os.environ.get("SELFAUDIT_PORT", str(DEFAULT_PORT)))
    static = REPO_ROOT / "frontend" / "dist"
    return Settings(
        data=DataPaths(data_dir),
        port=port,
        dev_origins=(VITE_DEV_ORIGIN,) if dev else (),
        static_dir=static if static.is_dir() else None,
    )
