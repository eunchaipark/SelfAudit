"""F-B01 시험 번들 빌드: 원본 `bench/sources/<대상 ID>/` → 결과물 `bench/bundles/<대상 ID>/`.

원본 폴더:
- `plan.json` — 심기 계획과 빌드 설정(F-B02 입력). 꼴은 `_read_plan`.
- `src/**` — 결과물이 될 파일. 글 파일 안의 자리를 채운다:
  `{{v:<정답 ID>}}` 가짜 값(걸러내기를 `|이름:인자`로 이음, 예 `{{v:N1-03|split:2:0}}`),
  `{{asset:<src 안 경로>}}` 그 파일의 결과물 경로.
- `build.json` — 빌드 기록(F-B01 2). 빌드가 쓴다. 번들 폴더 밖이다.

한 파일의 차례: 가짜 값 채우기 → 경로 채우기 → 이름 줄이기(JS, `mode: minified`, `rename.py`)
→ 더한 변환(`steps`) → 압축(JS, `mode: minified`) → 해시 이름(`hash_names`)
→ 소스맵(`sourcemaps`, 맵의 `sourcesContent`는 이름 줄이기·변환·압축 전 글 —
실제 빌드처럼 원래 이름).

**이름 줄이기**(F-B01 6, normal·hard): `plan.json` `rename`(줄일 이름 표, 글 목록)의 이름을
JS 파일마다 짧은 이름으로 바꾼다. 압축 모드에서는 늘 돈다(표가 비면 2자 넘는 선언에서 멈춘다).
펼침 모드(easy)에 표가 있으면 멈춘다. 표의 이름이 어느 JS 파일에도 이름으로 나오지 않으면 멈춘다
(지난 원본의 이름이 남은 표는 무엇을 줄였는지 거짓으로 말한다).

**더하는 변환**(T23 `encode.py`, T24 `obfuscate.py`): 이 폴더에 모듈을 더하고
`plan.json` `plugins`에 이름을 적는다. 모듈은 `FILTERS: Mapping[str, Filter]`
(가짜 값 걸러내기, 예 base64)와 `STEPS: Mapping[str, Step]`(파일 하나 변환, 예 난독화)
가운데 하나 이상을 둔다. 이 파일은 고치지 않는다.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import platform
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Final

from common.contracts import ContractJsonError, Json, read_json
from common.fingerprint import bundle_manifest_sha256
from common.paths import is_bundle_relpath, resolve_in_bundle
from sources.build_tools import fake, sourcemap
from sources.build_tools.minify import MinifyError, minify_js
from sources.build_tools.rename import RenameError, check_table, rename_js

__all__ = [
    "BUILD_DIR",
    "BUNDLES_DIR",
    "SOURCES_DIR",
    "BuildError",
    "BuildResult",
    "Filter",
    "Step",
    "StepContext",
    "build",
]

BUILD_DIR: Final = Path(__file__).resolve().parent
SOURCES_DIR: Final = BUILD_DIR.parent
BUNDLES_DIR: Final = SOURCES_DIR.parent / "bundles"
PLAN_NAME: Final = "plan.json"
RECORD_NAME: Final = "build.json"
SRC_NAME: Final = "src"
PLAN_SCHEMA: Final = "selfaudit-bench/plan@1"
RECORD_SCHEMA: Final = "selfaudit-bench/build@1"
# 대상 ID 꼴(계약 targets·answers와 같음). `build_tools`는 `_`가 있어 대상 ID가 될 수 없다
BUNDLE_ID: Final = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
ENTRY_ID: Final = re.compile(r"[A-Z0-9][A-Z0-9-]{1,29}")
# 더하는 변환 모듈 이름: 파이썬 모듈 이름 꼴, 30자까지(정답 ID 상한 30자와 같은 울타리 — 실제 이름은
# `encode`·`obfuscate`처럼 10자 안)
PLUGIN_NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,29}")
MODES: Final = frozenset({"expanded", "minified"})
# 자리를 채우는 글 파일: Vite 같은 웹 빌드가 내는 글 결과물의 확장자(화면·스크립트·스타일·맵·
# 목록·그림 글). 그 밖은 바이트 그대로 옮기되, 검사 '실험자료'가 글로 읽는 파일
# (바이너리 확장자 밖)이면 CR이 없어야 한다(F-B01 4 — 결과물 글 파일의 줄바꿈은 LF)
TEXT_SUFFIXES: Final = frozenset(
    {".html", ".js", ".mjs", ".css", ".json", ".map", ".txt", ".svg", ".webmanifest", ".xml"}
)
JS_SUFFIXES: Final = frozenset({".js", ".mjs"})
# 해시 이름 길이: Vite 기본(8자)과 같게. 번들 안 파일 수십 개에서 겹칠 일이 없다
HASH_CHARS: Final = 8
# 빌드 기록에 적는 명령. 실제 argv는 절대 경로가 들 수 있어 적지 않는다(F-B01 3)
COMMAND: Final = (
    "uv",
    "run",
    "--frozen",
    "--offline",
    "python",
    "-m",
    "sources.build_tools",
    "build",
)
# `{{v:ID|f:a:b}}`·`{{asset:path}}`.
# 글자 칸이 서로 겹치지 않고 길이가 정해져 있어 되돌아가지 않는다.
# 길이 울타리: 자리 이름 300자 = 번들 경로 상한(정답 ID 30자보다 길다),
# 걸러내기 이름 30자 = 모듈 이름과 같게, 인자 40자 = 대상 ID 상한과 같게(실제 인자는 한두 자),
# 걸러내기 4개·인자 4개 = 실제로 쓰는 것(`split:2:0` 하나, 인자 2개)의 2~4배
PLACEHOLDER: Final = re.compile(
    r"\{\{(v|asset):([A-Za-z0-9/._-]{1,300})"
    r"((?:\|[a-z0-9_]{1,30}(?::[A-Za-z0-9_-]{1,40}){0,4}){0,4})\}\}"
)
# 원본·결과물 파일 하나의 크기 상한: F-B03 근거 '결과물 파일 하나가 10MB 아래'
# (줄 번호 상한의 근거)와 맞춘다. 압축·변환은 글을 여러 번 복사해 메모리가 입력의 여러 배라,
# 큰 입력을 먼저 막는다
MAX_FILE_BYTES: Final = 10 * 1000 * 1000
_VALUE_OPEN: Final = "{{v:"  # 채운 뒤에도 남으면 꼴이 틀린 자리다(조용히 결과물에 남기지 않는다)
_ASSET_OPEN: Final = "{{asset:"
_LF: Final = chr(0x0A)
_CR: Final = chr(0x0D)
_BUILTIN_FILTERS: Final[Mapping[str, Callable[[str, Sequence[str]], str]]] = {
    "split": fake.split_piece,
}
_CORE_MODULES: Final = frozenset(
    {"build", "fake", "locate", "minify", "rename", "sourcemap", "verify"}
)
_BUILDING_SUFFIX: Final = ".building"  # 쓰는 동안의 임시 폴더 `bench/bundles/.<id>.building`
_OLD_SUFFIX: Final = ".old"  # 바꿔 넣는 동안 옛 결과물을 잠깐 두는 곳 `bench/bundles/.<id>.old`
_PACKAGE: Final = __name__.rpartition(".")[0]


class BuildError(ValueError):
    """빌드할 수 없다. 글에는 대상 ID·원본 안 경로·정답 ID만(값은 싣지 않는다)."""


@dataclass(frozen=True)
class StepContext:
    """더한 변환(`STEPS`)이 받는 것.

    같은 입력이면 같은 출력이어야 한다(F-B01 3) — 난수는 `seed`로.
    """

    bundle_id: str
    file: str  # src 안 경로
    options: Mapping[str, Json]

    @property
    def seed(self) -> str:
        return f"{self.bundle_id}/{self.file}"


type Filter = Callable[[str, Sequence[str]], str]
type Step = Callable[[str, StepContext], str]


@dataclass(frozen=True)
class _StepUse:
    name: str
    files: frozenset[str]
    options: Mapping[str, Json]


@dataclass(frozen=True)
class _Plan:
    bundle_id: str
    mode: str
    hash_names: frozenset[str]
    sourcemaps: frozenset[str]
    sourcemap_content: bool
    values: Mapping[str, Mapping[str, Json]]
    plugins: tuple[str, ...]
    steps: tuple[_StepUse, ...]
    rename: frozenset[str] = frozenset()


@dataclass(frozen=True)
class BuildResult:
    bundle_id: str
    bundle_dir: Path
    record_path: Path
    bundle_manifest_sha256: str
    files: Mapping[str, str]  # src 안 경로 → 결과물 경로
    values: Mapping[str, str] = field(repr=False)  # 정답 ID → 가짜 값(정답지 닻을 적을 때)
    warnings: tuple[str, ...] = ()  # 빌드는 됐지만 알릴 것(옛 폴더를 지우지 못함 등). 값은 없다


# --- 진입 ------------------------------------------------------------------------------------


def build(
    bundle_id: str, sources_dir: Path = SOURCES_DIR, bundles_dir: Path = BUNDLES_DIR
) -> BuildResult:
    """F-B01: 원본을 빌드해 결과물 폴더를 비우고 새로 만들고, 빌드 기록을 원본 폴더에 쓴다."""
    if not BUNDLE_ID.fullmatch(bundle_id):
        raise BuildError("대상 ID 꼴이 아님")
    source_dir = sources_dir / bundle_id
    if not (source_dir / PLAN_NAME).is_file() or not (source_dir / SRC_NAME).is_dir():
        raise BuildError(f"원본 폴더 없음(plan.json·src/): {bundle_id}")
    bundle_dir = bundles_dir / bundle_id
    _check_places(sources_dir, source_dir, bundles_dir, bundle_dir)
    plan = _read_plan(source_dir / PLAN_NAME, bundle_id)
    files = _read_sources(source_dir / SRC_NAME)
    outputs, names, values = _Builder(plan, files).run()
    warnings = _write_bundle(bundle_dir, outputs)
    fingerprint = bundle_manifest_sha256(bundle_dir)
    record_path = source_dir / RECORD_NAME
    record_path.write_bytes(_record(bundle_id, fingerprint))
    return BuildResult(
        bundle_id, bundle_dir, record_path, fingerprint, names, values, tuple(warnings)
    )


def _check_places(sources_dir: Path, source_dir: Path, bundles_dir: Path, bundle_dir: Path) -> None:
    """읽고 쓰고 지우는 곳이 바로가기가 아니고, 풀어 봐도 원본·결과물 모음 바로 아래다.

    `bench/bundles` 자체나 `bench/sources/<id>`가 정션이면 저장소 밖을 지울 수 있다(반려 1 2).
    """
    places = (
        sources_dir,
        source_dir,
        source_dir / SRC_NAME,
        source_dir / PLAN_NAME,
        source_dir / RECORD_NAME,
        bundles_dir,
        bundle_dir,
        _building_dir(bundle_dir),
        _old_dir(bundle_dir),
    )
    for path in places:
        if _is_link(path):
            raise BuildError(f"바로가기(링크·정션)는 받지 않음: {path.name}")
    if source_dir.resolve().parent != sources_dir.resolve():
        raise BuildError(f"원본 폴더가 원본 모음 밖을 가리킴: {source_dir.name}")
    if bundle_dir.resolve().parent != bundles_dir.resolve():
        raise BuildError(f"결과물 폴더가 결과물 모음 밖을 가리킴: {bundle_dir.name}")


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _building_dir(bundle_dir: Path) -> Path:
    return bundle_dir.with_name(f".{bundle_dir.name}{_BUILDING_SUFFIX}")


def _old_dir(bundle_dir: Path) -> Path:
    return bundle_dir.with_name(f".{bundle_dir.name}{_OLD_SUFFIX}")


# --- 계획 읽기 -------------------------------------------------------------------------------


def _read_plan(path: Path, bundle_id: str) -> _Plan:
    try:
        raw = read_json(path)
    except ContractJsonError as e:
        raise BuildError(f"{bundle_id}: plan.json — {e}") from None
    if not isinstance(raw, dict) or raw.get("schema") != PLAN_SCHEMA:
        raise BuildError(f"{bundle_id}: plan.json schema는 {PLAN_SCHEMA}")
    if raw.get("bundle_id") != bundle_id:
        raise BuildError(f"{bundle_id}: plan.json bundle_id가 폴더 이름과 다름")
    mode = raw.get("mode")
    if mode not in MODES:
        raise BuildError(f"{bundle_id}: mode는 expanded·minified")
    return _Plan(
        bundle_id=bundle_id,
        mode=str(mode),
        hash_names=frozenset(_str_list(raw, "hash_names", bundle_id)),
        sourcemaps=frozenset(_str_list(raw, "sourcemaps", bundle_id)),
        sourcemap_content=_bool(raw, "sourcemap_content", bundle_id),
        values=_values(raw, bundle_id),
        plugins=tuple(_str_list(raw, "plugins", bundle_id)),
        steps=_steps(raw, bundle_id),
        rename=frozenset(_str_list(raw, "rename", bundle_id)),
    )


def _str_list(raw: Mapping[str, Json], key: str, bundle_id: str) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BuildError(f"{bundle_id}: plan.json {key}는 글 목록")
    return [str(v) for v in value]


def _bool(raw: Mapping[str, Json], key: str, bundle_id: str) -> bool:
    value = raw.get(key, False)
    if not isinstance(value, bool):
        raise BuildError(f"{bundle_id}: plan.json {key}는 true·false")
    return value


def _values(raw: Mapping[str, Json], bundle_id: str) -> dict[str, Mapping[str, Json]]:
    value = raw.get("values", {})
    if not isinstance(value, dict):
        raise BuildError(f"{bundle_id}: plan.json values는 객체")
    out: dict[str, Mapping[str, Json]] = {}
    for entry_id, spec in value.items():
        if not ENTRY_ID.fullmatch(entry_id) or not isinstance(spec, dict):
            raise BuildError(f"{bundle_id}: values의 정답 ID 꼴 또는 칸이 틀림")
        out[entry_id] = spec
    try:
        fake.check_unique_prefixes(value)
    except fake.FakeValueError as e:
        raise BuildError(f"{bundle_id}: {e}") from None
    return out


def _steps(raw: Mapping[str, Json], bundle_id: str) -> tuple[_StepUse, ...]:
    value = raw.get("steps", [])
    if not isinstance(value, list):
        raise BuildError(f"{bundle_id}: plan.json steps는 목록")
    out: list[_StepUse] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict) or not isinstance(item.get("step"), str):
            raise BuildError(f"{bundle_id}: steps[{i}]에 step 이름이 없음")
        files = _str_list(item, "files", bundle_id)
        options = item.get("options", {})
        if not isinstance(options, dict):
            raise BuildError(f"{bundle_id}: steps[{i}].options는 객체")
        out.append(_StepUse(str(item["step"]), frozenset(files), options))
    return tuple(out)


def _load_plugins(
    names: Sequence[str], bundle_id: str
) -> tuple[dict[str, Filter], dict[str, Step]]:
    filters: dict[str, Filter] = dict(_BUILTIN_FILTERS)
    steps: dict[str, Step] = {}
    for name in names:
        if (
            not PLUGIN_NAME.fullmatch(name)
            or name in _CORE_MODULES
            or not (BUILD_DIR / f"{name}.py").is_file()
        ):
            raise BuildError(f"{bundle_id}: plugins의 {name!r}는 build_tools의 변환 모듈이 아님")
        module = importlib.import_module(f"{_PACKAGE}.{name}")
        more_filters: Mapping[str, Filter] = getattr(module, "FILTERS", {})
        more_steps: Mapping[str, Step] = getattr(module, "STEPS", {})
        if not more_filters and not more_steps:
            raise BuildError(f"{bundle_id}: {name}에 FILTERS·STEPS가 없음")
        if set(filters).intersection(more_filters) or set(steps).intersection(more_steps):
            raise BuildError(f"{bundle_id}: {name}의 이름이 이미 있음")
        filters.update(more_filters)
        steps.update(more_steps)
    return filters, steps


# --- 원본 읽기 -------------------------------------------------------------------------------


def _read_sources(src_dir: Path) -> dict[str, bytes]:
    """src 아래 일반 파일만(바로가기·정션 거절). 경로는 번들 경로 허용 꼴이어야 한다."""
    files: dict[str, bytes] = {}
    for path in sorted(src_dir.rglob("*")):
        rel = path.relative_to(src_dir).as_posix()
        if _is_link(path):
            raise BuildError(f"원본에 바로가기: {rel}")
        if path.is_dir():
            continue
        if not path.is_file() or not is_bundle_relpath(rel):
            raise BuildError(f"원본 경로가 허용 꼴이 아니거나 일반 파일이 아님: {rel!r}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise BuildError(f"원본 파일이 {MAX_FILE_BYTES}바이트를 넘음: {rel}")
        files[rel] = path.read_bytes()
    if not files:
        raise BuildError("원본 src/에 파일이 없음")
    return files


# --- 빌드 ------------------------------------------------------------------------------------


class _Builder:
    def __init__(self, plan: _Plan, files: Mapping[str, bytes]) -> None:
        self.plan = plan
        self.files = files
        self.filters, self.step_table = _load_plugins(plan.plugins, plan.bundle_id)
        self.values: dict[str, str] = {}
        self.texts: dict[str, str] = {}
        self.names: dict[str, str] = {}
        self.outputs: dict[str, bytes] = {}
        self.renamed: set[str] = set()
        self._check_plan()

    def _check_plan(self) -> None:
        bid = self.plan.bundle_id
        for rel in self.plan.hash_names | self.plan.sourcemaps:
            if rel not in self.files:
                raise BuildError(f"{bid}: 계획의 파일이 src에 없음: {rel}")
        for rel in self.plan.sourcemaps:
            if PurePosixPath(rel).suffix not in JS_SUFFIXES:
                raise BuildError(f"{bid}: 소스맵은 JS 파일만: {rel}")
        for use in self.plan.steps:
            if use.name not in self.step_table:
                raise BuildError(f"{bid}: 변환 {use.name!r}를 주는 plugins가 없음")
            missing = use.files - set(self.files)
            if missing:
                raise BuildError(f"{bid}: 변환 {use.name}의 파일이 src에 없음: {sorted(missing)}")
            if any(not _is_text(rel) for rel in use.files):
                raise BuildError(f"{bid}: 변환 {use.name}은 글 파일만")
        if self.plan.rename and self.plan.mode != "minified":
            raise BuildError(f"{bid}: 펼침 모드(easy)는 이름을 줄이지 않음(rename을 비운다)")
        try:
            check_table(self.plan.rename)
        except RenameError as e:
            raise BuildError(f"{bid}: {e}") from None

    def run(self) -> tuple[dict[str, bytes], dict[str, str], dict[str, str]]:
        for rel, data in self.files.items():
            if _is_text(rel):
                self.texts[rel] = self._fill_values(rel, _decode(rel, data))
        for rel in self._order():
            self._emit(rel)
        unused = self.plan.rename - self.renamed
        if unused:
            raise BuildError(
                f"{self.plan.bundle_id}: 줄일 이름 표의 이름이 JS에 나오지 않음: {sorted(unused)}"
            )
        return self.outputs, self.names, self.values

    def _order(self) -> list[str]:
        """경로 자리가 가리키는 파일을 먼저(해시 이름이 내용에 달려서). 서로 가리키면 멈춘다."""
        deps = {rel: self._asset_refs(rel) for rel in self.files}
        done: list[str] = []
        state: dict[str, int] = {}

        visiting, finished = 1, 2

        def visit(rel: str) -> None:
            if state.get(rel) == finished:
                return
            if state.get(rel) == visiting:
                raise BuildError(f"{self.plan.bundle_id}: 경로 자리가 서로 가리킴: {rel}")
            state[rel] = visiting
            for dep in sorted(deps[rel]):
                visit(dep)
            state[rel] = finished
            done.append(rel)

        for rel in sorted(self.files):
            visit(rel)
        return done

    def _asset_refs(self, rel: str) -> set[str]:
        text = self.texts.get(rel)
        if text is None:
            return set()
        refs = {m.group(2) for m in PLACEHOLDER.finditer(text) if m.group(1) == "asset"}
        missing = refs - set(self.files)
        if missing:
            raise BuildError(
                f"{self.plan.bundle_id}: {rel}의 경로 자리가 src에 없음: {sorted(missing)}"
            )
        return refs

    def _fill_values(self, rel: str, text: str) -> str:
        def replace(m: re.Match[str]) -> str:
            if m.group(1) != "v":
                return m.group(0)
            return self._value_with_filters(rel, m.group(2), m.group(3))

        filled = PLACEHOLDER.sub(replace, text)
        if _VALUE_OPEN in filled:
            raise BuildError(f"{self.plan.bundle_id}: {rel}에 꼴이 틀린 가짜 값 자리")
        return filled

    def _value_with_filters(self, rel: str, entry_id: str, chain: str) -> str:
        bid = self.plan.bundle_id
        spec = self.plan.values.get(entry_id)
        if spec is None:
            raise BuildError(f"{bid}: {rel}의 자리 {entry_id}가 plan.json values에 없음")
        if entry_id not in self.values:
            try:
                self.values[entry_id] = fake.make_value(bid, entry_id, spec)
            except fake.FakeValueError as e:
                raise BuildError(f"{bid}: {e}") from None
        value = self.values[entry_id]
        for part in filter(None, chain.split("|")):
            name, *args = part.split(":")
            func = self.filters.get(name)
            if func is None:
                raise BuildError(f"{bid}: {rel}의 걸러내기 {name!r}를 주는 plugins가 없음")
            try:
                value = func(value, args)
            except ValueError as e:
                raise BuildError(f"{bid}: {rel} {entry_id} {name}: {e}") from None
        return value

    def _fill_assets(self, rel: str, text: str) -> str:
        def replace(m: re.Match[str]) -> str:
            return self.names[m.group(2)] if m.group(1) == "asset" else m.group(0)

        filled = PLACEHOLDER.sub(replace, text)
        if _ASSET_OPEN in filled:
            raise BuildError(f"{self.plan.bundle_id}: {rel}에 꼴이 틀린 경로 자리")
        return filled

    def _emit(self, rel: str) -> None:
        text = self.texts.get(rel)
        if text is None:
            self._check_copied(rel)
            self._put(rel, rel, self.files[rel])
            return
        source = self._fill_assets(rel, text)
        is_js = PurePosixPath(rel).suffix in JS_SUFFIXES
        # 이름 줄이기는 줄바꿈을 그대로 두어 압축의 줄 조각(소스맵)이 원본 줄을 그대로 가리킨다
        code = self._rename(rel, source) if is_js else source
        stepped = False
        for use in self.plan.steps:
            if rel in use.files:
                ctx = StepContext(self.plan.bundle_id, rel, use.options)
                code = self.step_table[use.name](code, ctx)
                stepped = True
        segments: tuple[tuple[int, int], ...] = ()
        if is_js and self.plan.mode == "minified":
            try:
                minified = minify_js(code)
            except MinifyError as e:
                raise BuildError(f"{self.plan.bundle_id}: {rel}: {e}") from None
            code, segments = minified.code, minified.segments
        code = _with_final_newline(code)
        out_rel = self._hashed(rel, code)
        if rel in self.plan.sourcemaps:
            mappings = self._mappings(source, segments, stepped)
            code = self._add_map(rel, out_rel, source, code, mappings)
        self._put(rel, out_rel, code.encode("utf-8"))

    def _rename(self, rel: str, source: str) -> str:
        """F-B01 6: 압축 모드의 JS는 늘 이름 줄이기를 거친다(표가 비어도 선언 검사는 돈다)."""
        if self.plan.mode != "minified":
            return source
        try:
            renamed = rename_js(source, self.plan.rename, rel)
        except RenameError as e:
            raise BuildError(f"{self.plan.bundle_id}: {e}") from None
        self.renamed |= renamed.used
        return renamed.code

    def _hashed(self, rel: str, code: str) -> str:
        if rel not in self.plan.hash_names:
            return rel
        digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:HASH_CHARS]
        path = PurePosixPath(rel)
        return str(path.with_name(f"{path.stem}-{digest}{path.suffix}"))

    def _mappings(self, source: str, segments: tuple[tuple[int, int], ...], stepped: bool) -> str:
        if stepped:
            return sourcemap.segment_mappings([(0, 0)])  # 변환이 줄을 바꿔 첫 글자만 잇는다
        if self.plan.mode == "minified":
            return sourcemap.segment_mappings(segments)
        return sourcemap.line_mappings(source.count(_LF) + (0 if source.endswith(_LF) else 1))

    def _add_map(self, rel: str, out_rel: str, source: str, code: str, mappings: str) -> str:
        out_name = PurePosixPath(out_rel).name
        content = source if self.plan.sourcemap_content else None
        map_bytes = sourcemap.render_map(out_name, f"{SRC_NAME}/{rel}", content, mappings)
        map_rel = f"{out_rel}.map"
        if map_rel in self.files:
            raise BuildError(f"{self.plan.bundle_id}: 맵 경로가 원본 파일과 겹침: {map_rel}")
        self._put_output(map_rel, map_bytes)
        return f"{code}//# sourceMappingURL={out_name}.map{_LF}"

    def _check_copied(self, rel: str) -> None:
        """그대로 옮기는 파일 가운데 글 파일(바이너리 확장자 밖, UTF-8)도 CR이 없어야 한다.

        F-B01 4.
        """
        if PurePosixPath(rel).suffix.lower() in fake.binary_suffixes():
            return
        data = self.files[rel]
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return
        if _CR.encode("ascii") in data:
            raise BuildError(f"원본에 CR이 있음(줄바꿈은 LF만, F-B01 4): {rel}")

    def _put(self, rel: str, out_rel: str, data: bytes) -> None:
        self._put_output(out_rel, data)
        self.names[rel] = out_rel

    def _put_output(self, out_rel: str, data: bytes) -> None:
        """결과물 하나를 모은다.

        디스크에는 모두 모은 뒤에 쓰므로 여기서 걸리면 아무것도 쓰지 않는다.
        """
        bid = self.plan.bundle_id
        if not is_bundle_relpath(out_rel) or out_rel in self.outputs:
            raise BuildError(f"{bid}: 결과물 경로가 겹치거나 허용 꼴이 아님: {out_rel[:80]}")
        if len(data) > MAX_FILE_BYTES:
            raise BuildError(f"{bid}: 결과물 파일이 {MAX_FILE_BYTES}바이트를 넘음: {out_rel}")
        self.outputs[out_rel] = data


def _is_text(rel: str) -> bool:
    return PurePosixPath(rel).suffix.lower() in TEXT_SUFFIXES


def _decode(rel: str, data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise BuildError(f"원본 글 파일이 UTF-8이 아님: {rel}") from None
    if _CR in text:
        raise BuildError(f"원본에 CR이 있음(줄바꿈은 LF만, F-B01 4): {rel}")
    return text


def _with_final_newline(text: str) -> str:
    return text if text.endswith(_LF) else text + _LF


# --- 쓰기 ------------------------------------------------------------------------------------


def _write_bundle(bundle_dir: Path, outputs: Mapping[str, bytes]) -> list[str]:
    """F-B01 1: 결과물 폴더를 비우고 새로 만든다(지난 빌드 찌꺼기를 남기지 않는다).

    옆의 임시 폴더에 다 쓴 뒤 바꿔 넣는다(T21 검증 넘김):
    옛 폴더를 `.<id>.old`로 이름 바꿈 → 새 폴더를 제자리로 이름 바꿈 → 옛 폴더 지움.
    중간에 실패하면 옛 폴더를 되돌린다. 어디서 멈춰도 번들 자리에는
    옛 결과물이나 새 결과물 하나만 온전히 있다(되돌리기마저 실패하면 옛 결과물은 `.<id>.old`에).
    디스크 오류(`OSError`)는 `BuildError`로 알린다. 돌려주는 것은 경고(빌드는 됨).
    """
    building, old = _building_dir(bundle_dir), _old_dir(bundle_dir)
    try:
        _clear_leftovers(bundle_dir, building, old)
        building.mkdir(parents=True)
        for out_rel in sorted(outputs):
            path = resolve_in_bundle(building, out_rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(outputs[out_rel])
    except OSError as e:
        shutil.rmtree(building, ignore_errors=True)
        raise BuildError(f"결과물을 쓸 수 없음({type(e).__name__}): {bundle_dir.name}") from None
    return _swap_in(building, bundle_dir, old)


def _clear_leftovers(bundle_dir: Path, building: Path, old: Path) -> None:
    """지난 빌드가 남긴 임시 폴더를 치운다. 번들 자리가 비고 `.old`만 있으면(지난 되돌리기 실패)
    지우지 않고 먼저 제자리로 되돌린다 — 지우면 옛 결과물이 아주 사라진다(T22 반려 1 5)."""
    if building.exists():
        shutil.rmtree(building)
    if old.exists():
        if bundle_dir.exists():
            shutil.rmtree(old)
        else:
            old.rename(bundle_dir)


def _swap_in(building: Path, bundle_dir: Path, old: Path) -> list[str]:
    had_old = bundle_dir.exists()
    try:
        if had_old:
            bundle_dir.rename(old)
    except OSError as e:
        shutil.rmtree(building, ignore_errors=True)
        raise BuildError(
            f"결과물을 바꿔 넣을 수 없음({type(e).__name__}, 열린 파일?): {bundle_dir.name} 그대로"
        ) from None
    try:
        building.rename(bundle_dir)
    except OSError as e:
        shutil.rmtree(building, ignore_errors=True)
        _restore_old(had_old, old, bundle_dir)
        raise BuildError(
            f"결과물을 바꿔 넣을 수 없음({type(e).__name__}): {bundle_dir.name} 그대로"
        ) from None
    if not had_old:
        return []
    try:
        shutil.rmtree(old)
    except OSError as e:
        # 새 결과물은 이미 제자리다. 멈추면 빌드 기록(build.json)이 옛 지문으로 남아 더 어긋난다
        return [f"옛 폴더를 지우지 못함({type(e).__name__}): {old.name} — 손으로 지운다"]
    return []


def _restore_old(had_old: bool, old: Path, bundle_dir: Path) -> None:
    """새 폴더를 넣지 못했을 때 옛 폴더를 제자리로.

    그마저 안 되면 옛 결과물이 어디 있는지 알린다.
    """
    if not had_old:
        return
    try:
        old.rename(bundle_dir)
    except OSError as e:
        raise BuildError(
            f"바꿔 넣기와 되돌리기가 모두 실패({type(e).__name__}): 옛 결과물은 {old.name}에 있음"
        ) from None


def _record(bundle_id: str, fingerprint: str) -> bytes:
    """F-B01 2 빌드 기록. 시각·절대 경로를 넣지 않는다(같은 빌드면 같은 기록)."""
    scripts = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(BUILD_DIR.glob("*.py"))
    }
    record = {
        "schema": RECORD_SCHEMA,
        "bundle_id": bundle_id,
        "command": [*COMMAND, bundle_id],
        "tools": {
            "python": platform.python_version(),
            "node": None,  # 쓰지 않음(압축·난독화는 직접 만든 변환 스크립트)
            "build_scripts_sha256": scripts,
        },
        "bundle_manifest_sha256": fingerprint,
    }
    return (json.dumps(record, ensure_ascii=False, indent=2) + _LF).encode("utf-8")
