"""정답지·대상 목록 뜻 규칙 시험 (실험구조 2.10)."""

from __future__ import annotations

import pytest

from common.contracts import REPO_ROOT, ContractError, Json, validate_contract
from tests.common.examples import answers_example, first_item, first_location, targets_example


def test_common_정답지_줄범위_거꾸로·파일줄수_넘음() -> None:
    data = answers_example()
    location = first_location(first_item(data))
    location.update(line_start=13, line_end=12)
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0]", "line_end >= line_start")
    ]
    location.update(line_start=12, line_end=121)
    assert validate_contract("answers", data) == [
        ContractError("$.items[0].locations[0]", "line_end <= file_lines")
    ]


def test_common_정답지_ID_겹침() -> None:
    data = answers_example()
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    decoys[0]["id"] = "E1-01"
    assert validate_contract("answers", data) == [ContractError("$.decoys[0].id", "id 겹침")]


@pytest.mark.parametrize(
    ("origin", "difficulty", "complete", "expected"),
    [
        ("planted", "easy", True, []),
        ("practice", "mixed", False, []),
        ("planted", "mixed", True, ["$.difficulty"]),
        ("practice", "easy", False, ["$.difficulty"]),
        ("practice", "mixed", True, ["$.complete"]),
        ("planted", "hard", False, ["$.complete"]),
    ],
)
def test_common_정답지_종류와_난이도·complete(
    origin: str, difficulty: str, complete: bool, expected: list[str]
) -> None:
    data = answers_example()
    data.update(origin=origin, difficulty=difficulty, complete=complete)
    assert [e.where for e in validate_contract("answers", data)] == expected


@pytest.mark.parametrize(
    ("hiding", "decoded", "expected"),
    [
        ("encoded", "zelto_fakeDecodedValue01", []),
        ("split", "zelto_fakeDecodedValue01", []),
        ("plain", "zelto_fakeDecodedValue01", ["split·encoded·obfuscated만"]),
        ("encoded", None, []),
        ("encoded", "SAME", ["anchor와 같음"]),
    ],
)
def test_common_정답지_풀어낸값(hiding: str, decoded: str | None, expected: list[str]) -> None:
    data = answers_example()
    item = first_item(data)
    item["hiding"] = hiding
    item["decoded_anchor"] = item["anchor"] if decoded == "SAME" else decoded
    assert [e.rule for e in validate_contract("answers", data)] == expected


ITEM_LOC = "$.items[0].locations[0].anchor"


def _decoy(data: dict[str, Json]) -> dict[str, Json]:
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    return decoys[0]


def _decoy_location(data: dict[str, Json]) -> dict[str, Json]:
    locations = _decoy(data)["locations"]
    assert isinstance(locations, list) and isinstance(locations[0], dict)
    return locations[0]


def _overlaps(data: dict[str, Json]) -> list[tuple[str, str]]:
    return [(e.where, e.rule) for e in validate_contract("answers", data)]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PAY_TAIL_piece_01", []),
        (None, []),
        ("ITEM_ANCHOR", [(ITEM_LOC, "닻 겹침: 같음 ($.items[0].anchor)")]),
        ("ANCHOR_HEAD4", [(ITEM_LOC, "닻 겹침: 들어 있음 ($.items[0].anchor)")]),
        ("DECODED", [("$.items[0].decoded_anchor", f"닻 겹침: 같음 ({ITEM_LOC})")]),
        ("DECODED_PIECE", []),
        ("DECOY_ANCHOR", [(ITEM_LOC, "닻 겹침: 같음 ($.decoys[0].anchor)")]),
        ("abc", [(ITEM_LOC, "minLength 4")]),
    ],
)
def test_common_정답지_위치닻(value: str | None, expected: list[tuple[str, str]]) -> None:
    """실험구조 8.4 2 '닻 겹침': 위치 닻은 자기 닻과 같거나 서로 들어 있으면 안 되고, 자기 풀어낸
    값과는 같으면 안 된다(나눠 쓴 조각이 풀어낸 값 안에 드는 것은 된다). 다른 정답·미끼의 닻과는
    같거나 들어 있으면 안 된다."""
    data = answers_example()
    item = first_item(data)
    item.update(hiding="split", decoded_anchor="zelto_fakeDecodedValue01")
    anchor, decoded = item["anchor"], item["decoded_anchor"]
    assert isinstance(anchor, str) and isinstance(decoded, str)
    named: dict[str, Json] = {
        "ITEM_ANCHOR": anchor,
        "ANCHOR_HEAD4": anchor[:4],
        "DECODED": decoded,
        "DECODED_PIECE": decoded[6:16],
        "DECOY_ANCHOR": _decoy(data)["anchor"],
    }
    first_location(item)["anchor"] = named.get(value or "", value)
    assert _overlaps(data) == expected


def test_common_정답지_미끼풀어낸값이_정답닻과_같음() -> None:
    data = answers_example()
    decoy = _decoy(data)
    decoy.update(hiding="encoded", decoded_anchor=first_item(data)["anchor"])
    assert _overlaps(data) == [("$.decoys[0].decoded_anchor", "닻 겹침: 같음 ($.items[0].anchor)")]


def test_common_정답지_닻겹침_다른정답끼리_양방향() -> None:
    """미끼 위치 닻이 정답 풀어낸 값 안에, 그리고 미끼 풀어낸 값이 정답 위치 닻 안에."""
    data = answers_example()
    item = first_item(data)
    item.update(hiding="encoded", decoded_anchor="zelto_fakeDecodedValue01")
    _decoy_location(data)["anchor"] = "fakeDecoded"
    assert _overlaps(data) == [
        ("$.items[0].decoded_anchor", "닻 겹침: 들어 있음 ($.decoys[0].locations[0].anchor)")
    ]
    _decoy_location(data)["anchor"] = None
    _decoy(data).update(hiding="encoded", decoded_anchor="piece")
    first_location(item)["anchor"] = "long_piece_here"
    assert _overlaps(data) == [(ITEM_LOC, "닻 겹침: 들어 있음 ($.decoys[0].decoded_anchor)")]


def test_common_정답지_위치닻_미끼도() -> None:
    data = answers_example()
    _decoy_location(data)["anchor"] = "cover_piece_only_here"
    assert validate_contract("answers", data) == []
    _decoy_location(data)["anchor"] = _decoy(data)["anchor"]
    assert [e.where for e in validate_contract("answers", data)] == [
        "$.decoys[0].locations[0].anchor"
    ]


def _many_anchors(n_items: int, per_item: int) -> dict[str, Json]:
    data = answers_example()
    item = first_item(data)
    items: list[Json] = []
    for i in range(n_items):
        copy = dict(item)
        copy["id"] = f"E1-{i:03d}"
        copy["anchor"] = f"anchor_{i:03d}_" + "a" * 100
        copy["locations"] = [
            {**first_location(item), "anchor": f"loc_{i:03d}_{j:02d}_" + "b" * 100}
            for j in range(per_item)
        ]
        items.append(copy)
    data["items"] = items
    return data


def test_common_정답지_위치닻_100개넘으면_오류() -> None:
    assert _overlaps(_many_anchors(20, 5)) == []
    assert _overlaps(_many_anchors(101, 1)) == [("$", "위치 닻 100개 넘음")]


def test_common_정답지_닻겹침_오류100곳에서_멈춤() -> None:
    data = _many_anchors(60, 1)
    items = data["items"]
    assert isinstance(items, list)
    for raw in items:
        assert isinstance(raw, dict)
        first_location(raw)["anchor"] = "same_piece_everywhere"
    rules = [e.rule for e in validate_contract("answers", data)]
    assert len(rules) == 101 and rules[-1] == "닻 겹침 100곳에서 멈춤, 나머지 생략"


def test_common_정답지_닻겹침_상한에서_시간() -> None:
    """정답 200개·위치 닻 100개(상한)에서 둘씩 비교가 끝나는지 — 0.25초쯤(8.4 '닻 겹침')."""
    import time

    data = _many_anchors(200, 1)
    items = data["items"]
    assert isinstance(items, list)
    for i, raw in enumerate(items):
        assert isinstance(raw, dict)
        raw.update(hiding="encoded", decoded_anchor=f"D{i:03d}" + "ba" * 98)
        location = first_location(raw)
        location["anchor"] = f"L{i:03d}" + "ab" * 98 if i < 100 else None
    started = time.perf_counter()
    assert _overlaps(data) == []
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize(
    ("hiding", "decoded", "expected"),
    [
        ("encoded", "Lobby kiosk: tap a room", []),
        ("split", "Lobby kiosk: tap a room", []),
        (None, None, []),
        ("comment", None, []),
        (None, "Lobby kiosk: tap a room", ["split·encoded·obfuscated만"]),
        ("plain", "Lobby kiosk: tap a room", ["split·encoded·obfuscated만"]),
        ("encoded", "SAME", ["anchor와 같음"]),
        ("hidden", None, ["enum"]),
    ],
)
def test_common_정답지_미끼_hiding·풀어낸값(
    hiding: str | None, decoded: str | None, expected: list[str]
) -> None:
    """실험구조 8.4 3·6: 미끼의 선택 칸 hiding·decoded_anchor, 뜻 규칙은 정답과 같다."""
    data = answers_example()
    decoys = data["decoys"]
    assert isinstance(decoys, list) and isinstance(decoys[0], dict)
    decoy = decoys[0]
    if hiding is not None:
        decoy["hiding"] = hiding
    if decoded is not None:
        decoy["decoded_anchor"] = decoy["anchor"] if decoded == "SAME" else decoded
    assert [e.rule for e in validate_contract("answers", data)] == expected


def test_common_대상목록_ID겹침·경로꼴() -> None:
    data = targets_example()
    rows = data["targets"]
    assert isinstance(rows, list)
    rows.append(
        {"id": "easy-1", "kind": "planted", "bundle": "../x", "answers": "bench/answers/x.json"}
    )
    rows.append(
        {
            "id": "juice-shop-18",
            "kind": "practice",
            "bundle": ".tools/juice-shop/frontend/dist",
            "answers": "bench/answers/juice-shop-18.json",
        }
    )
    assert validate_contract("targets", data) == [
        ContractError("$.targets[2].id", "id 겹침"),
        ContractError("$.targets[2].bundle", "bench/bundles/<id>"),
        ContractError("$.targets[2].answers", "bench/answers/<id>.json"),
        ContractError("$.targets[3].bundle", "bench/bundles/<id>"),
    ]


@pytest.mark.parametrize(
    ("target_id", "kind", "expected"),
    [
        ("empty", "planted", [ContractError("$.targets[0].id", "예약 ID(empty·gate)")]),
        ("gate", "practice", [ContractError("$.targets[0].id", "예약 ID(empty·gate)")]),
        ("gate", "mine", [ContractError("$.targets[0].id", "예약 ID(empty·gate)")]),
        ("empty-1", "planted", []),  # 예약 ID와 글자까지 같을 때만
        ("gates", "planted", []),
    ],
)
def test_common_대상목록_예약ID_empty·gate_거절(
    target_id: str, kind: str, expected: list[ContractError]
) -> None:
    if kind == "mine":
        bundle, answers = "C:\\Users\\fake\\AppData\\Local\\SelfAudit-private\\b", None
    else:
        bundle, answers = f"bench/bundles/{target_id}", f"bench/answers/{target_id}.json"
    entry: dict[str, Json] = {"id": target_id, "kind": kind, "bundle": bundle, "answers": answers}
    data: dict[str, Json] = {"schema": "selfaudit-bench/targets@1", "targets": [entry]}
    assert validate_contract("targets", data) == expected


BS = chr(92)
INSIDE_REPO = str(REPO_ROOT / "bench" / "bundles" / "blog")
SNEAK_IN = str(REPO_ROOT.parent / "zz") + BS + ".." + BS + REPO_ROOT.name + BS + "bench"


@pytest.mark.parametrize(
    ("bundle", "answers", "expected"),
    [
        ("C:\\Users\\fake\\AppData\\Local\\SelfAudit-private\\bundles\\blog", None, []),
        ("D:/private/blog", "D:/private/answers/blog.json", []),
        ("bundles/blog", None, ["$.targets[0].bundle"]),
        ("C:\\fake\\blog", "answers/blog.json", ["$.targets[0].answers"]),
        (BS * 2 + "server" + BS + "share" + BS + "blog", None, ["$.targets[0].bundle"]),  # UNC
        (BS * 2 + "?" + BS + "C:" + BS + "fake" + BS + "blog", None, ["$.targets[0].bundle"]),
        (BS * 2 + "." + BS + "C:" + BS + "fake" + BS + "blog", None, ["$.targets[0].bundle"]),
        ("C:fake\\blog", None, ["$.targets[0].bundle"]),  # 드라이브 상대
        (INSIDE_REPO, None, ["$.targets[0].bundle"]),  # 저장소 안
        (INSIDE_REPO + (BS + "..") * 4 + BS + "x", None, []),  # 풀면 저장소 밖
        (SNEAK_IN, None, ["$.targets[0].bundle"]),  # 글로는 밖, 풀면 저장소 안
    ],
)
def test_common_대상목록_내앱은_저장소밖_드라이브경로(
    bundle: str, answers: str | None, expected: list[str]
) -> None:
    entry: dict[str, Json] = {
        "id": "mine-blog",
        "kind": "mine",
        "bundle": bundle,
        "answers": answers,
    }
    data: dict[str, Json] = {"schema": "selfaudit-bench/targets@1", "targets": [entry]}
    assert [e.where for e in validate_contract("targets", data)] == expected
