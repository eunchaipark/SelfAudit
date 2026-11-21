"""REA 실험 환경을 다시 만든다: 휴대용 Node + rea-agents (설계, docs/설계/REA환경.md).

사용자 허락(2026-11-21): nodejs.org 공식 휴대용 zip을 저장소 안 `.tools/`(git에 안 올림)에 받아
REA 전용으로만 쓰고, rea-agents를 버전 고정으로 설치한다. 관리자 권한·시스템 PATH·지금 Node는 건드리지 않는다.

하는 일 (이미 맞게 깔려 있으면 그 단계는 건너뛴다):
1. Node zip과 SHASUMS256.txt를 새 빈 임시 폴더에 받고, zip의 sha256이 ① 아래 고정값 ② SHASUMS256.txt의
   값과 모두 같은지 본다. 하나라도 다르면 멈춘다.
2. zip을 `.tools/node/`에 푼다(맨 위 폴더 한 겹을 벗기고, 폴더 밖으로 나가는 항목이 있으면 멈춘다).
3. `ops/scripts/rea/package.json`·`package-lock.json`(버전과 해시를 고정한 것)을 `.tools/rea/`에 복사하고
   휴대용 npm으로 `npm ci --ignore-scripts`. 사용자 npm 설정(~/.npmrc)은 읽지 않게 빈 설정 파일을 쓴다.
4. `rea --version`이 고정 버전과 같은지 본다.

쓰는 법: python -I ops/scripts/setup_rea.py [--tools-dir <절대 경로>]   (기본은 저장소의 .tools)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINNED_DIR = Path(__file__).resolve().parent / "rea"

# 고정값. 바꿀 때는 docs/설계/REA환경.md '버전과 해시'도 같이 고친다.
NODE_VERSION = "v24.22.3"
NODE_ZIP = f"node-{NODE_VERSION}-win-x64.zip"
NODE_ZIP_SHA256 = "e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f"
NODE_BASE_URL = f"https://nodejs.org/dist/{NODE_VERSION}/"
REA_VERSION = "6.10.1"
# zip 안 node.exe의 sha256. 이미 깔린 node.exe가 이 값과 다르면 버전 글이 같아도 다시 깔지 않고 멈춘다
NODE_EXE_SHA256 = "86fc4785327db5f5c7558dc6156c543b433c313e813a222e088086222ab4afa6"
# 다시 쓸 때 맞춰 보는 실행 파일 두 개(npm·REA 진입점)의 sha256. 폴더 전체 해시는 이 PC에서 node 62초,
# rea node_modules 328초가 걸려(2026-11-22 잼) 매번 돌리기엔 길다 — 진입점 해시 + lock 파일이 같은지로 대신한다
NPM_CLI_SHA256 = "3ce7cba6f5128dd5f54c98b6a5036b0f850496878cc2e21044b675fe3c594e3e"
REA_MJS_SHA256 = "029dbe9918c9af46f724915f255c94712b53afb8707a829fea35527a4d6a5576"
ALLOWED_URL_PREFIX = "https://nodejs.org/dist/"

# 받는 크기 상한(바이트). zip은 고정 크기와 정확히 같아야 하고, SHASUMS256.txt(3,171바이트)는 64KB 안이어야 한다
NODE_ZIP_BYTES = 37_762_649
SHASUMS_MAX_BYTES = 64 * 1024
# 시간 상한(초). 근거: 이 PC에서 zip 받기는 몇 초, npm ci는 237초·348초(2026-11-21 두 번 잼).
# 소켓 한 번 읽기 60초(서버가 멈춘 것으로 본다), 받기 전체 600초(38MB를 약 0.5Mbps에서도 받는 시간),
# npm ci 1,800초(잰 가장 긴 값의 약 5배 — 느린 날 멈추지 않으면서 무한정 기다리지 않게). 모두 추정이고,
# 넘으면 멈추고 다시 돌리면 된다(이미 맞는 단계는 건너뛴다)
SOCKET_TIMEOUT_S = 60
DOWNLOAD_DEADLINE_S = 600
NPM_TIMEOUT_S = 1800
VERSION_TIMEOUT_S = 60
CHUNK = 1 << 20

# npm·node에 넘기는 환경 변수 허용 목록. 토큰·키가 든 변수(NPM_TOKEN, GITHUB_TOKEN 등)가 섞이지 않게 한다
ENV_PASS = (
    "SystemRoot",
    "SystemDrive",
    "windir",
    "ComSpec",
    "PATHEXT",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
)


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """리디렉트도 허용 주소(nodejs.org/dist) 안으로만 따라간다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not newurl.startswith(ALLOWED_URL_PREFIX):
            raise SystemExit(f"허용 주소 밖으로 리디렉트: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_CheckedRedirect)


def download(url: str, dest: Path, max_bytes: int, exact: bool) -> None:
    """허용 주소에서 max_bytes까지만 받는다. exact면 크기가 정확히 같아야 한다. 전체 시간도 막는다."""
    if not url.startswith(ALLOWED_URL_PREFIX):
        raise SystemExit(f"허용하지 않은 주소: {url}")
    deadline = time.monotonic() + DOWNLOAD_DEADLINE_S
    got = 0
    with _OPENER.open(url, timeout=SOCKET_TIMEOUT_S) as resp, dest.open("wb") as out:
        if not resp.geturl().startswith(ALLOWED_URL_PREFIX):
            raise SystemExit(f"허용 주소 밖에서 받음: {resp.geturl()}")
        length = resp.headers.get("Content-Length")
        if length is not None and (int(length) > max_bytes or (exact and int(length) != max_bytes)):
            raise SystemExit(f"받을 크기가 예상과 다릅니다: {length}바이트 (예상 {max_bytes})")
        while block := resp.read(CHUNK):
            got += len(block)
            if got > max_bytes:
                raise SystemExit(f"받는 크기가 상한 {max_bytes}바이트를 넘었습니다")
            if time.monotonic() > deadline:
                raise SystemExit(f"받기가 {DOWNLOAD_DEADLINE_S}초를 넘었습니다")
            out.write(block)
    if exact and got != max_bytes:
        raise SystemExit(f"받은 크기 {got}바이트가 예상 {max_bytes}바이트와 다릅니다")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def shasums_value(shasums: Path, name: str) -> str:
    for line in shasums.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name:
            return parts[0].lower()
    raise SystemExit(f"SHASUMS256.txt에 {name}이 없습니다")


def extract(zip_path: Path, dest: Path) -> None:
    top = f"node-{NODE_VERSION}-win-x64/"
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.filename.startswith(top):
                raise SystemExit(f"예상 밖 항목: {info.filename}")
            rel = info.filename[len(top):]
            if not rel:
                continue
            out = (dest / rel).resolve()
            if dest_resolved not in out.parents:
                raise SystemExit(f"폴더 밖으로 나가는 항목: {info.filename}")
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)


def run_version(cmd: list[str], env: dict[str, str]) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=VERSION_TIMEOUT_S, env=env, check=False)  # noqa: S603
    return done.stdout.strip() if done.returncode == 0 else ""


def setup_node(tools: Path, env: dict[str, str]) -> Path:
    node_dir = tools / "node"
    node = node_dir / "node.exe"
    if node.is_file():
        npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if sha256_of(node) != NODE_EXE_SHA256 or not npm_cli.is_file() or sha256_of(npm_cli) != NPM_CLI_SHA256:
            raise SystemExit(f"{node_dir}의 node.exe·npm-cli.js sha256이 고정값과 다릅니다. 폴더를 지우고 다시 돌리세요")
        if run_version([str(node), "--version"], env) == NODE_VERSION:
            print(f"Node {NODE_VERSION}: 이미 있음 (node.exe sha256 일치)")
            return node_dir
    if node_dir.exists():
        raise SystemExit(f"{node_dir}에 다른 것이 있습니다. 지우고 다시 돌리세요")
    work = Path(tempfile.mkdtemp(prefix="node-dl-"))
    try:
        zip_path, shasums = work / NODE_ZIP, work / "SHASUMS256.txt"
        download(NODE_BASE_URL + "SHASUMS256.txt", shasums, SHASUMS_MAX_BYTES, exact=False)
        download(NODE_BASE_URL + NODE_ZIP, zip_path, NODE_ZIP_BYTES, exact=True)
        actual = sha256_of(zip_path)
        listed = shasums_value(shasums, NODE_ZIP)
        if not (actual == listed == NODE_ZIP_SHA256):
            raise SystemExit(f"sha256 불일치: 받은 것 {actual}, SHASUMS {listed}, 고정 {NODE_ZIP_SHA256}")
        extract(zip_path, node_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if sha256_of(node) != NODE_EXE_SHA256 or run_version([str(node), "--version"], env) != NODE_VERSION:
        raise SystemExit("풀었지만 node.exe의 sha256이나 버전이 맞지 않습니다")
    print(f"Node {NODE_VERSION}: 설치함 (sha256 {NODE_ZIP_SHA256})")
    return node_dir


def setup_rea(tools: Path, node_dir: Path, env: dict[str, str]) -> None:
    rea_dir = tools / "rea"
    rea_mjs = rea_dir / "node_modules" / "rea-agents" / "scripts" / "rea.mjs"
    node = str(node_dir / "node.exe")
    if rea_mjs.is_file():
        same_lock = all(
            (rea_dir / name).is_file() and (rea_dir / name).read_bytes() == (PINNED_DIR / name).read_bytes()
            for name in ("package.json", "package-lock.json")
        )
        if same_lock and sha256_of(rea_mjs) == REA_MJS_SHA256 and run_version([node, str(rea_mjs), "--version"], env) == REA_VERSION:
            print(f"rea-agents {REA_VERSION}: 이미 있음 (lock·rea.mjs sha256 일치)")
            return
        print("rea-agents: lock이나 rea.mjs가 고정값과 달라 npm ci로 다시 깝니다")
    rea_dir.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(PINNED_DIR / name, rea_dir / name)
    npm_cli = node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
    cmd = [node, str(npm_cli), "ci", "--prefix", str(rea_dir), "--ignore-scripts", "--no-audit", "--no-fund"]
    subprocess.run(cmd, env=env, timeout=NPM_TIMEOUT_S, check=True)  # noqa: S603
    got = run_version([node, str(rea_mjs), "--version"], env)
    if got != REA_VERSION:
        raise SystemExit(f"rea --version이 {got!r}입니다 (고정 {REA_VERSION})")
    print(f"rea-agents {REA_VERSION}: 설치함 → {rea_mjs}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools-dir", default=str(ROOT / ".tools"))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    tools = Path(args.tools_dir).resolve()
    tools.mkdir(parents=True, exist_ok=True)
    npmrc = tools / "npmrc-empty"
    npmrc.write_text("", encoding="utf-8")
    env = {k: os.environ[k] for k in ENV_PASS if k in os.environ}
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.pathsep.join([str(tools / "node"), str(Path(system_root) / "System32"), system_root])
    env["NPM_CONFIG_USERCONFIG"] = str(npmrc)
    env["NPM_CONFIG_CACHE"] = str(tools / "npm-cache")
    env["NPM_CONFIG_UPDATE_NOTIFIER"] = "false"
    node_dir = setup_node(tools, env)
    setup_rea(tools, node_dir, env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
