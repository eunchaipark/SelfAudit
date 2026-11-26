"""계약 읽기·검증: `bench/contracts/*.schema.json` (실험구조 2.2~2.4·2.10, 정한 것과 근거는 2.9).

`validate_contract`는 계약(스키마)을 본 뒤, 스키마로 쓸 수 없는 뜻 규칙(정답지·대상 목록)까지 본다.
오류 글에는 값을 싣지 않는다(위치와 규칙만).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Final, Literal

from common.schema import (
    MAX_ERRORS,
    ContractError,
    Json,
    SchemaUnsupportedError,
    check_schema,
    is_too_deep,
    validate,
)

__all__ = [
    "CONTRACTS_DIR",
    "CONTRACT_NAMES",
    "MAX_JSON_BYTES",
    "RESERVED_TARGET_IDS",
    "TARGET_MANIFEST_KEY",
    "ContractError",
    "ContractJsonError",
    "ContractName",
    "ContractViolationError",
    "Json",
    "SchemaUnsupportedError",
    "check_answers_semantics",
    "check_targets_semantics",
    "load_schema",
    "read_contract",
    "read_json",
    "validate_contract",
]

type ContractName = Literal["answers", "findings", "run", "targets"]

CONTRACT_NAMES: Final[tuple[ContractName, ...]] = ("answers", "findings", "run", "targets")
CONTRACTS_DIR: Final = Path(__file__).resolve().parents[1] / "contracts"
# 계약 파일 하나의 크기 상한. 가장 큰 결과(100개 × 칸 상한 1,100자 × UTF-8 4바이트 + notes)가
# 약 0.45MB라 그 9배쯤의 울타리다. 대화 기록(jsonl)은 이 함수로 읽지 않는다
MAX_JSON_BYTES: Final = 4 * 1024 * 1024
_ERRORS_IN_MESSAGE: Final = 20

_HIDDEN_KINDS: Final = frozenset({"split", "encoded", "obfuscated"})
# 정답지 하나의 위치 닻 상한(8.4 2). 지금 필요한 곳은 여섯 번들을 합쳐 8곳이라 번들 하나는 많아야
# 서너 곳이다. 100은 그 30배쯤의 울타리이고, 닻 겹침 검사(둘씩 비교)의 일을 묶는다.
MAX_LOCATION_ANCHORS: Final = 100
_REPO_KINDS: Final = frozenset({"planted", "practice"})
# 빈·문지기 실행의 `run.json` `target_id`(F-R06 2, 실험구조 8.5 2). 대상 목록에 같은 ID가 있으면
# 그 대상의 실행 ID(`empty-a-1-…`)가 빈·문지기 실행과 같은 꼴이 되어 이름만으로 가를 수 없다(8.8 5)
RESERVED_TARGET_IDS: Final = frozenset({"empty", "gate"})
# 대상 목록의 내 앱 지문 칸(F-R02 2㉡의 기준, 실험구조 8.9 2). 정답지의 같은 이름 칸과 뜻이 같다
TARGET_MANIFEST_KEY: Final = "bundle_manifest_sha256"
_ANSWERS_DIR: Final = "bench/answers"
_BUNDLES_DIR: Final = "bench/bundles"
_DRIVE: Final = re.compile("[A-Za-z]:")
REPO_ROOT: Final = CONTRACTS_DIR.parents[1]


class ContractJsonError(ValueError):
    """JSON으로 읽을 수 없다(없음·너무 큼·깨짐·같은 키·NaN·너무 깊음). 값은 싣지 않는다."""


class ContractViolationError(ValueError):
    """`read_contract`가 계약에 어긋난 파일을 만났다. `errors`에 어긋난 곳이 모두 있다."""

    def __init__(self, path: Path, errors: list[ContractError]) -> None:
        self.path = path
        self.errors = tuple(errors)
        shown = "; ".join(map(str, errors[:_ERRORS_IN_MESSAGE]))
        more = len(errors) - _ERRORS_IN_MESSAGE
        tail = f" … 외 {more}곳" if more > 0 else ""
        super().__init__(f"{path.name}: 계약에 어긋남 {len(errors)}곳 — {shown}{tail}")


# --- 읽기 ------------------------------------------------------------------------------------


def read_json(path: Path, max_bytes: int = MAX_JSON_BYTES) -> Json:
    """JSON 파일 하나를 엄격하게 읽는다(2.9): 크기 상한, UTF-8, 같은 키 두 번·NaN·Infinity·
    넘치는 수(`1e999`)·너무 긴 정수·MAX_DEPTH보다 깊은 값은 거절한다."""
    try:
        with path.open("rb") as f:
            data = f.read(max_bytes + 1)
    except OSError as e:
        raise ContractJsonError(f"{path.name}: 읽을 수 없음 ({type(e).__name__})") from None
    if len(data) > max_bytes:
        raise ContractJsonError(f"{path.name}: {max_bytes}바이트를 넘음")
    try:
        value: Json = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_no_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as e:
        # ValueError: 깨진 JSON·UTF-8 아님·너무 긴 정수. RecursionError: 아주 깊은 중첩
        raise ContractJsonError(
            f"{path.name}: JSON으로 읽을 수 없음 ({type(e).__name__})"
        ) from None
    if is_too_deep(value):
        raise ContractJsonError(f"{path.name}: 값이 너무 깊음")
    return value


def _unique_keys(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    out: dict[str, Json] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("같은 키가 두 번 있다")
        out[key] = value
    return out


def _no_constant(_name: str) -> Json:
    raise ValueError("NaN·Infinity는 JSON 값이 아니다")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("float 범위를 넘는 수")
    return value


def load_schema(name: ContractName) -> dict[str, Json]:
    """계약 하나를 읽고, 이 검증기가 다 아는 키워드만 바르게 쓰는지 확인한다."""
    schema = read_json(CONTRACTS_DIR / f"{name}.schema.json")
    if not isinstance(schema, dict):
        raise SchemaUnsupportedError(f"{name}: 계약 맨 위가 객체가 아님")
    check_schema(schema)
    return schema


def validate_contract(name: ContractName, instance: Json) -> list[ContractError]:
    """`instance`가 계약 `name`에 맞는지. 맞으면 빈 목록, 아니면 어긋난 곳(차례는 늘 같다).

    스키마에 맞을 때만 뜻 규칙(`answers`·`targets`)을 이어서 본다.
    """
    errors = validate(instance, load_schema(name))
    if errors or not isinstance(instance, dict):
        return errors
    if name == "answers":
        return check_answers_semantics(instance)
    if name == "targets":
        return check_targets_semantics(instance)
    return []


def read_contract(name: ContractName, path: Path) -> dict[str, Json]:
    """파일을 읽어 계약으로 검증한다. 어긋나면 `ContractViolationError`(오류 목록 포함)."""
    value = read_json(path)
    errors = validate_contract(name, value)
    if errors:
        raise ContractViolationError(path, errors)
    assert isinstance(value, dict)  # 네 계약 모두 맨 위가 type object라 검증을 지나면 객체다
    return value


# --- 뜻 규칙 (스키마에 맞은 값만 받는다) ---------------------------------------------------------


def check_answers_semantics(answers: Mapping[str, Json]) -> list[ContractError]:
    """정답지 뜻 규칙(2.10·8.4): 줄 범위, ID 고유, 종류와 난이도·complete, 풀어낸 값(정답·미끼),
    위치 닻·풀어낸 값이 다른 닻과 겹치지 않음(8.4 '닻 겹침')."""
    errors: list[ContractError] = []
    _check_origin(answers, errors)
    seen: set[str] = set()
    for group in ("items", "decoys"):
        for i, entry in enumerate(_objects(answers.get(group))):
            where = f"$.{group}[{i}]"
            entry_id = entry.get("id")
            if isinstance(entry_id, str):
                if entry_id in seen:
                    errors.append(ContractError(f"{where}.id", "id 겹침"))
                seen.add(entry_id)
            for j, location in enumerate(_objects(entry.get("locations"))):
                _check_location(location, f"{where}.locations[{j}]", errors)
            _check_decoded(entry, where, errors)
    _check_anchor_overlaps(answers, errors)
    return errors


def _check_origin(answers: Mapping[str, Json], errors: list[ContractError]) -> None:
    planted = answers.get("origin") == "planted"
    if (answers.get("difficulty") == "mixed") == planted:
        errors.append(ContractError("$.difficulty", "planted는 easy·normal·hard, practice는 mixed"))
    if answers.get("complete") is not planted:
        errors.append(ContractError("$.complete", "planted는 true, practice는 false"))


def _check_location(location: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    start, end, lines = (location.get(k) for k in ("line_start", "line_end", "file_lines"))
    if not (isinstance(start, int | float) and isinstance(end, int | float)):
        return
    if end < start:
        errors.append(ContractError(where, "line_end >= line_start"))
    if isinstance(lines, int | float) and end > lines:
        errors.append(ContractError(where, "line_end <= file_lines"))


def _anchor_texts(answers: Mapping[str, Json]) -> list[tuple[str, str, str, str]]:
    """정답지의 닻 글 모두: (주인 정답·미끼 자리, 칸 자리, 칸 종류, 글)."""
    texts: list[tuple[str, str, str, str]] = []
    for group in ("items", "decoys"):
        for i, entry in enumerate(_objects(answers.get(group))):
            owner = f"$.{group}[{i}]"
            for key in ("anchor", "decoded_anchor"):
                value = entry.get(key)
                if isinstance(value, str):
                    texts.append((owner, f"{owner}.{key}", key, value))
            for j, location in enumerate(_objects(entry.get("locations"))):
                value = location.get("anchor")
                if isinstance(value, str):
                    texts.append((owner, f"{owner}.locations[{j}].anchor", "location", value))
    return texts


def _overlap(a: str, b: str) -> str | None:
    if a == b:
        return "같음"
    if a in b or b in a:
        return "들어 있음"
    return None


def _check_anchor_overlaps(answers: Mapping[str, Json], errors: list[ContractError]) -> None:
    """닻 겹침(8.4 2·6). 위치 닻과 풀어낸 값은 번들 안 고유성(F-B07 6)을 받지 않거나(풀어낸 값)
    새 칸이라, 정답지 안에서 다른 닻과 '같음'·'들어 있음'(어느 쪽이 어느 쪽 안이든)을 막는다.

    - 다른 정답·미끼: 위치 닻·풀어낸 값 ↔ 그쪽의 닻·풀어낸 값·위치 닻 — 같음·들어 있음 모두 오류.
      한 결과의 evidence가 두 정답(또는 정답과 미끼)에 같이 맞게 되기 때문이다.
    - 같은 정답·미끼: 위치 닻 ↔ 자기 닻 — 같음·들어 있음 오류(닻이 이미 그 자리를 가리키거나,
      위치 닻이 닻이 나오는 다른 자리에도 나온다). 위치 닻 ↔ 자기 풀어낸 값 — 같음만 오류.
      나눠 쓴 값은 조각(위치 닻)이 풀어낸 값 안에 드는 것이 정상이다(N2-01).
      자기 위치 닻끼리는 보지 않는다(같은 정답을 가리킬 뿐이다).

    비용: 둘씩 비교라 닻 글 수의 제곱이다. 위치 닻은 정답지 하나에 MAX_LOCATION_ANCHORS(100)까지,
    닻·풀어낸 값은 정답 200 + 미끼 50의 두 칸(500)이라 많아야 600 × 350쌍, 각 글 200자 —
    2진 글자 꼴 최악에서 0.25초쯤(2026-11-24 잼, 실험구조 8.4 '닻 겹침').
    오류는 MAX_ERRORS에서 멈춘다.
    """
    texts = _anchor_texts(answers)
    if sum(1 for _, _, kind, _ in texts if kind == "location") > MAX_LOCATION_ANCHORS:
        errors.append(ContractError("$", f"위치 닻 {MAX_LOCATION_ANCHORS}개 넘음"))
        return
    found = 0
    for i, (owner, where, kind, text) in enumerate(texts):
        if kind == "anchor":
            continue  # 닻끼리는 F-B07 6(번들 안 고유성)이 본다
        for j, (other_owner, other_where, other_kind, other) in enumerate(texts):
            if i == j or (other_kind != "anchor" and j < i):
                continue  # 새 칸끼리는 한 번만
            if other_owner == owner:
                pair = {kind, other_kind}
                if pair == {"location", "anchor"}:
                    rule = _overlap(text, other)
                elif pair == {"location", "decoded_anchor"}:
                    rule = "같음" if text == other else None
                else:
                    continue  # 풀어낸 값 ↔ 자기 닻은 _check_decoded, 자기 위치 닻끼리는 보지 않음
            else:
                rule = _overlap(text, other)
            if rule is None:
                continue
            if found >= MAX_ERRORS:
                errors.append(ContractError("$", f"닻 겹침 {MAX_ERRORS}곳에서 멈춤, 나머지 생략"))
                return
            errors.append(ContractError(where, f"닻 겹침: {rule} ({other_where})"))
            found += 1


def _check_decoded(item: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    """풀어낸 값(정답·미끼, 8.4 6): 숨긴 방법이 split·encoded·obfuscated일 때만, anchor와 다르게.

    미끼는 `hiding`이 선택 칸이라 없으면 숨긴 방법이 아닌 것으로 본다."""
    decoded = item.get("decoded_anchor")
    if decoded is None:
        return
    if item.get("hiding") not in _HIDDEN_KINDS:
        errors.append(ContractError(f"{where}.decoded_anchor", "split·encoded·obfuscated만"))
    if decoded == item.get("anchor"):
        errors.append(ContractError(f"{where}.decoded_anchor", "anchor와 같음"))


def check_targets_semantics(
    targets: Mapping[str, Json], repo_root: Path = REPO_ROOT
) -> list[ContractError]:
    """대상 목록 뜻 규칙(2.9·2.10·8.8 5·8.9 2, F-B05): ID 고유, 예약 ID(`empty`·`gate`) 아님, 저장소
    대상은 `bench/bundles/<id>`·`bench/answers/<id>.json`이고 지문 칸이 없음(정답지가 기준), 내 앱은
    드라이브 절대 경로이고 풀어 본 뒤에도 저장소 밖이며 지문 칸 `bundle_manifest_sha256`이 있음."""
    errors: list[ContractError] = []
    seen: set[str] = set()
    for i, entry in enumerate(_objects(targets.get("targets"))):
        where = f"$.targets[{i}]"
        target_id = entry.get("id")
        if isinstance(target_id, str):
            if target_id in RESERVED_TARGET_IDS:
                errors.append(ContractError(f"{where}.id", "예약 ID(empty·gate)"))
            if target_id in seen:
                errors.append(ContractError(f"{where}.id", "id 겹침"))
            seen.add(target_id)
        if entry.get("kind") in _REPO_KINDS:
            _check_repo_target(entry, where, errors)
        else:
            _check_mine_target(entry, where, repo_root, errors)
    return errors


def _check_repo_target(entry: Mapping[str, Json], where: str, errors: list[ContractError]) -> None:
    target_id = entry.get("id")
    if entry.get("bundle") != f"{_BUNDLES_DIR}/{target_id}":
        errors.append(ContractError(f"{where}.bundle", "bench/bundles/<id>"))
    if entry.get("answers") != f"{_ANSWERS_DIR}/{target_id}.json":
        errors.append(ContractError(f"{where}.answers", "bench/answers/<id>.json"))
    if TARGET_MANIFEST_KEY in entry:
        errors.append(ContractError(f"{where}.{TARGET_MANIFEST_KEY}", "mine만(정답지가 기준)"))


def _check_mine_target(
    entry: Mapping[str, Json], where: str, repo_root: Path, errors: list[ContractError]
) -> None:
    bundle, answers = entry.get("bundle"), entry.get("answers")
    if not (isinstance(bundle, str) and _is_outside_drive_path(bundle, repo_root)):
        errors.append(ContractError(f"{where}.bundle", "mine은 저장소 밖 드라이브 절대 경로"))
    if answers is not None and not (
        isinstance(answers, str) and _is_outside_drive_path(answers, repo_root)
    ):
        errors.append(
            ContractError(f"{where}.answers", "mine은 null 또는 저장소 밖 드라이브 절대 경로")
        )
    if TARGET_MANIFEST_KEY not in entry:
        errors.append(ContractError(f"{where}.{TARGET_MANIFEST_KEY}", "mine은 지문 칸이 있어야 함"))


def _is_outside_drive_path(path: str, repo_root: Path) -> bool:
    """`C:\\…` 꼴만(UNC `\\\\server`·`\\\\?\\`·`\\\\.\\` 거절), 그리고 풀어 본 뒤 저장소 밖."""
    pure = PureWindowsPath(path)
    if not (pure.is_absolute() and _DRIVE.fullmatch(pure.drive)):
        return False
    resolved = Path(path).resolve()
    return not resolved.is_relative_to(repo_root.resolve())


def _objects(value: Json) -> list[dict[str, Json]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []
