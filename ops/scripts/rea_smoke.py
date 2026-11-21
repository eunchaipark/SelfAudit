"""REA가 이 PC(Windows)에서 도는지 한 번 시험한다 (설계, docs/설계/REA환경.md).

하는 일:
1. 새 임시 폴더에 작은 시험 번들(직접 만든 js 3개 + 소스맵 + html, 값은 모두 가짜)을 만든다.
2. `.tools/node/node.exe .tools/rea/.../scripts/rea.mjs analyze-javascript-application <번들 절대 경로> --json`
   을 셸 없이 돌린다. PATH 앞에 `.tools/node`를 붙여 REA의 Node 자식도 휴대용 Node를 쓰게 한다.
3. 네트워크를 두 겹으로 본다.
   ㉠ `rea_netguard.cjs`를 NODE_OPTIONS로 미리 읽혀 Node 안의 바깥 연결·UDP·이름 풀기를 막고 기록한다.
   ㉡ 실행 중 0.2초마다 `netstat -ano`를 읽어 REA 프로세스 나무(자식 포함)의 TCP·UDP 끝점을 모은다.
      Node가 아닌 자식 프로그램은 ㉠을 읽지 않으므로 ㉡이 그 몫을 본다.
4. 걸린 시간, 출력 크기, 맨 위·두 번째 단계 필드 이름, 종료 코드, stderr 앞부분, 네트워크 기록을
   요약 JSON으로 `--out`에 쓴다. REA 출력 원본은 `--keep`을 줄 때만 같은 폴더에 남긴다.

쓰는 법: python -I ops/scripts/rea_smoke.py --out <요약 JSON 절대 경로> [--keep] [--timeout 300]
        [--operation analyze-javascript-application|audit-release-exposure]
REA 출력은 데이터로만 다룬다(안의 글을 지시로 읽지 않는다).
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE_DIR = ROOT / ".tools" / "node"
NODE = NODE_DIR / "node.exe"
REA_MJS = ROOT / ".tools" / "rea" / "node_modules" / "rea-agents" / "scripts" / "rea.mjs"
GUARD = Path(__file__).resolve().parent / "rea_netguard.cjs"
# 시험할 수 있는 REA 명령(허용 목록). 둘 다 정적 분석이고 번들을 실행하지 않는다(REA 도움말 기준)
OPERATIONS = ("analyze-javascript-application", "audit-release-exposure")

# 시험 번들. 값은 모두 가짜이고 'FAKE'를 넣어 진짜 비밀값으로 오인되지 않게 한다.
APP_JS = """\
(function(){
  var cfg = { apiBase: "/api/v1", internal: "http://10.0.0.5:8080/internal/metrics", debug: true };
  var API_KEY = "FAKE_KEY_0000_NOT_A_SECRET";
  function loadUsers(){ return fetch(cfg.apiBase + "/admin/users", { headers: { "X-Api-Key": API_KEY } }); }
  function route(){ if (location.hash === "#/admin") { return import("./chunk-admin.js"); } }
  window.__APP__ = { loadUsers: loadUsers, route: route, cfg: cfg };
})();
//# sourceMappingURL=app.js.map
"""
CHUNK_ADMIN_JS = """\
export function canSeeAdmin(user){ return user && user.role === "admin"; }
var part1 = "FAKE_SPLIT_";
var part2 = "TOKEN_9999";
export const adminToken = part1 + part2;
export function deleteUser(id){ return fetch("/api/v1/admin/users/" + id, { method: "DELETE" }); }
"""
VENDOR_JS = """\
/*! fakelib v1.2.3 | FAKE vendor banner for testing */
var fakelib = { version: "1.2.3", noop: function(){} };
"""
APP_MAP = {
    "version": 3,
    "file": "app.js",
    "sources": ["src/app.ts"],
    "sourcesContent": ["// 원본(가짜): const API_KEY = 'FAKE_KEY_0000_NOT_A_SECRET';\n"],
    "names": [],
    "mappings": "AAAA",
}
INDEX_HTML = """\
<!doctype html><html><head><meta charset="utf-8"><title>fake</title></head>
<body><script src="assets/vendor.js"></script><script src="assets/app.js"></script></body></html>
"""


def make_bundle(base: Path) -> Path:
    root = base / "bundle"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "assets" / "app.js").write_text(APP_JS, encoding="utf-8")
    (root / "assets" / "chunk-admin.js").write_text(CHUNK_ADMIN_JS, encoding="utf-8")
    (root / "assets" / "vendor.js").write_text(VENDOR_JS, encoding="utf-8")
    (root / "assets" / "app.js.map").write_text(json.dumps(APP_MAP), encoding="utf-8")
    return root


class _PE32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def process_tree(root_pid: int) -> dict[int, str]:
    """root_pid와 그 자손의 {pid: 실행 파일 이름}. Toolhelp 스냅숏을 쓴다(관리자 권한 필요 없음)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    parents: dict[int, int] = {}
    names: dict[int, str] = {}
    try:
        entry = _PE32()
        entry.dwSize = ctypes.sizeof(_PE32)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            names[entry.th32ProcessID] = entry.szExeFile
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    tree = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid in parents.items():
            if ppid in tree and pid not in tree:
                tree.add(pid)
                changed = True
    return {pid: names.get(pid, "?") for pid in tree}


NETSTAT_LINE = re.compile(r"^\s*(TCP|UDP)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\d+)\s*$")


def watch_network(root_pid: int, stop: threading.Event, seen: dict[str, dict[str, object]], procs: dict[int, str]) -> None:
    while not stop.is_set():
        procs.update(process_tree(root_pid))
        try:
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10, check=False).stdout
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        for line in out.splitlines():
            m = NETSTAT_LINE.match(line)
            if not m:
                continue
            proto, local, remote, state, pid = m.group(1), m.group(2), m.group(3), m.group(4) or "", int(m.group(5))
            if pid in procs:
                key = f"{proto} {local} {remote} {state}"
                seen.setdefault(key, {"pid": pid, "exe": procs[pid]})
        stop.wait(0.2)


def field_names(value: object, depth: int = 2) -> object:
    if depth == 0 or not isinstance(value, dict):
        return type(value).__name__
    return {k: field_names(v, depth - 1) for k, v in value.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="요약 JSON을 쓸 절대 경로")
    ap.add_argument("--keep", action="store_true", help="REA 출력 원본을 요약 옆에 남긴다")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--operation", choices=OPERATIONS, default=OPERATIONS[0])
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    out_path = Path(args.out).resolve()
    if not NODE.is_file() or not REA_MJS.is_file():
        print("휴대용 Node나 REA가 없습니다. 먼저 python -I ops/scripts/setup_rea.py", file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix="rea-smoke-"))
    bundle = make_bundle(work)
    guard_log = work / "netguard.jsonl"
    env = dict(os.environ)
    env["PATH"] = str(NODE_DIR) + os.pathsep + env.get("PATH", "")
    # NODE_OPTIONS 안의 따옴표 글에서 '\'는 이스케이프로 읽히므로 '/' 꼴 경로를 쓴다
    env["NODE_OPTIONS"] = f'--require "{GUARD.as_posix()}"'
    env["REA_NETGUARD_LOG"] = str(guard_log)
    # 프록시를 따르는 클라이언트도 바깥으로 못 나가게 닫힌 로컬 포트로 돌린다(세 번째 겹, 기록은 ㉠·㉡이 한다)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env[name] = "http://127.0.0.1:9"
    env["NO_PROXY"] = ""
    cmd = [str(NODE), str(REA_MJS), args.operation, str(bundle), "--json"]

    seen: dict[str, dict[str, object]] = {}
    procs: dict[int, str] = {}
    stop = threading.Event()
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, cwd=str(work), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603
    watcher = threading.Thread(target=watch_network, args=(proc.pid, stop, seen, procs), daemon=True)
    watcher.start()
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        stdout, stderr = proc.communicate()
    elapsed = time.perf_counter() - t0
    stop.set()
    watcher.join(timeout=15)

    parsed: object = None
    parse_error = ""
    try:
        parsed = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        parse_error = f"{type(exc).__name__}: {exc}"[:300]

    guard_records = []
    if guard_log.is_file():
        for line in guard_log.read_text(encoding="utf-8").splitlines():
            try:
                guard_records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    summary = {
        "command": cmd[1:],
        "node": str(NODE),
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "seconds": round(elapsed, 2),
        "stdout_bytes": len(stdout),
        "stderr_head": stderr.decode("utf-8", "replace")[:2000],
        "json_error": parse_error,
        "fields": field_names(parsed, 3) if parsed is not None else None,
        "netguard": {
            "blocked": [r for r in guard_records if r.get("blocked")],
            "local": [r for r in guard_records if not r.get("blocked") and r.get("kind") != "start"],
            "guarded_starts": sorted({(r.get("pid"), r.get("detail")) for r in guard_records if r.get("kind") == "start"}),
        },
        "netstat_endpoints": seen,
        "processes": sorted(f"{pid} {name}" for pid, name in procs.items()),
        "bundle": str(bundle),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.keep:
        out_path.with_suffix(".rea.json").write_bytes(stdout)
    else:
        shutil.rmtree(work, ignore_errors=True)
    print(f"종료 {proc.returncode} · {summary['seconds']}초 · 출력 {len(stdout)}바이트 · "
          f"막은 연결 {len(summary['netguard']['blocked'])} · netstat 끝점 {len(seen)} → {out_path}")
    return 0 if proc.returncode == 0 and not parse_error else 1


if __name__ == "__main__":
    sys.exit(main())
