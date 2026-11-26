"""F-R05 조건 확인 (R4) 시험. 기능명세 F-R05 예시를 옮겼다(init 줄 칸 이름은 추정, 값은 가상)."""

from __future__ import annotations

import gc
import json
import time
import tracemalloc
from collections.abc import Callable
from typing import Any

import pytest

from run import condition as rc

MODEL = "claude-test-4-0-20261101"
BASE = ["Read", "Grep", "Glob"]
REA = [
    "mcp__rea__analyze_javascript_application",
    "mcp__rea__audit_release_exposure",
    "mcp__rea__trace_javascript_semantics",
    "mcp__rea__trace_application_feature",
]
# 선형 4N/N 약 4, 제곱 약 16의 가운데(부하 흔들림을 두 배까지 받아 줌, 코드규칙 6장)
LINEAR_RATIO_LIMIT = 8.0


def init(**fields: Any) -> dict[str, Any]:
    line: dict[str, Any] = {
        "type": "system",
        "subtype": "init",
        "tools": list(BASE),
        "mcp_servers": [],
        "model": MODEL,
        "permissionMode": "dontAsk",
    }
    line.update(fields)
    return line


def init_b(**fields: Any) -> dict[str, Any]:
    base = {"tools": BASE + REA, "mcp_servers": [{"name": "rea", "status": "connected"}]}
    return init(**{**base, **fields})


def stream(*lines: dict[str, Any] | str) -> bytes:
    return b"".join(
        (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)).encode() + b"\n"
        for x in lines
    )


def check(condition: str, *lines: dict[str, Any] | str) -> rc.InitCheck:
    return rc.check_init(stream(*lines), condition, MODEL)


def test_F_R05_모두맞으면_ok() -> None:
    assert check("A", init()) == rc.InitCheck("passed", "")
    assert check("B", init_b()) == rc.InitCheck("passed", "")


def test_F_R05_A에_도구더있으면_mismatch() -> None:
    assert check("A", init(tools=[*BASE, "Bash"])) == rc.InitCheck("failed", "tools")


def test_F_R05_A에_REA도구있으면_mismatch() -> None:
    assert check("A", init(tools=BASE + REA)).detail == "tools"


def test_F_R05_도구빠져도_mismatch() -> None:
    assert check("A", init(tools=["Read", "Grep"])).detail == "tools"
    assert check("B", init_b(tools=BASE + REA[:3])).detail == "tools"


def test_F_R05_같은도구두번도_mismatch() -> None:
    assert check("A", init(tools=[*BASE, "Read"])).detail == "tools"


def test_F_R05_B_extract_artifact_있으면_mismatch() -> None:
    """거르개가 새는 것(허용 밖 REA 도구가 보임)."""
    tools = [*BASE, *REA, "mcp__rea__extract_artifact"]
    assert check("B", init_b(tools=tools)).detail == "tools"


def test_F_R05_B_rea_연결안됨_mismatch() -> None:
    servers = [{"name": "rea", "status": "failed"}]
    assert check("B", init_b(mcp_servers=servers)) == rc.InitCheck("failed", "mcp_servers")


@pytest.mark.parametrize(
    "servers",
    [
        [],
        [{"name": "rea", "status": "connected"}, {"name": "x", "status": "connected"}],
        [{"name": "other", "status": "connected"}],
        "rea",
    ],
)
def test_F_R05_B_서버가_rea하나가아니면_mismatch(servers: Any) -> None:
    assert check("B", init_b(mcp_servers=servers)).detail == "mcp_servers"


def test_F_R05_A에_서버있으면_mismatch() -> None:
    servers = [{"name": "rea", "status": "connected"}]
    assert check("A", init(mcp_servers=servers)).detail == "mcp_servers"


def test_F_R05_모델다르면_mismatch() -> None:
    assert check("A", init(model="claude-other-4-0")) == rc.InitCheck("failed", "model")


def test_F_R05_권한모드다르면_mismatch() -> None:
    assert check("B", init_b(permissionMode="default")) == rc.InitCheck("failed", "permissionMode")


def test_F_R05_여러칸다르면_다른칸이름만_차례로() -> None:
    result = check("A", init(tools=["Bash"], model="x", permissionMode="bypassPermissions"))
    assert result == rc.InitCheck("failed", "tools,model,permissionMode")


def test_F_R05_칸이없으면_mismatch() -> None:
    line = init()
    del line["tools"], line["permissionMode"]
    assert check("A", line).detail == "tools,permissionMode"


def test_F_R05_init줄없음_missing() -> None:
    assert check("A", {"type": "assistant", "message": {}}).result == "missing"
    assert rc.check_init(b"", "A", MODEL).result == "missing"


def test_F_R05_init줄_JSON아님_missing() -> None:
    assert check("A", '{"type": "system", "subtype": "init", "tools": [').result == "missing"


def test_F_R05_첫_init줄만_본다() -> None:
    """앞의 다른 system 줄은 건너뛰고, 둘째 init 줄은 보지 않는다."""
    other = {"type": "system", "subtype": "hook_response"}
    assert check("A", other, init(), init(tools=["Bash"])).result == "passed"
    assert check("A", init(tools=["Bash"]), init()).result == "failed"


def test_F_R05_조건_AB밖이면_거절() -> None:
    with pytest.raises(ValueError):
        rc.check_init(stream(init()), "C", MODEL)


def test_F_R05_detail에_값을_싣지않음() -> None:
    secretish = "claude-가짜-비밀-글"
    result = check("A", init(model=secretish, tools=["가짜도구"]))
    assert secretish not in result.detail and "가짜도구" not in result.detail


# --- 처리량 (보안규칙 5장, 실험구조 8.1 ⑤) ---------------------------------------------------


def min_time(work: Callable[[], object], repeats: int = 3) -> float:
    gc.disable()
    try:
        best = float("inf")
        for _ in range(repeats):
            started = time.perf_counter()
            work()
            best = min(best, time.perf_counter() - started)
        return best
    finally:
        gc.enable()


def transcript(n: int) -> bytes:
    """init 줄이 맨 끝에 있는 대화 기록(앞에 한글 섞인 다른 줄 n개, 원문이 모두 다름)."""
    lines = [
        {"type": "user", "message": {"content": f"가나다라 {i} 한글 줄 {'마바사' * 20} {i}"}}
        for i in range(n)
    ]
    return stream(*lines, init())


@pytest.mark.parametrize("n", [10_000, 20_000])
def test_F_R05_처리량_init이_끝에있어도_선형(n: int) -> None:
    small, large = transcript(n), transcript(4 * n)
    assert rc.check_init(large, "A", MODEL).result == "passed"
    ratio = min_time(lambda: rc.check_init(large, "A", MODEL)) / min_time(
        lambda: rc.check_init(small, "A", MODEL)
    )
    assert ratio < LINEAR_RATIO_LIMIT
    tracemalloc.start()
    rc.check_init(large, "A", MODEL)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < len(large)  # 줄마다 읽고 버린다(입력만큼 사본을 만들지 않는다)
