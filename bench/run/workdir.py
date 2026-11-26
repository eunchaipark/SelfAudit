"""F-R02 실행 폴더: 저장소 밖 폴더·대상 복사·시작 전 확인·settings·mcp.json·치우기 (실험구조 3.2).

실행 폴더 맨 위는 홈 밖 `%SystemDrive%\\SelfAudit-bench-runs`다(실험구조 8.9 1 — 홈 아래면 위쪽에
사용자의 `~/.claude`가 있어 ㉢이 늘 멈춘다). 드라이브 맨 위에 새로 만든 폴더는 다른 사용자도 고칠 수
있게 권한을 물려받으므로, 맨 위는 이 사용자·SYSTEM·Administrators만 닿는 권한으로 만들고 이미 있으면
그 권한을 허용 꼴과 맞춘다.

이 모듈은 실험 전용 설정 폴더에서 `settings.json` 하나만 쓴다. 그 폴더의 다른 파일(로그인 정보
`.credentials.json` 등)은 열지도, 목록을 읽지도, 옮기지도 않는다(F-R02 7).
"""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import json
import ntpath
import os
import re
import shutil
import stat
from collections.abc import Iterable, Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from common.contracts import Json, read_contract, read_json
from common.fingerprint import ManifestError, bundle_manifest_sha256, format_manifest
from run.plan import Target

__all__ = [
    "DENY_TOOLS",
    "EMPTY_MANIFEST_SHA256",
    "BatchStop",
    "BenchPlaces",
    "McpConfig",
    "PreparedRun",
    "RunDir",
    "check_batch_only",
    "check_manifest",
    "check_no_claude_upward",
    "check_no_reparse",
    "copy_bundle",
    "create_run_dir",
    "deny_rule_forms",
    "deny_rules",
    "ensure_runs_root",
    "expected_manifest",
    "is_inside",
    "prepare_run",
    "remove_run_dir",
    "write_mcp_config",
    "write_settings",
]

RUNS_DIR_NAME: Final = "SelfAudit-bench-runs"
CONFIG_DIR_NAME: Final = "SelfAudit-bench-claude"
PRIVATE_DIR_NAME: Final = "SelfAudit-private"
ARCHIVE_DIR_NAME: Final = "SelfAudit-bench-archive"
TARGET_DIR_NAME: Final = "target"
SETTINGS_NAME: Final = "settings.json"
MCP_NAME: Final = "mcp.json"
DENY_TOOLS: Final = ("Read", "Grep", "Glob")
# F-R06 2: 빈 실행의 지문 = 빈 목록을 이은 빈 글의 sha256 (폴더를 읽지 않는다, 실험구조 8.5 2)
EMPTY_MANIFEST_SHA256: Final = hashlib.sha256("".join(format_manifest({})).encode()).hexdigest()
# F-R02 2㉢ — Claude Code가 작업 폴더 위쪽에서 읽는 지시·설정 파일 이름(대소문자는 NTFS가 무시)
UPWARD_MARKERS: Final = ("CLAUDE.md", "CLAUDE.local.md", ".claude")
TEMPLATE_DIR: Final = Path(__file__).resolve().parent
_BATCH_ID: Final = re.compile(r"[0-9]{8}-[0-9]{4}-[a-z0-9]{4,12}")
_RUN_ID: Final = re.compile(r"[a-z0-9][a-z0-9-]{3,79}")
_DRIVE_ABS: Final = re.compile(r"[A-Za-z]:\\")
_SYSTEM_DRIVE: Final = re.compile(r"[A-Za-z]:")
# 실행 폴더 맨 위 권한의 허용 꼴(SDDL): 소유자는 이 사용자나 Administrators,
# DACL은 물려받지 않음(P), 허용 항목은 SYSTEM·Administrators·소유자 권한(OW)·이 사용자뿐.
# 거부 항목은 막기만 하므로 받는다
_SDDL: Final = re.compile(r"O:(?P<owner>[^:()]+)D:(?P<flags>[A-Z]*)(?P<aces>(?:\([^()]*\))*)")
_ACE: Final = re.compile(r"\(([^;()]*);[^()]*;([^;()]*)\)")
_TRUSTED_SIDS: Final = frozenset({"SY", "BA", "OW"})
_PRIVATE_DIR_MODE: Final = (
    0o700  # 파이썬 3.13+ Windows: 이 값이면 이 사용자·관리자만 닿는 DACL로 만든다
)
# 권한 규칙 글에서 뜻을 갖는 글자(글롭·괄호). 경로에 있으면 규칙이 다른 곳을 가리키므로 멈춘다
_RULE_SPECIAL: Final = frozenset("*?[]{}()!")
_PLACEHOLDERS: Final = ("<PYTHON>", "<ROOT>", "<RUN>")
_LEFTOVER_PLACEHOLDER: Final = re.compile(r"<[A-Z_]+>")
_REPO_KINDS: Final = frozenset({"planted", "practice"})


class BatchStop(RuntimeError):
    """F-R02 예외: 시작 전 확인이 어긋남 → 그 배치를 멈춘다. `rule`은 규칙 번호(㉠ 등).

    글에는 무엇이 어긋났는지만 싣는다(비밀값·로그인 정보·사용자 홈 경로를 싣지 않는다).
    """

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"배치 멈춤 [{rule}] {detail}")


@dataclass(frozen=True)
class BenchPlaces:
    """저장소 밖 맨 위 폴더들.

    실행 폴더·설정·내 앱 원자료·보관이 서로 다른 맨 위 폴더다(지도 '기술'). 실행 폴더만 홈 밖
    `runs_parent`(실제로는 `%SystemDrive%\\`) 아래이고, 나머지는 `%LOCALAPPDATA%` 아래다.
    """

    repo_root: Path
    local_app_data: Path
    user_profile: Path
    runs_parent: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str], repo_root: Path) -> BenchPlaces:
        by_upper = {k.upper(): v for k, v in env.items()}
        local, home = by_upper.get("LOCALAPPDATA", ""), by_upper.get("USERPROFILE", "")
        drive = by_upper.get("SYSTEMDRIVE", "")
        if not (_DRIVE_ABS.match(local) and _DRIVE_ABS.match(home)):
            raise BatchStop("환경", "LOCALAPPDATA·USERPROFILE가 드라이브 절대 경로가 아님")
        if not _SYSTEM_DRIVE.fullmatch(drive):
            raise BatchStop("환경", "SystemDrive가 드라이브 글자(C:) 꼴이 아님")
        return cls(
            repo_root=repo_root,
            local_app_data=Path(local),
            user_profile=Path(home),
            runs_parent=Path(drive + "\\"),
        )

    @property
    def runs_root(self) -> Path:
        return self.runs_parent / RUNS_DIR_NAME

    @property
    def config_dir(self) -> Path:
        return self.local_app_data / CONFIG_DIR_NAME

    @property
    def private_dir(self) -> Path:
        return self.local_app_data / PRIVATE_DIR_NAME

    @property
    def archive_dir(self) -> Path:
        return self.local_app_data / ARCHIVE_DIR_NAME


@dataclass(frozen=True)
class RunDir:
    batch_dir: Path
    run_dir: Path
    target: Path


@dataclass(frozen=True)
class McpConfig:
    path: Path
    data: bytes  # 실행 폴더에 쓴 바이트(`<RUN>`이 풀려 있어 실행마다 다르다)
    template_sha256: str  # 틀(`bench/run/mcp-A.json`·`mcp-B.json`) 바이트의 sha256 — 조건마다 같다


@dataclass(frozen=True)
class PreparedRun:
    run: RunDir
    mcp: McpConfig
    settings_path: Path
    manifest_sha256: str


# --- 실행 폴더 -------------------------------------------------------------------------------


def create_run_dir(places: BenchPlaces, batch_id: str, run_id: str) -> RunDir:
    """F-R02 1: `%SystemDrive%\\SelfAudit-bench-runs\\<배치 ID>\\<실행 ID>\\target\\`를 만든다.

    맨 위(권한)와 배치 폴더(재분석 지점)를 **만들기 전에** 보고, 만든 뒤 ㉣까지 본다.
    """
    if not (_BATCH_ID.fullmatch(batch_id) and _RUN_ID.fullmatch(run_id)):
        raise BatchStop("1", "배치 ID·실행 ID 꼴이 아님")
    root = places.runs_root
    if is_inside(root, places.repo_root):
        raise BatchStop("1", "실행 폴더가 저장소 안")
    ensure_runs_root(root)
    batch_dir = root / batch_id
    run_dir = batch_dir / run_id
    if os.path.lexists(batch_dir):
        if _is_reparse(batch_dir) or not batch_dir.is_dir():
            raise BatchStop("1", f"{batch_dir.name}가 재분석 지점(정션·링크)이거나 폴더가 아님")
    else:
        batch_dir.mkdir()
    try:
        run_dir.mkdir()
    except FileExistsError:
        raise BatchStop("㉣", "이 실행의 폴더가 이미 있음") from None
    target = run_dir / TARGET_DIR_NAME
    target.mkdir()
    run = RunDir(batch_dir=batch_dir, run_dir=run_dir, target=target)
    check_batch_only(run)
    return run


def ensure_runs_root(root: Path) -> None:
    """F-R02 1: 실행 폴더 맨 위를 이 사용자만 닿는 권한으로 만들거나, 이미 있으면 그 권한을 본다.

    드라이브 맨 위(`C:\\`)는 로그인한 누구나 폴더를 만들 수 있고, 거기 만든 폴더는 '로그인한
    사용자: 수정'을 물려받는다. 그대로 두면 다른 사용자가 복사본을 바꾸거나(㉡ 뒤), 맨 위를 먼저
    만들어 두거나 정션으로 바꿔 둘 수 있다. 그래서 만들 때는 물려받지 않는 권한(`mode=0o700`,
    파이썬 3.13+)으로 한 번에 만들고, 있으면 허용 꼴(`_SDDL`·`_TRUSTED_SIDS`)과 맞지 않을 때
    멈춘다(고치지 않는다).

    부모(드라이브 맨 위)의 DACL은 보지 않는다 — 가정: 관리자가 아닌 살아 있는 계정에 드라이브 맨
    위의 '아래 지우기'·모든 권한·권한 바꾸기가 없다(그 항목은 관리자만 넣을 수 있고 이 PC의 관리자는
    사용자 자신이다, 실험구조 8.10 3).
    """
    with contextlib.suppress(FileExistsError):
        os.mkdir(root, _PRIVATE_DIR_MODE)
    if _is_reparse(root) or not root.is_dir():
        raise BatchStop("1", f"{root.name}가 재분석 지점(정션·링크)이거나 폴더가 아님")
    if not _owner_only_acl(_security_sddl(root), _current_user_sid()):
        raise BatchStop(
            "1",
            f"{root.name} 권한이 이 사용자·SYSTEM·Administrators만이 아님"
            " (실행기가 만든 폴더가 아니면 지우고 다시 돌린다)",
        )


def _owner_only_acl(sddl: str, user_sid: str) -> bool:
    """SDDL이 허용 꼴인가.

    소유자가 이 사용자·Administrators, DACL 보호(P), 허용 항목은 믿는 SID만.
    """
    match = _SDDL.fullmatch(sddl)
    if match is None or "P" not in match["flags"]:
        return False
    trusted = _TRUSTED_SIDS | {user_sid}
    if match["owner"] not in {user_sid, "BA"}:
        return False
    for kind, sid in _ACE.findall(match["aces"]):
        if kind == "D":
            continue
        if kind != "A" or sid not in trusted:
            return False
    return True


_OWNER_SECURITY_INFORMATION: Final = 0x1
_DACL_SECURITY_INFORMATION: Final = 0x4
_SE_FILE_OBJECT: Final = 1
_SDDL_REVISION_1: Final = 1
_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER: Final = 1


def _security_sddl(path: Path) -> str:
    """폴더의 소유자와 DACL을 SDDL 글로(`GetNamedSecurityInfoW`). 못 읽으면 멈춘다."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    info = _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION
    descriptor = ctypes.c_void_p()
    owner, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    code = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        info,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if code != 0:
        raise BatchStop("1", f"실행 폴더 맨 위 권한을 읽을 수 없음 (Win32 {code})")
    try:
        text = wintypes.LPWSTR()
        ok = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, _SDDL_REVISION_1, info, ctypes.byref(text), None
        )
        if not ok:
            raise BatchStop("1", f"권한을 글로 바꿀 수 없음 (Win32 {ctypes.get_last_error()})")
        try:
            return str(text.value)
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.LocalFree(descriptor)


def _current_user_sid() -> str:
    """이 프로세스 사용자의 SID 글(`S-1-5-21-…`). 경로·이름이 아니라 SID로 견준다."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.ConvertSidToStringSidW.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise BatchStop("1", "프로세스 토큰을 열 수 없음")
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buffer, size, ctypes.byref(size)):
            raise BatchStop("1", "사용자 SID를 읽을 수 없음")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER.User.Sid
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise BatchStop("1", "SID를 글로 바꿀 수 없음")
        try:
            return str(text.value)
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.CloseHandle(token)


def copy_bundle(source: Path, target: Path) -> None:
    """F-R02 1: 번들을 **파일만** 복사한다.

    정션·심볼릭 링크(재분석 지점)는 따라가지도 복사하지도 않는다.
    """
    if not source.is_dir():
        raise BatchStop("1", "대상 번들 폴더가 없음")

    def walk_failed(error: OSError) -> None:
        # os.walk는 못 읽은 폴더를 조용히 건너뛴다. 건너뛰면 복사본이 원본과 다르다
        raise BatchStop("1", f"번들 폴더를 읽을 수 없음 ({type(error).__name__})") from error

    for current, dirnames, filenames in os.walk(source, onerror=walk_failed):
        base = Path(current)
        dirnames[:] = [d for d in dirnames if not _is_reparse(base / d)]
        dest = target.joinpath(base.relative_to(source))
        dest.mkdir(exist_ok=True)
        for name in filenames:
            path = base / name
            if _is_reparse(path) or not path.is_file():
                continue
            shutil.copyfile(path, dest / name, follow_symlinks=False)


def expected_manifest(target: Target) -> str:
    """F-R02 2㉡의 기준 지문.

    저장소 대상(planted·practice)은 정답지의 `bundle_manifest_sha256`이고 정답지 `origin`이 목록
    종류와 같아야 한다(F-B05 4). 내 앱은 **대상 목록에 적힌 지문**이다(실험구조 8.9 2 — 복사 전
    원본 폴더의 지문은 배치 도중 원본이 다시 빌드되어도 늘 '같음'이라 A·B가 같은 대상을 봤다는
    보장이 안 된다). 내 앱에 정답지도 있으면 두 지문이 같아야 한다.
    """
    listed = target.manifest_sha256
    if target.kind not in _REPO_KINDS and listed is None:
        raise BatchStop("㉡", "내 앱 대상 목록에 지문 칸이 없음")
    if target.answers is None:
        if listed is None:
            raise BatchStop("㉡", "기준 지문이 없음(정답지도 목록의 지문 칸도 없음)")
        return listed
    answers = read_contract("answers", target.answers)
    if target.kind in _REPO_KINDS and answers.get("origin") != target.kind:
        raise BatchStop("㉡", "정답지 origin이 대상 목록 종류와 다름")
    digest = answers.get("bundle_manifest_sha256")
    assert isinstance(digest, str)  # 계약의 필수 칸
    if listed is not None and listed != digest:
        raise BatchStop("㉡", "대상 목록의 지문과 정답지의 지문이 다름")
    return digest


# --- 시작 전 확인 (F-R02 2) ------------------------------------------------------------------


def check_no_reparse(target: Path) -> None:
    """㉠ `target` 아래에 재분석 지점(정션·심볼릭 링크 등)이 없다."""

    def walk_failed(error: OSError) -> None:
        raise BatchStop("㉠", f"target을 읽을 수 없음 ({type(error).__name__})") from error

    for current, dirnames, filenames in os.walk(target, onerror=walk_failed):
        base = Path(current)
        for name in (*dirnames, *filenames):
            if _is_reparse(base / name):
                rel = (base / name).relative_to(target).as_posix()
                raise BatchStop("㉠", f"target 안 재분석 지점: {rel!r}")


def check_manifest(target: Path, expected: str) -> None:
    """㉡ `target`의 지문(F-B04)이 기준 지문과 같다.

    빈 실행(기준이 빈 목록 지문)은 빈 폴더여야 한다.
    """
    if expected == EMPTY_MANIFEST_SHA256:
        if any(target.iterdir()):
            raise BatchStop("㉡", "빈 실행의 target이 비어 있지 않음")
        return
    if _manifest_or_stop(target, "복사본") != expected:
        raise BatchStop("㉡", "복사한 target의 지문이 기준 지문과 다름")


def check_no_claude_upward(target: Path) -> None:
    """㉢ `target`부터 위쪽 폴더 어디에도 `CLAUDE.md`·`CLAUDE.local.md`·`.claude`가 없다.

    파일·폴더·깨진 링크 모두 걸린다. 적힌 경로와 realpath로 푼 경로의 위쪽을 **둘 다** 본다 — 위쪽에
    정션이 있으면 Claude Code가 어느 쪽으로 올라가 읽는지 알 수 없어서다.
    """
    chains = {"": Path(os.path.abspath(target)), "푼 경로 ": Path(os.path.realpath(target))}
    for label, start in chains.items():
        for depth, folder in enumerate((start, *start.parents)):
            for name in UPWARD_MARKERS:
                if os.path.lexists(folder / name):
                    # 홈 아래 경로에는 사용자 이름이 있다 — 몇 단계 위인지만 알린다
                    raise BatchStop("㉢", f"target {label}위로 {depth}단계 폴더에 {name}가 있음")


def check_batch_only(run: RunDir) -> None:
    """㉣ 배치 폴더 안에 이 실행의 폴더만 있다(치우지 못한 지난 실행이 남으면 멈춘다)."""
    others = sum(1 for p in run.batch_dir.iterdir() if p.name != run.run_dir.name)
    if others:
        # 개수만 싣는다 — 남은 폴더 이름은 실행 ID라 내 앱 실행이면 `mine-<대상 ID>`가 샌다
        raise BatchStop("㉣", f"배치 폴더에 다른 것이 {others}개 남음")


# --- settings.json (F-R02 3) ----------------------------------------------------------------


def deny_rule_forms(path: Path) -> tuple[str, str]:
    """거절 규칙 경로의 두 꼴 `//C:/…/**`와 `//c/…/**`. 어느 쪽이 먹히는지는 F-R10이 꼴마다 잰다."""
    text = ntpath.normpath(str(path))
    if not _DRIVE_ABS.match(text):
        raise BatchStop("3", "거절할 경로가 드라이브 절대 경로가 아님")
    if any(ch in _RULE_SPECIAL for ch in text):
        raise BatchStop("3", "거절할 경로에 규칙에서 뜻을 갖는 글자(글롭·괄호)가 있음")
    posix = text.replace("\\", "/").rstrip("/")
    drive, rest = posix[0], posix[2:]
    return f"//{drive.upper()}:{rest}/**", f"//{drive.lower()}{rest}/**"


def deny_rules(paths: Iterable[Path]) -> list[str]:
    """경로마다 `Read`·`Grep`·`Glob` 세 도구 × 두 꼴. 같은 규칙은 한 번만."""
    rules: list[str] = []
    for path in paths:
        forms = deny_rule_forms(path)
        rules += [f"{tool}({form})" for tool in DENY_TOOLS for form in forms]
    return list(dict.fromkeys(rules))


def deny_paths(places: BenchPlaces, run: RunDir, extra: Sequence[Path] = ()) -> list[Path]:
    """F-R02 3 거절할 곳: 설정 폴더 자신·내 앱 원자료·보관·저장소·`~/.claude`·`~/.ssh`·
    형제 실행 폴더.

    `SelfAudit-bench-runs` 맨 위는 넣지 않는다(거절이 허용보다 앞서 자기 target까지 막는다).
    `extra`는 문지기(F-R10 3)가 미끼 폴더를 같은 함수·같은 꼴로 더하는 자리다.
    """
    siblings = sorted(p for p in run.batch_dir.iterdir() if p.name != run.run_dir.name)
    return [
        places.config_dir,
        places.private_dir,
        places.archive_dir,
        places.repo_root,
        places.user_profile / ".claude",
        places.user_profile / ".ssh",
        *siblings,
        *extra,
    ]


def write_settings(places: BenchPlaces, run: RunDir, extra_deny: Sequence[Path] = ()) -> Path:
    """F-R02 3: 실험 전용 설정 폴더의 `settings.json`을 **실행마다** 같은 틀로 다시 쓴다."""
    rules = deny_rules(deny_paths(places, run, extra_deny))
    # 훅 없음·플러그인 없음 (칸 이름은 Claude Code 설정 꼴, 추정 — 첫 보정 실행의 init 줄에서 확인)
    settings = {"hooks": {}, "enabledPlugins": {}, "permissions": {"deny": rules}}
    config = places.config_dir
    config.mkdir(parents=True, exist_ok=True)
    if _is_reparse(config):
        raise BatchStop("3", "설정 폴더가 재분석 지점(정션·링크)")
    path = config / SETTINGS_NAME
    tmp = config / (SETTINGS_NAME + ".tmp")
    tmp.write_bytes(_json_bytes(settings))
    os.replace(tmp, path)
    return path


# --- mcp.json (F-R02 4) ---------------------------------------------------------------------


def write_mcp_config(run: RunDir, condition: str, python_exe: Path, repo_root: Path) -> McpConfig:
    """F-R02 4: 조건의 틀을 풀어 `mcp.json`으로 쓴다.

    `mcp-A.json` = 빈 서버, `mcp-B.json` = REA 하나(거르개를 거침).
    """
    if condition not in ("A", "B"):
        raise BatchStop("4", "조건이 A·B 밖")
    if not python_exe.is_absolute():
        raise BatchStop("4", "파이썬 경로가 절대 경로가 아님")
    template = TEMPLATE_DIR / f"mcp-{condition}.json"
    raw = template.read_bytes()
    values = {"<PYTHON>": str(python_exe), "<ROOT>": str(repo_root), "<RUN>": str(run.run_dir)}
    filled = _fill(read_json(template), values)
    data = _json_bytes(filled)
    if _LEFTOVER_PLACEHOLDER.search(data.decode("utf-8")):
        raise BatchStop("4", "MCP 설정 틀에 풀지 못한 자리 표시가 남음")
    path = run.run_dir / MCP_NAME
    with path.open("xb") as f:
        f.write(data)
    return McpConfig(path=path, data=data, template_sha256=hashlib.sha256(raw).hexdigest())


def _fill(value: Json, values: Mapping[str, str]) -> Json:
    if isinstance(value, str):
        for key in _PLACEHOLDERS:
            value = value.replace(key, values[key])
        return value
    if isinstance(value, list):
        return [_fill(v, values) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, values) for k, v in value.items()}
    return value


# --- 한 번에 / 치우기 ------------------------------------------------------------------------


def prepare_run(
    places: BenchPlaces,
    batch_id: str,
    run_id: str,
    *,
    source: Path | None,
    expected: str,
    condition: str,
    python_exe: Path,
    extra_deny: Sequence[Path] = (),
) -> PreparedRun:
    """F-R02 1~4를 차례로: 폴더 → 복사(빈 실행은 `source=None`) → ㉠~㉣ → settings.json → mcp.json.

    확인이 어긋나면 `BatchStop`. 실행 폴더는 지우지 않고 남긴다(무엇이 어긋났는지 사람이 본다).
    """
    run = create_run_dir(places, batch_id, run_id)
    if source is not None:
        copy_bundle(source, run.target)
    check_no_reparse(run.target)
    check_manifest(run.target, expected)
    check_no_claude_upward(run.target)
    check_batch_only(run)
    settings = write_settings(places, run, extra_deny)
    mcp = write_mcp_config(run, condition, python_exe, places.repo_root)
    return PreparedRun(run=run, mcp=mcp, settings_path=settings, manifest_sha256=expected)


def remove_run_dir(places: BenchPlaces, run: RunDir) -> None:
    """F-R02 6: 원자료를 옮긴 뒤 실행 폴더 전체를 지운다.

    링크가 아닌 실제 폴더이고 자리가 맞을 때만 지운다.

    지우지 못하면 `OSError`가 그대로 올라간다 — 다음 실행의 ㉣이 남은 폴더를 보고 멈춘다.
    """
    expected = places.runs_root / run.batch_dir.name / run.run_dir.name
    if _norm(run.run_dir) != _norm(expected) or _is_reparse(run.run_dir):
        raise BatchStop("6", "지울 실행 폴더의 자리가 맞지 않거나 재분석 지점")
    if _norm(Path(os.path.realpath(run.run_dir)).parent) != _norm(
        Path(os.path.realpath(places.runs_root / run.batch_dir.name))
    ):
        raise BatchStop("6", "실행 폴더를 풀어 보니 배치 폴더 밖")
    shutil.rmtree(run.run_dir)


# --- 도움 함수 -------------------------------------------------------------------------------


def _manifest_or_stop(folder: Path, what: str) -> str:
    try:
        return bundle_manifest_sha256(folder)
    except ManifestError as e:
        raise BatchStop("㉡", f"{what} 지문을 낼 수 없음: {e}") from None


def _is_reparse(path: Path) -> bool:
    try:
        attrs = os.lstat(path).st_file_attributes
    except OSError:
        return True  # 볼 수 없는 것은 링크로 친다(실패하면 안전한 쪽 — 복사하지 않고, 확인은 멈춤)
    return (
        bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT) or path.is_symlink() or path.is_junction()
    )


def _norm(path: Path) -> str:
    return ntpath.normcase(ntpath.normpath(str(path)))


def is_inside(path: Path, root: Path) -> bool:
    """`path`를 realpath로 푼 것이 `root`를 푼 것과 같거나 그 아래."""
    p = _norm(Path(os.path.realpath(path)))
    r = _norm(Path(os.path.realpath(root)))
    return p == r or p.startswith(r.rstrip("\\") + "\\")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
