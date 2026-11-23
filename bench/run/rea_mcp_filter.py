"""F-R04 MCP 거르개 (R4, 조건 B): Claude Code ↔ REA 사이 stdio JSON-RPC를 허용 꼴만 통과시킨다.

쓰는 법 (`bench/run/mcp-B.json`의 틀. 실행기 F-R02가 `<…>`를 그 실행의 값으로 바꿔
`mcp.json`에 쓴다):
    <bench 파이썬> -I rea_mcp_filter.py --allow <도구,…> --target <실행 폴더>\\target
        --netguard-log <실행 폴더>\\netguard.jsonl --env-dir <실행 폴더>\\rea-env
        -- <ROOT>\\.tools\\node\\node.exe <ROOT>\\.tools\\rea\\…\\rea.mjs mcp

하는 일 (기능명세 F-R04, docs/설계/REA환경.md 6절):
1. REA를 허용 목록 환경으로, 작업 폴더 = target으로 셸 없이 띄운다.
   ㉠(NODE_OPTIONS·REA_NETGUARD_LOG)을 넣고, 홈·APPDATA·LOCALAPPDATA·TEMP·TMP는
   `--env-dir` 아래 빈 폴더로 돌린다.
2. Claude Code → REA는 메서드 허용 목록만. REA가 거는 요청은 넘기지 않고 거르개가 오류로 답한다.
3. `initialize` 응답에서 tools 말고 다른 능력을 지우고, `tools/list` 응답은 매번 허용 도구만 남긴다.
4. 허용 밖 `tools/call`은 REA에 보내지 않는다.
5. 허용 도구의 인자를 거른다: 인자 이름 허용 목록, 경로 칸은 realpath로 푼 경로가 target 안일 때만
   푼 경로로 바꿔 보냄, source_paths는 input_path 안의 정규화한 상대 경로로, trace의 Evidence 칸은
   같은 세션 참조만, 나머지 모든 글은 경로 꼴이면 경로 칸 규칙을 통과해야 하고 펼침 꼴은 늘 거절.
6. 거절하면 Claude Code에 JSON-RPC 오류를 돌려주고 REA에는 아무것도 보내지 않는다.

검사한 메시지는 다시 직렬화해서 보낸다(받은 글을 그대로 넘기지 않는다):
검사한 값과 받는 쪽이 읽는 값이 같아야 해서다. 같은 키가 두 번 있는 꼴은
읽는 프로그램마다 다르게 읽을 수 있어 아예 거절한다.

표준 라이브러리만 쓰고 다른 bench 모듈을 import하지 않는다: `python -I`로 띄우면 스크립트 폴더가
sys.path에 들어가지 않는다. 오류·로그 글에는 받은 값을 싣지 않는다(위치와 규칙만, 보안코딩 '실험').
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final, NamedTuple

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None

ROOT: Final = Path(__file__).resolve().parents[2]
NETGUARD: Final = ROOT / "ops" / "scripts" / "rea_netguard.cjs"

# REA환경.md 6절 '조건 B에 허용하는 REA 도구' 표의 받는 인자 (D-041)
TOOL_ARGUMENTS: Final[Mapping[str, frozenset[str]]] = {
    "analyze_javascript_application": frozenset(
        {
            "input_path",
            "source_paths",
            "format",
            "integrity_policy",
            "semantic_precision",
            "max_semantic_nodes",
            "max_semantic_nodes_per_file",
            "max_semantic_unknowns",
            "max_semantic_unknowns_per_file",
            "max_heap_mb",
            "analysis_timeout_ms",
            "detail",
            "view",
        }
    ),
    "audit_release_exposure": frozenset({"path", "max_file_bytes"}),
    "trace_javascript_semantics": frozenset({"application", "query"}),
    "trace_application_feature": frozenset(
        {"application", "seed", "direction", "semantic_page", "view", "native_observations"}
    ),
}
# 경로 칸(②, 필수). 표에서 '경로, 필수'로 적힌 칸
PATH_FIELD: Final[Mapping[str, str]] = {
    "analyze_javascript_application": "input_path",
    "audit_release_exposure": "path",
}
SOURCE_PATHS_FIELD: Final = "source_paths"
# Evidence를 받는 칸(④). REA 6.10.1 계약에서 둘 다 evidenceInputSchema(인라인 Evidence 또는 참조)다
REFERENCE_FIELD: Final[Mapping[str, str]] = {
    "trace_javascript_semantics": "application",
    "trace_application_feature": "application",
}
REFERENCE_ARRAY_FIELD: Final[Mapping[str, str]] = {
    "trace_application_feature": "native_observations",
}
# 같은 세션 참조의 꼴: REA 6.10.1 `dist/domain/evidenceReference.js`의
# retainedEvidenceReferenceSchema: strictObject {kind: "retained-evidence",
# evidence_id: ev_ + 소문자 sha256 64자}
REFERENCE_KIND: Final = "retained-evidence"
EVIDENCE_ID: Final = re.compile(r"ev_[a-f0-9]{64}")

CLIENT_REQUESTS: Final = frozenset({"initialize", "ping", "tools/list", "tools/call"})
CLIENT_NOTIFICATIONS: Final = frozenset({"notifications/initialized", "notifications/cancelled"})
CALL_PARAMS: Final = frozenset({"name", "arguments", "_meta"})
KEPT_CAPABILITY: Final = "tools"
# initialize 응답에서 넘기는 키(MCP InitializeResult의 필수 키). instructions·_meta 등은 지운다
INITIALIZE_KEYS: Final = ("protocolVersion", "capabilities", "serverInfo")

# JSON-RPC 2.0 오류 코드. -32000은 구현이 정하는 서버 오류 범위의 첫 값(REA가 없거나 끝남)
PARSE_ERROR: Final = -32700
INVALID_REQUEST: Final = -32600
METHOD_NOT_FOUND: Final = -32601
INVALID_PARAMS: Final = -32602
INTERNAL_ERROR: Final = -32603
SERVER_ERROR: Final = -32000

# Claude Code가 보내는 한 줄의 상한과 깊이 상한: common.contracts.read_json과 같은 값(4 MiB, 64)
MAX_CLIENT_LINE_BYTES: Final = 4 * 1024 * 1024
MAX_DEPTH: Final = 64

# 환경: rea_smoke.py ENV_PASS와 같은 허용 목록(REA환경.md 6절 CLI 꼴)
ENV_PASS: Final = (
    "SystemRoot",
    "SystemDrive",
    "windir",
    "ComSpec",
    "PATHEXT",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)
HOME_VARS: Final = ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA")
TEMP_VARS: Final = ("TEMP", "TMP")
# mcp.json의 env로 받는 REA 설정(D-041 도구 묶음). 값은 그대로 넘긴다
PASS_THROUGH: Final = ("REA_MCP_TOOL_FAMILIES",)
# ㉢ 프록시(REA환경.md 4절): 프록시를 따르는 클라이언트를 닫힌 로컬 포트로 돌린다
PROXY_VARS: Final = ("HTTP_PROXY", "HTTPS_PROXY")
CLOSED_PROXY: Final = "http://127.0.0.1:9"

SEPARATORS: Final = "\\/"
VERBATIM_PREFIX: Final = "\\\\?\\"
DRIVE: Final = re.compile(r"[A-Za-z]:")
DRIVE_ABSOLUTE: Final = re.compile(r"[A-Za-z]:[\\/]")
FILE_URL: Final = "file:"
# 펼침 꼴(⑤): `%이름%`, `$이름`·`${이름}`·`$(…)`, `~`로 시작.
# 모두 앞에서 한 번만 훑는 꼴이라 입력 길이에 선형이다
PERCENT_VAR: Final = re.compile(r"%[^%]+%")
DOLLAR_VAR: Final = re.compile(r"\$[A-Za-z_{(]")
HOME_MARK: Final = "~"
QUOTES: Final = "\"'`"
SEGMENT: Final = re.compile(r"[^\\/]+")
# 글자 그대로를 맞춰 보는 칸: REA 6.10.1 스키마가 seed를 'Typed literal starting point …
# value is the literal text', query를 'feature or text query'로 적는다. 열어 보는 경로가
# 아니라 `/api/…` 같은 글이 정당하게 들어온다(fake_rea/rea-6.10.1-tools.json으로 시험이 확인)
LITERAL_TEXT_FIELDS: Final[Mapping[str, frozenset[str]]] = {
    "trace_application_feature": frozenset({"seed"}),
    "trace_javascript_semantics": frozenset({"query"}),
}
# REA를 놓아 둔 채 입력을 닫으면 0.065~0.072초 안에 스스로 끝났다(진짜 REA 6.10.1, 2026-11-23, 3번).
# 5초는 그 약 70배: 바쁜 PC에서도 스스로 끝날 틈을 주고, 넘으면 나무째 끝낸다. Claude Code가 떠난
# 뒤의 분석 결과는 쓸 곳이 없어 더 기다릴 까닭이 없고, 길면 실행기(F-R03)의 정리가 늦어진다
STOP_WAIT_S: Final = 5.0


class ConfigError(ValueError):
    """거르개 설정(명령줄)이 맞지 않아 띄우지 않는다."""


class Rejected(ValueError):
    """이 요청을 REA에 보내지 않고 오류로 답한다. 글에는 위치와 규칙만 담는다."""

    def __init__(self, code: int, rule: str) -> None:
        super().__init__(rule)
        self.code = code
        self.rule = rule


class Unreadable(ValueError):
    """JSON으로 읽을 수 없는 줄."""


@dataclass(frozen=True)
class Policy:
    """그 실행의 허용 도구와 realpath로 푼 target."""

    allow: frozenset[str]
    target: str


class Outgoing(NamedTuple):
    """보낼 곳(`client` = Claude Code, `rea`)과 보낼 메시지."""

    to: str
    message: dict[str, Json]


@dataclass(frozen=True)
class Config:
    policy: Policy
    netguard_log: str
    env_dir: Path
    command: list[str]


# ---------------------------------------------------------------- JSON 읽기·쓰기


def _unique_keys(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    result: dict[str, Json] = {}
    for key, value in pairs:
        if key in result:
            raise Unreadable("같은 키가 두 번 있음")
        result[key] = value
    return result


def _no_constant(_name: str) -> Json:
    raise Unreadable("NaN·Infinity는 JSON이 아님")


def _finite_float(text: str) -> float:
    value = float(text)
    if value in {float("inf"), float("-inf")}:
        raise Unreadable("범위를 넘는 수")
    return value


def _depth(value: Json) -> int:
    deepest = 0
    stack: list[tuple[Json, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        deepest = max(deepest, depth)
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return deepest


def parse_line(raw: bytes, max_depth: int | None) -> Json:
    """엄격한 JSON 한 줄(같은 키·NaN·무한·UTF-8 아님 거절). max_depth가 있으면 깊이도 본다."""
    try:
        text = raw.decode("utf-8")
        value: Json = json.loads(
            text,
            object_pairs_hook=_unique_keys,
            parse_constant=_no_constant,
            parse_float=_finite_float,
        )
    # ValueError: UTF-8 아님·JSON 아님·위 거절들, 그리고 4,300자리를 넘는 정수(int 변환 상한)
    except (ValueError, RecursionError) as error:
        raise Unreadable("JSON으로 읽을 수 없음") from error
    if max_depth is not None and _depth(value) > max_depth:
        raise Unreadable("깊이 상한을 넘음")
    return value


def dump_line(message: Mapping[str, Json]) -> bytes:
    text = json.dumps(message, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return text.encode("ascii") + b"\n"


def _error(msg_id: Json, code: int, message: str) -> dict[str, Json]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _log(rule: str) -> None:
    """stderr에 한 줄. 규칙·예외 이름만 싣고 받은 값은 싣지 않는다."""
    print(f"rea_mcp_filter: {rule}", file=sys.stderr, flush=True)


def _reply_id(message: Json) -> Json:
    msg_id = message.get("id") if isinstance(message, dict) else None
    return msg_id if _valid_id(msg_id) else None


def _valid_id(value: Json) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _id_key(value: Json) -> tuple[str, str]:
    return (type(value).__name__, str(value))


# ---------------------------------------------------------------- 거절 규칙 ("<칸>: <규칙>")

# 오류 글은 규칙 이름만 싣고 받은 값은 싣지 않는다. '없는 경로'와 '밖'을 같은 글로 두는 것은
# 오류 글로 target 밖 파일이 있는지 없는지가 드러나지 않게 하려고다(검증 T31 3)
RULE_NOT_TEXT: Final = "비어 있지 않은 글이어야 함"
RULE_VERBATIM: Final = "드라이브가 아닌 \\\\?\\ 경로"
RULE_NUL: Final = "NUL 글자"
RULE_UNC: Final = "UNC·장치 경로"
RULE_ROOT_RELATIVE: Final = "드라이브 없는 루트 기준 경로"
RULE_DRIVE_RELATIVE: Final = "드라이브 상대 경로"
RULE_FILE_URL: Final = "file: 주소"
RULE_ADS: Final = "드라이브 뒤의 ':'(ADS)"
RULE_NOT_INSIDE: Final = "target 안의 있는 경로가 아님"
RULE_EXPANSION: Final = "펼침 꼴(~·%이름%·$이름)"
RULE_NOT_ARRAY: Final = "비어 있지 않은 배열이어야 함"
RULE_SOURCE_SHAPE: Final = "input_path 기준 상대 경로가 아님"
RULE_INPUT_ITSELF: Final = "input_path 자신"
RULE_NOT_IN_INPUT: Final = "input_path 안의 있는 경로가 아님"
RULE_REFERENCE: Final = (
    f'같은 세션 참조만 받음 {{"kind": "{REFERENCE_KIND}", "evidence_id": "ev_…"}}'
)
RULE_REQUIRED: Final = "필수"
RULE_PARAMS: Final = "name·arguments·_meta만 받음"
RULE_TOOL: Final = "허용 밖 도구"
RULE_ARGUMENTS_OBJECT: Final = "객체여야 함"
RULE_ARGUMENT_NAME: Final = "인자 목록 밖의 인자"


def _reject(where: str, rule: str) -> Rejected:
    return Rejected(INVALID_PARAMS, f"{where}: {rule}")


# ---------------------------------------------------------------- 경로 칸 (②)


def is_within(path: str, root: str) -> bool:
    """normcase 뒤 root와 같거나 `root + "\\"`로 시작하는지."""
    folded, base = os.path.normcase(path), os.path.normcase(root)
    return folded == base or folded.startswith(base + "\\")


def _drive_letter(path: str) -> str:
    return os.path.splitdrive(path.removeprefix(VERBATIM_PREFIX))[0][:1].lower()


def _realpath(path: str, where: str, rule: str) -> str:
    try:
        return os.path.realpath(path, strict=True)
    except (OSError, ValueError) as error:
        raise _reject(where, rule) from error


def _strip_verbatim(value: str, where: str) -> str:
    """`\\\\?\\C:\\…`은 앞 4자를 떼고 본다. 그 밖의 `\\\\?\\` 꼴(UNC·GLOBALROOT·볼륨)은 거절."""
    if not value.startswith(VERBATIM_PREFIX):
        return value
    rest = value[len(VERBATIM_PREFIX) :]
    if not DRIVE_ABSOLUTE.match(rest):
        raise _reject(where, RULE_VERBATIM)
    return rest


def _check_path_shape(text: str, where: str) -> None:
    """② 허용 꼴: 드라이브 문자 절대 경로 또는 target 기준 상대 경로만."""
    if chr(0) in text:
        raise _reject(where, RULE_NUL)
    if text[:1] and text[0] in SEPARATORS:
        if text[1:2] and text[1] in SEPARATORS:
            raise _reject(where, RULE_UNC)
        raise _reject(where, RULE_ROOT_RELATIVE)
    drive_absolute = bool(DRIVE_ABSOLUTE.match(text))
    if DRIVE.match(text) and not drive_absolute:
        raise _reject(where, RULE_DRIVE_RELATIVE)
    if text[: len(FILE_URL)].lower() == FILE_URL:
        raise _reject(where, RULE_FILE_URL)
    if ":" in (text[2:] if drive_absolute else text):
        raise _reject(where, RULE_ADS)


def resolve_path_field(value: Json, where: str, target: str) -> str:
    """F-R04 5②. 허용 꼴이고 realpath로 푼 경로가 target 안이면 푼 경로를 돌려준다."""
    if not isinstance(value, str) or not value:
        raise _reject(where, RULE_NOT_TEXT)
    text = _strip_verbatim(value, where)
    _check_path_shape(text, where)
    if DRIVE_ABSOLUTE.match(text):
        # 다른 드라이브는 풀어 보지도 않는다: 네트워크 드라이브(`Z:\`)면 realpath가 연결을 연다
        if _drive_letter(text) != _drive_letter(target):
            raise _reject(where, RULE_NOT_INSIDE)
        joined = text
    else:
        joined = os.path.join(target, text)
    resolved = _realpath(joined, where, RULE_NOT_INSIDE)
    if not is_within(resolved, target):
        raise _reject(where, RULE_NOT_INSIDE)
    # audit_release_exposure는 파일을 받으면 부모 폴더 목록도 읽는다(6절 표). 여기서 푼 파일이
    # target 안이면 그 부모는 target 자신이거나 그 아래라 따로 볼 것이 없다
    return resolved


# ---------------------------------------------------------------- source_paths (③)


def resolve_source_paths(value: Json, input_root: str) -> list[Json]:
    """F-R04 5③. input_path 기준 상대 경로만, 풀어서 input_path 아래면 `/` 꼴 상대 경로로 바꾼다."""
    if not isinstance(value, list) or not value:
        raise _reject(SOURCE_PATHS_FIELD, RULE_NOT_ARRAY)
    result: list[Json] = []
    for index, item in enumerate(value):
        where = f"{SOURCE_PATHS_FIELD}[{index}]"
        if not isinstance(item, str) or not item:
            raise _reject(where, RULE_NOT_TEXT)
        if chr(0) in item or item[0] in SEPARATORS or ":" in item:
            raise _reject(where, RULE_SOURCE_SHAPE)
        resolved = _realpath(os.path.join(input_root, item), where, RULE_NOT_IN_INPUT)
        # 같으면 파일 이름이 없다(REA 정의: 인벤토리의 파일 경로, application root 기준)
        if os.path.normcase(resolved) == os.path.normcase(input_root):
            raise _reject(where, RULE_INPUT_ITSELF)
        if not is_within(resolved, input_root):
            raise _reject(where, RULE_NOT_IN_INPUT)
        result.append(os.path.relpath(resolved, input_root).replace("\\", "/"))
    return result


# ---------------------------------------------------------------- 같은 세션 참조 (④)


def check_reference(value: Json, where: str) -> None:
    """F-R04 5④. `{"kind": "retained-evidence", "evidence_id": "ev_<sha256>"}`만.

    REA가 이 칸을 `{"type": "object"}`로만 알려, 에이전트가 꼴을 알 길은 이 오류 글뿐이다.
    """
    if not isinstance(value, dict) or set(value) != {"kind", "evidence_id"}:
        raise _reject(where, RULE_REFERENCE)
    evidence_id = value["evidence_id"]
    if value["kind"] != REFERENCE_KIND or not isinstance(evidence_id, str):
        raise _reject(where, RULE_REFERENCE)
    if not EVIDENCE_ID.fullmatch(evidence_id):
        raise _reject(where, RULE_REFERENCE)


def _check_reference_array(value: Json, where: str) -> None:
    if not isinstance(value, list):
        raise _reject(where, RULE_NOT_ARRAY)
    for index, item in enumerate(value):
        check_reference(item, f"{where}[{index}]")


# ---------------------------------------------------------------- 그물 (⑤)


def _strings(value: Json) -> Iterator[str]:
    """값 안의 모든 글(객체 키 포함). 깊이는 읽을 때 이미 막았다."""
    stack: list[Json] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def strip_wrapping(text: str) -> str:
    """앞뒤 공백(유니코드 공백 포함)과 따옴표를 벗긴다. 받는 쪽이 벗겨 읽을 수 있어서다."""
    while True:
        stripped = text.strip().strip(QUOTES)
        if stripped == text:
            return text
        text = stripped


def is_expansion(text: str) -> bool:
    """홈·환경 변수로 펼칠 수 있는 꼴: `~`로 시작, `%이름%`, `$이름`·`${이름}`·`$(…)`."""
    return (
        text.startswith(HOME_MARK)
        or bool(PERCENT_VAR.search(text))
        or bool(DOLLAR_VAR.search(text))
    )


def has_dot_dot_segment(text: str) -> bool:
    """`..` 마디가 있는지. Windows는 마디 끝의 점·공백을 지워 `.. `·`...`도 `..`로 읽을 수 있다.

    마디를 목록으로 나누지 않고 하나씩 훑는다(큰 글에서 메모리가 입력의 몇 배로 늘지 않게).
    """
    if ".." not in text and ". " not in text:
        return False  # 점 둘 이상이고 점·공백뿐인 마디에는 둘 중 하나가 꼭 들어 있다
    for match in SEGMENT.finditer(text):
        segment = match.group()
        if segment.count(".") >= 2 and not segment.rstrip(" ."):
            return True
    return False


def looks_like_path(text: str) -> bool:
    """경로 꼴: 드라이브 문자로 시작, 구분자 둘로 시작(UNC·장치), `file:`, `..` 마디."""
    if DRIVE.match(text) or text[: len(FILE_URL)].lower() == FILE_URL:
        return True
    if len(text) >= 2 and text[0] in SEPARATORS and text[1] in SEPARATORS:
        return True
    return has_dot_dot_segment(text)


def _is_root_relative(text: str) -> bool:
    return text[:1] in {"\\", "/"} and not (len(text) >= 2 and text[1] in SEPARATORS)


def check_expansions(arguments: Mapping[str, Json]) -> None:
    """F-R04 5⑤ 앞부분. 모든 칸의 모든 글(경로 칸 포함)에서 펼침 꼴은 늘 거절한다.

    경로를 풀기 전에 본다: 상대 경로로 풀다가 '없음'으로 거절되면 어느 규칙이 막았는지 흐려진다.
    """
    for field, value in arguments.items():
        for raw in _strings(value):
            if is_expansion(strip_wrapping(raw)):
                raise _reject(field, RULE_EXPANSION)


def scan_strings(
    tool: str, arguments: Mapping[str, Json], target: str, path_checked: frozenset[str]
) -> None:
    """F-R04 5⑤. ②·③·④가 본 칸 밖의 모든 글을 공백·따옴표를 벗긴 꼴로 본다.

    경로 꼴은 ②를 통과해야 한다. 드라이브 없는 루트 기준 꼴(`\\Users\\…`·`/Users/…`)은 REA가
    절대 경로로 받으므로(REA 6.10.1 localPath.js) 글자 그대로를 맞춰 보는 칸(LITERAL_TEXT_FIELDS)
    밖에서는 거절한다.
    """
    literal = LITERAL_TEXT_FIELDS.get(tool, frozenset())
    for field, value in arguments.items():
        if field in path_checked:
            continue
        for raw in _strings(value):
            text = strip_wrapping(raw)
            if looks_like_path(text):
                resolve_path_field(text, field, target)
            elif field not in literal and _is_root_relative(text):
                raise _reject(field, RULE_ROOT_RELATIVE)


# ---------------------------------------------------------------- tools/call (①~⑤)


def _meta(value: Json) -> dict[str, Json]:
    # 진행 알림에 쓰는 progressToken만 넘긴다. REA가 _meta로 받을 다른 것은 없다
    if not isinstance(value, dict):
        raise _reject("_meta", RULE_ARGUMENTS_OBJECT)
    token = value.get("progressToken")
    return {"progressToken": token} if token is not None and _valid_id(token) else {}


def filter_tool_call(params: Json, policy: Policy) -> dict[str, Json]:
    """F-R04 4·5. 허용 도구·허용 인자만, 경로 칸은 푼 경로로 바꾼 params를 돌려준다."""
    if not isinstance(params, dict) or not set(params) <= CALL_PARAMS:
        raise _reject("params", RULE_PARAMS)
    name = params.get("name")
    if not isinstance(name, str) or name not in policy.allow:
        raise _reject("name", RULE_TOOL)
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise _reject("arguments", RULE_ARGUMENTS_OBJECT)
    allowed = TOOL_ARGUMENTS[name]
    if not set(arguments) <= allowed:
        names = ", ".join(sorted(allowed))
        raise _reject("arguments", f"{RULE_ARGUMENT_NAME} (허용: {names})")
    sent = _filter_arguments(name, arguments, policy.target)
    result: dict[str, Json] = {"name": name, "arguments": sent}
    if "_meta" in params:
        result["_meta"] = _meta(params["_meta"])
    return result


def _filter_arguments(name: str, arguments: dict[str, Json], target: str) -> dict[str, Json]:
    sent = dict(arguments)
    check_expansions(arguments)
    path_checked: set[str] = set()
    reference = REFERENCE_FIELD.get(name)
    if reference is not None:
        if reference not in arguments:
            raise _reject(reference, RULE_REQUIRED)
        check_reference(arguments[reference], reference)
        path_checked.add(reference)
    array = REFERENCE_ARRAY_FIELD.get(name)
    if array is not None and array in arguments:
        _check_reference_array(arguments[array], array)
        path_checked.add(array)
    field = PATH_FIELD.get(name)
    if field is not None:
        if field not in arguments:
            raise _reject(field, RULE_REQUIRED)
        resolved = resolve_path_field(arguments[field], field, target)
        sent[field] = resolved
        path_checked.add(field)
        if SOURCE_PATHS_FIELD in arguments:
            sent[SOURCE_PATHS_FIELD] = resolve_source_paths(arguments[SOURCE_PATHS_FIELD], resolved)
            path_checked.add(SOURCE_PATHS_FIELD)
    scan_strings(name, arguments, target, frozenset(path_checked))
    return sent


# ---------------------------------------------------------------- 응답 거르기 (2·3)


def filter_initialize_result(result: Json) -> Json:
    """F-R04 2. 응답 키는 허용 목록만, capabilities에서는 tools만 남긴다.

    `instructions`도 지운다(총괄 판단, 검증 T31 4): 조건 B만 받는 안내 글이 되면 A·B가 REA 말고도
    달라지고(요구사항 5.1), 그 글이 거르개가 숨긴 도구를 말해 헛호출로 비용만 는다.
    """
    if not isinstance(result, dict):
        raise Rejected(INTERNAL_ERROR, "REA initialize 응답 꼴이 아님")
    kept: dict[str, Json] = {key: result[key] for key in INITIALIZE_KEYS if key in result}
    capabilities = result.get("capabilities")
    tools: dict[str, Json] = {}
    if isinstance(capabilities, dict) and KEPT_CAPABILITY in capabilities:
        tools[KEPT_CAPABILITY] = capabilities[KEPT_CAPABILITY]
    kept["capabilities"] = tools
    return kept


def filter_tools_list_result(result: Json, allow: frozenset[str]) -> Json:
    """F-R04 3. 허용 도구만 남긴다(list_changed 뒤 다시 받은 목록도 매번)."""
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not isinstance(tools, list):
        raise Rejected(INTERNAL_ERROR, "REA tools/list 응답 꼴이 아님")
    kept: list[Json] = [t for t in tools if isinstance(t, dict) and t.get("name") in allow]
    return {**result, "tools": kept}


# ---------------------------------------------------------------- 메시지 길잡이


class Router:
    """두 방향의 메시지를 받아 보낼 것(Outgoing) 목록을 돌려준다. 입출력은 하지 않는다."""

    def __init__(self, policy: Policy, rea_running: bool) -> None:
        self._policy = policy
        self._rea_running = rea_running
        self._pending: dict[tuple[str, str], tuple[Json, str]] = {}
        self._lock = threading.Lock()

    def from_client(self, raw: bytes) -> list[Outgoing]:
        """Claude Code → REA 한 줄. 생각 못 한 예외도 거르개를 죽이지 않고 오류로 답한다."""
        try:
            message = parse_line(raw, MAX_DEPTH)
        except Unreadable:
            return [Outgoing("client", _error(None, PARSE_ERROR, "JSON으로 읽을 수 없음"))]
        try:
            with self._lock:
                return self._client_message(message)
        except Exception as error:  # 넘기지 않는 쪽으로 끝낸다(실패하면 안전한 쪽)
            _log(f"요청 처리 중 예외 {type(error).__name__}")
            return [Outgoing("client", _error(_reply_id(message), INTERNAL_ERROR, "거르개 오류"))]

    def from_rea(self, raw: bytes) -> list[Outgoing]:
        """REA → Claude Code 한 줄. 읽을 수 없거나 꼴이 아닌 줄은 넘기지 않고 오류로 알린다."""
        try:
            message = parse_line(raw, None)
        except Unreadable:
            return self._rea_unreadable("REA가 보낸 줄을 JSON으로 읽을 수 없음")
        try:
            with self._lock:
                return self._rea_message(message)
        except Exception as error:  # 넘기지 않는 쪽으로 끝낸다
            _log(f"REA 메시지 처리 중 예외 {type(error).__name__}")
            return self._rea_unreadable("REA가 보낸 줄을 처리하지 못함")

    @staticmethod
    def _rea_unreadable(rule: str) -> list[Outgoing]:
        # 어느 요청의 응답인지 모르므로 id 없이 알린다(F-R04 예외 '그 글을 넘기지 않고 오류')
        _log(rule)
        return [Outgoing("client", _error(None, INTERNAL_ERROR, rule))]

    @staticmethod
    def too_long() -> list[Outgoing]:
        """상한을 넘는 줄은 읽지 않고 오류로 답한다."""
        return [Outgoing("client", _error(None, PARSE_ERROR, "줄이 상한을 넘음"))]

    def rea_stopped(self) -> list[Outgoing]:
        """REA가 끝났다. 답을 기다리던 요청마다 오류를 돌려준다."""
        with self._lock:
            self._rea_running = False
            pending = list(self._pending.values())
            self._pending.clear()
        return [Outgoing("client", _error(i, SERVER_ERROR, "REA가 끝남")) for i, _ in pending]

    def _client_message(self, message: Json) -> list[Outgoing]:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return [self._invalid(message)]
        if "method" not in message:
            return []  # 응답: REA의 요청을 넘기지 않으므로 받을 일이 없다
        method = message["method"]
        if not isinstance(method, str):
            return [self._invalid(message)]
        if "id" not in message:
            return self._client_notification(method, message)
        msg_id = message["id"]
        if not _valid_id(msg_id):
            return [self._invalid(message)]
        try:
            return [self._client_request(msg_id, method, message)]
        except Rejected as rejected:
            # 메서드 이름도 받은 값이라 싣지 않는다(규칙만)
            _log(f"거절: {rejected.rule}")
            return [Outgoing("client", _error(msg_id, rejected.code, rejected.rule))]

    @staticmethod
    def _invalid(message: Json) -> Outgoing:
        return Outgoing(
            "client", _error(_reply_id(message), INVALID_REQUEST, "JSON-RPC 요청 꼴이 아님")
        )

    def _client_request(self, msg_id: Json, method: str, message: dict[str, Json]) -> Outgoing:
        if method not in CLIENT_REQUESTS:
            raise Rejected(METHOD_NOT_FOUND, "허용 밖 메서드")
        if not self._rea_running:
            raise Rejected(SERVER_ERROR, "REA가 떠 있지 않음")
        key = _id_key(msg_id)
        if key in self._pending:
            raise Rejected(INVALID_REQUEST, "같은 id의 요청이 아직 끝나지 않음")
        sent: dict[str, Json] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if method == "tools/call":
            sent["params"] = filter_tool_call(message.get("params"), self._policy)
        elif "params" in message:
            sent["params"] = message["params"]
        self._pending[key] = (msg_id, method)
        return Outgoing("rea", sent)

    def _client_notification(self, method: str, message: dict[str, Json]) -> list[Outgoing]:
        if method not in CLIENT_NOTIFICATIONS or not self._rea_running:
            return []
        params = message.get("params")
        if method == "notifications/cancelled":
            request_id = params.get("requestId") if isinstance(params, dict) else None
            if not _valid_id(request_id) or _id_key(request_id) not in self._pending:
                return []
        sent: dict[str, Json] = {"jsonrpc": "2.0", "method": method}
        if "params" in message:
            sent["params"] = params
        return [Outgoing("rea", sent)]

    def _rea_message(self, message: Json) -> list[Outgoing]:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._rea_unreadable("REA가 보낸 줄이 JSON-RPC 꼴이 아님")
        if "method" in message:
            if not isinstance(message["method"], str):
                return self._rea_unreadable("REA가 보낸 줄이 JSON-RPC 꼴이 아님")
            return self._rea_request_or_notification(message)
        msg_id = message.get("id")
        if not _valid_id(msg_id):
            return self._rea_unreadable("REA 응답의 id가 꼴이 아님")
        entry = self._pending.pop(_id_key(msg_id), None)
        if entry is None:
            _log("보낸 적 없는 id의 REA 응답을 버림")
            return []
        try:
            return [Outgoing("client", self._response(msg_id, entry[1], message))]
        except Rejected as rejected:
            return [Outgoing("client", _error(msg_id, rejected.code, rejected.rule))]

    def _rea_request_or_notification(self, message: dict[str, Json]) -> list[Outgoing]:
        if "id" in message:
            # REA가 거는 요청(sampling·roots·elicitation…)은 Claude Code에 넘기지 않는다
            msg_id = message["id"]
            if not _valid_id(msg_id):
                return self._rea_unreadable("REA 요청의 id가 꼴이 아님")
            _log("REA가 건 요청에 오류로 답함")
            return [Outgoing("rea", _error(msg_id, METHOD_NOT_FOUND, "거르개가 넘기지 않는 요청"))]
        sent: dict[str, Json] = {"jsonrpc": "2.0", "method": message["method"]}
        if "params" in message:
            sent["params"] = message["params"]
        return [Outgoing("client", sent)]

    def _response(self, msg_id: Json, method: str, message: dict[str, Json]) -> dict[str, Json]:
        if ("result" in message) == ("error" in message):
            raise Rejected(INTERNAL_ERROR, "REA 응답 꼴이 아님")
        if "error" in message:
            return {"jsonrpc": "2.0", "id": msg_id, "error": message["error"]}
        result = message["result"]
        if method == "initialize":
            result = filter_initialize_result(result)
        elif method == "tools/list":
            result = filter_tools_list_result(result, self._policy.allow)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}


# ---------------------------------------------------------------- 설정·환경 (1)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rea_mcp_filter", allow_abbrev=False)
    parser.add_argument("--allow", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--netguard-log", required=True)
    parser.add_argument("--env-dir", required=True)
    return parser


def _outside_target(raw: str, target: str, name: str) -> str:
    """파일·폴더 하나의 절대 경로. 부모는 있어야 하고, 푼 경로가 target 밖이어야 한다."""
    raw = raw.rstrip(SEPARATORS)
    if not os.path.isabs(raw) or not DRIVE_ABSOLUTE.match(raw):
        raise ConfigError(f"{name}: 드라이브 문자 절대 경로여야 함")
    try:
        parent = os.path.realpath(os.path.dirname(raw), strict=True)
    except OSError as error:
        raise ConfigError(f"{name}: 부모 폴더가 없음") from error
    path = os.path.join(parent, os.path.basename(raw))
    if is_within(path, target):
        raise ConfigError(f"{name}: target 안이면 안 됨")
    return path


def has_reparse_point(root: str) -> bool:
    """root 아래에 재분석 지점(정션·심볼릭 링크 등)이 하나라도 있는지. 따라 들어가지 않는다.

    거르개는 경로 칸의 맨 위만 풀므로, `input_path: <T>`로 REA가 폴더를 훑다가 안쪽 정션을 따라
    밖을 읽을 수 있다. 실행기 F-R02 ㉠이 먼저 막지만 거르개도 띄우기 전에 한 번 더 본다(두 층,
    검증 T31 6). 훑지 못하는 폴더가 있으면 있는 것으로 본다(실패하면 안전한 쪽).
    """
    folders = [root]
    while folders:
        folder = folders.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        return True
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.path)
        except OSError:
            return True
    return False


def load_config(argv: Sequence[str]) -> Config:
    """F-R04 입력. `--` 뒤는 REA 명령(첫 칸은 절대 경로)."""
    if "--" not in argv:
        raise ConfigError("REA 명령 앞에 -- 가 없음")
    split = list(argv).index("--")
    options = _parser().parse_args(list(argv[:split]))
    command = list(argv[split + 1 :])
    if not command or not os.path.isabs(command[0]):
        raise ConfigError("REA 프로그램은 절대 경로여야 함")
    allow = options.allow.split(",")
    if len(set(allow)) != len(allow) or not set(allow) <= set(TOOL_ARGUMENTS):
        raise ConfigError("--allow: 인자 규칙이 있는 도구만, 한 번씩")
    if not DRIVE_ABSOLUTE.match(options.target):
        raise ConfigError("--target: 드라이브 문자 절대 경로여야 함")
    try:
        target = os.path.realpath(options.target, strict=True)
    except OSError as error:
        raise ConfigError("--target: 없는 폴더") from error
    if not os.path.isdir(target) or os.path.dirname(target) == target:
        raise ConfigError("--target: 드라이브 맨 위가 아닌 폴더여야 함")
    if has_reparse_point(target):
        raise ConfigError("--target: 아래에 재분석 지점(정션·심볼릭 링크)이 있음")
    netguard_log = _outside_target(options.netguard_log, target, "--netguard-log")
    env_dir = _outside_target(options.env_dir, target, "--env-dir")
    if not NETGUARD.is_file():
        raise ConfigError("rea_netguard.cjs가 없음")
    return Config(Policy(frozenset(allow), target), netguard_log, Path(env_dir), command)


def build_rea_env(
    environ: Mapping[str, str], program: str, env_dir: Path, netguard_log: str
) -> dict[str, str]:
    """F-R04 1. REA에 줄 허용 목록 환경(바깥 값은 ENV_PASS·PASS_THROUGH만)."""
    env = {name: environ[name] for name in (*ENV_PASS, *PASS_THROUGH) if name in environ}
    paths = [os.path.dirname(program)]
    system_root = environ.get("SystemRoot")
    if system_root:
        paths += [os.path.join(system_root, "System32"), system_root]
    env["PATH"] = os.pathsep.join(paths)
    for name in HOME_VARS:
        env[name] = str(env_dir / "home" / name)
    for name in TEMP_VARS:
        env[name] = str(env_dir / "tmp")
    # NODE_OPTIONS 따옴표 안의 `\`는 이스케이프로 읽히므로 `/` 꼴(REA환경.md 6절)
    env["NODE_OPTIONS"] = f'--require "{NETGUARD.as_posix()}"'
    env["REA_NETGUARD_LOG"] = netguard_log
    for name in PROXY_VARS:
        env[name] = CLOSED_PROXY
    return env


def make_env_dirs(env: Mapping[str, str]) -> None:
    for name in (*HOME_VARS, *TEMP_VARS):
        Path(env[name]).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- 입출력


class Bridge:
    """Router가 돌려준 메시지를 두 쪽 스트림에 쓴다.

    Claude Code 쪽은 두 스레드(요청 읽기·REA 읽기)가 잠금 하나로 쓴다. REA 쪽은 큐 하나와 쓰기
    스레드 하나가 맡는다: REA 입력 파이프가 차서 쓰기가 막혀도 다른 스레드가 잠금을 쥔 채 서지 않고,
    쓰는 차례가 넣은 차례 그대로다(검증 T31 8).
    """

    def __init__(self, router: Router, client: IO[bytes], rea: IO[bytes] | None) -> None:
        self.router = router
        self._client = client
        self._client_lock = threading.Lock()
        self._rea = rea
        self._rea_queue: queue.Queue[bytes | None] = queue.Queue()
        self._writer: threading.Thread | None = None
        if rea is not None:
            self._writer = threading.Thread(target=self._write_rea, args=(rea,), daemon=True)
            self._writer.start()

    def deliver(self, outgoing: list[Outgoing]) -> None:
        for item in outgoing:
            if item.to == "client":
                with self._client_lock:
                    self._client.write(dump_line(item.message))
                    self._client.flush()
            elif self._rea is not None:
                self._rea_queue.put(dump_line(item.message))

    def _write_rea(self, rea: IO[bytes]) -> None:
        while (data := self._rea_queue.get()) is not None:
            try:
                rea.write(data)
                rea.flush()
            except OSError:
                _log("REA 입력에 쓰지 못함")
                self.deliver(self.router.rea_stopped())
                break
        try:
            rea.close()
        except OSError:
            _log("REA 입력을 닫지 못함")

    def close_rea(self) -> None:
        """넣어 둔 것을 다 쓴 뒤 REA 입력을 닫는다(REA는 입력이 끝나면 스스로 끝난다)."""
        if self._writer is None:
            return
        self._rea_queue.put(None)
        self._writer.join(timeout=STOP_WAIT_S)


def _client_lines(stream: IO[bytes]) -> Iterator[bytes | None]:
    """한 줄씩. 상한을 넘는 줄은 줄 끝까지 읽어 버리고 None을 낸다."""
    while True:
        raw = stream.readline(MAX_CLIENT_LINE_BYTES + 1)
        if not raw:
            return
        if len(raw) > MAX_CLIENT_LINE_BYTES and not raw.endswith(b"\n"):
            while raw and not raw.endswith(b"\n"):
                raw = stream.readline(MAX_CLIENT_LINE_BYTES)
            yield None
            continue
        if raw.strip():
            yield raw.rstrip(b"\r\n")


def _pump_rea(bridge: Bridge, stdout: IO[bytes]) -> None:
    try:
        for raw in iter(stdout.readline, b""):
            if raw.strip():
                bridge.deliver(bridge.router.from_rea(raw))
    except Exception as error:  # 읽기가 깨져도 기다리는 요청에 답하고 끝낸다
        _log(f"REA 출력 읽기 중 예외 {type(error).__name__}")
    finally:
        bridge.deliver(bridge.router.rea_stopped())


def _start_rea(config: Config, env: dict[str, str]) -> subprocess.Popen[bytes] | None:
    try:
        return subprocess.Popen(  # noqa: S603 — 설정이 준 인자 목록, 셸 없음
            config.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=config.policy.target,
            env=env,
            shell=False,
        )
    except OSError:
        _log("REA를 띄우지 못함")
        return None


def kill_tree(pid: int, environ: Mapping[str, str]) -> bool:
    """`%SystemRoot%\\System32\\taskkill.exe /T /F /PID`로 프로세스 나무째 끝낸다.

    셸 없이, 절대 경로로 부른다. PATH에서 찾지 않는 것은 실행 폴더·target에 같은 이름의
    프로그램을 두어 바꿔치기할 수 없게 하려고다.
    """
    system_root = environ.get("SystemRoot")
    if not system_root:
        return False
    taskkill = os.path.join(system_root, "System32", "taskkill.exe")
    try:
        result = subprocess.run(  # noqa: S603 — 고정된 절대 경로와 정수 PID, 셸 없음
            [taskkill, "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=STOP_WAIT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def main(argv: Sequence[str] | None = None) -> int:
    """F-R04 MCP 거르개를 띄운다. 설정이 맞지 않으면 2로 끝난다."""
    try:
        config = load_config(sys.argv[1:] if argv is None else argv)
    except ConfigError as error:
        _log(str(error))
        return 2
    env = build_rea_env(os.environ, config.command[0], config.env_dir, config.netguard_log)
    make_env_dirs(env)
    process = _start_rea(config, env)
    router = Router(config.policy, rea_running=process is not None)
    bridge = Bridge(router, sys.stdout.buffer, process.stdin if process else None)
    pump: threading.Thread | None = None
    if process is not None and process.stdout is not None:
        pump = threading.Thread(target=_pump_rea, args=(bridge, process.stdout), daemon=True)
        pump.start()
    for raw in _client_lines(sys.stdin.buffer):
        bridge.deliver(router.too_long() if raw is None else router.from_client(raw))
    _stop(process, bridge, pump)
    return 0


def _stop(
    process: subprocess.Popen[bytes] | None, bridge: Bridge, pump: threading.Thread | None
) -> None:
    """입력을 닫아 스스로 끝날 틈을 주고, STOP_WAIT_S 안에 안 끝나면 나무째 끝낸다."""
    if process is None:
        return
    bridge.close_rea()
    try:
        process.wait(timeout=STOP_WAIT_S)
    except subprocess.TimeoutExpired:
        if not kill_tree(process.pid, os.environ):
            _log("taskkill로 끝내지 못해 본 프로세스만 끝냄")
            process.kill()
        process.wait(timeout=STOP_WAIT_S)
    if pump is not None:
        pump.join(timeout=STOP_WAIT_S)


if __name__ == "__main__":
    raise SystemExit(main())
