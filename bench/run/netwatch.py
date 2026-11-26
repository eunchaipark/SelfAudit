"""F-R07 네트워크 기록: ㉠ netguard.jsonl 세기 · ㉡ 프로세스 밖 폴링 · 방화벽 규칙 상태 (실험구조
3.7).

기록 장치이지 차단 장치가 아니다(REA환경.md 4절). 기록이 하나라도 있으면(㉠ 막은 것·㉡ 끝점) 그
배치를
멈추고 총괄에 알린다 — REA의 바깥 연결은 지금까지 기록된 적이 없어 생기면 원인을 먼저 봐야 한다.

㉡은 Claude Code 프로세스 나무 안에서 이미지 경로가 `<ROOT>\\.tools\\node\\node.exe`인 프로세스와
그 자손만
본다. Claude Code 자신(나무의 뿌리)과 그 밖 자식(거르개 파이썬 등)의 연결은 보지 않는다 — Claude
Code의
모델 호출은 실험의 일부다(D-036). 조건 A에도 돌린다(기록 0이어야 한다, 감시가 헛것을 잡지 않는지
보는 대조).
"""

from __future__ import annotations

import ctypes
import io
import json
import ntpath
import re
import subprocess
import threading
from collections.abc import Callable, Mapping
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from run.workdir import BatchStop

__all__ = [
    "FIREWALL_RULE_NAME",
    "POLL_S",
    "Endpoint",
    "NetRecord",
    "NetWatch",
    "NetguardCounts",
    "NetstatError",
    "check_network",
    "firewall_state",
    "network_record",
    "parse_netstat",
    "process_snapshot",
    "read_netguard",
    "run_netstat",
    "watched_pids",
]

# 0.2초: `netstat -ano` 한 번이 이 PC에서 0.04~0.07초라 한 코어의 20~35%만 쓴다(REA환경.md 4절)
POLL_S: Final = 0.2
NETSTAT_TIMEOUT_S: Final = 10.0
FIREWALL_TIMEOUT_S: Final = 30.0
FIREWALL_RULE_NAME: Final = "SelfAudit REA node 바깥 막기"  # REA환경.md 4절 New-NetFirewallRule
FIREWALL_STATES: Final = frozenset({"on", "off", "absent"})
NETGUARD_START: Final = "start"  # rea_netguard.cjs가 읽힐 때 남기는 첫 줄의 kind
_NETSTAT_LINE: Final = re.compile(rb"^\s*(TCP|UDP)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\d+)\s*$")
# Toolhelp(Win32 tlhelp32.h)
_TH32CS_SNAPPROCESS: Final = 0x2
_INVALID_HANDLE: Final = ctypes.c_void_p(-1).value
_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_MAX_IMAGE_CHARS: Final = 32_768
# 방화벽 규칙 상태를 읽는 PowerShell 글(규칙 이름 말고 바깥 값이 들어가지 않는다)
_FIREWALL_SCRIPT: Final = (
    "$r = @(Get-NetFirewallRule -DisplayName '"
    + FIREWALL_RULE_NAME
    + "' -ErrorAction SilentlyContinue); "
    "if ($r.Count -eq 0) { 'absent' } "
    "elseif (@($r | Where-Object { $_.Enabled -eq 'True' }).Count -gt 0) { 'on' } "
    "else { 'off' }"
)

type Snapshot = Mapping[int, tuple[int, str]]  # pid → (부모 pid, 실행 파일 이름)
type Runner = Callable[[list[str]], tuple[int, bytes]]  # 인자 목록 → (종료 코드, stdout)


class NetstatError(RuntimeError):
    """F-R07 예외: `netstat` 실행 실패 → 그 실행 `error`(기록 없이 채점하지 않는다)."""


@dataclass(frozen=True)
class Endpoint:
    proto: str
    local: str
    remote: str
    state: str
    pid: int


@dataclass(frozen=True)
class NetguardCounts:
    """㉠ 기록 수. `processes`는 ㉠을 읽은(감시한) 프로세스 수 = `start` 줄의 서로 다른 pid 수."""

    blocked: int
    local: int
    processes: int


@dataclass
class NetRecord:
    """㉡ 한 실행의 폴링 기록."""

    polls: int = 0
    endpoints: dict[tuple[str, str, str, str], tuple[int, str]] = field(default_factory=dict)
    rea_processes: dict[int, str] = field(default_factory=dict)  # pid → 실행 파일 이름
    error: str | None = None

    def to_json(self) -> bytes:
        """`netstat.json`. 실행 파일은 이름만 싣는다(경로에는 사용자 이름이 있다)."""
        value = {
            "poll_s": POLL_S,
            "polls": self.polls,
            "endpoints": [
                {
                    "proto": k[0],
                    "local": k[1],
                    "remote": k[2],
                    "state": k[3],
                    "pid": v[0],
                    "image": v[1],
                }
                for k, v in self.endpoints.items()
            ],
            "rea_processes": [
                {"pid": p, "image": n} for p, n in sorted(self.rea_processes.items())
            ],
            "error": self.error,
        }
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# --- ㉠ ------------------------------------------------------------------------------------


def read_netguard(data: bytes) -> NetguardCounts:
    """`netguard.jsonl`(거르개가 REA에 넣은 ㉠의 기록) 세기.

    `blocked: true` → 막은 수, `blocked: false`이고 `start`가 아님 → 루프백·로컬 통과 수. 읽을 수
    없는
    줄은 막은 것으로 센다(실패하면 안전한 쪽 — 배치가 멈추고 사람이 본다). 값(주소)은 싣지 않는다.
    """
    blocked = local = 0
    pids: set[int] = set()
    for line in io.BytesIO(data):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            blocked += 1
            continue
        if not isinstance(obj, dict):
            blocked += 1
            continue
        if obj.get("kind") == NETGUARD_START:
            pid = obj.get("pid")
            if isinstance(pid, int):
                pids.add(pid)
            continue
        if obj.get("blocked") is False:
            local += 1
        else:
            blocked += 1
    return NetguardCounts(blocked=blocked, local=local, processes=len(pids))


# --- ㉡ ------------------------------------------------------------------------------------


def parse_netstat(text: bytes) -> list[Endpoint]:
    """`netstat -ano` 출력의 TCP·UDP 줄. 머리줄·빈 줄은 건너뛴다(한 줄씩, 입력에 선형)."""
    out: list[Endpoint] = []
    for line in io.BytesIO(text):
        m = _NETSTAT_LINE.match(line)
        if m is None:
            continue
        out.append(
            Endpoint(
                proto=m.group(1).decode(),
                local=m.group(2).decode("ascii", "replace"),
                remote=m.group(3).decode("ascii", "replace"),
                state=(m.group(4) or b"").decode("ascii", "replace"),
                pid=int(m.group(5)),
            )
        )
    return out


def run_netstat(environ: Mapping[str, str]) -> bytes:
    """`%SystemRoot%\\System32\\NETSTAT.EXE -ano`를 셸 없이, 절대 경로로. 실패하면
    `NetstatError`."""
    exe = _system32(environ, "NETSTAT.EXE")
    try:
        done = subprocess.run(  # noqa: S603 — 고정 절대 경로, 셸 없음
            [exe, "-ano"],
            capture_output=True,
            timeout=NETSTAT_TIMEOUT_S,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise NetstatError(f"netstat 실행 실패 ({type(e).__name__})") from None
    if done.returncode != 0:
        raise NetstatError(f"netstat 종료 코드 {done.returncode}")
    return done.stdout


def watched_pids(
    snapshot: Snapshot, root_pid: int, node_image: str, image_of: Callable[[int], str | None]
) -> set[int]:
    """`root_pid`의 자손 가운데 이미지 경로가 `node_image`인 것과 그 자손(뿌리 자신은 뺀다).

    이미지 경로는 대소문자·구분자를 맞춰(normcase·normpath) 비교한다.
    """
    children: dict[int, list[int]] = {}
    for pid, (ppid, _name) in snapshot.items():
        if pid != ppid:
            children.setdefault(ppid, []).append(pid)
    want = _norm(node_image)
    watched: set[int] = set()
    stack = [(child, False) for child in children.get(root_pid, [])]
    seen = {root_pid}
    while stack:
        pid, under_node = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        if not under_node:
            image = image_of(pid)
            under_node = image is not None and _norm(image) == want
        if under_node:
            watched.add(pid)
        stack.extend((child, under_node) for child in children.get(pid, []))
    return watched


class NetWatch:
    """㉡ 폴링을 따로 도는 실 하나로. `start(pid)` → 실행이 끝나면 `stop()` → `NetRecord`.

    시험은 `netstat`·`snapshot`·`image_of`를 가짜로 준다. 폴링 사이 0.2초보다 짧게 열렸다 닫힌
    연결은
    놓칠 수 있다(REA환경.md 4절 한계 ⑤).
    """

    def __init__(
        self,
        node_image: Path,
        environ: Mapping[str, str],
        *,
        poll_s: float = POLL_S,
        netstat: Callable[[], bytes] | None = None,
        snapshot: Callable[[], Snapshot] | None = None,
        image_of: Callable[[int], str | None] | None = None,
    ) -> None:
        self._node_image = str(node_image)
        self._poll_s = poll_s
        self._netstat = netstat or (lambda: run_netstat(environ))
        self._snapshot = snapshot or process_snapshot
        self._image_of = image_of or process_image
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._root = 0
        self.record = NetRecord()

    def start(self, root_pid: int) -> None:
        self._root = root_pid
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> NetRecord:
        """멈추고 마지막으로 한 번 더 본다(끝나기 직전 연결)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self.poll_once()
        return self.record

    def poll_once(self) -> None:
        """한 번 본다. 무엇이 실패하든(프로세스 목록·이미지 경로·netstat) `record.error`에 적는다 —
        감시가 소리 없이 멈추면 '기록 0'이 통과로 세어진다(F-R07 예외: 기록 없이 채점하지
        않는다)."""
        if self.record.error is not None:
            return
        try:
            self._poll()
        except NetstatError as e:
            self.record.error = str(e)
        except Exception as e:  # 실 안의 예외는 부르는 쪽에 닿지 않는다 — 삼키지 않고 기록한다
            self.record.error = f"㉡ 폴링 실패 ({type(e).__name__})"

    def _poll(self) -> None:
        snapshot = self._snapshot()
        pids = watched_pids(snapshot, self._root, self._node_image, self._image_of)
        endpoints = parse_netstat(self._netstat())
        for pid in pids:
            self.record.rea_processes.setdefault(pid, snapshot[pid][1])
        self.record.polls += 1
        for ep in endpoints:
            if ep.pid in pids:
                key = (ep.proto, ep.local, ep.remote, ep.state)
                self.record.endpoints.setdefault(key, (ep.pid, snapshot[ep.pid][1]))

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                self.poll_once()
                self._stop.wait(self._poll_s)
        finally:
            # 멈추라는 말 없이 실이 끝났으면(예: poll_once 밖의 실패) 감시가 없던 것이다
            if not self._stop.is_set() and self.record.error is None:
                self.record.error = "㉡ 폴링 실이 일찍 끝남"


# --- 방화벽·합치기 --------------------------------------------------------------------------


def firewall_state(environ: Mapping[str, str], runner: Runner | None = None) -> str:
    """F-R07 3: 규칙 "SelfAudit REA node 바깥 막기"의 상태 `on`·`off`·`absent`. 읽을 수 없으면
    `unknown`
    (멈추지 않는다 — 규칙은 사용자 확인(관리자 권한)이라 있을 수도 없을 수도 있다)."""
    try:
        exe = _system32(environ, "WindowsPowerShell", "v1.0", "powershell.exe")
    except NetstatError:
        return "unknown"
    argv = [exe, "-NoProfile", "-NonInteractive", "-Command", _FIREWALL_SCRIPT]
    try:
        code, out = (runner or _run_capture)(argv)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = out.decode("ascii", "replace").strip()
    return text if code == 0 and text in FIREWALL_STATES else "unknown"


def network_record(guard: NetguardCounts, watch: NetRecord) -> dict[str, int]:
    """F-R07 4: `run.json`의 `network`."""
    return {
        "netguard_blocked": guard.blocked,
        "netguard_local": guard.local,
        "netstat_endpoints": len(watch.endpoints),
        "guarded_processes": guard.processes,
        "rea_processes": len(watch.rea_processes),
    }


def check_network(network: Mapping[str, int]) -> None:
    """F-R07 5: ㉠ 막은 수나 ㉡ 끝점 수가 하나라도 있으면 배치를 멈춘다(개수만 싣는다)."""
    blocked, endpoints = network["netguard_blocked"], network["netstat_endpoints"]
    if blocked or endpoints:
        raise BatchStop("F-R07 5", f"네트워크 기록 있음: ㉠ 막은 {blocked}, ㉡ 끝점 {endpoints}")


def _run_capture(argv: list[str]) -> tuple[int, bytes]:
    done = subprocess.run(  # noqa: S603 — 고정 절대 경로와 고정 글, 셸 없음
        argv,
        capture_output=True,
        timeout=FIREWALL_TIMEOUT_S,
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
    )
    return done.returncode, done.stdout


def _system32(environ: Mapping[str, str], *parts: str) -> str:
    by_upper = {k.upper(): v for k, v in environ.items()}
    root = by_upper.get("SYSTEMROOT", "")
    if not ntpath.isabs(root):
        raise NetstatError("SystemRoot가 없거나 절대 경로가 아님")
    return ntpath.join(root, "System32", *parts)


def _norm(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path))


# --- Win32 ---------------------------------------------------------------------------------


class _ProcessEntry(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    )


def process_snapshot() -> dict[int, tuple[int, str]]:
    """모든 프로세스의 (부모 pid, 실행 파일 이름). Toolhelp라 관리자 권한이 필요 없다."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snap = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE:
        raise NetstatError("프로세스 목록을 읽을 수 없음")
    out: dict[int, tuple[int, str]] = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), str(entry.szExeFile))
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def process_image(pid: int) -> str | None:
    """프로세스의 실행 파일 전체 경로(`QueryFullProcessImageNameW`). 못 열면 None."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(_MAX_IMAGE_CHARS)
        size = wintypes.DWORD(_MAX_IMAGE_CHARS)
        if not k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return str(buffer.value)
    finally:
        k32.CloseHandle(handle)
