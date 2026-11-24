"""F-B07 번들 구성 검사 — 번들 하나(규칙 2~14·16~20)와 대상 목록 한 줄(F-B05 4).

여섯 번들을 모아 보는 것(규칙 1, 규칙 4의 '난이도마다 8개', 규칙 15 같은 방법 미끼, bench 전체
서비스 꼴)은 `tests/bundles/test_f_b07_suite.py`가 이 결과(`BundleReport.categories`·
`item_hidings`·`decoy_hidings`)로 센다.
찍는 글에는 값(닻·풀어낸 값·파일 글)이 없다 — 정답 ID·경로·줄·규칙 번호만
(F-B07 출력, 보안코딩 '실험').
"""

from __future__ import annotations

import heapq
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from common.contracts import (
    ContractJsonError,
    Json,
    read_contract,
    read_json,
    validate_contract,
)
from common.fingerprint import ManifestError, bundle_manifest_sha256, manifest_lines
from common.lines import count_lines, window_covers_file
from common.paths import resolve_in_bundle
from sources.build_tools import fake
from sources.build_tools.build import BUILD_DIR

__all__ = [
    "ANCHOR_SHORT_MAX",
    "COVER_TOLERANCE",
    "DECOYS_RANGE",
    "DECOY_DISTANCE",
    "ENCODED_LENGTH_RATIO",
    "HIDING_BY_DIFFICULTY",
    "ITEMS_RANGE",
    "MIN_CATEGORIES",
    "BundleReport",
    "CoverRow",
    "Problem",
    "Target",
    "check_bundle",
    "check_target",
    "covers_file",
    "decoy_hiding_gaps",
    "encoding_of",
    "format_cover_table",
    "places",
    "repo_target",
    "text_files",
]

REPO_ROOT: Final = BUILD_DIR.parents[2]
TARGETS_PATH: Final = REPO_ROOT / "bench" / "targets.json"
# F-B07 3: 심은 번들마다 정답 8~10개, 미끼 2~3개(설계 2.7 표)
ITEMS_RANGE: Final = (8, 10)
DECOYS_RANGE: Final = (2, 3)
# F-B07 4: 번들마다 주·보조 범주를 합쳐 8개 가운데 6개 이상
MIN_CATEGORIES: Final = 6
# F-B07 13: 줄 허용 범위 T = 2 (F-G02 2㉢)
COVER_TOLERANCE: Final = 2
# F-B02 규칙 3: 난이도마다 쓰는 숨기는 방법. 그 밖에는 `none`만
HIDING_BY_DIFFICULTY: Final[Mapping[str, frozenset[str]]] = {
    "easy": frozenset({"plain", "comment", "config"}),
    "normal": frozenset({"split", "encoded", "config"}),
    "hard": frozenset({"obfuscated", "sourcemap_only", "split"}),
}
HIDING_ANYWHERE: Final = "none"
RECORDED_DIFFICULTIES: Final = frozenset({"normal", "hard"})
# 규칙 6㉯: 위치 밖에서 나온 곳을 이만큼 찾으면 더 찾지 않는다(실패는 이미 정해졌고,
# 알릴 곳은 몇 개면 된다 — 같은 글자가 이어진 큰 파일에서 나온 곳을 다 모으면
# 메모리가 입력의 수십 배가 된다, 반려 1 1)
MAX_OUTSIDE_PLACES: Final = 5
# 규칙 16 (F-B03 5): 줄로 가를 수 없는 위치가 있는 정답·미끼의 닻 상한 — evidence 300자의 약 1/5
ANCHOR_SHORT_MAX: Final = 64
# 규칙 17 (F-B02 9): 같은 인코딩 정답·미끼의 길이 비(긴 쪽 ÷ 짧은 쪽) 상한
ENCODED_LENGTH_RATIO: Final = 1.5
# 규칙 20 (설계 8.8 6): 미끼 닻과 정답 닻을 함께 덮는 가장 짧은 구간이 이 글자 수를 넘어야 한다.
# 결과 계약 evidence 상한(findings.schema.json maxLength)과 같은 값 — 시험이 둘이 같은지 본다
DECOY_DISTANCE: Final = 300
# 규칙 20을 어긴 짝을 이만큼 찾으면 그 번들에서 더 찾지 않는다
# (실패는 정해졌고 알릴 곳은 몇 개면 된다)
MAX_DISTANCE_PROBLEMS: Final = 20
# 규칙 18 (F-B02 6): 예약 이름(RFC 2606). 뒤에 이름 글자가 이어지면(`.testing`) 예약 이름이 아니다
RESERVED_NAME: Final = re.compile(r"\.(?:example|test|invalid|localhost)(?![A-Za-z0-9-])", re.I)
_HEX: Final = re.compile(r"(?:[0-9a-f]{2})+")
_BASE64: Final = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_HEX_CHARS: Final = frozenset(b"0123456789abcdef")
_BASE64_CHARS: Final = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
)
_ENCODED: Final = "encoded"
_LF: Final = 0x0A
_CR: Final = 0x0D
_TAB: Final = chr(0x09)
_ANCHOR_FIELDS: Final = (".anchor", ".decoded_anchor")
_MAX_LENGTH: Final = "maxLength"


@dataclass(frozen=True)
class Problem:
    """규칙 하나를 어긴 곳. `where`는 정답(미끼) ID·`경로:줄`·계약 칸 위치."""

    rule: str
    where: str
    reason: str

    def __str__(self) -> str:
        if self.rule == "9":  # F-B07 예시 꼴: `AWS 접근 키 bench/bundles/…:줄`
            return f"규칙 9 {self.reason} {self.where}"
        return f"규칙 {self.rule} {self.where}: {self.reason}"


@dataclass(frozen=True)
class CoverRow:
    """F-B07 13 확인 기록 한 줄: 이 위치의 줄 허용 범위가 파일 전체를 덮는가."""

    entry_id: str
    file: str
    line_start: int
    line_end: int
    file_lines: int
    covers: bool


@dataclass(frozen=True)
class BundleReport:
    bundle_id: str
    difficulty: str | None
    problems: tuple[Problem, ...]
    cover_rows: tuple[CoverRow, ...]
    categories: frozenset[str]  # 주·보조 범주를 합친 것(T25가 난이도마다 모은다)
    item_hidings: frozenset[str] = frozenset()  # 정답의 숨긴 방법(규칙 15, 난이도마다 모은다)
    decoy_hidings: frozenset[str] = frozenset()  # 미끼의 숨긴 방법


@dataclass(frozen=True)
class Target:
    """대상 목록 한 줄(F-B05). 저장소 대상은 경로를 저장소 맨 위 기준으로 푼 것."""

    id: str
    kind: str
    bundle_dir: Path
    answers_path: Path | None


@dataclass(frozen=True)
class _Entry:
    id: str
    locations: tuple[Mapping[str, Json], ...]
    anchor: str | None
    decoded: str | None = None
    hiding: str | None = None
    decoy: bool = False

    def location_anchors(self) -> list[tuple[int, str]]:
        return [
            (i, str(loc["anchor"]))
            for i, loc in enumerate(self.locations)
            if isinstance(loc.get("anchor"), str)
        ]


# --- 대상 -----------------------------------------------------------------------------------


def repo_target(
    bundle_id: str, targets_path: Path = TARGETS_PATH, repo_root: Path = REPO_ROOT
) -> Target:
    """저장소 안 대상 목록에서 한 줄. 계약·뜻 규칙(F-B05 1·2·5)은 `read_contract`가 본다."""
    targets = read_contract("targets", targets_path)
    for entry in _objects(targets.get("targets")):
        if entry.get("id") != bundle_id:
            continue
        bundle, answers = entry.get("bundle"), entry.get("answers")
        if not isinstance(bundle, str) or not isinstance(answers, str):
            break
        return Target(bundle_id, str(entry.get("kind")), repo_root / bundle, repo_root / answers)
    raise LookupError(f"대상 목록에 없거나 정답지가 없음: {bundle_id}")


def check_target(target: Target) -> BundleReport:
    """F-B07 번들 하나 + F-B05 4(종류 = 정답지 `origin`)."""
    if target.answers_path is None:
        return _failed(target.id, Problem("2", "$", "정답지가 없는 대상(mine)은 검사하지 않음"))
    if not target.bundle_dir.is_dir():
        return _failed(target.id, Problem("F-B05", "bundle", "번들 폴더 없음"))
    try:
        answers = read_json(target.answers_path)
    except ContractJsonError as e:
        return _failed(target.id, Problem("2", "$", str(e)))
    report = check_bundle(target.bundle_dir, answers)
    extra: list[Problem] = []
    if isinstance(answers, dict):
        if answers.get("origin") != target.kind:
            extra.append(Problem("F-B05 4", "$.origin", "대상 목록의 종류와 다름"))
        if answers.get("bundle_id") != target.id:
            extra.append(Problem("2", "$.bundle_id", "대상 ID와 다름"))
    return BundleReport(
        report.bundle_id,
        report.difficulty,
        report.problems + tuple(extra),
        report.cover_rows,
        report.categories,
        report.item_hidings,
        report.decoy_hidings,
    )


def _failed(bundle_id: str, problem: Problem) -> BundleReport:
    return BundleReport(bundle_id, None, (problem,), (), frozenset())


# --- 번들 하나 --------------------------------------------------------------------------------


def check_bundle(bundle_dir: Path, answers: Json) -> BundleReport:
    """F-B07 2~13: 정답지 `answers`(읽은 값)가 번들 `bundle_dir`과 맞는지."""
    name = bundle_dir.name
    errors = validate_contract("answers", answers)
    if errors or not isinstance(answers, dict):
        failed = tuple(Problem(_contract_rule(e.where, e.rule), e.where, e.rule) for e in errors)
        return BundleReport(name, None, failed, (), frozenset())
    bundle_id = str(answers["bundle_id"])
    difficulty = str(answers["difficulty"])
    items = _objects(answers["items"])
    decoys = _objects(answers["decoys"])
    entries = [_entry(e, decoy=False) for e in items] + [_entry(e, decoy=True) for e in decoys]
    categories = frozenset(str(c) for item in items for c in _strings(item.get("categories")))
    problems: list[Problem] = []
    if answers["origin"] == "planted":
        _check_counts(items, decoys, problems)
        _check_categories(categories, problems)
        _check_hiding(items, difficulty, problems)
        _check_decoy_hiding(decoys, problems)
    files = _read_bundle(bundle_dir, problems)
    if files is not None:
        texts = _text_files(files)
        _check_fingerprint(bundle_dir, answers, problems)
        _check_locations(entries, files, problems)
        _check_anchors(entries, texts, problems)
        _check_location_anchors(entries, texts, problems)
        _check_unsplittable(entries, texts, problems)
        _check_encoded_lengths(entries, texts, problems)
        _check_distance(entries, texts, problems)
        _check_service_shapes(texts, _shown_dir(bundle_dir), problems)
    _check_short_anchors(entries, problems)
    _check_reserved_names(entries, problems)
    _check_fake_values(items, decoys, problems)
    _check_unique_prefixes(items, problems)
    rows = _cover_rows(entries) if difficulty in RECORDED_DIFFICULTIES else ()
    return BundleReport(
        bundle_id,
        difficulty,
        tuple(problems),
        rows,
        categories,
        frozenset(e.hiding for e in entries if not e.decoy and e.hiding),
        frozenset(e.hiding for e in entries if e.decoy and e.hiding),
    )


def _contract_rule(where: str, rule: str) -> str:
    """계약 오류의 F-B07 규칙 번호: 닻 200자 넘음은 7, 그 밖은 2."""
    if where.endswith(_ANCHOR_FIELDS) and rule.startswith(_MAX_LENGTH):
        return "7"
    return "2"


def text_files(bundle_dir: Path) -> dict[str, bytes]:
    """번들의 글 파일(지문과 같은 목록에서 바이너리 확장자 밖). 정답지 만들기(`locate`)도 쓴다."""
    files: dict[str, bytes] = {}
    for line in manifest_lines(bundle_dir):
        rel = line.split(_TAB, 1)[0]
        files[rel] = resolve_in_bundle(bundle_dir, rel).read_bytes()
    return _text_files(files)


def _text_files(files: Mapping[str, bytes]) -> dict[str, bytes]:
    """번들의 글 파일: 검사 '실험자료'가 글로 읽는 것(바이너리 확장자 밖)과 같다(F-B07 6·9)."""
    binary = fake.binary_suffixes()
    return {
        rel: data for rel, data in files.items() if PurePosixPath(rel).suffix.lower() not in binary
    }


def _shown_dir(bundle_dir: Path) -> str:
    """찍을 번들 경로: 저장소 안이면 `bench/bundles/<id>` 꼴, 밖(시험의 임시 폴더)이면 폴더 이름."""
    try:
        return bundle_dir.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return bundle_dir.name


def _entry(raw: Mapping[str, Json], *, decoy: bool) -> _Entry:
    anchor, decoded, hiding = raw.get("anchor"), raw.get("decoded_anchor"), raw.get("hiding")
    return _Entry(
        str(raw.get("id")),
        tuple(_objects(raw.get("locations"))),
        anchor if isinstance(anchor, str) else None,
        decoded if isinstance(decoded, str) else None,
        hiding if isinstance(hiding, str) else None,
        decoy,
    )


def _check_counts(
    items: Sequence[Mapping[str, Json]], decoys: Sequence[Mapping[str, Json]], out: list[Problem]
) -> None:
    low, high = ITEMS_RANGE
    if not low <= len(items) <= high:
        out.append(Problem("3", "$.items", f"정답 {len(items)}개(심은 번들은 {low}~{high}개)"))
    low, high = DECOYS_RANGE
    if not low <= len(decoys) <= high:
        out.append(Problem("3", "$.decoys", f"미끼 {len(decoys)}개(심은 번들은 {low}~{high}개)"))


def _check_categories(categories: frozenset[str], out: list[Problem]) -> None:
    if len(categories) < MIN_CATEGORIES:
        out.append(
            Problem("4", "$.items", f"범주 {len(categories)}개(번들마다 {MIN_CATEGORIES}개 이상)")
        )


def _check_hiding(items: Sequence[Mapping[str, Json]], difficulty: str, out: list[Problem]) -> None:
    allowed = HIDING_BY_DIFFICULTY.get(difficulty, frozenset())
    used: set[str] = set()
    for item in items:
        hiding = str(item.get("hiding"))
        used.add(hiding)
        if hiding not in allowed and hiding != HIDING_ANYWHERE:
            out.append(
                Problem("5", str(item.get("id")), f"{hiding}는 {difficulty} 줄의 방법이 아님")
            )
    for missing in sorted(allowed - used):
        out.append(Problem("5", "$.items", f"{difficulty} 줄의 {missing}가 한 번도 없음"))


def _read_bundle(bundle_dir: Path, out: list[Problem]) -> dict[str, bytes] | None:
    """번들의 파일(지문과 같은 목록). 지문을 낼 수 없는 번들이면 None(규칙 8)."""
    try:
        lines = manifest_lines(bundle_dir)
    except ManifestError as e:
        out.append(Problem("8", ".", f"번들 지문을 낼 수 없음 — {e}"))
        return None
    files: dict[str, bytes] = {}
    for line in lines:
        rel = line.split(_TAB, 1)[0]
        files[rel] = resolve_in_bundle(bundle_dir, rel).read_bytes()
    return files


def _check_fingerprint(bundle_dir: Path, answers: Mapping[str, Json], out: list[Problem]) -> None:
    if answers["bundle_manifest_sha256"] != bundle_manifest_sha256(bundle_dir):
        out.append(Problem("8", "$.bundle_manifest_sha256", "번들 지문과 다름"))


def _check_locations(
    entries: Iterable[_Entry], files: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 11(`file_lines`가 번들과 같음)·12(위치의 파일이 번들에 있음). 미끼 위치도 본다."""
    for entry in entries:
        for loc in entry.locations:
            rel = str(loc["file"])
            data = files.get(rel)
            if data is None:
                out.append(Problem("12", entry.id, f"위치 파일이 번들에 없음: {rel}"))
                continue
            actual = count_lines(data)
            if loc["file_lines"] != actual:
                out.append(
                    Problem("11", entry.id, f"{rel} file_lines {loc['file_lines']} ≠ 번들 {actual}")
                )


def _check_anchors(
    entries: Iterable[_Entry], texts: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 6: 닻이 글 파일에 있고(㉮), 나오는 곳이 모두 그 정답(미끼) 위치 안(㉯).

    줄바꿈이 든 닻은 실패.
    """
    for entry in entries:
        if entry.anchor is None:
            continue
        needle = entry.anchor.encode("utf-8")
        if _LF in needle or _CR in needle:
            out.append(Problem("6", entry.id, "닻에 줄바꿈"))
            continue
        found = False
        outside: list[tuple[str, int]] = []
        for rel, line in _anchor_lines(texts, needle):
            found = True
            if not _inside(entry, rel, line):
                outside.append((rel, line))
                if len(outside) >= MAX_OUTSIDE_PLACES:
                    break
        if not found:
            out.append(Problem("6㉮", entry.id, "닻이 번들에 없음"))
        elif outside:
            shown = ", ".join(f"{rel}:{line}" for rel, line in outside)
            out.append(Problem("6㉯", entry.id, f"닻이 위치 밖에도 나옴({shown})"))


def places(texts: Mapping[str, bytes], needle: bytes) -> Iterator[tuple[str, int]]:
    """닻이 나오는 `(경로, 줄)`(줄마다 한 번, 흘려 보내며). 정답지 만들기(`locate`)도 쓴다."""
    return _anchor_lines(texts, needle)


def covers_file(loc: Mapping[str, Json]) -> bool:
    """줄로 가를 수 없는 위치(F-G02 2㉢, T = 2): 줄 허용 범위가 파일 전체를 덮는다."""
    return window_covers_file(
        _as_int(loc["line_start"]),
        _as_int(loc["line_end"]),
        _as_int(loc["file_lines"]),
        COVER_TOLERANCE,
    )


def _check_location_anchors(
    entries: Iterable[_Entry], texts: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 6 위치 닻 판: ㉮ 그 위치의 파일에 나오고 ㉯ 나오는 곳이 모두 그 위치의 파일·줄 범위 안.

    정답의 다른 위치 안이어도 안 된다(설계 8.4 2 ⓐ). 줄바꿈이 든 위치 닻은 실패.
    """
    for entry in entries:
        for i, anchor in entry.location_anchors():
            loc = entry.locations[i]
            where = f"{entry.id}.locations[{i}]"
            needle = anchor.encode("utf-8")
            if _LF in needle or _CR in needle:
                out.append(Problem("6", where, "위치 닻에 줄바꿈"))
                continue
            rel = str(loc["file"])
            if rel not in texts:
                continue  # 위치 파일이 없음은 규칙 12
            start, end = _as_int(loc["line_start"]), _as_int(loc["line_end"])
            found = False
            outside: list[tuple[str, int]] = []
            for place, line in _anchor_lines(texts, needle):
                inside = place == rel and start <= line <= end
                found = found or inside
                if not inside:
                    outside.append((place, line))
                    if len(outside) >= MAX_OUTSIDE_PLACES:
                        break
            if not found:
                out.append(Problem("6㉮", where, "위치 닻이 그 위치에 없음"))
            if outside:
                shown = ", ".join(f"{p}:{n}" for p, n in outside)
                out.append(Problem("6㉯", where, f"위치 닻이 그 위치 밖에도 나옴({shown})"))


def _check_unsplittable(
    entries: Iterable[_Entry], texts: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 14: 닻·풀어낸 값이 있는 정답·미끼의 줄로 가를 수 없는 위치마다, 그 파일에
    정답(미끼) 닻이나 그 위치의 위치 닻이 글자 그대로 있다(풀어낸 값은 번들에 없어 세지 않는다).
    """
    for entry in entries:
        if entry.anchor is None and entry.decoded is None:
            continue
        for i, loc in enumerate(entry.locations):
            data = texts.get(str(loc["file"]))
            if data is None or not covers_file(loc):
                continue  # 위치 파일이 없음은 규칙 12
            own = loc.get("anchor")
            needles = [n for n in (entry.anchor, own) if isinstance(n, str)]
            if not any(n.encode("utf-8") in data for n in needles):
                out.append(
                    Problem("14", f"{entry.id}.locations[{i}]", "그 파일에 닻·위치 닻이 없음")
                )


def _check_short_anchors(entries: Iterable[_Entry], out: list[Problem]) -> None:
    """규칙 16: 줄로 가를 수 없는 위치가 하나라도 있으면 닻·풀어낸 값·위치 닻이 64자 이하."""
    for entry in entries:
        if not any(covers_file(loc) for loc in entry.locations):
            continue
        fields = [("anchor", entry.anchor), ("decoded_anchor", entry.decoded)]
        fields += [(f"locations[{i}].anchor", a) for i, a in entry.location_anchors()]
        for label, value in fields:
            if value is not None and len(value) > ANCHOR_SHORT_MAX:
                out.append(Problem("16", f"{entry.id}.{label}", f"{len(value)}자(64자까지)"))


def encoding_of(anchor: str) -> str | None:
    """인코딩 닻의 꼴: 16진(소문자, 짝수 자리) `hex` · base64 `base64`. 둘 다 아니면 None.

    16진 글은 base64 글자이기도 해서 16진을 먼저 본다.
    """
    if _HEX.fullmatch(anchor):
        return "hex"
    if _BASE64.fullmatch(anchor):
        return "base64"
    return None


def _encoded_length(anchor: str, encoding: str, texts: Mapping[str, bytes]) -> int | None:
    """번들에 든 인코딩된 글 전체의 길이: 닻이 처음 나오는 곳에서 같은 꼴 글자로 앞뒤를 넓힌다.

    닻이 인코딩된 글의 앞 조각이어도(긴 SVG) 글 전체를 잰다(F-B02 9 '번들에 든 인코딩된 글').
    """
    chars = _HEX_CHARS if encoding == "hex" else _BASE64_CHARS
    needle = anchor.encode("ascii")
    for rel in sorted(texts):
        data = texts[rel]
        start = data.find(needle)
        if start < 0:
            continue
        end = start + len(needle)
        while start > 0 and data[start - 1] in chars:
            start -= 1
        while end < len(data) and data[end] in chars:
            end += 1
        return end - start
    return None


def _check_encoded_lengths(
    entries: Sequence[_Entry], texts: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 17 (F-B02 9): 같은 인코딩 정답·미끼가 한 번들에 있으면, 정답마다 같은 인코딩 미끼 가운데
    하나는 번들에 든 인코딩된 글의 길이가 1.5배 안(긴 쪽 ÷ 짧은 쪽)."""
    lengths: dict[str, list[tuple[_Entry, int]]] = {}
    for entry in entries:
        if entry.hiding != _ENCODED or entry.anchor is None:
            continue
        encoding = encoding_of(entry.anchor)
        if encoding is None:
            continue  # 규칙 17은 base64·16진 꼴 닻끼리만 견준다
        length = _encoded_length(entry.anchor, encoding, texts)
        if length is not None:
            lengths.setdefault(encoding, []).append((entry, length))
    for encoding, found in sorted(lengths.items(), key=lambda kv: kv[0]):
        decoys = [n for e, n in found if e.decoy]
        if not decoys:
            continue
        for entry, length in found:
            if entry.decoy:
                continue
            best = min(max(length, n) / min(length, n) for n in decoys)
            if best > ENCODED_LENGTH_RATIO:
                out.append(
                    Problem(
                        "17", entry.id, f"{encoding} {length}자, 가장 가까운 미끼와 {best:.2f}배"
                    )
                )


def _check_reserved_names(entries: Sequence[_Entry], out: list[Problem]) -> None:
    """규칙 18 (F-B02 6): 예약 이름(`.example`·`.test`·`.invalid`·`.localhost`)을 한 번들 안에서
    정답·미끼 한쪽에만 쓰지 않는다. 정답지의 닻·풀어낸 값·위치 닻으로 본다."""
    used: dict[bool, set[str]] = {False: set(), True: set()}
    for entry in entries:
        texts = [entry.anchor, entry.decoded, *(a for _, a in entry.location_anchors())]
        if any(t is not None and RESERVED_NAME.search(t) for t in texts):
            used[entry.decoy].add(entry.id)
    if bool(used[False]) != bool(used[True]):
        side = "정답" if used[False] else "미끼"
        ids = ", ".join(sorted(used[False] | used[True]))
        out.append(Problem("18", ids, f"예약 이름을 {side}에만 씀"))


def _check_decoy_hiding(decoys: Iterable[Mapping[str, Json]], out: list[Problem]) -> None:
    """규칙 19 (F-B03 7): 심은 번들의 미끼마다 숨긴 방법(`hiding`)이 있다."""
    for decoy in decoys:
        if not isinstance(decoy.get("hiding"), str):
            out.append(Problem("19", str(decoy.get("id")), "미끼에 hiding이 없음"))


def _check_distance(
    entries: Sequence[_Entry], texts: Mapping[str, bytes], out: list[Problem]
) -> None:
    """규칙 20 (설계 8.8 6): 파일마다 미끼의 닻·위치 닻이 나오는 곳과 정답의 닻·위치 닻이 나오는
    곳의 모든 짝에서, 둘을 함께 덮는 가장 짧은 구간(글자 수)이 300자를 넘는다.

    나오는 곳을 시작 자리 차례로 흘려 보내며(닻마다 `str.find`, `heapq.merge`) 반대쪽에서 마지막으로
    나온 곳 하나와만 견준다. 그것으로 모든 짝을 본 것과 같다: 반대쪽 `a`(시작 ≤ 지금 `d`의 시작)와의
    구간은 `max(두 끝) − a.시작`이라, `a`가 `d`를 품지 않으면 시작이 늦은 `a`일수록 짧다.
    `a`가 `d`를 품으면 구간이 `a`의 길이(닻 200자 상한)라 어차피 300자 안이다.
    메모리는 닻 수만큼, 시간은 파일 길이 × 닻 수 + 나온 곳 수 × log(닻 수).
    """
    found = 0
    for rel in sorted(texts):
        text = texts[rel].decode("utf-8", errors="replace")
        needles = _distance_needles(entries, text)
        last: dict[bool, tuple[int, int, str]] = {}
        reported: set[tuple[str, str]] = set()
        for start, end, decoy, entry_id in heapq.merge(*(_finds(text, *n) for n in needles)):
            other = last.get(not decoy)
            last[decoy] = (start, end, entry_id)
            if other is None:
                continue
            span = max(end, other[1]) - other[0]
            pair = (entry_id, other[2]) if decoy else (other[2], entry_id)
            if span > DECOY_DISTANCE or pair in reported:
                continue
            reported.add(pair)
            out.append(Problem("20", pair[0], f"정답 {pair[1]}와 {rel}에서 {span}자 구간"))
            found += 1
            if found >= MAX_DISTANCE_PROBLEMS:
                return


def _distance_needles(entries: Iterable[_Entry], text: str) -> list[tuple[str, bool, str]]:
    """그 파일에 나오는 닻·위치 닻: `(글, 미끼인가, 정답·미끼 ID)`. 같은 정답 안 같은 글은 한 번."""
    needles: list[tuple[str, bool, str]] = []
    for entry in entries:
        own = {entry.anchor, *(a for _, a in entry.location_anchors())}
        for needle in sorted(n for n in own if n):
            if needle in text:
                needles.append((needle, entry.decoy, entry.id))
    return needles


def _finds(
    text: str, needle: str, decoy: bool, entry_id: str
) -> Iterator[tuple[int, int, bool, str]]:
    """글에서 닻이 나오는 곳을 시작 자리마다(겹쳐 나와도) 차례로."""
    start = text.find(needle)
    while start >= 0:
        yield start, start + len(needle), decoy, entry_id
        start = text.find(needle, start + 1)


def _anchor_lines(texts: Mapping[str, bytes], needle: bytes) -> Iterator[tuple[str, int]]:
    """닻이 나오는 `(경로, 줄)`을 한 번씩, 흘려 보내며. 줄은 나오는 곳의 시작 글자가 든 줄.

    한 줄에서 찾으면 그 줄 끝으로 건너뛴다(같은 줄에서 더 나와도 줄은 같다). 줄은 앞 자리에서
    이어 세어, 파일마다 입력 길이에 선형이고 모은 것을 들고 있지 않는다.
    """
    for rel in sorted(texts):
        data = texts[rel]
        line, counted = 1, 0
        start = data.find(needle)
        while start >= 0:
            line += data.count(_LF, counted, start)
            counted = start
            yield rel, line
            line_end = data.find(_LF, start)
            if line_end < 0:
                break
            start = data.find(needle, line_end + 1)


def _inside(entry: _Entry, rel: str, line: int) -> bool:
    return any(
        loc["file"] == rel and _as_int(loc["line_start"]) <= line <= _as_int(loc["line_end"])
        for loc in entry.locations
    )


def _check_service_shapes(texts: Mapping[str, bytes], shown: str, out: list[Problem]) -> None:
    """규칙 9: 검사 '실험자료'와 같은 꼴·같은 줄 나눔으로 번들 글 파일을 본다.

    꼴 이름과 줄만 찍는다.
    """
    for rel in sorted(texts):
        text = texts[rel].decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name in fake.service_shape_names(line):
                out.append(Problem("9", f"{shown}/{rel}:{lineno}", name))


def _check_fake_values(
    items: Iterable[Mapping[str, Json]], decoys: Iterable[Mapping[str, Json]], out: list[Problem]
) -> None:
    """규칙 10: 규칙 4로 만든 값(키·토큰·비밀번호)이 든 정답·미끼의 닻·풀어낸 값이 F-B02 5를 지킴.

    범주와 상관없이 값의 꼴로 가른다(반려 1 9, 총괄 대리 — `client_authz` 토큰도 규칙 4 값이다).
    ㉯는 `fake_value_problems`가 접두어 있는 값(키 꼴)에만 건다 —
    비밀번호·조각·인코딩 글에는 걸지 않는다.
    """
    for entry in [*items, *decoys]:
        values = [(entry.get(k), k) for k in ("anchor", "decoded_anchor")]
        if not any(isinstance(v, str) and fake.rule4_form(v) for v, _ in values):
            continue
        for value, label in values:
            if not isinstance(value, str):
                continue
            for problem in fake.fake_value_problems(value) + fake.token_problems(value):
                out.append(Problem("10", f"{entry.get('id')}.{label}", problem))


def _check_unique_prefixes(items: Iterable[Mapping[str, Json]], out: list[Problem]) -> None:
    """F-B02 4ⓐ: 한 번들 안 정답마다 다른 접두어(같은 접두어 하나가 검색 표식이 되지 않게)."""
    seen: dict[str, str] = {}
    for item in items:
        entry_id = str(item.get("id"))
        for key in ("anchor", "decoded_anchor"):
            value = item.get(key)
            prefix = fake.key_prefix(value) if isinstance(value, str) else None
            if prefix is None:
                continue
            if seen.setdefault(prefix, entry_id) != entry_id:
                out.append(Problem("F-B02 4ⓐ", entry_id, f"접두어가 {seen[prefix]}와 같음"))


def _cover_rows(entries: Iterable[_Entry]) -> tuple[CoverRow, ...]:
    rows = []
    for entry in entries:
        for loc in entry.locations:
            start, end, lines = (
                _as_int(loc["line_start"]),
                _as_int(loc["line_end"]),
                _as_int(loc["file_lines"]),
            )
            covers = window_covers_file(start, end, lines, COVER_TOLERANCE)
            rows.append(CoverRow(entry.id, str(loc["file"]), start, end, lines, covers))
    return tuple(rows)


def decoy_hiding_gaps(reports: Iterable[BundleReport]) -> dict[str, frozenset[str]]:
    """규칙 15 (F-B02 8): 난이도마다(번들을 합쳐) 정답이 쓰는 숨긴 방법(`none` 빼고) 가운데
    그 방법을 거친 미끼가 없는 것. 빈 dict면 지킨다."""
    items: dict[str, set[str]] = {}
    decoys: dict[str, set[str]] = {}
    for report in reports:
        if report.difficulty is None:
            continue
        items.setdefault(report.difficulty, set()).update(report.item_hidings)
        decoys.setdefault(report.difficulty, set()).update(report.decoy_hidings)
    gaps: dict[str, frozenset[str]] = {}
    for difficulty in sorted(items):
        missing = items[difficulty] - decoys.get(difficulty, set()) - {HIDING_ANYWHERE}
        if missing:
            gaps[difficulty] = frozenset(missing)
    return gaps


def format_cover_table(rows: Sequence[CoverRow]) -> list[str]:
    """F-B07 13 확인 기록 표(마크다운)."""
    if not rows:
        return []
    head = [
        "| 정답·미끼 | 파일 | 줄 | file_lines | 줄 허용 범위가 파일을 덮음 |",
        "|---|---|---|---|---|",
    ]
    return head + [
        f"| {r.entry_id} | {r.file} | {r.line_start}~{r.line_end} | {r.file_lines} | "
        f"{'덮음' if r.covers else '덮지 않음'} |"
        for r in rows
    ]


def _objects(value: Json) -> list[dict[str, Json]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _strings(value: Json) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _as_int(value: Json) -> int:
    # 계약을 지난 줄 번호는 정수다(검증기는 12.0도 받으므로 int로 바꾼다, bench/README)
    return int(value) if isinstance(value, int | float) else 0
