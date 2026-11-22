"""F-B01 시험 번들 빌드 (기능명세 F-B01, 실험구조 1절). 원본·결과물은 tmp_path 아래(값은 가짜)."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import sys
import types
from collections.abc import Sequence
from pathlib import Path

import pytest

from common.contracts import Json
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from sources._build import build as build_module
from sources._build import fake
from sources._build.build import BuildError, StepContext, build
from sources._build.minify import MinifyError, minify_js
from tests.bundles.conftest import Dirs, WriteSource, make_plan

LF = chr(0x0A)
CR = chr(0x0D)
APP_JS = LF.join(
    [
        "/*! tinyquery v1.4.2 | MIT */",
        "// 주석은 압축에서 지운다",
        "const PAY_KEY = " + '"{{v:X1-01}}";',
        "const PARTS = [" + '"{{v:X1-02|split:2:0}}", "{{v:X1-02|split:2:1}}"];',
        "function total(a, b) {",
        "  return a + +b;",
        "}",
        "window.go = function () {",
        '  return total(1, "2") + PAY_KEY.length + PARTS.join("").length;',
        "};",
        "",
    ]
)
INDEX_HTML = '<!doctype html>\n<script src="{{asset:assets/app.js}}"></script>\n'
VALUES: dict[str, Json] = {
    "X1-01": {"form": "key", "prefix": "zelto_"},
    "X1-02": {"form": "password"},
}
FILES: dict[str, str | bytes] = {
    "index.html": INDEX_HTML,
    "assets/app.js": APP_JS,
    "favicon.ico": bytes([0, 1, 2, 0x0D, 0x0A, 255]),
}


def _plan(bundle_id: str, **overrides: Json) -> dict[str, Json]:
    base: dict[str, Json] = {
        "values": VALUES,
        "hash_names": ["assets/app.js"],
        "sourcemaps": ["assets/app.js"],
        "sourcemap_content": True,
    }
    base.update(overrides)
    return make_plan(bundle_id, **base)


def _bundle_bytes(bundle_dir: Path) -> dict[str, bytes]:
    return {
        p.relative_to(bundle_dir).as_posix(): p.read_bytes()
        for p in sorted(bundle_dir.rglob("*"))
        if p.is_file()
    }


def test_F_B01_같은원본_두번빌드_바이트같음(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", _plan("easy-1"), FILES)
    first = build("easy-1", dirs.sources, dirs.bundles)
    first_bytes = _bundle_bytes(first.bundle_dir)
    first_record = first.record_path.read_bytes()
    second = build("easy-1", dirs.sources, dirs.bundles)
    assert second.bundle_manifest_sha256 == first.bundle_manifest_sha256
    assert _bundle_bytes(second.bundle_dir) == first_bytes
    assert second.record_path.read_bytes() == first_record
    other = dirs.bundles.parent / "other-bundles"
    third = build("easy-1", dirs.sources, other)
    assert third.bundle_manifest_sha256 == first.bundle_manifest_sha256


def test_F_B01_빌드기록_도구버전(write_source: WriteSource, dirs: Dirs) -> None:
    source_dir = write_source("easy-1", _plan("easy-1"), FILES)
    result = build("easy-1", dirs.sources, dirs.bundles)
    assert result.record_path == source_dir / "build.json"
    assert not (result.bundle_dir / "build.json").exists()  # 번들 폴더 밖이어야 한다
    record = json.loads(result.record_path.read_text(encoding="utf-8"))
    assert record["bundle_id"] == "easy-1"
    assert record["command"][-2:] == ["build", "easy-1"]
    assert record["tools"]["python"] == platform.python_version()
    build_py = Path(build_module.__file__).read_bytes()
    assert (
        record["tools"]["build_scripts_sha256"]["build.py"] == hashlib.sha256(build_py).hexdigest()
    )
    assert record["bundle_manifest_sha256"] == bundle_manifest_sha256(result.bundle_dir)
    # 결과물·기록에 시각·임시 폴더·절대 경로를 넣지 않는다(F-B01 3)
    tmp_root = str(dirs.sources.parent)
    texts = [result.record_path.read_bytes(), *_bundle_bytes(result.bundle_dir).values()]
    for data in texts:
        text = data.decode("utf-8", errors="replace")
        assert tmp_root not in text
        assert tmp_root.replace("\\", "/") not in text


def test_F_B01_압축모드_한줄_해시이름(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("normal-1", _plan("normal-1", mode="minified"), FILES)
    result = build("normal-1", dirs.sources, dirs.bundles)
    js_rel = result.files["assets/app.js"]
    assert re.fullmatch(r"assets/app-[0-9a-f]{8}\.js", js_rel)
    js = (result.bundle_dir / js_rel).read_bytes()
    assert count_lines(js) == 2  # 압축 코드 한 줄 + sourceMappingURL 한 줄
    code, url = js.decode("utf-8").splitlines()
    assert url == f"//# sourceMappingURL={Path(js_rel).name}.map"
    assert code.startswith("/*! tinyquery v1.4.2 | MIT */")
    assert "주석은 압축에서" not in code
    assert "a+ +b" in code
    html = (result.bundle_dir / "index.html").read_text(encoding="utf-8")
    assert f'src="{js_rel}"' in html
    source_map = json.loads((result.bundle_dir / f"{js_rel}.map").read_text(encoding="utf-8"))
    assert source_map["file"] == Path(js_rel).name
    key = fake.make_key("normal-1", "X1-01", "zelto_")
    assert key in source_map["sourcesContent"][0]  # 맵에는 압축 전 글(원본)
    assert "{{" not in code and "{{" not in source_map["sourcesContent"][0]


def test_F_B01_펼침모드_줄바꿈있음(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", _plan("easy-1", hash_names=[]), FILES)
    result = build("easy-1", dirs.sources, dirs.bundles)
    js = (result.bundle_dir / "assets/app.js").read_bytes()
    assert count_lines(js) == APP_JS.count(LF) + 1  # 원본 줄 + sourceMappingURL 한 줄
    assert CR.encode() not in js
    key = fake.make_key("easy-1", "X1-01", "zelto_")
    assert f'const PAY_KEY = "{key}";' in js.decode("utf-8")
    parts = fake.split_value(fake.make_password("easy-1", "X1-02"), 2)
    assert f'["{parts[0]}", "{parts[1]}"]' in js.decode("utf-8")
    assert result.values["X1-01"] == key
    assert (result.bundle_dir / "favicon.ico").read_bytes() == FILES["favicon.ico"]


def test_F_B01_지난빌드_찌꺼기_없음(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", _plan("easy-1"), FILES)
    old = dirs.bundles / "easy-1" / "assets" / "old.js"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    result = build("easy-1", dirs.sources, dirs.bundles)
    assert not old.exists()
    assert "assets/old.js" not in _bundle_bytes(result.bundle_dir)


def test_F_B01_원본에_CRLF_멈춤(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", _plan("easy-1"), {**FILES, "assets/app.js": APP_JS.replace(LF, CR + LF)})
    with pytest.raises(BuildError, match="CR"):
        build("easy-1", dirs.sources, dirs.bundles)


def test_F_B01_원본폴더없음_대상ID_알림(dirs: Dirs) -> None:
    with pytest.raises(BuildError, match="easy-9"):
        build("easy-9", dirs.sources, dirs.bundles)


@pytest.mark.parametrize("bundle_id", ["_build", "Easy-1", "a", "../x"])
def test_F_B01_대상ID꼴_아니면_거절(bundle_id: str, dirs: Dirs) -> None:
    with pytest.raises(BuildError, match="대상 ID"):
        build(bundle_id, dirs.sources, dirs.bundles)


def test_F_B01_계획에_없는_자리_멈춤(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", _plan("easy-1", values={}), FILES)
    with pytest.raises(BuildError, match="X1-01"):
        build("easy-1", dirs.sources, dirs.bundles)


def test_F_B01_없는_plugin_거절(write_source: WriteSource, dirs: Dirs) -> None:
    for name in ("nothere", "build", "../x"):
        shutil.rmtree(dirs.sources / "easy-1", ignore_errors=True)
        write_source("easy-1", _plan("easy-1", plugins=[name]), FILES)
        with pytest.raises(BuildError, match="plugins"):
            build("easy-1", dirs.sources, dirs.bundles)


def test_F_B01_더한변환_plugins로_부름(
    write_source: WriteSource, dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T23·T24 꼴: _build에 모듈을 더하고 plan.json에 이름만 적으면 build.py 고침 없이 부른다."""
    seen: list[str] = []

    def shout(value: str, args: Sequence[str]) -> str:
        return value.upper()

    def mark(text: str, ctx: StepContext) -> str:
        seen.append(ctx.seed)
        return text.replace("total", "sum2")

    probe = types.ModuleType("sources._build.probe")
    probe.FILTERS = {"shout": shout}  # type: ignore[attr-defined]
    probe.STEPS = {"mark": mark}  # type: ignore[attr-defined]
    plugin_dir = tmp_path / "plugin_dir"
    plugin_dir.mkdir()
    (plugin_dir / "probe.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(build_module, "BUILD_DIR", plugin_dir)
    monkeypatch.setitem(sys.modules, "sources._build.probe", probe)
    files = {**FILES, "assets/app.js": APP_JS.replace("{{v:X1-01}}", "{{v:X1-01|shout}}")}
    steps: list[Json] = [{"step": "mark", "files": ["assets/app.js"]}]
    write_source("easy-1", _plan("easy-1", plugins=["probe"], steps=steps), files)
    result = build("easy-1", dirs.sources, dirs.bundles)
    js = (result.bundle_dir / result.files["assets/app.js"]).read_text(encoding="utf-8")
    assert fake.make_key("easy-1", "X1-01", "zelto_").upper() in js
    assert "sum2(1" in js
    assert seen == ["easy-1/assets/app.js"]


def test_F_B01_압축_자동세미콜론_자리_멈춤() -> None:
    with pytest.raises(MinifyError, match="2줄"):
        minify_js("const a = 1" + LF + "const b = 2;" + LF)


def test_F_B01_압축_글과_정규식은_그대로() -> None:
    src = LF.join(["const s = 'a  // b';", "const r = /a\\/ b/g;", "const t = `x  y`;", ""])
    assert minify_js(src).code == "const s='a  // b';const r=/a\\/ b/g;const t=`x  y`;"
