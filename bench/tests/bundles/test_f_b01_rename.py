"""F-B01 6 이름 줄이기 (normal·hard, CR-008 ㉠~㉢). 명세 예시를 그대로 옮긴다. 값은 가짜다.

원본·결과물은 tmp_path 아래. 저장소의 normal·hard 원본은 tmp로 복사해 다시 빌드한다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, BuildError, build
from sources.build_tools.rename import RenameError, _classify, rename_js
from tests.bundles.conftest import Dirs, WriteSource, make_plan

LF = chr(0x0A)
MINIFIED = ("normal-1", "normal-2", "hard-1", "hard-2")


def _renamed(source: str, *names: str) -> str:
    return rename_js(source, names, "assets/app.js").code


def _stops(source: str, *names: str) -> str:
    with pytest.raises(RenameError) as err:
        rename_js(source, names, "assets/app.js")
    return str(err.value)


def test_F_B01_표의이름_결과물에없음() -> None:
    """예시: normal 원본 `const PAY_TAIL = "…"`, 표에 PAY_TAIL → 결과물에 PAY_TAIL이 없다."""
    out = _renamed('const PAY_TAIL = "x1";' + LF + "send(PAY_TAIL);" + LF, "PAY_TAIL", "send")
    assert "PAY_TAIL" not in out
    assert out == 'const a = "x1";' + LF + "b(a);" + LF


def test_F_B01_선언이름_표밖이면_빌드실패(write_source: WriteSource, dirs: Dirs) -> None:
    """예시: `const KIOSK_BANNER = …`, 표에 없음 → 빌드 멈춤, 원본 파일·줄과 이름 알림."""
    source = "const ok = 1;" + LF + 'const KIOSK_BANNER = "Lobby";' + LF
    plan = make_plan("normal-9", mode="minified")
    write_source("normal-9", plan, {"assets/app.js": source})
    with pytest.raises(BuildError, match=r"assets/app\.js 2줄: .*KIOSK_BANNER"):
        build("normal-9", dirs.sources, dirs.bundles)
    assert not (dirs.bundles / "normal-9").exists()


def test_F_B01_표밖_2자이름은_통과() -> None:
    """예시: 표에 없는 선언 이름 `ok`(2자) → 통과(2자 넘는 이름만 멈춤)."""
    assert _renamed("const ok = 1;" + LF) == "const ok = 1;" + LF


@pytest.mark.parametrize("source", ["const {tail} = cfg;", "let [a, tail] = cfg;"])
def test_F_B01_구조분해_선언_멈춤(source: str) -> None:
    """예시: hard 원본 `const {tail} = cfg` → 빌드 멈춤(구조 분해 선언)."""
    assert "구조 분해" in _stops(source, "tail", "cfg")


def test_F_B01_속성·전역·글은_그대로() -> None:
    """예시: `cfg.serviceToken`, `{pass: x}`, `window.__APP_CONFIG__`, 글 `"PAY_TAIL"` → 그대로."""
    source = (
        "const cfg = window.__APP_CONFIG__;"
        + LF
        + 'const x = { pass: cfg.serviceToken, "PAY_TAIL": 1, PAY_TAIL: 2 };'
        + LF
        + "x?.pass;"
        + LF
    )
    out = _renamed(source, "cfg", "PAY_TAIL", "pass", "serviceToken")
    assert out == (
        "const a = window.__APP_CONFIG__;"
        + LF
        + 'const x = { pass: a.serviceToken, "PAY_TAIL": 1, PAY_TAIL: 2 };'
        + LF
        + "x?.pass;"
        + LF
    )


def test_F_B01_easy는_줄이지않음(write_source: WriteSource, dirs: Dirs) -> None:
    """예시: easy 원본 `const PAY_TAIL = "…"` → 그대로. 펼침 모드에 표를 적으면 멈춘다."""
    source = 'const PAY_TAIL = "x1";' + LF
    write_source("easy-9", make_plan("easy-9"), {"assets/app.js": source})
    result = build("easy-9", dirs.sources, dirs.bundles)
    assert (result.bundle_dir / "assets" / "app.js").read_text(encoding="utf-8") == source
    shutil.rmtree(dirs.sources / "easy-9")
    write_source("easy-9", make_plan("easy-9", rename=["PAY_TAIL"]), {"assets/app.js": source})
    with pytest.raises(BuildError, match="펼침 모드"):
        build("easy-9", dirs.sources, dirs.bundles)


@pytest.mark.parametrize("source", ["send({payKey});", "send({a, payKey});"])
def test_F_B01_단축속성_export_빌드멈춤(source: str) -> None:
    """㉠ 예시: `send({payKey})`·`{a, payKey}`, 표에 payKey → 멈춤(원본 파일·줄·이름)."""
    message = _stops("let payKey = 1;" + LF + source, "payKey")
    assert "assets/app.js 2줄" in message and "payKey" in message and "단축 속성" in message


def test_F_B01_단축속성을_풀어쓰면_속성은그대로() -> None:
    """㉠ 예시: `{payKey: payKey}`, 짧은 이름 `a` → 결과물 `{payKey: a}`(값 자리만 바뀜)."""
    assert _renamed("let payKey = 1;send({payKey: payKey});", "payKey", "send") == (
        "let a = 1;b({payKey: a});"
    )


def test_F_B01_괄호안_인자는_단축속성아님() -> None:
    """㉠ 예시: `send(payKey, 2)` → 가장 안쪽 괄호가 `(`라 ㉠ 꼴이 아니고 짧은 이름으로 바뀐다."""
    assert _renamed("let payKey = 1;send(payKey, 2);", "payKey") == "let a = 1;send(a, 2);"


def test_F_B01_export선언이름은_그대로() -> None:
    """㉡ 예시: `export function mountCourier(el) {…}`, 표에 없음 → 그대로, 멈추지 않음.
    매개변수는 표대로 바뀐다. 표에 mountCourier가 있으면 멈춤."""
    source = "export function mountCourier(root) { root.x = 1; }"
    assert _renamed(source, "root") == "export function mountCourier(a) { a.x = 1; }"
    assert "export" in _stops(source, "mountCourier", "root")
    assert _renamed("export async function start(el) {}") == "export async function start(el) {}"
    assert _renamed("export const VERSION = 1;") == "export const VERSION = 1;"


@pytest.mark.parametrize(
    "source",
    [
        "export { a as b };",
        'export * from "./x.js";',
        'import { x } from "./y.js";',
        'import x from "./y.js";',
    ],
)
def test_F_B01_export목록·정적import_멈춤(source: str) -> None:
    """㉢ 예시: `export {…}`·`export *`·`import {…}`·`import x from` → 빌드 멈춤."""
    assert _stops(source)


def test_F_B01_동적import는_그대로() -> None:
    """㉢ 예시: `import("./courier.js").then(m => m.mountCourier(el))` → 그대로(`.` 뒤는 속성)."""
    source = 'import("./courier.js").then((m) => m.mountCourier(el));'
    assert _renamed(source, "mountCourier") == source


def test_F_B01_짧은이름은_그파일의_이름과_겹치지않음() -> None:
    """새 이름은 그 파일에 이름으로 나오는 글(`a`·`b`·예약어)을 건너뛴다(겹치면 뜻이 바뀐다)."""
    out = _renamed("const a = 1, b = 2;const PAY_TAIL = a + b;if (PAY_TAIL) {}", "PAY_TAIL")
    assert out == "const a = 1, b = 2;const c = a + b;if (c) {}"


def test_F_B01_표의이름이_JS에없으면_멈춤(write_source: WriteSource, dirs: Dirs) -> None:
    plan = make_plan("normal-9", mode="minified", rename=["OLD_NAME"])
    write_source("normal-9", plan, {"assets/app.js": "const ok = 1;" + LF})
    with pytest.raises(BuildError, match="OLD_NAME"):
        build("normal-9", dirs.sources, dirs.bundles)


def _rebuild(bundle_id: str, root: Path) -> dict[str, bytes]:
    sources = root / "sources"
    sources.mkdir(parents=True)
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    result = build(bundle_id, sources, root / "bundles")
    return {
        p.relative_to(result.bundle_dir).as_posix(): p.read_bytes()
        for p in sorted(result.bundle_dir.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize("bundle_id", MINIFIED)
def test_F_B01_같은원본_두번빌드_바이트같음(bundle_id: str, tmp_path: Path) -> None:
    """예시: normal·hard 원본을 각각 두 번 빌드(이름 줄이기 포함) → 두 결과물의 바이트가 같다.

    저장소의 결과물과도 같다(커밋한 번들 = 원본을 다시 빌드한 것)."""
    first = _rebuild(bundle_id, tmp_path / "one")
    second = _rebuild(bundle_id, tmp_path / "two")
    assert first == second
    committed = {
        p.relative_to(BUNDLES_DIR / bundle_id).as_posix(): p.read_bytes()
        for p in sorted((BUNDLES_DIR / bundle_id).rglob("*"))
        if p.is_file()
    }
    assert first == committed


@pytest.mark.parametrize("bundle_id", MINIFIED)
def test_F_B01_줄인이름_결과물에없음(bundle_id: str) -> None:
    """normal·hard 결과물 JS에서 표의 이름이 이름 자리(선언·부름)로 나오지 않는다.

    속성·열쇠 자리(`{api: a}`의 api)와 글은 그대로라 남을 수 있다(F-B01 6 — 속성 이름은 둔다).
    """
    plan = json.loads((SOURCES_DIR / bundle_id / "plan.json").read_text(encoding="utf-8"))
    table = set(plan["rename"])
    assert table
    for path in sorted((BUNDLES_DIR / bundle_id).rglob("*.js")):
        code = path.read_text(encoding="utf-8")
        named = {
            tok.text for tok, role in _classify(code, path.name) if role in {"ident", "declared"}
        }
        assert not (named & table), (path.name, sorted(named & table))


def test_F_B01_이름줄인_normal결과_문법검사_통과(tmp_path: Path) -> None:
    """보통 번들의 모든 JS(이름 줄이기를 거침)가 JS 문법(모듈)으로 읽힌다 — `node --check`.

    어려움 번들은 `test_F_B01_난독화결과_문법검사_통과`가 본다.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node가 없어 문법 검사를 건너뜀(PATH에 node)")
    checked = 0
    for bundle_id in ("normal-1", "normal-2"):
        for path in sorted((BUNDLES_DIR / bundle_id).rglob("*.js")):
            copy = tmp_path / f"{bundle_id}-{path.stem}.mjs"
            copy.write_bytes(path.read_bytes())
            # 읽기만 한다(--check는 실행하지 않음). 셸 없이, 인자는 고정 + 임시 파일 경로뿐
            result = subprocess.run(  # noqa: S603
                [node, "--check", str(copy)], capture_output=True, timeout=60, check=False
            )
            assert result.returncode == 0, copy.name
            checked += 1
    assert checked == 4
