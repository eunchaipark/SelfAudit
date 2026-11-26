"""F-R07 네트워크 기록 (R4) 시험. 기능명세 F-R07 예시를 옮겼다(값은 가상).

바깥 연결은 만들지 않는다. ㉡의 나무·끝점 판정은 가짜 프로세스 목록·가짜 netstat 글로 보고, 진짜
`netstat -ano`·Toolhelp는 읽기만 한다(이 PC의 연결을 만들지 않음).
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import pytest

from run import netwatch as nw
from run import workdir as rw

NODE = r"C:\repo\.tools\node\node.exe"
PYTHON = Path(getattr(sys, "_base_executable", sys.executable))
# 선형 4N/N 약 4, 제곱 약 16의 가운데(부하 흔들림을 두 배까지 받아 줌, 코드규칙 6장)
LINEAR_RATIO_LIMIT = 8.0

# Claude Code(100) → 거르개 파이썬(101) → REA node(102) → 분석 자식 node(103)·conhost(104)
#                  → git(105, node 아님)  / 나무 밖 node(200)
SNAPSHOT = {
    100: (1, "claude.exe"),
    101: (100, "python.exe"),
    102: (101, "node.exe"),
    103: (102, "node.exe"),
    104: (102, "conhost.exe"),
    105: (100, "git.exe"),
    200: (1, "node.exe"),
}
IMAGES = {
    100: r"C:\Users\u\AppData\Roaming\npm\claude.exe",
    101: r"C:\Python\python.exe",
    102: NODE,
    103: NODE.upper(),  # 대소문자만 다른 꼴도 같은 실행 파일
    104: r"C:\Windows\System32\conhost.exe",
    105: r"C:\Git\git.exe",
    200: NODE,
}


def netstat_text(*rows: tuple[str, str, str, str, int]) -> bytes:
    head = "\r\n활성 연결\r\n\r\n  프로토콜  로컬 주소    외부 주소    상태    PID\r\n"
    body = "".join(f"  {p}    {loc}   {rem}   {st}   {pid}\r\n" for p, loc, rem, st, pid in rows)
    return (head + body).encode("cp949")


def fake_watch(netstat: bytes) -> nw.NetWatch:
    return nw.NetWatch(
        Path(NODE),
        {},
        poll_s=0.01,
        netstat=lambda: netstat,
        snapshot=lambda: SNAPSHOT,
        image_of=IMAGES.get,
    )


def test_F_R07_tools_node만_본다() -> None:
    """나무 안 node.exe와 그 자손만. Claude Code 자신·node 아닌 자식·나무 밖 node는 보지 않는다."""
    assert nw.watched_pids(SNAPSHOT, 100, NODE, IMAGES.get) == {102, 103, 104}
    rows = [
        ("TCP", "10.0.0.5:50000", "203.0.113.9:443", "ESTABLISHED", 100),  # Claude Code 모델 호출
        ("TCP", "10.0.0.5:50001", "192.0.2.1:443", "SYN_SENT", 103),  # REA 분석 자식
        ("UDP", "0.0.0.0:5353", "*:*", "", 104),
        ("TCP", "10.0.0.5:50002", "192.0.2.2:443", "ESTABLISHED", 105),
        ("TCP", "10.0.0.5:50003", "192.0.2.3:443", "ESTABLISHED", 200),
    ]
    watch = fake_watch(netstat_text(*rows))
    watch.start(100)
    record = watch.stop()
    assert {v[0] for v in record.endpoints.values()} == {103, 104}
    assert set(record.rea_processes) == {102, 103, 104}
    network = nw.network_record(nw.NetguardCounts(0, 0, 1), record)
    assert network["netstat_endpoints"] == 2 and network["rea_processes"] == 3
    out = json.loads(record.to_json())
    assert {e["image"] for e in out["endpoints"]} == {"node.exe", "conhost.exe"}
    assert "Users" not in record.to_json().decode()  # 실행 파일은 이름만


def test_F_R07_조건A_기록0() -> None:
    """A: REA 서버가 없어 나무에 node가 없다 → ㉡ 끝점 0, REA 프로세스 0 → 계속."""
    snapshot = {100: (1, "claude.exe"), 105: (100, "git.exe")}
    watch = nw.NetWatch(
        Path(NODE),
        {},
        poll_s=0.01,
        netstat=lambda: netstat_text(("TCP", "10.0.0.5:1", "203.0.113.9:443", "ESTABLISHED", 100)),
        snapshot=lambda: snapshot,
        image_of=IMAGES.get,
    )
    watch.start(100)
    time.sleep(0.05)
    record = watch.stop()
    assert record.polls >= 1
    network = nw.network_record(nw.read_netguard(b""), record)
    assert network == {
        "netguard_blocked": 0,
        "netguard_local": 0,
        "netstat_endpoints": 0,
        "guarded_processes": 0,
        "rea_processes": 0,
    }
    nw.check_network(network)  # 멈추지 않음


def guard_line(**fields: object) -> bytes:
    return json.dumps(fields, ensure_ascii=False).encode() + b"\n"


def test_F_R07_예시_B_막은0_루프백0_끝점0_REA2_계속() -> None:
    netguard = guard_line(pid=7, kind="start", detail="rea.mjs mcp", blocked=False)
    counts = nw.read_netguard(netguard)
    record = nw.NetRecord(polls=3, rea_processes={7: "node.exe", 8: "node.exe"})
    network = nw.network_record(counts, record)
    assert network["rea_processes"] == 2 and network["guarded_processes"] == 1
    nw.check_network(network)


def test_F_R07_netguard_세기() -> None:
    data = b"".join(
        [
            guard_line(pid=1, kind="start", detail="x", blocked=False),
            guard_line(pid=2, kind="start", detail="x", blocked=False),
            guard_line(pid=1, kind="start", detail="x", blocked=False),
            guard_line(pid=1, kind="tcp-local", detail="127.0.0.1:9", blocked=False),
            guard_line(pid=1, kind="pipe-local", detail="\\\\.\\pipe\\x", blocked=False),
            guard_line(pid=1, kind="tcp", detail="192.0.2.1:443", blocked=True),
            b"\n",
        ]
    )
    assert nw.read_netguard(data) == nw.NetguardCounts(blocked=1, local=2, processes=2)


@pytest.mark.parametrize("bad", [b"{not json\n", b"[1, 2]\n", guard_line(kind="tcp")])
def test_F_R07_netguard_읽을수없는줄은_막은것으로(bad: bytes) -> None:
    """잘린 줄·꼴 아닌 줄·blocked 칸이 없는 줄은 막은 것으로 센다(실패하면 안전한 쪽)."""
    assert nw.read_netguard(bad).blocked == 1


def test_F_R07_기록있으면_배치멈춤() -> None:
    """B, ㉠에 192.0.2.1:443 막음 1 → 배치 멈춤. B, ㉡에 REA 자식의 끝점 1 → 배치 멈춤."""
    blocked = nw.read_netguard(guard_line(pid=1, kind="tcp", detail="192.0.2.1:443", blocked=True))
    with pytest.raises(rw.BatchStop) as e:
        nw.check_network(nw.network_record(blocked, nw.NetRecord()))
    assert e.value.rule == "F-R07 5"
    assert "192.0.2.1" not in str(e.value)  # 개수만 싣는다
    rows = [("TCP", "10.0.0.5:50001", "192.0.2.1:443", "SYN_SENT", 103)]
    watch = fake_watch(netstat_text(*rows))
    watch.start(100)
    with pytest.raises(rw.BatchStop):
        nw.check_network(nw.network_record(nw.NetguardCounts(0, 0, 1), watch.stop()))


def test_F_R07_netstat실패면_기록에_오류() -> None:
    """netstat 실행 실패 → 그 실행 error(기록 없이 채점하지 않는다) — 부르는 쪽이
    `record.error`로."""

    def broken() -> bytes:
        raise nw.NetstatError("netstat 종료 코드 1")

    watch = nw.NetWatch(
        Path(NODE), {}, poll_s=0.01, netstat=broken, snapshot=lambda: SNAPSHOT, image_of=IMAGES.get
    )
    watch.start(100)
    record = watch.stop()
    assert record.error == "netstat 종료 코드 1"
    assert json.loads(record.to_json())["error"] == "netstat 종료 코드 1"


def failing_on(call: int, error: Exception) -> Callable[[], dict[int, tuple[int, str]]]:
    """`call`번째 부름에서만 실패하는 가짜 프로세스 목록(그 밖에는 node가 바깥에 붙은 나무)."""
    state = {"n": 0}

    def snapshot() -> dict[int, tuple[int, str]]:
        state["n"] += 1
        if state["n"] == call:
            raise error
        return SNAPSHOT

    return snapshot


@pytest.mark.parametrize("call", [1, 3], ids=["첫폴링", "중간폴링"])
@pytest.mark.parametrize(
    "error",
    [nw.NetstatError("프로세스 목록을 읽을 수 없음"), OSError("가짜"), KeyError(7)],
    ids=["NetstatError", "OSError", "생각못한예외"],
)
def test_F_R07_폴링이_한번이라도_실패하면_오류(call: int, error: Exception) -> None:
    """프로세스 목록이 한 번 실패해도 감시 실이 소리 없이 죽지 않고 `record.error`로 남는다
    → 그 실행 error(기록 없이 채점하지 않는다). 끝점 0이 '통과'로 세어지지 않는다(T32 반려 1)."""
    rows = netstat_text(("TCP", "10.0.0.5:5000", "192.0.2.1:443", "ESTABLISHED", 103))
    watch = nw.NetWatch(
        Path(NODE),
        {},
        poll_s=0.01,
        netstat=lambda: rows,
        snapshot=failing_on(call, error),
        image_of=IMAGES.get,
    )
    watch.start(100)
    time.sleep(0.2)
    record = watch.stop()
    assert record.error is not None
    if isinstance(error, nw.NetstatError):
        assert record.error == "프로세스 목록을 읽을 수 없음"
    else:
        assert record.error == f"㉡ 폴링 실패 ({type(error).__name__})"
    assert record.polls == call - 1  # 실패한 뒤로는 세지 않는다
    assert json.loads(record.to_json())["error"] == record.error


def test_F_R07_이미지경로가_실패해도_오류() -> None:
    def broken(_pid: int) -> str | None:
        raise OSError("가짜")

    watch = nw.NetWatch(
        Path(NODE), {}, poll_s=0.01, netstat=lambda: b"", snapshot=lambda: SNAPSHOT, image_of=broken
    )
    watch.start(100)
    assert watch.stop().error == "㉡ 폴링 실패 (OSError)"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_F_R07_폴링실이_일찍끝나면_오류(monkeypatch: pytest.MonkeyPatch) -> None:
    """poll_once 밖에서 실이 끝나도(멈추라는 말 없이) 감시가 없던 것으로 적는다."""
    watch = fake_watch(b"")

    def boom(_timeout: float | None = None) -> bool:
        raise RuntimeError("가짜")

    monkeypatch.setattr(watch._stop, "wait", boom)
    watch.start(100)
    assert watch._thread is not None
    watch._thread.join(timeout=5)
    assert watch.stop().error == "㉡ 폴링 실이 일찍 끝남"


def test_F_R07_netstat_SystemRoot없으면_실패() -> None:
    with pytest.raises(nw.NetstatError):
        nw.run_netstat({})


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ((0, b"on\r\n"), "on"),
        ((0, b"off\r\n"), "off"),
        ((0, b"absent\r\n"), "absent"),
        ((0, b"Enabled\r\n"), "unknown"),
        ((1, b"on\r\n"), "unknown"),
        ((0, b""), "unknown"),
    ],
)
def test_F_R07_방화벽상태_기록(answer: tuple[int, bytes], expected: str) -> None:
    seen: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[int, bytes]:
        seen.append(argv)
        return answer

    state = nw.firewall_state({"SystemRoot": r"C:\Windows"}, runner)
    assert state == expected
    argv = seen[0]
    assert argv[0] == r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    assert "Get-NetFirewallRule" in argv[-1] and nw.FIREWALL_RULE_NAME in argv[-1]


def test_F_R07_방화벽상태_읽을수없으면_unknown_멈추지않음() -> None:
    def runner(_argv: list[str]) -> tuple[int, bytes]:
        raise subprocess.TimeoutExpired("powershell", 30)

    assert nw.firewall_state({"SystemRoot": r"C:\Windows"}, runner) == "unknown"
    assert nw.firewall_state({}, runner) == "unknown"


def test_F_R07_netstat_줄읽기() -> None:
    text = netstat_text(
        ("TCP", "127.0.0.1:5000", "0.0.0.0:0", "LISTENING", 42),
        ("TCP", "[::1]:5001", "[::]:0", "LISTENING", 43),
        ("UDP", "0.0.0.0:5353", "*:*", "", 44),
    )
    assert nw.parse_netstat(text) == [
        nw.Endpoint("TCP", "127.0.0.1:5000", "0.0.0.0:0", "LISTENING", 42),
        nw.Endpoint("TCP", "[::1]:5001", "[::]:0", "LISTENING", 43),
        nw.Endpoint("UDP", "0.0.0.0:5353", "*:*", "", 44),
    ]


def test_F_R07_진짜netstat_읽기만() -> None:
    """이 PC의 `netstat -ano`(읽기만)를 읽어 꼴을 맞춘다 — 어느 PC에나 듣는 끝점이 있다."""
    endpoints = nw.parse_netstat(nw.run_netstat(os.environ))
    assert endpoints
    assert all(e.proto in {"TCP", "UDP"} and e.pid >= 0 for e in endpoints)


def test_F_R07_진짜_프로세스나무와_이미지경로(tmp_path: Path) -> None:
    """자식 파이썬이 손자 파이썬을 띄움 → 이미지가 '파이썬'(가짜 node 자리)인 자손을 찾는다."""
    script = tmp_path / "tree.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "c = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])\n"
        "print(c.pid, flush=True)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    parent = subprocess.Popen(  # noqa: S603 — 시험이 만든 고정 인자
        [str(PYTHON), "-I", str(script)], stdout=subprocess.PIPE
    )
    try:
        assert parent.stdout is not None
        grandchild = int(parent.stdout.readline())
        snapshot = nw.process_snapshot()
        assert snapshot[grandchild][0] == parent.pid
        image = nw.process_image(grandchild)
        assert image is not None
        assert os.path.normcase(image) == os.path.normcase(str(PYTHON))
        assert nw.watched_pids(snapshot, parent.pid, str(PYTHON), nw.process_image) == {grandchild}
    finally:
        subprocess.run(  # noqa: S603 — 고정 절대 경로와 정수 PID
            [os.path.join(os.environ["SYSTEMROOT"], "System32", "taskkill.exe"), "/T", "/F",
             "/PID", str(parent.pid)],
            capture_output=True,
            check=False,
        )  # fmt: skip
        parent.wait(timeout=10)


def test_F_R07_순환하는_부모표도_끝남() -> None:
    """pid 재사용으로 부모 표가 고리를 이뤄도 멈추지 않는다."""
    snapshot = {10: (11, "node.exe"), 11: (10, "node.exe"), 12: (12, "x.exe")}
    assert nw.watched_pids(snapshot, 10, NODE, lambda _p: NODE) == {11}


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


def netguard_lines(n: int) -> bytes:
    """걸림 n개(막은 기록, 원문이 모두 다름 — 한글 detail 섞음)."""
    return b"".join(
        guard_line(pid=i % 7, kind="tcp", detail=f"192.0.2.{i % 250}:{i} 가나다 {i}", blocked=True)
        for i in range(n)
    )


@pytest.mark.parametrize("n", [10_000, 20_000])
def test_F_R07_처리량_netguard_걸림N_선형(n: int) -> None:
    small, large = netguard_lines(n), netguard_lines(4 * n)
    assert nw.read_netguard(large).blocked == 4 * n
    ratio = min_time(lambda: nw.read_netguard(large)) / min_time(lambda: nw.read_netguard(small))
    assert ratio < LINEAR_RATIO_LIMIT
    tracemalloc.start()
    nw.read_netguard(large)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < len(large)


@pytest.mark.parametrize("n", [10_000, 20_000])
def test_F_R07_처리량_netstat_끝점N_선형(n: int) -> None:
    def rows(k: int) -> bytes:
        return netstat_text(
            *(("TCP", f"10.0.{i // 250}.{i % 250}:{i}", "192.0.2.1:443", "ESTABLISHED", 103)
              for i in range(k))
        )  # fmt: skip

    small, large = rows(n), rows(4 * n)
    assert len(nw.parse_netstat(large)) == 4 * n
    ratio = min_time(lambda: nw.parse_netstat(large)) / min_time(lambda: nw.parse_netstat(small))
    assert ratio < LINEAR_RATIO_LIMIT
