"""F-B03 정답지 만들기: 원본의 정답 목록 `answers.in.json` + 빌드 결과 → `bench/answers/<id>.json`.

번들을 고치면 `python -m sources.build_tools answers <id>` 하나로 번들과 정답지를 다시 만든다(R3·R4
'명령 하나로 다시', T22 반려 1 3). 줄 번호는 닻을 검색해 얻지 않는다 —
닻 검색으로 위치를 만들면 F-B07 6 닻 고유성 검사가 뜻을 잃는다.
대신 위치마다 **줄 표식**(결과물의 그 줄에만 있는 글)을 적는다.

`answers.in.json` 꼴(`selfaudit-bench/answers-in@1`):
- 맨 위: `schema`, `bundle_id`, `origin`, `difficulty`, `items`, `decoys`
- 정답: `id`, `categories`, `hiding`, `anchor`, `decoded_anchor`, `at`, `planted`, `why`
- 미끼: `id`, `anchor`, `at`, `why`
- `anchor`·`decoded_anchor`: 글 그대로, `null`, 또는 `{"value": "<정답 ID>", "chain": "split:2:0"}`
  (심기 계획의 가짜 값, `chain`은 원본 자리 `{{v:ID|…}}`의 걸러내기와 같은 꼴, 없어도 됨)
- `at`: `[{"file": "<src 안 경로>", "marker": "<그 줄에만 있는 글>"} | {"file": …, "map": true}]` —
  `map`이면 그 파일 소스맵의 1줄
오류 글에는 값(닻·줄 표식)을 싣지 않는다 — 정답 ID·경로만.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from common.contracts import ContractJsonError, Json, read_json, validate_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from common.paths import resolve_in_bundle
from sources.build_tools import build as build_module
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, BuildResult, Filter, build

__all__ = ["ANSWERS_DIR", "ANSWERS_IN", "LocateError", "write_answers"]

ANSWERS_DIR: Final = BUNDLES_DIR.parent / "answers"
ANSWERS_IN: Final = "answers.in.json"
IN_SCHEMA: Final = "selfaudit-bench/answers-in@1"
ANSWERS_SCHEMA: Final = "selfaudit-bench/answers@1"
MAP_LINE: Final = 1  # 소스맵은 한 줄 JSON이다(sourcemap.render_map)
_LF: Final = chr(0x0A)


class LocateError(ValueError):
    """정답지를 만들 수 없다(목록 꼴·줄 표식·계약). 글에는 정답 ID·경로만."""


def write_answers(
    bundle_id: str,
    sources_dir: Path = SOURCES_DIR,
    bundles_dir: Path = BUNDLES_DIR,
    answers_dir: Path = ANSWERS_DIR,
) -> tuple[Path, BuildResult]:
    """F-B03: 번들을 다시 빌드하고(F-B01, 같은 원본이면 같은 바이트) 정답지를 쓴다.

    돌려주는 것은 정답지 경로와 빌드 결과(경고 포함).
    """
    result = build(bundle_id, sources_dir, bundles_dir)
    spec = _read_spec(sources_dir / bundle_id / ANSWERS_IN, bundle_id)
    plan = build_module._read_plan(sources_dir / bundle_id / build_module.PLAN_NAME, bundle_id)
    filters, _steps = build_module._load_plugins(plan.plugins, bundle_id)
    answers = _make_answers(spec, result, filters)
    errors = validate_contract("answers", answers)
    if errors:
        shown = "; ".join(map(str, errors[:10]))
        raise LocateError(f"{bundle_id}: 만든 정답지가 계약에 어긋남 — {shown}")
    path = answers_dir / f"{bundle_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(answers, ensure_ascii=False, indent=2) + _LF).encode("utf-8"))
    return path, result


def _read_spec(path: Path, bundle_id: str) -> dict[str, Json]:
    try:
        spec = read_json(path)
    except ContractJsonError as e:
        raise LocateError(f"{bundle_id}: {ANSWERS_IN} — {e}") from None
    if not isinstance(spec, dict) or spec.get("schema") != IN_SCHEMA:
        raise LocateError(f"{bundle_id}: {ANSWERS_IN} schema는 {IN_SCHEMA}")
    if spec.get("bundle_id") != bundle_id:
        raise LocateError(f"{bundle_id}: {ANSWERS_IN} bundle_id가 폴더 이름과 다름")
    return spec


def _make_answers(
    spec: Mapping[str, Json], result: BuildResult, filters: Mapping[str, Filter]
) -> dict[str, Json]:
    difficulty = spec.get("difficulty")
    items: list[Json] = []
    for raw in _objects(spec.get("items")):
        entry_id = str(raw.get("id"))
        items.append(
            {
                "id": entry_id,
                "categories": raw.get("categories"),
                "difficulty": difficulty,
                "hiding": raw.get("hiding"),
                "locations": _locations(raw.get("at"), result, entry_id),
                "anchor": _anchor(raw.get("anchor"), result, filters, entry_id),
                "decoded_anchor": _anchor(raw.get("decoded_anchor"), result, filters, entry_id),
                "planted": raw.get("planted"),
                "why": raw.get("why"),
            }
        )
    decoys: list[Json] = []
    for raw in _objects(spec.get("decoys")):
        entry_id = str(raw.get("id"))
        decoys.append(
            {
                "id": entry_id,
                "locations": _locations(raw.get("at"), result, entry_id),
                "anchor": _anchor(raw.get("anchor"), result, filters, entry_id),
                "why": raw.get("why"),
            }
        )
    return {
        "schema": ANSWERS_SCHEMA,
        "bundle_id": result.bundle_id,
        "origin": spec.get("origin"),
        "difficulty": difficulty,
        "bundle_manifest_sha256": bundle_manifest_sha256(result.bundle_dir),
        "complete": spec.get("origin") == "planted",
        "items": items,
        "decoys": decoys,
    }


def _anchor(raw: Json, result: BuildResult, filters: Mapping[str, Filter], entry_id: str) -> Json:
    """글 그대로, `null`, 또는 심기 계획의 가짜 값(+ 걸러내기)."""
    if raw is None or isinstance(raw, str):
        return raw
    if not isinstance(raw, dict) or not isinstance(raw.get("value"), str):
        raise LocateError(f"{entry_id}: anchor는 글·null·{{'value': 정답 ID}}")
    value = result.values.get(str(raw["value"]))
    if value is None:
        raise LocateError(f"{entry_id}: value의 정답 ID가 원본 자리에 쓰이지 않음")
    chain = raw.get("chain", "")
    if not isinstance(chain, str):
        raise LocateError(f"{entry_id}: chain은 글")
    for part in filter(None, chain.split("|")):
        name, *args = part.split(":")
        func = filters.get(name)
        if func is None:
            raise LocateError(f"{entry_id}: 걸러내기 {name!r}를 주는 plugins가 없음")
        value = func(value, args)
    return value


def _locations(raw: Json, result: BuildResult, entry_id: str) -> list[Json]:
    if not isinstance(raw, list) or not raw:
        raise LocateError(f"{entry_id}: at은 위치 하나 이상의 목록")
    return [_location(at, result, entry_id) for at in raw]


def _location(at: Json, result: BuildResult, entry_id: str) -> Json:
    if not isinstance(at, dict) or not isinstance(at.get("file"), str):
        raise LocateError(f"{entry_id}: 위치마다 file(src 안 경로)이 필요")
    out_rel = result.files.get(str(at["file"]))
    if out_rel is None:
        raise LocateError(f"{entry_id}: src에 없는 파일: {at['file']}")
    if at.get("map") is True:
        out_rel = f"{out_rel}.map"
        line = MAP_LINE
        data = _read(result.bundle_dir, out_rel, entry_id)
    else:
        marker = at.get("marker")
        if not isinstance(marker, str) or not marker or _LF in marker:
            raise LocateError(f"{entry_id}: marker는 한 줄 글")
        data = _read(result.bundle_dir, out_rel, entry_id)
        line = _marker_line(data, marker, entry_id, out_rel)
    return {"file": out_rel, "line_start": line, "line_end": line, "file_lines": count_lines(data)}


def _read(bundle_dir: Path, out_rel: str, entry_id: str) -> bytes:
    path = resolve_in_bundle(bundle_dir, out_rel)
    if not path.is_file():
        raise LocateError(f"{entry_id}: 결과물에 없는 파일: {out_rel}")
    return path.read_bytes()


def _marker_line(data: bytes, marker: str, entry_id: str, out_rel: str) -> int:
    """줄 표식이 든 줄(1부터). 한 줄에만 있어야 한다 — 둘 이상이면 어느 줄인지 정해지지 않는다."""
    needle = marker.encode("utf-8")
    found = [i for i, line in enumerate(data.split(_LF.encode("ascii")), start=1) if needle in line]
    if len(found) != 1:
        raise LocateError(f"{entry_id}: {out_rel}에서 줄 표식이 {len(found)}줄에 있음(1줄이어야)")
    return found[0]


def _objects(value: Json) -> Sequence[dict[str, Json]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []
