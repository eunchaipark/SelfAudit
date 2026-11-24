"""F-B03 정답지 만들기: 원본의 정답 목록 `answers.in.json` + 빌드 결과 → `bench/answers/<id>.json`.

번들을 고치면 `python -m sources.build_tools answers <id>` 하나로 번들과 정답지를 다시 만든다(R3·R4
'명령 하나로 다시', T22 반려 1 3). 줄 번호는 닻을 검색해 얻지 않는다 —
닻 검색으로 위치를 만들면 F-B07 6 닻 고유성 검사가 뜻을 잃는다.
대신 위치마다 **줄 표식**(결과물의 그 줄에만 있는 글)을 적는다.

`answers.in.json` 꼴(`selfaudit-bench/answers-in@1`):
- 맨 위: `schema`, `bundle_id`, `origin`, `difficulty`, `items`, `decoys`
- 정답: `id`, `categories`, `hiding`, `anchor`, `decoded_anchor`, `at`, `planted`, `why`
- 미끼: `id`, `hiding`, `anchor`, `decoded_anchor`(없어도 됨), `at`, `why`
- `anchor`·`decoded_anchor`: 글 그대로, `null`, `{"value": "<정답 ID>", "chain": "split:2:0"}`
  (심기 계획의 가짜 값, `chain`은 원본 자리 `{{v:ID|…}}`의 걸러내기와 같은 꼴, 없어도 됨), 또는
  `{"map_of": "<src 안 경로>"}`(그 파일 결과물의 맵 파일 이름 — 해시가 내용에 달려 손으로 못 적는다)
- `at`: `[{"file": "<src 안 경로>", "marker": "<그 줄에만 있는 글>"} | {"file": …, "map": true}]` —
  `map`이면 그 파일 소스맵의 1줄. 위치마다 `anchor`(위치 닻, F-B03 12 — 글이나 위 `value` 꼴)를
  더할 수 있다
오류 글에는 값(닻·줄 표식)을 싣지 않는다 — 정답 ID·경로만.

**64자 앞 조각**(F-B03 5, 설계 8.8 2): 줄로 가를 수 없는 위치가 있는 정답·미끼의 닻·풀어낸 값이
64자를 넘으면 명령이 앞 조각으로 줄인다. 닻은 16자부터 한 자씩 늘려 번들 안 나오는 곳이 모두
그 정답(미끼)의 위치 안인 첫 길이(F-B07 6), 풀어낸 값은 번들 글 어디에도 없고 다른 정답·미끼의
닻·풀어낸 값·위치 닻과 어느 쪽으로도 겹치지 않는 첫 길이. 64자 안에 없으면 멈춘다(번들을 고친다).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Final

from common.contracts import ContractJsonError, Json, read_json, validate_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from common.paths import resolve_in_bundle
from sources.build_tools import build as build_module
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, BuildResult, Filter, build
from sources.build_tools.verify import ANCHOR_SHORT_MAX, covers_file, places, text_files

__all__ = ["ANSWERS_DIR", "ANSWERS_IN", "LocateError", "write_answers"]

ANSWERS_DIR: Final = BUNDLES_DIR.parent / "answers"
ANSWERS_IN: Final = "answers.in.json"
IN_SCHEMA: Final = "selfaudit-bench/answers-in@1"
ANSWERS_SCHEMA: Final = "selfaudit-bench/answers@1"
MAP_LINE: Final = 1  # 소스맵은 한 줄 JSON이다(sourcemap.render_map)
SHORT_MIN: Final = 16  # 64자 앞 조각의 가장 짧은 길이(F-B03 5)
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
    _shorten(answers, text_files(result.bundle_dir))
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
                "locations": _locations(raw.get("at"), result, entry_id, filters),
                "anchor": _anchor(raw.get("anchor"), result, filters, entry_id),
                "decoded_anchor": _anchor(raw.get("decoded_anchor"), result, filters, entry_id),
                "planted": raw.get("planted"),
                "why": raw.get("why"),
            }
        )
    decoys: list[Json] = []
    for raw in _objects(spec.get("decoys")):
        entry_id = str(raw.get("id"))
        decoy: dict[str, Json] = {
            "id": entry_id,
            "locations": _locations(raw.get("at"), result, entry_id, filters),
            "anchor": _anchor(raw.get("anchor"), result, filters, entry_id),
        }
        if raw.get("hiding") is not None:  # 선택 칸(F-B03 7) — 심은 번들은 F-B07 19가 꼭 본다
            decoy["hiding"] = raw["hiding"]
        decoded = _anchor(raw.get("decoded_anchor"), result, filters, entry_id)
        if decoded is not None:
            decoy["decoded_anchor"] = decoded
        decoy["why"] = raw.get("why")
        decoys.append(decoy)
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
    """글 그대로, `null`, 심기 계획의 가짜 값(+ 걸러내기), 또는 결과물 맵 파일 이름(`map_of`)."""
    if raw is None or isinstance(raw, str):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("map_of"), str):
        out_rel = result.files.get(str(raw["map_of"]))
        if out_rel is None:
            raise LocateError(f"{entry_id}: map_of의 파일이 src에 없음")
        return f"{PurePosixPath(out_rel).name}.map"
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


def _locations(
    raw: Json, result: BuildResult, entry_id: str, filters: Mapping[str, Filter]
) -> list[Json]:
    if not isinstance(raw, list) or not raw:
        raise LocateError(f"{entry_id}: at은 위치 하나 이상의 목록")
    out: list[Json] = []
    for at in raw:
        location = _location(at, result, entry_id)
        if isinstance(at, dict) and at.get("anchor") is not None:
            location["anchor"] = _anchor(at["anchor"], result, filters, entry_id)
        out.append(location)
    return out


def _location(at: Json, result: BuildResult, entry_id: str) -> dict[str, Json]:
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


def _shorten(answers: Mapping[str, Json], texts: Mapping[str, bytes]) -> None:
    """F-B03 5: 줄로 가를 수 없는 위치가 있는 정답·미끼의 64자 넘는 닻·풀어낸 값을 앞 조각으로.

    닻을 먼저 모두 정하고(풀어낸 값의 겹침을 정해진 닻과 견주려고), 풀어낸 값은 정답지 차례로.
    """
    entries = [*_objects(answers.get("items")), *_objects(answers.get("decoys"))]
    for entry in entries:
        anchor = entry.get("anchor")
        if _needs_short(entry, anchor):
            assert isinstance(anchor, str)
            entry["anchor"] = _short_anchor(entry, anchor, texts)
    for entry in entries:
        decoded = entry.get("decoded_anchor")
        if _needs_short(entry, decoded):
            assert isinstance(decoded, str)
            others = [t for e in entries if e is not entry for t in _anchor_texts(e)]
            entry["decoded_anchor"] = _short_decoded(entry, decoded, texts, others)


def _needs_short(entry: Mapping[str, Json], value: Json) -> bool:
    if not isinstance(value, str) or len(value) <= ANCHOR_SHORT_MAX:
        return False
    return any(covers_file(loc) for loc in _objects(entry.get("locations")))


def _short_anchor(entry: Mapping[str, Json], anchor: str, texts: Mapping[str, bytes]) -> str:
    """앞에서부터 16자 이상, 번들 안 나오는 곳이 모두 그 정답(미끼)의 위치 안인 가장 짧은 조각."""
    locations = _objects(entry.get("locations"))
    for length in range(SHORT_MIN, ANCHOR_SHORT_MAX + 1):
        piece = anchor[:length]
        if _only_inside(locations, places(texts, piece.encode("utf-8"))):
            return piece
    raise LocateError(f"{entry.get('id')}: 64자 안에 번들에서 고유한 닻 앞 조각이 없음")


def _short_decoded(
    entry: Mapping[str, Json], decoded: str, texts: Mapping[str, bytes], others: Sequence[str]
) -> str:
    """앞에서부터 16자 이상, 번들 글 어디에도 없고(㉠) 다른 정답·미끼의 닻 글과 어느 쪽으로도
    겹치지 않는(㉡) 가장 짧은 조각(㉢, 설계 8.8 2). 자기 닻·위치 닻과는 같지만 않으면 된다."""
    own = [t for t in _anchor_texts(entry) if t != decoded]
    for length in range(SHORT_MIN, ANCHOR_SHORT_MAX + 1):
        piece = decoded[:length]
        needle = piece.encode("utf-8")
        if any(needle in data for data in texts.values()):
            continue
        if any(piece in other or other in piece for other in others):
            continue
        if piece not in own:
            return piece
    raise LocateError(f"{entry.get('id')}: 64자 안에 겹치지 않는 풀어낸 값 앞 조각이 없음")


def _anchor_texts(entry: Mapping[str, Json]) -> list[str]:
    texts = [v for v in (entry.get("anchor"), entry.get("decoded_anchor")) if isinstance(v, str)]
    for loc in _objects(entry.get("locations")):
        value = loc.get("anchor")
        if isinstance(value, str):
            texts.append(value)
    return texts


def _only_inside(locations: Sequence[Mapping[str, Json]], found: Iterable[tuple[str, int]]) -> bool:
    """나오는 곳이 하나 이상이고 모두 위치 안(흘려 보내며, 밖이 하나 나오면 멈춘다)."""
    seen = False
    for rel, line in found:
        if not _inside(locations, rel, line):
            return False
        seen = True
    return seen


def _inside(locations: Sequence[Mapping[str, Json]], rel: str, line: int) -> bool:
    return any(
        loc.get("file") == rel and _int(loc.get("line_start")) <= line <= _int(loc.get("line_end"))
        for loc in locations
    )


def _int(value: Json) -> int:
    return int(value) if isinstance(value, int | float) else 0


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
