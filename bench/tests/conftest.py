"""실험 도구 시험 공통 (설계). 레인 시험은 여기 픽스처를 쓰고, 고칠 것은 설계에 요청한다.

- 대상 번들은 시험 안에서 `make_bundle`로 만든다. 가짜 값만(실험구조 2.2 '가짜 값의 꼴').
- 바깥 접속은 pyproject의 `--allow-hosts`가 막는다(test_socket.py, 한계는 README).
- 실제 `claude.exe`·REA를 부르지 않는다. 실행기 시험은 가짜 실행 파일로(실험구조 3.9).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import pytest

from common.paths import resolve_in_bundle


class MakeBundle(Protocol):
    def __call__(self, files: Mapping[str, bytes], name: str = "bundle") -> Path: ...


@pytest.fixture
def make_bundle(tmp_path: Path) -> MakeBundle:
    """`{번들 안 경로: 내용}`으로 tmp_path 아래에 번들 폴더를 만든다. 경로는 2.2 허용 꼴만."""

    def make(files: Mapping[str, bytes], name: str = "bundle") -> Path:
        root = tmp_path / name
        root.mkdir()
        for rel, data in files.items():
            path = resolve_in_bundle(root, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return root

    return make
