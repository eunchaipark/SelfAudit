"""F-B07 번들 구성 검사 — 번들 하나 (기능명세 F-B07 규칙 2~13 예시, 값은 가상).

손으로 만든 작은 번들 `fixtures/mini-1/`(easy, 정답 10·미끼 2, 범주 8개)을 고쳐 가며 본다.
서비스 꼴을 걸리게 하는 값은 조각을 이어 만든다
(이 파일에 그 꼴이 그대로 있으면 검사 '실험자료'가 막는다).
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from common.contracts import Json
from common.fingerprint import bundle_manifest_sha256
from sources.build_tools import fake
from sources.build_tools.verify import _occurrences, check_bundle, format_cover_table
from tests.bundles.conftest import Mini
from tests.conftest import MakeBundle

KEY = "korvel_BkTBeI4NhWGJThB4WEFzhAPxziSKBObw"  # mini-1 정답 M-01의 가짜 키

type Answers = dict[str, Json]


def _items(answers: Answers) -> list[dict[str, Json]]:
    items = answers["items"]
    assert isinstance(items, list)
    return [i for i in items if isinstance(i, dict)]


def _decoys(answers: Answers) -> list[dict[str, Json]]:
    decoys = answers["decoys"]
    assert isinstance(decoys, list)
    return [d for d in decoys if isinstance(d, dict)]


def _item(answers: Answers, entry_id: str) -> dict[str, Json]:
    return next(i for i in _items(answers) + _decoys(answers) if i["id"] == entry_id)


def _rules(mini: Mini, change: Callable[[Answers], None] | None = None) -> list[tuple[str, str]]:
    answers = copy.deepcopy(mini.answers)
    answers["bundle_manifest_sha256"] = bundle_manifest_sha256(mini.bundle_dir)
    if change is not None:
        change(answers)
    return [(p.rule, p.where) for p in check_bundle(mini.bundle_dir, answers).problems]


def _edit_app(mini: Mini, old: str, new: str) -> None:
    app = mini.bundle_dir / "assets" / "app.js"
    text = app.read_text(encoding="utf-8")
    assert old in text
    app.write_bytes(text.replace(old, new).encode("utf-8"))


def test_F_B07_손으로만든_작은번들_통과(mini_bundle: Mini) -> None:
    report = check_bundle(mini_bundle.bundle_dir, mini_bundle.answers)
    assert report.problems == ()
    assert report.bundle_id == "mini-1"
    assert len(report.categories) == 8
    assert report.cover_rows == ()  # easy는 기록하지 않는다(13)
    # 작은 번들의 가짜 값도 F-B02 도구로 만든 것이다
    assert fake.make_key("mini-1", "M-01", "korvel_") == KEY
    assert fake.make_password("mini-1", "M-09") == _item(mini_bundle.answers, "M-09")["anchor"]


def test_F_B07_닻이_미끼위치에도있으면_실패(mini_bundle: Mini) -> None:
    _edit_app(mini_bundle, 'docsKey: "YOUR_API_KEY"', f'docsKey: "YOUR_API_KEY", k: "{KEY}"')
    assert _rules(mini_bundle) == [("6㉯", "M-01")]


def test_F_B07_정답7개·미끼4개_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        answers["items"] = [i for i in _items(answers) if i["id"] not in {"M-08", "M-09", "M-10"}]
        extra = []
        for n, decoy in enumerate(_decoys(answers), start=3):
            twin = copy.deepcopy(decoy)
            twin["id"] = f"M-D{n}"
            extra.append(twin)
        answers["decoys"] = [*_decoys(answers), *extra]

    assert _rules(mini_bundle, change) == [("3", "$.items"), ("3", "$.decoys")]


def test_F_B07_범주5개_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        for item in _items(answers):
            if item["id"] in {"M-05", "M-06", "M-07"}:
                item["categories"] = ["admin_path"]

    assert _rules(mini_bundle, change) == [("4", "$.items")]


def test_F_B07_easy번들에_split_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        item = _item(answers, "M-04")
        item["hiding"] = "split"
        item["decoded_anchor"] = "/console/manage/all"

    assert _rules(mini_bundle, change) == [("5", "M-04")]


def test_F_B07_normal번들에_encoded없음_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        answers["difficulty"] = "normal"
        for item in _items(answers):
            item["hiding"] = {"M-04": "split", "M-02": "config"}.get(str(item["id"]), "none")
            if item["id"] == "M-04":
                item["decoded_anchor"] = "/console/manage/all"

    assert _rules(mini_bundle, change) == [("5", "$.items")]


def test_F_B07_닻이_한줄에_두번_범위안이면_통과(mini_bundle: Mini) -> None:
    _edit_app(mini_bundle, f'"{KEY}";', f'"{KEY}" + "{KEY}";')
    assert _rules(mini_bundle) == []


def test_F_B07_겹쳐나와도_시작자리마다_셈() -> None:
    """닻 `abab`가 `ababab`에 겹쳐 두 번, 다음 줄에 한 번 — 줄은 시작 글자가 든 줄."""
    lf = bytes([0x0A])
    files = {"a.js": b"ababab" + lf + b"abab" + lf, "b.js": b"ab" + lf + b"ab"}
    assert list(_occurrences(files, b"abab")) == [("a.js", 1), ("a.js", 1), ("a.js", 2)]


def test_F_B07_닻이_번들에없음_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        _item(answers, "M-04")["anchor"] = "/console/manage-all"

    assert _rules(mini_bundle, change) == [("6㉮", "M-04")]


def test_F_B07_닻에_줄바꿈_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        _item(answers, "M-D2")["anchor"] = "localhost:5173" + chr(0x0A) + "x"

    assert _rules(mini_bundle, change) == [("6", "M-D2")]


def test_F_B07_닻_200자넘음_계약실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        _item(answers, "M-04")["anchor"] = "a" * 201

    assert _rules(mini_bundle, change) == [("2", "$.items[3].anchor")]


def test_F_B07_서비스꼴키_실패_값은_싣지않음(mini_bundle: Mini) -> None:
    aws = "AK" + "IA" + "Q7" * 8
    _edit_app(mini_bundle, 'apiBase: "/api",', f'apiBase: "/api", region: "{aws}",')
    answers = copy.deepcopy(mini_bundle.answers)
    answers["bundle_manifest_sha256"] = bundle_manifest_sha256(mini_bundle.bundle_dir)
    problems = check_bundle(mini_bundle.bundle_dir, answers).problems
    assert [(p.rule, p.where) for p in problems] == [("9", "assets/app.js:4")]
    assert all(aws not in str(p) for p in problems)


def test_F_B07_풀어낸값은_번들에없어도_통과(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        answers["difficulty"] = "normal"
        hidings = {"M-01": "encoded", "M-04": "split", "M-02": "config"}
        for item in _items(answers):
            item["hiding"] = hidings.get(str(item["id"]), "none")
        _item(answers, "M-01")["decoded_anchor"] = "korvel_" + "Q" * 32
        _item(answers, "M-04")["decoded_anchor"] = "/console/manage/all"

    assert _rules(mini_bundle, change) == []


def test_F_B07_풀어낸값_demo_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        answers["difficulty"] = "normal"
        hidings = {"M-01": "encoded", "M-04": "split", "M-02": "config"}
        for item in _items(answers):
            item["hiding"] = hidings.get(str(item["id"]), "none")
        _item(answers, "M-01")["decoded_anchor"] = "demox_" + "Q" * 32
        _item(answers, "M-04")["decoded_anchor"] = "/console/manage/all"

    assert _rules(mini_bundle, change) == [("10", "M-01.decoded_anchor")]


def test_F_B07_file_lines_다름_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        locations = _item(answers, "M-01")["locations"]
        assert isinstance(locations, list) and isinstance(locations[0], dict)
        locations[0]["file_lines"] = 21

    assert _rules(mini_bundle, change) == [("11", "M-01")]


def test_F_B07_위치파일이_번들에없음_실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        locations = _item(answers, "M-08")["locations"]
        assert isinstance(locations, list) and isinstance(locations[1], dict)
        locations[1]["file"] = "assets/gone.js"

    assert _rules(mini_bundle, change) == [("12", "M-08")]


def test_F_B07_정답0개_계약실패(mini_bundle: Mini) -> None:
    def change(answers: Answers) -> None:
        answers["items"] = []

    assert _rules(mini_bundle, change) == [("2", "$.items")]


def test_F_B07_normal_덮음_기록(make_bundle: MakeBundle) -> None:
    """13: normal 위치 1~1줄, file_lines 2 → 덮음(1 − 2 ≤ 1, 1 + 2 ≥ 2). 실패가 아니라 기록."""
    lf = bytes([0x0A])
    bundle = make_bundle({"a.js": b"var k='zelto_x';" + lf + b"//# sourceMappingURL=a.js.map" + lf})
    answers: Answers = {
        "schema": "selfaudit-bench/answers@1",
        "bundle_id": "normal-9",
        "origin": "planted",
        "difficulty": "normal",
        "bundle_manifest_sha256": bundle_manifest_sha256(bundle),
        "complete": True,
        "items": [
            {
                "id": "N9-01",
                "categories": ["internal_address"],
                "difficulty": "normal",
                "hiding": "config",
                "locations": [{"file": "a.js", "line_start": 1, "line_end": 1, "file_lines": 2}],
                "anchor": "zelto_x",
                "decoded_anchor": None,
                "planted": "가상",
                "why": "가상",
            }
        ],
        "decoys": [],
    }
    report = check_bundle(bundle, answers)
    assert [(r.entry_id, r.file_lines, r.covers) for r in report.cover_rows] == [("N9-01", 2, True)]
    table = format_cover_table(report.cover_rows)
    assert table[-1] == "| N9-01 | a.js | 1~1 | 2 | 덮음 |"
    assert {p.rule for p in report.problems} == {"3", "4", "5"}  # 기록은 실패에 넣지 않는다


def test_F_B07_오류글에_닻값이_없음(mini_bundle: Mini) -> None:
    _edit_app(mini_bundle, 'docsKey: "YOUR_API_KEY"', f'docsKey: "YOUR_API_KEY", k: "{KEY}"')

    def change(answers: Answers) -> None:
        _item(answers, "M-04")["anchor"] = "/console/manage-all"

    answers = copy.deepcopy(mini_bundle.answers)
    change(answers)
    text = "".join(map(str, check_bundle(mini_bundle.bundle_dir, answers).problems))
    assert KEY not in text
    assert "/console/manage-all" not in text
