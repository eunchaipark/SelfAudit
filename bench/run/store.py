"""F-R06 원자료 저장: 자리·대화 기록 가림·결과 경로 정규화·`run.json` (실험구조 2.4·3.8·4절·8.5).

원자료 자리 (F-R06 1):
- `planted`·`practice` 대상 실행 → `<저장소>\\bench\\results\\<YYYY-MM-DD>\\<실행 ID>\\`
- `mine` 대상 실행 → `%LOCALAPPDATA%\\SelfAudit-private\\results\\<YYYY-MM-DD>\\<실행 ID>\\`
- 빈·문지기 실행(`run_kind` `empty`·`gate`)
  → `%LOCALAPPDATA%\\SelfAudit-bench-archive\\<배치 ID>\\<실행 ID>\\`
내 앱·빈·문지기 원자료가 풀어 보니 저장소 안이면 쓰지 않고 멈춘다(실험구조 4절 ⑴).
"""

from __future__ import annotations

import hashlib
import io
import json
import ntpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final
from urllib.parse import quote

from common.contracts import ContractError, Json, validate_contract
from common.paths import normalize_finding_path
from run.workdir import EMPTY_MANIFEST_SHA256, BenchPlaces, is_inside

__all__ = [
    "RAW_FILES",
    "RESERVED_RUN_KINDS",
    "TRANSCRIPT_LIMIT_BYTES",
    "RunFacts",
    "StoreError",
    "StoredRun",
    "StreamFacts",
    "check_out_dir",
    "home_left",
    "mask_paths",
    "normalize_findings",
    "raw_dir",
    "read_stream",
    "run_record",
    "store_run",
]

RUN_JSON: Final = "run.json"
FINDINGS_JSON: Final = "findings.json"
TRANSCRIPT: Final = "transcript.jsonl"
NETGUARD: Final = "netguard.jsonl"
NETSTAT: Final = "netstat.json"
RAW_FILES: Final = (RUN_JSON, FINDINGS_JSON, TRANSCRIPT, NETGUARD, NETSTAT)  # F-R06 3, 이 다섯만
TRANSCRIPT_LIMIT_BYTES: Final = 2 * 1024 * 1024  # F-R06 6: 이보다 **크면** 저장소 밖 보관
RESERVED_RUN_KINDS: Final = frozenset({"empty", "gate"})
RUN_SCHEMA: Final = "selfaudit-bench/run@1"
RUN_MARK: Final = "<RUN>"
HOME_MARK: Final = "<HOME>"
MAX_DETAIL_CHARS: Final = 500  # run.schema.json outcome.detail
MAX_RUN_ID_CHARS: Final = 80
# result 줄에서 구조화 결과를 담는 칸 이름(추정 — 첫 보정 실행의 result 줄에서 확인, F-R03 7)
STRUCTURED_KEY: Final = "structured_output"
USAGE_KEYS: Final = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
OTHER_TOOL: Final = (
    "<그 밖>"  # 도구 이름이 이름 꼴이 아니면 한데 센다(대화 기록 글을 칸 이름으로 옮기지 않게)
)
_TOOL_NAME: Final = re.compile(r"[A-Za-z0-9_\-]{1,128}")
_RUN_ID: Final = re.compile(r"[a-z0-9][a-z0-9-]{3,79}")
_BATCH_ID: Final = re.compile(r"[0-9]{8}-[0-9]{4}-[a-z0-9]{4,12}")
_MINE: Final = "mine"
_MINE_PREFIX: Final = "mine-"
_PLANTED: Final = "planted"


class StoreError(RuntimeError):
    """F-R06 예외: 쓰지 않거나(자리·꼴), 쓴 뒤에도 배치를 멈춰야 한다(홈 경로가 남음).

    값은 싣지 않는다.
    """

    def __init__(self, detail: str, written: Path | None = None) -> None:
        self.detail = detail
        self.written = written  # 멈추기 전에 쓴 원자료 폴더(없으면 None)
        super().__init__(f"원자료 저장 멈춤: {detail}")


@dataclass(frozen=True)
class RunFacts:
    """`run.json`에 적을 것 가운데 부르는 쪽(F-R03·R05·R07·R10)이 아는 것.

    지표·대화 기록 칸은 여기서 낸다.
    """

    run_kind: str
    run_id: str
    batch_id: str
    target_id: str
    target_kind: str
    bundle_manifest_sha256: str
    condition: str
    repeat_index: int
    started_at: datetime
    ended_at: datetime
    versions: Mapping[str, Json]
    settings: Mapping[str, Json]
    status: str
    exit_code: int | None
    init_check: str
    detail: str
    wall_s: float
    network: Mapping[str, int]


@dataclass(frozen=True)
class StreamFacts:
    result: dict[str, Json] | None  # 마지막 `type: result` 줄
    tool_calls: dict[str, int]
    bad_lines: int  # JSON으로 읽지 못한 줄 수


@dataclass(frozen=True)
class StoredRun:
    out_dir: Path
    record: dict[str, Json]
    transcript_path: Path


# --- 자리 ------------------------------------------------------------------------------------


def raw_dir(
    places: BenchPlaces,
    *,
    run_kind: str,
    target_kind: str,
    run_id: str,
    batch_id: str,
    batch_date: date,
) -> Path:
    """F-R06 1: 원자료 폴더 자리. 날짜는 배치를 시작한 로컬 날짜."""
    if not (_RUN_ID.fullmatch(run_id) and _BATCH_ID.fullmatch(batch_id)):
        raise StoreError(f"실행 ID({MAX_RUN_ID_CHARS}자까지)·배치 ID 꼴이 아님")
    day = batch_date.isoformat()
    if run_kind in RESERVED_RUN_KINDS:
        # 실행 ID 앞머리로 빈·문지기 실행을 가린다(F-R01 3 `<대상 ID>-…`, 대상 ID = 예약 ID) —
        # 어긋나면 보관 폴더에서 폴더 이름만 보고 대상 실행과 섞인다
        if not run_id.startswith(f"{run_kind}-"):
            raise StoreError(
                "빈·문지기 실행은 실행 ID가 empty-·gate-(run_kind와 같은 앞머리)로 시작"
            )
        return places.archive_dir / batch_id / run_id
    # 종류 글과 실행 ID 꼴이 어긋나면 어느 쪽이 맞는지 모른다 — 저장소 쪽을 고르지 않고 멈춘다
    if (target_kind == _MINE) != run_id.startswith(_MINE_PREFIX):
        raise StoreError("내 앱 실행은 실행 ID가 mine-로 시작하고, 그 밖은 mine-로 시작하지 않는다")
    if target_kind == _MINE:
        return places.private_dir / "results" / day / run_id
    return places.repo_root / "bench" / "results" / day / run_id


def check_out_dir(out_dir: Path, *, run_kind: str, target_kind: str, repo_root: Path) -> None:
    """F-R06 2: 내 앱·빈·문지기 원자료의 자리가 (풀어 보니) 저장소 안이면 거절한다."""
    must_be_outside = target_kind == _MINE or run_kind in RESERVED_RUN_KINDS
    if must_be_outside and is_inside(out_dir, repo_root):
        raise StoreError("내 앱·빈·문지기 원자료 자리가 저장소 안")


# --- 대화 기록 -------------------------------------------------------------------------------


def read_stream(data: bytes) -> StreamFacts:
    """stream-json 줄을 훑어 마지막 `result` 줄과 도구 이름별 호출 수를 낸다.

    호출은 `tool_use` id마다 한 번만 센다.
    """
    result: dict[str, Json] | None = None
    seen_ids: set[str] = set()
    calls: dict[str, int] = {}
    bad = 0
    # 줄 목록을 한꺼번에 만들지 않는다(입력만큼 사본이 생긴다). BytesIO는 입력 버퍼를 나눠 쓴다
    for line in io.BytesIO(data):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            bad += 1
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "result":
            result = obj
        elif kind == "assistant":
            _count_tools(obj, seen_ids, calls)
    return StreamFacts(result=result, tool_calls=calls, bad_lines=bad)


def _count_tools(obj: Mapping[str, Json], seen_ids: set[str], calls: dict[str, int]) -> None:
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "tool_use"):
            continue
        use_id = block.get("id")
        if isinstance(use_id, str):
            if use_id in seen_ids:
                continue
            seen_ids.add(use_id)
        name = block.get("name")
        key = name if isinstance(name, str) and _TOOL_NAME.fullmatch(name) else OTHER_TOOL
        calls[key] = calls.get(key, 0) + 1


def _json(text: str, *, ascii_only: bool = True) -> str:
    """JSON 문자열 안의 꼴(따옴표 뺌). `ascii_only`면 ASCII 밖 글자를 `\\uXXXX`로."""
    return json.dumps(text, ensure_ascii=ascii_only)[1:-1]


def _variants(spelling: str) -> list[str]:
    """한 경로 글의 꼴.

    - 한 겹: `\\` 꼴, `/` 꼴, JSON 안 꼴(`\\\\` 구분, ASCII 밖은 그대로·`\\uXXXX` 둘), `/` 꼴의
      JSON 꼴, JSON `\\/` 꼴.
    - 두 겹(JSON 글이 다시 JSON 글에 실린 꼴 — 도구가 낸 JSON이 stream-json 줄에 실릴 때): 한 겹
      JSON 꼴들을 한 번 더 JSON으로(구분 `\\\\\\\\`·`\\\\\\/`, 글자 `\\\\uXXXX`, 실험구조 8.10 2).
    - URL 인코딩 꼴(`%5C`·`%2F` — 질의 글에 실린 경로), 표준 `file:` 주소 꼴(구분자 `/`·`:`는
      그대로, ASCII 밖만 `%XX`).
    """
    slash = spelling.replace("\\", "/")
    json_once = {
        _json(spelling, ascii_only=False),
        _json(spelling),
        _json(slash),
        _json(slash).replace("/", "\\/"),
    }
    json_twice = {_json(v, ascii_only=a) for v in json_once for a in (True, False)}
    urls = {quote(spelling, safe=""), quote(slash, safe=""), quote(slash, safe="/:")}
    return sorted({spelling, slash} | json_once | json_twice | urls)


def _path_forms(path: str) -> tuple[list[bytes], list[str]]:
    """F-R06 5 가림에 쓰는 꼴: (앞부분이 있는 꼴의 UTF-8 바이트, 드라이브 없는 맨 꼬리의 마디들).

    명세의 세 꼴(드라이브 절대 경로의 `\\`·`/`·JSON `\\\\` 꼴)에 더해, 같은 곳을 가리키는
    드라이브 없는 꼴도 넣는다: `//c/…`(거절 규칙 꼴, F-R02 3), `/c/…`(Git Bash 꼴),
    `\\\\localhost\\C$\\…`(관리 공유) — 여기까지가 앞부분이 있는 꼴이고 긴 꼴부터 글자 그대로
    바꾼다(짧은 꼴이 긴 꼴의 일부를 먼저 깨지 않게). 드라이브 없는 `\\Users\\…`(맨 꼬리)는 앞부분이
    없어 웹 주소(`/api/Users/u123`)와 겹치므로 뒤 경계(`_TAIL_END`)가 있을 때만 바꾼다
    (실험구조 8.9 3). 맨 꼬리는 꼴을 늘어놓지 않고 마디로 넘긴다 — `_tail_regex`가 구분자·글자의
    꼴을 따로 고른다.
    """
    win = ntpath.normpath(path)
    spellings = [win]
    segments: list[str] = []
    drive, tail = ntpath.splitdrive(win)
    if len(drive) == 2 and drive[1] == ":" and len(tail) > 1:
        letter, slash_tail = drive[0], tail.replace("\\", "/")
        spellings += [
            f"\\\\localhost\\{letter.upper()}${tail}",
            f"\\\\127.0.0.1\\{letter.upper()}${tail}",
            f"//{letter.lower()}{slash_tail}",
            f"/{letter.lower()}{slash_tail}",
        ]
        segments = _segments(tail)
    anchored = {v.encode("utf-8") for s in spellings for v in _variants(s)}
    return _longest_first(anchored), segments


def _segments(path: str) -> list[str]:
    return [s for s in path.split("\\") if s]


def _longest_first(forms: set[bytes]) -> list[bytes]:
    return sorted(forms, key=lambda f: (-len(f), f))


# 경로 한 마디(사용자 이름)가 이어지는 글자. 이것이 뒤따르면 그 마디의 끝이 아니다(`u123`·`u_x`).
# 구분자·따옴표·공백·`.`·`%`(인코딩된 구분자)·ASCII 밖(한글 조사 등)·글 끝은 경계로 친다 — 경계를
# 넓게 잡을수록 '남음'이 되어 멈추는 쪽이다(실패하면 안전한 쪽)
_TAIL_END: Final = rb"(?![A-Za-z0-9_\-])"
# 마디 사이 구분자: `\` 1~4개(그대로·한 겹 JSON·세 개·두 겹 JSON), `\` 0~4개 + `/`(`/` 꼴과
# JSON `\/` 꼴의 한 겹·두 겹), URL 인코딩 `%5C`·`%2F`. 4개까지인 까닭은 실험구조 8.10 2
_SEP: Final = rb"(?:\\{1,4}|\\{0,4}/|%5C|%2F)"
# ASCII 밖 글자 하나의 JSON 이스케이프 앞머리: `\u`(한 겹) ~ `\` 넷 + `u`(두 겹)
_UNIT_ESCAPE: Final = rb"\\{1,4}u"
_PLAIN_ASCII: Final = frozenset("_.-~")  # URL 인코딩(`quote`)이 바꾸지 않는 ASCII 기호


def _char_pattern(ch: str) -> bytes:
    """이름 글자 하나의 꼴: 그대로(UTF-8)·URL 인코딩(`%XX`, UTF-8 바이트마다)·ASCII 밖이면 JSON
    `\\uXXXX`(UTF-16 단위마다, 앞 역슬래시 1~4개)."""
    raw = ch.encode("utf-8")
    if ch.isascii() and (ch.isalnum() or ch in _PLAIN_ASCII):
        return re.escape(raw)
    alternatives = [re.escape(raw), b"".join(b"%%%02X" % byte for byte in raw)]
    if not ch.isascii():
        units = ch.encode("utf-16-be")
        alternatives.append(
            b"".join(
                _UNIT_ESCAPE + b"%04x" % int.from_bytes(units[i : i + 2])
                for i in range(0, len(units), 2)
            )
        )
    return b"(?:" + b"|".join(alternatives) + b")"


def _tail_regex(segments: list[str], *, leading: bool, flags: int = 0) -> re.Pattern[bytes]:
    """드라이브 없는 꼬리(마디들)를 구분자·글자의 꼴마다 따로 골라, 뒤 경계까지 찾는 정규식.

    꼴을 통째로 늘어놓지 않으므로 섞인 꼴(한 겹 구분자와 두 겹 구분자가 함께, 그대로인 한글과
    `\\uXXXX`가 함께)도 잡는다. `leading`이면 꼬리 앞 구분자까지 맞춘다(가림 — `/api/Users/u`가
    `/api<HOME>`). 되돌아감이 없는 꼴이다: 구분자·글자마다 고를 것이 정해진 몇 개(역슬래시 1~4개)라
    시작 자리마다 드는 비용이 꼬리 길이에 비례하는 상수다 — 입력에 선형.
    """
    body = _SEP.join(b"".join(_char_pattern(c) for c in seg) for seg in segments)
    return re.compile((_SEP if leading else b"") + body + _TAIL_END, flags)


def mask_paths(data: bytes, run_dir: str, home: str) -> bytes:
    """F-R06 5: **먼저** 실행 폴더를 `<RUN>`으로, **그다음** 홈 폴더를 `<HOME>`으로(글자 그대로).

    앞부분이 있는 꼴은 뒤 경계 없이, 드라이브 없는 맨 꼬리는 뒤 경계가 있을 때만 바꾼다.
    맨 꼬리는 대소문자를 그대로 맞춘다(대소문자만 다른 꼴은 가리지 않고 `home_left`가 찾아 멈춘다).
    바이트(UTF-8) 그대로 바꾼다 — 글로 풀면 한글이 든 기록은 글자마다 2~4바이트라 메모리가 는다.
    """
    for path, mark in ((run_dir, RUN_MARK), (home, HOME_MARK)):
        anchored, segments = _path_forms(path)
        for form in anchored:
            data = data.replace(form, mark.encode())
        if segments:
            data = _sub_bytes(_tail_regex(segments, leading=True), mark.encode(), data)
    return data


def _sub_bytes(pattern: re.Pattern[bytes], mark: bytes, data: bytes) -> bytes:
    """`pattern.sub(mark, data)`과 같되 맞은 곳마다 조각 객체를 쌓지 않는다.

    `re.sub`은 맞은 곳이 촘촘하면(번들 글의 경로마다) 조각 목록이 입력의 6배까지 컸다(잰 것,
    실험구조 8.9 3). 쓰는 버퍼 하나에 바로 이어 쓴다 — 최고 메모리는 입력 + 결과.
    """
    first = pattern.search(data)
    if first is None:
        return data
    out = io.BytesIO()
    view = memoryview(data)
    last = 0
    for match in pattern.finditer(data, first.start()):
        out.write(view[last : match.start()])
        out.write(mark)
        last = match.end()
    out.write(view[last:])
    return out.getvalue()


def _home_needle(home: str) -> re.Pattern[bytes]:
    """홈 폴더의 드라이브 없는 꼬리(`Users\\<이름>`)를 모든 꼴로, 대소문자 없이, 뒤 경계까지 찾는
    정규식."""
    win = ntpath.normpath(home)
    segments = _segments(ntpath.splitdrive(win)[1]) or _segments(win)
    return _tail_regex(segments, leading=False, flags=re.IGNORECASE)


def home_left(data: bytes, home: str) -> bool:
    """F-R06 5: 가린 뒤에도 홈 폴더 경로가 (대소문자만 다른 꼴·드라이브 없는 꼴까지) 남았는가.

    드라이브 없는 꼬리 `Users\\<이름>`를 찾으므로 `C:`·`/c/`·`\\\\localhost\\C$` 등 어느 앞부분이든
    걸린다. 구분자는 역슬래시 1~4개·`/`(앞 역슬래시 0~4개)·`%5C`·`%2F`, 이름의 ASCII 밖 글자는
    그대로·`%XX`·`\\uXXXX`(앞 역슬래시 1~4개)를 마디·글자마다 섞어서도 찾는다(두 겹 JSON 꼴,
    실험구조 8.10 2). 이름 뒤에 이름이 이어지면(`Users/<이름>1`) 홈이 아닌 다른 마디라 남음으로
    치지 않는다(실험구조 8.9 3 — 웹 주소 `/api/Users/u123`이 배치를 멈추던 것). 사본을 만들지
    않는다(`casefold`는 한글 글에서 입력의 십수 배를 썼다). 대소문자는 ASCII만 맞춘다(바이트
    정규식) — ASCII 밖 글자의 대소문자 꼴은 잡지 못한다(한계). 역슬래시 5개 이상(세 겹 JSON)도
    잡지 못한다(한계, 8.10 2).
    """
    return _home_needle(home).search(data) is not None


# --- 결과 ------------------------------------------------------------------------------------


def normalize_findings(value: Json, target_root: str) -> Json:
    """F-R06 4: 결과마다 `file`을 대상 기준 상대 경로로. 그 밖은 그대로.

    F-G02 1과 같은 `normalize_finding_path`를 쓴다.
    """
    if not isinstance(value, dict):
        return value
    items = value.get("findings")
    if not isinstance(items, list):
        return value
    out = dict(value)
    out["findings"] = [_normalize_item(item, target_root) for item in items]
    return out


def _normalize_item(item: Json, target_root: str) -> Json:
    if not (isinstance(item, dict) and isinstance(item.get("file"), str)):
        return item
    fixed = dict(item)
    file = item["file"]
    assert isinstance(file, str)
    fixed["file"] = normalize_finding_path(file, target_root)
    return fixed


def _metrics(
    result: Mapping[str, Json] | None, facts: StreamFacts, wall_s: float
) -> dict[str, Json]:
    r: Mapping[str, Json] = result or {}
    usage = r.get("usage")
    u: Mapping[str, Json] = usage if isinstance(usage, dict) else {}
    tool_calls: dict[str, Json] = dict(facts.tool_calls)
    return {
        "wall_s": wall_s,
        "duration_ms": _int_or_none(r.get("duration_ms")),
        "duration_api_ms": _int_or_none(r.get("duration_api_ms")),
        "num_turns": _int_or_none(r.get("num_turns")),
        "total_cost_usd": _number_or_none(r.get("total_cost_usd")),
        "usage": {k: _int_or_none(u.get(k)) for k in USAGE_KEYS},
        "tool_calls": tool_calls,
    }


def _int_or_none(value: Json) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number_or_none(value: Json) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def run_record(
    facts: RunFacts,
    *,
    stream: StreamFacts,
    status: str,
    detail: str,
    transcript: Mapping[str, Json],
) -> dict[str, Json]:
    """F-R06 7: `run.json` 한 벌(계약 `run.schema.json`).

    계약에 어긋나면 `StoreError`(쓰지 않음).
    """
    if facts.started_at.tzinfo is None or facts.ended_at.tzinfo is None:
        raise StoreError("시각에 시간대가 없음")
    record: dict[str, Json] = {
        "schema": RUN_SCHEMA,
        "run_kind": facts.run_kind,
        "run_id": facts.run_id,
        "batch_id": facts.batch_id,
        "target_id": facts.target_id,
        "target_kind": facts.target_kind,
        "bundle_manifest_sha256": facts.bundle_manifest_sha256,
        "condition": facts.condition,
        "repeat_index": facts.repeat_index,
        "started_at": facts.started_at.isoformat(timespec="seconds"),
        "ended_at": facts.ended_at.isoformat(timespec="seconds"),
        "versions": dict(facts.versions),
        "settings": dict(facts.settings),
        "outcome": {
            "status": status,
            "exit_code": facts.exit_code,
            "init_check": facts.init_check,
            "detail": detail[:MAX_DETAIL_CHARS],
        },
        "metrics": _metrics(stream.result, stream, facts.wall_s),
        "network": dict(facts.network),
        "transcript": dict(transcript),
    }
    errors = validate_contract("run", record)
    if errors:
        raise StoreError("run.json이 계약에 어긋남: " + _where(errors))
    return record


def _check_identity(facts: RunFacts) -> None:
    """F-R06 2 빈·문지기 실행의 칸: `target_id` = 예약 ID, `target_kind` = planted,
    빈 실행 지문 = 빈 목록의 지문. 실행 ID 꼴·길이(80자)는 `raw_dir`이 본다."""
    if facts.run_kind not in RESERVED_RUN_KINDS:
        return
    if facts.target_id != facts.run_kind or facts.target_kind != _PLANTED:
        raise StoreError(
            "빈·문지기 실행의 target_id는 run_kind와 같은 예약 ID, target_kind는 planted"
        )
    if facts.run_kind == "empty" and facts.bundle_manifest_sha256 != EMPTY_MANIFEST_SHA256:
        raise StoreError("빈 실행의 지문이 빈 목록의 지문이 아님")


# --- 저장 ------------------------------------------------------------------------------------


def store_run(
    places: BenchPlaces,
    facts: RunFacts,
    *,
    batch_date: date,
    run_dir: Path,
    target: Path,
    stream: bytes,
    netguard: bytes = b"",
    netstat: bytes = b"",
) -> StoredRun:
    """F-R06: 원자료 폴더에 파일 다섯(구조화 결과가 없으면 `findings.json` 없이)을 쓴다.

    - 상태: 부르는 쪽이 낸 상태(F-R03·R05). `ok`인데 결과가 원본 계약에 어긋나면 `format_failure`.
    - 가림(F-R06 5)은 대화 기록과 함께 쓰는 글 파일 모두에 건다. 가린 뒤 홈 경로가 남으면 그 실행을
      `error`로 적고(`run.json`만 원자료 폴더에, 대화 기록은 저장소 밖 보관)
      `StoreError`로 배치를 멈춘다.
    - 원자료 폴더·보관 파일이 이미 있으면 덮어쓰지 않고 멈춘다. 쓰기 실패도 `StoreError`.
    """
    _check_identity(facts)
    out = raw_dir(
        places,
        run_kind=facts.run_kind,
        target_kind=facts.target_kind,
        run_id=facts.run_id,
        batch_id=facts.batch_id,
        batch_date=batch_date,
    )
    check_out_dir(
        out, run_kind=facts.run_kind, target_kind=facts.target_kind, repo_root=places.repo_root
    )
    home, run_text = str(places.user_profile), str(run_dir)
    parsed = read_stream(stream)

    def masked(data: bytes) -> bytes:
        return mask_paths(data, run_text, home)

    transcript_bytes = masked(stream)
    side = {NETGUARD: masked(netguard), NETSTAT: masked(netstat)}
    status, detail = facts.status, facts.detail
    findings_bytes: bytes | None = None
    structured = parsed.result.get(STRUCTURED_KEY) if parsed.result is not None else None
    if structured is not None:
        normalized = normalize_findings(structured, str(target))
        errors = validate_contract("findings", normalized)
        if errors and status == "ok":
            status, detail = "format_failure", "findings 계약: " + _where(errors)
        findings_bytes = masked(_json_text(normalized).encode("utf-8"))
    blobs = [transcript_bytes, *side.values(), *([findings_bytes] if findings_bytes else [])]
    leaked = any(home_left(b, home) for b in blobs)
    if leaked:
        status, detail = "error", "가린 뒤에도 홈 경로가 남음(대소문자만 다른 꼴 등)"
    to_archive = leaked or len(transcript_bytes) > TRANSCRIPT_LIMIT_BYTES
    transcript_path = (
        places.archive_dir / f"{facts.run_id}.jsonl" if to_archive else out / TRANSCRIPT
    )
    transcript_info: dict[str, Json] = {
        "stored": "archive" if to_archive else "results",
        "bytes": len(transcript_bytes),
        "sha256": hashlib.sha256(transcript_bytes).hexdigest(),
    }
    record = run_record(
        facts, stream=parsed, status=status, detail=detail, transcript=transcript_info
    )
    record_bytes = _json_text(record).encode("utf-8")
    if home_left(record_bytes, home):
        raise StoreError("run.json에 홈 경로가 있음(쓰지 않음)")
    files: dict[str, bytes] = {RUN_JSON: record_bytes}
    if not leaked:
        files |= side
        if findings_bytes is not None:
            files[FINDINGS_JSON] = findings_bytes
        if not to_archive:
            files[TRANSCRIPT] = transcript_bytes
    # 원자료 폴더('이미 있음' 확인)를 먼저 만든다 — 보관 파일을 먼저 쓰고 멈추면 짝 없이 남는다
    _make_raw_dir(places, facts, out)
    if to_archive:
        _write_archive(places, transcript_path, transcript_bytes, out)
    _write_raw_files(out, files)
    if leaked:
        raise StoreError(detail, written=out)
    return StoredRun(out_dir=out, record=record, transcript_path=transcript_path)


def _write_archive(places: BenchPlaces, path: Path, data: bytes, out: Path) -> None:
    """보관 파일을 쓴다. 못 쓰면 막 만든 빈 원자료 폴더 `out`을 지운다(다시 돌릴 때 '이미 있음'이
    되지 않게, 짝 없는 빈 폴더가 남지 않게)."""
    try:
        if is_inside(path, places.repo_root):
            raise StoreError("보관 자리가 저장소 안")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                f.write(data)
        except FileExistsError:
            raise StoreError("보관 파일이 이미 있음(덮어쓰지 않음)") from None
        except OSError as e:
            raise StoreError(f"보관 파일 쓰기 실패 ({type(e).__name__})") from None
    except StoreError as stop:
        try:
            out.rmdir()
        except OSError:
            raise StoreError(stop.detail + ", 빈 원자료 폴더를 지우지 못함", written=out) from None
        raise


def _make_raw_dir(places: BenchPlaces, facts: RunFacts, out: Path) -> None:
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.mkdir()
    except FileExistsError:
        raise StoreError("원자료 폴더가 이미 있음(덮어쓰지 않음)") from None
    except OSError as e:
        raise StoreError(f"원자료 폴더를 만들 수 없음 ({type(e).__name__})") from None
    # 만든 뒤 다시 본다: 중간 폴더가 정션이면 글 경로는 밖이어도 실제 자리는 저장소 안일 수 있다
    check_out_dir(
        out, run_kind=facts.run_kind, target_kind=facts.target_kind, repo_root=places.repo_root
    )


def _write_raw_files(out: Path, files: Mapping[str, bytes]) -> None:
    try:
        for name in RAW_FILES:
            if name in files:
                with (out / name).open("xb") as f:
                    f.write(files[name])
    except OSError as e:
        raise StoreError(f"원자료 쓰기 실패 ({type(e).__name__})", written=out) from None


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _where(errors: list[ContractError]) -> str:
    return "; ".join(map(str, errors[:5]))
