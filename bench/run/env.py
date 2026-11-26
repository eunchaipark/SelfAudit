"""F-R02 5 Claude Code를 띄울 환경: 허용 목록만 (실험구조 3.2 '허용 목록 환경').

사용자 환경의 토큰·키 변수가 대상 에이전트나 REA에 가지 않게, 이름을 적은 변수만 넘긴다.
REA는 거르개(`rea_mcp_filter.py`)가 이보다 더 좁은 환경으로 띄운다.
"""

from __future__ import annotations

import ntpath
from collections.abc import Mapping
from pathlib import Path
from typing import Final

__all__ = ["ENV_PASS", "EnvError", "claude_env"]

# 이름의 대소문자는 넘길 때 이 꼴로 맞춘다(Windows 환경 이름은 대소문자를 가리지 않는다)
ENV_PASS: Final = (
    "SystemRoot",
    "SystemDrive",
    "windir",
    "ComSpec",
    "PATHEXT",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "TEMP",
    "TMP",
)
_SYSTEM32: Final = "System32"


class EnvError(ValueError):
    """허용 목록 환경을 만들 수 없다(값은 싣지 않는다)."""


def claude_env(source: Mapping[str, str], config_dir: Path) -> dict[str, str]:
    """F-R02 5: 허용 목록 변수 + `PATH`(System32만) + `CLAUDE_CONFIG_DIR` +
    `DISABLE_AUTOUPDATER=1`."""
    by_upper = {k.upper(): v for k, v in source.items()}
    env = {name: by_upper[name.upper()] for name in ENV_PASS if name.upper() in by_upper}
    system_root = env.get("SystemRoot", "")
    if not ntpath.isabs(system_root):
        raise EnvError("SystemRoot가 없거나 절대 경로가 아님")
    if not config_dir.is_absolute():
        raise EnvError("설정 폴더가 절대 경로가 아님")
    env["PATH"] = ntpath.join(system_root, _SYSTEM32)
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    env["DISABLE_AUTOUPDATER"] = "1"
    return env
