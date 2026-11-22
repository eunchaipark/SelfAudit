"""F-B04 번들 지문 — 빌드가 쓰고, 번들이 바뀌면 검사가 멈춘다 (기능명세 F-B04 예시, 값은 가상).

지문 계산 자체는 공통 함수(`common.fingerprint`, 시험 `tests/common/test_fingerprint.py`)다.
"""

from __future__ import annotations

import json

from common.fingerprint import bundle_manifest_sha256
from sources.build_tools.build import build
from sources.build_tools.verify import check_bundle
from tests.bundles.conftest import Dirs, Mini, WriteSource, make_plan
from tests.conftest import MakeBundle

LF = bytes([0x0A])
CRLF = bytes([0x0D, 0x0A])
EXAMPLE = "bc0d66f7f304129e1ccb817e6a3b5cfe4fe53e031c08703e76da0634446946ed"
EXAMPLE_CRLF = "a9ac53474d219871fe2158df818a3c75eec3438faf3e36f0410d287b543f20fb"


def test_F_B04_한바이트_바뀌면_지문다름_멈춤(make_bundle: MakeBundle, mini_bundle: Mini) -> None:
    lf = make_bundle(
        {"index.html": b"<!doctype html>" + LF, "assets/app.js": b"console.log(1)" + LF}
    )
    crlf = make_bundle(
        {"index.html": b"<!doctype html>" + LF, "assets/app.js": b"console.log(1)" + CRLF},
        name="crlf",
    )
    assert bundle_manifest_sha256(lf) == EXAMPLE
    assert bundle_manifest_sha256(crlf) == EXAMPLE_CRLF
    # 정답지 지문과 번들 지문이 다르면 검사가 멈춘다(F-B07 8)
    assert check_bundle(mini_bundle.bundle_dir, mini_bundle.answers).problems == ()
    app = mini_bundle.bundle_dir / "assets" / "app.js"
    data = app.read_bytes()
    changed = data.replace(b'"Mini Shop "', b'"Mini Shoq "')  # 한 바이트만(줄 수·닻은 그대로)
    assert len(changed) == len(data) and changed != data
    app.write_bytes(changed)
    rules = [
        (p.rule, p.where)
        for p in check_bundle(mini_bundle.bundle_dir, mini_bundle.answers).problems
    ]
    assert rules == [("8", "$.bundle_manifest_sha256")]


def test_F_B04_빌드기록의_지문이_결과물지문(write_source: WriteSource, dirs: Dirs) -> None:
    write_source("easy-1", make_plan("easy-1"), {"index.html": "<!doctype html>\n"})
    result = build("easy-1", dirs.sources, dirs.bundles)
    record = json.loads(result.record_path.read_text(encoding="utf-8"))
    assert record["bundle_manifest_sha256"] == bundle_manifest_sha256(result.bundle_dir)
    assert record["bundle_manifest_sha256"] == result.bundle_manifest_sha256
    (result.bundle_dir / "index.html").write_bytes(b"<!doctype html>" + CRLF)
    assert bundle_manifest_sha256(result.bundle_dir) != record["bundle_manifest_sha256"]
