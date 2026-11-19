"""F-S02 소스맵 노출 — 기능명세 예시를 그대로 옮긴다."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable

from app.contracts.engine import Finding, Location, Severity, Skipped, SkipReason
from app.rules import secrets, sourcemaps, text

KEY = b"selfaudit-test-key"  # 명세 '로컬 키'의 테스트 키 (가상)
AWS = "AKIAIOSFODNN7EXAMPLE"
NOTICE_1 = "건너뛴 소스맵 1개는 내용을 점검하지 않았습니다. 배포에서 .map을 뺐는지 확인하세요"
NOTICE_2 = "건너뛴 소스맵 2개는 내용을 점검하지 않았습니다. 배포에서 .map을 뺐는지 확인하세요"


def scan(
    path: str, content: str, bundle: Iterable[str] = (), skipped: Iterable[Skipped] = ()
) -> sourcemaps.SourcemapScan:
    in_bundle = sourcemaps.bundle_paths([path, *bundle], skipped)
    spans = secrets.scan_file(path, content, KEY).spans
    return sourcemaps.scan_file(path, content, in_bundle=in_bundle, s01_spans=spans)


def found(
    path: str, content: str, bundle: Iterable[str] = (), skipped: Iterable[Skipped] = ()
) -> list[Finding]:
    return list(scan(path, content, bundle, skipped).findings)


def only(path: str, content: str, bundle: Iterable[str] = ()) -> Finding:
    result = found(path, content, bundle)
    assert len(result) == 1, result
    return result[0]


def sourcemap(sources: list[object], contents: list[object]) -> str:
    return json.dumps({"version": 3, "sources": sources, "sourcesContent": contents})


# ---- 1번: .map 파일 ----


def test_F_S02_맵_sourcesContent12_높음() -> None:
    raw = sourcemap(
        [f"src/m{i}.ts" for i in range(12)], [f"export const v{i} = {i};" for i in range(12)]
    )
    f = only("assets/index.js.map", raw)
    assert (f.rule_id, f.severity) == ("S02-MAP-CONTENT", Severity.HIGH)
    assert f.value == "sourcesContent 12개 / sources 12개"
    assert f.path == "assets/index.js.map"
    assert f.location is None
    assert f.evidence_key == "-"
    assert f.fix == "배포 빌드에서 소스맵을 끄거나(.map 빼기), 오류 추적 서비스에만 따로 올리세요"


def test_F_S02_null_빈문자열이면_PATHS_낮음() -> None:
    f = only("assets/index.js.map", sourcemap(["a.ts", "b.ts"], [None, ""]))
    assert (f.rule_id, f.severity) == ("S02-MAP-PATHS", Severity.LOW)
    assert f.value == "sourcesContent 0개 / sources 2개"
    assert f.fix == "원본 폴더 구조가 드러납니다. 배포에서 .map을 빼세요"


def test_F_S02_내용과_이름이_모두_없으면_발견없음() -> None:
    assert found("a.js.map", sourcemap([], [])) == []
    assert found("a.js.map", json.dumps({"version": 3, "mappings": ""})) == []


def test_F_S02_내용_일부만_있으면_있는_수만_센다() -> None:
    f = only("a.js.map", sourcemap(["a.ts", "b.ts", "c.ts"], ["x", None, ""]))
    assert (f.rule_id, f.value) == ("S02-MAP-CONTENT", "sourcesContent 1개 / sources 3개")


def test_F_S02_JSON객체아님_배열도_건너뜀() -> None:
    for raw in ("not json", "[1,2]", "123", '"x"', "null"):
        result = scan("bad.js.map", raw)
        assert (result.findings, result.not_sourcemap) == ((), True), raw
    assert scan("a.js.map", sourcemap([], [])).not_sourcemap is False


def test_F_S02_BOM이_붙은_map도_JSON으로_읽는다() -> None:
    raw = text.BOM + sourcemap(["a.ts"], [f'k="{AWS}"'])
    assert only("a.js.map", raw).rule_id == "S02-MAP-CONTENT"
    # 같은 판정이 F-S01에도 쓰인다(S01이 원문을 놓치지 않는다)
    assert [f.rule_id for f in secrets.scan_file("a.js.map", raw, KEY).findings] == ["S01-AWS"]


# ---- 2~4번: JS·CSS의 sourceMappingURL ----


def test_F_S02_map이_번들에_있으면_JS는_발견없음() -> None:
    assert found("app.js", "x();\n//# sourceMappingURL=app.js.map", ["app.js.map"]) == []


def test_F_S02_map이_번들에_없으면_DANGLING() -> None:
    f = only("app.js", "x();\n//# sourceMappingURL=app.js.map")
    assert (f.rule_id, f.severity, f.path) == ("S02-DANGLING", Severity.LOW, "app.js")
    assert f.value == "app.js.map"
    assert f.location == Location(2, 22)
    assert f.evidence_key == "-"
    assert f.fix == "번들에는 없지만 서버에 .map이 따로 올라갔는지 확인하세요"


def test_F_S02_대소문자_다르면_DANGLING() -> None:
    f = only("assets/app.js", "//# sourceMappingURL=App.js.map", ["assets/app.js.map"])
    assert (f.rule_id, f.severity, f.path) == ("S02-DANGLING", Severity.LOW, "assets/app.js")


def test_F_S02_물음표_뒤를_뗀다() -> None:
    assert (
        found("assets/app.js", "//# sourceMappingURL=app.js.map?v=3", ["assets/app.js.map"]) == []
    )
    assert found("assets/app.js", "//# sourceMappingURL=app.js.map#x", ["assets/app.js.map"]) == []


def test_F_S02_슬래시로_시작하면_맨위_기준() -> None:
    css = "a{}\n/*# sourceMappingURL=/assets/a.css.map */"
    assert found("assets/a.css", css, ["assets/a.css.map"]) == []
    # `*/` 앞에 공백이 없어도 값은 `*/` 앞까지
    assert found("assets/a.css", "/*# sourceMappingURL=a.css.map*/", ["assets/a.css.map"]) == []


def test_F_S02_퍼센트_디코딩() -> None:
    assert (
        found("assets/app.js", "//# sourceMappingURL=my%20app.js.map", ["assets/my app.js.map"])
        == []
    )


def test_F_S02_맵_밖으로_나가면_DANGLING() -> None:
    f = only("app.js", "//# sourceMappingURL=../../secret.map", ["secret.map"])
    assert (f.rule_id, f.value) == ("S02-DANGLING", "../../secret.map")
    # 폴더 안에서 위로 올라가도 맨 위를 넘지 않으면 번들 안
    assert (
        found("assets/js/app.js", "//# sourceMappingURL=../maps/a.map", ["assets/maps/a.map"]) == []
    )


def test_F_S02_골뱅이_꼴도_본다() -> None:
    f = only("old.js", "//@ sourceMappingURL=old.js.map")
    assert f.rule_id == "S02-DANGLING"


def test_F_S02_주소_형식이면_DANGLING() -> None:
    for value in (
        "https://cdn.myapp.kr/app.js.map",
        "http://cdn.myapp.kr/app.js.map",
        "file:///C:/build/app.js.map",
        "//cdn.myapp.kr/app.js.map",
    ):
        f = only(
            "app.js", f"//# sourceMappingURL={value}", ["app.js.map", "cdn.myapp.kr/app.js.map"]
        )
        assert (f.rule_id, f.value) == ("S02-DANGLING", value)


def test_F_S02_data_URL_INLINE() -> None:
    value = "data:application/json;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbXX0="
    f = only("app.js", f"x();\n//# sourceMappingURL={value}")
    assert (f.rule_id, f.severity, f.path) == ("S02-INLINE", Severity.HIGH, "app.js")
    assert f.value == "data:application/json;base64,e…"
    assert f.fix == "인라인 소스맵을 끄세요 (배포 빌드 설정)"
    assert "eyJ2ZXJzaW9u" not in f.snippet


def test_F_S02_마지막_sourceMappingURL만_본다() -> None:
    content = (
        "//# sourceMappingURL=a.js.map\nx();\n"
        "/*# sourceMappingURL=data:x */\n//# sourceMappingURL=b.js.map"
    )
    f = only("app.js", content, ["a.js.map"])
    assert (f.rule_id, f.value) == ("S02-DANGLING", "b.js.map")
    assert only("app.js", content.rsplit("\n", 1)[0], ["a.js.map"]).rule_id == "S02-INLINE"


def test_F_S02_JS_CSS가_아니면_보지_않는다() -> None:
    for path in ("index.html", "data.json"):
        assert found(path, "//# sourceMappingURL=gone.map") == []
    for path in ("a.mjs", "a.cjs", "A.JS"):
        assert only(path, "//# sourceMappingURL=gone.map").rule_id == "S02-DANGLING"


def test_F_S02_근거조각에_S01_원문이_없다() -> None:
    content = (
        'password:"hunter2hunter2";\n'
        "//# sourceMappingURL=https://deploy:pw1234567@maps.myapp.kr/a.js.map"
    )
    f = only("app.js", content)
    assert f.rule_id == "S02-DANGLING"
    for raw in ("hunter2hunter2", "pw1234567"):
        assert raw not in f.snippet, f.snippet


# ---- 6번: 건너뛴 소스맵 안내 ----


def test_F_S02_건너뛴map_크기초과면_DANGLING없고_안내1개() -> None:
    skipped = [Skipped("assets/app.js.map", SkipReason.TOO_LARGE)]
    assert found("assets/app.js", "//# sourceMappingURL=app.js.map", (), skipped) == []
    assert sourcemaps.skipped_notice(skipped) == NOTICE_1


def test_F_S02_건너뛴map2개_안내n2() -> None:
    skipped = [
        Skipped("a.js.map", SkipReason.TOO_LARGE),
        Skipped("B.JS.MAP", SkipReason.NAME_CLASH),
        Skipped("c.js", SkipReason.TOO_LARGE),
    ]
    assert sourcemaps.skipped_notice(skipped) == NOTICE_2


def test_F_S02_소스맵형식아님은_안내에_세지않음() -> None:
    assert scan("bad.js.map", "not json").not_sourcemap is True
    assert sourcemaps.skipped_notice([Skipped("bad.js.map", SkipReason.NOT_SOURCEMAP)]) is None
    assert sourcemaps.skipped_notice([]) is None


# ---- 성능 ----


def test_F_S02_표시가_많아도_선형() -> None:
    for unit in ("//# sourceMappingURL=", "/*# sourceMappingURL=", "//# sourceMappingURL=a "):
        content = unit * 50_000
        t0 = time.perf_counter()
        scan("app.js", content)
        assert time.perf_counter() - t0 < 5.0, unit
