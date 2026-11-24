"""어려움 번들 hard-1·hard-2 (기능명세 F-B01·F-B02·F-B03·F-B07, 설계 2.7 표 hard 줄).

hard 줄: 압축(한 줄) + 직접 만든 난독화(문자열 배열·배열 돌리기·글자 코드),
숨기는 방법 `obfuscated`·`sourcemap_only`·`split`. 난독화는 `build_tools/obfuscate.py`(T24).
난독화 결과를 푸는 일은 이 시험이 따로 한다(도구의 코드를 쓰지 않고 결과물 글만 읽어서) —
도구가 틀려도 같은 틀린 셈으로 통과하지 않게. 값은 모두 가짜다.
"""

from __future__ import annotations

import ipaddress
import itertools
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from common.contracts import Json, read_contract
from common.fingerprint import bundle_manifest_sha256
from common.lines import count_lines
from sources.build_tools import fake, obfuscate
from sources.build_tools.build import BUNDLES_DIR, SOURCES_DIR, StepContext, build
from sources.build_tools.locate import write_answers
from sources.build_tools.verify import (
    HIDING_BY_DIFFICULTY,
    REPO_ROOT,
    check_target,
    repo_target,
)
from tests.bundles.conftest import bundle_texts, expected_short, short_or_none

HARD = ("hard-1", "hard-2")
ALL_CATEGORIES = 8
HIDDEN = frozenset({"split", "encoded", "obfuscated"})
# 난독화한 파일(원본 src 안 경로) — plan.json steps와 같아야 한다(시험 `_obfuscated_files`가 본다)
OBFUSCATED = {"hard-1": "assets/index.js", "hard-2": "assets/app.js"}
# 난독화 결과 머리: 배열 · 되돌리는 즉시 실행 함수 · 찾기 함수(obfuscate 머리글의 꼴)
HEADER = re.compile(
    r"const (_0x[0-9a-f]{4})=\[(.*?)\];"
    r"\(function\(a,n\)\{while\(n--\)\{a\.push\(a\.shift\(\)\);\}\}\)\(\1,(0x[0-9a-f]+)\);"
    r"function (_0x[0-9a-f]{4})\(i\)\{return \1\[i\];\}"
)
ENTRY = re.compile(r'"((?:\\x[0-9a-f]{2}|\\u[0-9a-f]{4})*)"')
CODE_UNIT = re.compile(r"\\x([0-9a-f]{2})|\\u([0-9a-f]{4})")
# 원본의 큰따옴표 글(우리 원본은 이스케이프 없는 큰따옴표 글만 쓴다 —
# 아니면 배열에서 찾지 못해 실패)
STRING_LITERAL = re.compile(r'"([^"\\\n]*)"')
CHAR_CODES = re.compile(r"(?:\\x[0-9a-f]{2}|\\u[0-9a-f]{4})+")
HASHED = re.compile(r"[a-z]+-[0-9a-f]{8}\.(?:js|css)")
MAP_LINE = re.compile(r"//# sourceMappingURL=[a-z]+-[0-9a-f]{8}\.js\.map")
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
PUBLIC_HOSTS = frozenset({"res.cloudinary.com", "d3r8k2m7x4q9wz.cloudfront.net"})
IPV4 = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
URL_HOST = re.compile(r"(?:https?|wss?)://([A-Za-z0-9.-]+)")
# 손으로 나눈 글(심기 계획 값이 아닌 것): 정답지 ID → 실행할 때 이어 붙이는 조각 차례.
# 미끼 둘은 '나눔'을 거치는 미끼다(숨긴 방법마다 그 방법을 거치는 미끼 — 배정문 공정성)
HAND_SPLIT = {
    "H1-05": ("/internal", "/expense/bulk-approve"),
    "H1-D2": ("https://res.cloudinary.com", "/trevia/image/upload/"),
    "H2-06": ("/staff", "/subscriptions/force-renew"),
    "H2-D2": ("https://d3r8k2m7x4q9wz.cloudfront.net", "/plants/photos/"),
}
# 바깥 주소(공개 CDN)를 담은 설정 열쇠
HOST_KEYS = {"hard-1": "receiptCdn", "hard-2": "photoHost"}
# 미끼가 거치는 숨기는 방법(정답지 미끼에는 hiding 칸이 없어 시험이 적는다)
DECOY_HIDING = {
    "H1-D1": "obfuscated",
    "H1-D2": "split",
    "H1-D3": "sourcemap_only",
    "H2-D1": "obfuscated",
    "H2-D2": "split",
    "H2-D3": "sourcemap_only",
}
# 한 정답의 값을 상수에 담는 자리(압축 꼴 `const <짧은 이름>=<찾기>(0x…);`) — 돌리기 시험이
# 찾기 번호를 읽는다. 상수 이름은 이름 줄이기(F-B01 6)로 짧아져 이름이 아니라 값으로 찾는다
CONST_SLOTS = {"hard-1": "H1-01", "hard-2": "H2-01"}
SAMPLE = (
    'const cfg = {apiBase: "/api", "dumpState": true};\n'
    'const url = cfg.apiBase + "/me";\n'
    'switch (url) { case "/x": break; default: break; }\n'
    "fetch(url).then((r) => r.json());\n"
    "const n = 1.5 + cfg?.size;\n"
    "const all = [...[1, 2]];\n"
    "const r = /a\\/b/g;\n"
    'import("/assets/more.js").then((m) => m.go("한글 🌱"));\n'
)


# --- 결과물 읽기 (도구를 쓰지 않는다) -------------------------------------------------------------


@dataclass(frozen=True)
class Decoded:
    array_name: str
    lookup_name: str
    stored: tuple[str, ...]  # 결과물에 적힌 차례
    turns: int
    body: str  # 머리 뒤의 코드

    @property
    def logical(self) -> tuple[str, ...]:
        """`push(shift())`를 `turns`번 한 뒤의 배열 — 찾기 번호가 가리키는 차례."""
        n = len(self.stored)
        return tuple(self.stored[(i + self.turns) % n] for i in range(n))

    def lookups(self) -> Iterator[int]:
        pattern = re.compile(re.escape(self.lookup_name) + r"\((0x[0-9a-f]+)\)")
        for m in pattern.finditer(self.body):
            yield int(m.group(1), 16)


def _unescape(entry: str) -> str:
    units = [int(a or b, 16) for a, b in CODE_UNIT.findall(entry)]
    return "".join(map(chr, units)).encode("utf-16", "surrogatepass").decode("utf-16")


def _decode(code: str) -> Decoded:
    m = HEADER.match(code)
    assert m is not None, "난독화 머리가 없음"
    entries = ENTRY.findall(m.group(2))
    assert ",".join(f'"{e}"' for e in entries) == m.group(2)  # 배열에는 글자 코드 글만
    stored = tuple(_unescape(e) for e in entries)
    return Decoded(m.group(1), m.group(4), stored, int(m.group(3), 16), code[m.end() :])


def _answers(bundle_id: str) -> dict[str, Json]:
    return read_contract("answers", REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json")


def _entries(answers: dict[str, Json], group: str) -> list[dict[str, Json]]:
    value = answers[group]
    assert isinstance(value, list)
    return [e for e in value if isinstance(e, dict)]


def _items(bundle_id: str, hiding: str | None = None) -> list[dict[str, Json]]:
    items = _entries(_answers(bundle_id), "items")
    return [i for i in items if hiding is None or i["hiding"] == hiding]


def _decoys(bundle_id: str) -> list[dict[str, Json]]:
    return _entries(_answers(bundle_id), "decoys")


def _location_files(entry: dict[str, Json]) -> set[str]:
    locations = entry["locations"]
    assert isinstance(locations, list)
    return {str(loc["file"]) for loc in locations if isinstance(loc, dict)}


def _texts(bundle_id: str) -> dict[str, str]:
    bundle = BUNDLES_DIR / bundle_id
    return {
        path.relative_to(bundle).as_posix(): path.read_bytes().decode("utf-8")
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }


def _obfuscated_path(bundle_id: str) -> str:
    """난독화한 파일의 결과물 경로(해시 이름). 그런 파일은 번들에 하나다."""
    stem = Path(OBFUSCATED[bundle_id]).stem
    (name,) = [
        rel for rel in _texts(bundle_id) if re.fullmatch(rf"assets/{stem}-[0-9a-f]{{8}}\.js", rel)
    ]
    return name


def _obfuscated(bundle_id: str) -> Decoded:
    return _decode(_texts(bundle_id)[_obfuscated_path(bundle_id)].rstrip(chr(0x0A)))


def _occurrences(text: str, needle: str) -> int:
    count, start = 0, text.find(needle)
    while start >= 0:
        count += 1
        start = text.find(needle, start + 1)
    return count


def _plan(bundle_id: str) -> dict[str, Json]:
    plan = json.loads((SOURCES_DIR / bundle_id / "plan.json").read_text(encoding="utf-8"))
    assert isinstance(plan, dict)
    return plan


def _generated(bundle_id: str) -> dict[str, str]:
    """심기 계획(plan.json values)으로 만든 가짜 값 {정답·미끼 ID: 값}."""
    values = _plan(bundle_id)["values"]
    assert isinstance(values, dict)
    return {
        eid: fake.make_value(bundle_id, eid, spec)
        for eid, spec in values.items()
        if isinstance(spec, dict)
    }


def _expected_decoded(bundle_id: str, entry: dict[str, Json], whole: str) -> str:
    """정답지 풀어낸 값의 기대값: 값 전체 `whole`, 64자를 넘고 줄로 가를 수 없는 위치가 있으면
    F-B03 5의 앞 조각(`expected_short`)."""
    answers = _answers(bundle_id)
    texts = bundle_texts(BUNDLES_DIR / bundle_id)
    return expected_short(whole, entry, answers, texts, decoded=True)


def _named(code: str, decoded: Decoded) -> str:
    """시험에서 읽기 쉽게 배열·찾기 함수 이름을 A·F로 바꾼 글."""
    return code.replace(decoded.array_name, "A").replace(decoded.lookup_name, "F")


# --- 글자 코드 도구 (obfuscate.py) ------------------------------------------------------------


def test_F_B02_hard_글자코드_꼴() -> None:
    """글자마다 `\\xHH`(0xff까지)·`\\uHHHH`, BMP 밖은 UTF-16 두 칸, 16진 소문자."""
    assert obfuscate.char_codes("zelto_") == "\\x7a\\x65\\x6c\\x74\\x6f\\x5f"
    assert obfuscate.char_codes("요A") == "\\uc694\\x41"
    assert obfuscate.char_codes(chr(0x1F331)) == "\\ud83c\\udf31"
    assert obfuscate.to_charcode("zelto_b0C4", ["3"]) == "\\x7a\\x65\\x6c"
    assert obfuscate.to_charcode("ab", []) == "\\x61\\x62"
    for bad in (["0"], ["3"], ["x"], ["1", "2"]):
        with pytest.raises(ValueError, match="charcode") as err:
            obfuscate.to_charcode("ab", bad)
        assert "ab" not in str(err.value)


def test_F_B02_hard_글자코드() -> None:
    """결과물의 배열 글은 모두 글자 코드이고(`_decode`가 꼴을 본다), 숨긴 정답의 닻은
    배열 글의 글자 코드 조각이며, 풀면 풀어낸 값(또는 그 앞부분·조각)이 된다."""
    for bundle_id in HARD:
        decoded = _obfuscated(bundle_id)
        code = _texts(bundle_id)[_obfuscated_path(bundle_id)]
        for item in _items(bundle_id):
            if item["hiding"] not in {"obfuscated", "split"}:
                continue
            anchor = str(item["anchor"])
            # 풀어낸 값 전체: 심기 계획 값이면 그 값, 아니면(경로·주소) 정답지의 값
            value = _generated(bundle_id).get(str(item["id"]), str(item["decoded_anchor"]))
            assert item["decoded_anchor"] == _expected_decoded(bundle_id, item, value), item["id"]
            assert CHAR_CODES.fullmatch(anchor), item["id"]
            assert anchor in code, item["id"]
            plain = _unescape(anchor)
            assert plain in value, item["id"]
            if item["hiding"] == "obfuscated":
                assert value.startswith(plain) or plain == value, item["id"]
                assert any(value in entry for entry in decoded.stored), item["id"]


# --- 숨기는 방법 (F-B02 2·3) ------------------------------------------------------------------


def test_F_B02_hard_문자열배열_원값이_결과물에없음() -> None:
    """난독화한 파일에는 머리 밖에 글이 하나도 없고(모든 글이 배열로), 숨긴 정답의 풀어낸 값은
    번들 어디에도 글 그대로 없다. 원본의 글은 모두 배열에 있다."""
    for bundle_id in HARD:
        decoded = _obfuscated(bundle_id)
        assert not any(q in decoded.body for q in ("'", '"', "`")), bundle_id
        texts = _texts(bundle_id)
        for item in _items(bundle_id):
            if item["hiding"] in HIDDEN:
                value = str(item["decoded_anchor"])
                assert not any(value in t for t in texts.values()), item["id"]
        source = (SOURCES_DIR / bundle_id / "src" / OBFUSCATED[bundle_id]).read_text(
            encoding="utf-8"
        )
        literals = [m for m in STRING_LITERAL.findall(source) if "{{" not in m]  # 자리 없는 글
        assert literals
        for literal in literals:
            assert literal in decoded.stored, (bundle_id, len(literal))


def test_F_B02_hard_문자열배열_도구() -> None:
    """글·이름 접근·객체 열쇠(따옴표 있든 없든)가 찾기 함수 부름이 되고, 그 밖은 그대로다.

    `case` 뒤 글은 식이라 부름이 되고 `default:`·숫자·`?.`·펼침·정규식 글은 그대로 둔다.
    """
    out = obfuscate.obfuscate_js(SAMPLE, "t/sample.js")
    decoded = _decode(out.split(chr(0x0A), 1)[0])
    body = _named(out.split(chr(0x0A), 1)[1], decoded)
    values = decoded.logical

    def f(text: str) -> str:
        return f"F({values.index(text):#x})"

    assert body.splitlines() == [
        f"const cfg = {{[{f('apiBase')}]: {f('/api')}, [{f('dumpState')}]: true}};",
        f"const url = cfg[{f('apiBase')}] + {f('/me')};",
        f"switch (url) {{ case {f('/x')}: break; default: break; }}",
        f"fetch(url)[{f('then')}]((r) => r[{f('json')}]());",
        "const n = 1.5 + cfg?.size;",
        "const all = [...[1, 2]];",
        "const r = /a\\/b/g;",
        f"import({f('/assets/more.js')})[{f('then')}]((m) => m[{f('go')}]({f('한글 🌱')}));",
    ]
    assert len(set(values)) == len(values)  # 같은 글은 한 칸


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ('const a = `x`; const b = "y";', "템플릿"),
        ('import x from "./x.js";\nconst b = "y";', "정적 import"),
        ('export { a } from "./a.js";\nconst b = "y";', "정적 import"),
        ('const a = "\\q"; const b = "y";', "이스케이프"),
        ('const a = "x\\u00"; const b = "y";', "이스케이프"),
        ('const a = "x";', "적음"),
        ('const a = "x" + "y";' + chr(0x0D) + chr(0x0A), "CR"),
        ('const a = "x' + chr(0x0A) + '"; const b = "y";', "줄바꿈"),
        ('const a = "x"; const b = "y"; /* 끝', "주석"),
    ],
)
def test_F_B02_hard_난독화_받지않는원본_멈춤(source: str, rule: str) -> None:
    """받지 않는 원본은 멈추고 원본 줄·규칙만 알린다(글 값은 싣지 않는다)."""
    with pytest.raises(obfuscate.ObfuscateError, match=rule) as err:
        obfuscate.obfuscate_js(source, "t/x.js")
    assert '"x"' not in str(err.value) and "./x.js" not in str(err.value)


def test_F_B02_hard_난독화_options_받지않음() -> None:
    ctx = StepContext("t", "assets/a.js", {"turns": 3})
    with pytest.raises(obfuscate.ObfuscateError, match="options"):
        obfuscate.obfuscate_step('const a = "x"; const b = "y";', ctx)


def test_F_B02_hard_돌리기() -> None:
    """배열은 돌려 적혀 있다: 적힌 차례로 읽으면 찾기 번호와 글이 어긋나고, `push(shift())`를
    `turns`번 한 뒤라야 맞다. 되돌린 배열은 코드에 처음 나온 차례다."""
    for bundle_id in HARD:
        decoded = _obfuscated(bundle_id)
        n = len(decoded.stored)
        assert 0 < decoded.turns < n, bundle_id
        assert decoded.logical != decoded.stored, bundle_id
        first_seen = list(dict.fromkeys(decoded.lookups()))
        assert first_seen == list(range(n)), bundle_id  # 처음 나온 차례 = 되돌린 배열 차례
        value = _generated(bundle_id)[CONST_SLOTS[bundle_id]]
        slots = re.finditer(
            rf"const [A-Za-z]{{1,2}}={re.escape(decoded.lookup_name)}\((0x[0-9a-f]+)\);",
            decoded.body,
        )
        indexes = [int(m.group(1), 16) for m in slots]
        matched = [i for i in indexes if decoded.logical[i] == value]
        assert len(matched) == 1, bundle_id
        assert decoded.stored[matched[0]] != value, bundle_id  # 돌리지 않고 읽으면 다른 글


def test_F_B02_hard_sourcemap_only_값은_map에만() -> None:
    """`sourcemap_only` 정답과 그 방법을 거치는 미끼: 닻은 소스맵 `sourcesContent` 안에만 있고,
    맵이 가리키는 JS를 포함해 맵 밖 어떤 파일에도 없다. 위치는 맵 파일뿐이다."""
    for bundle_id in HARD:
        texts = _texts(bundle_id)
        entries = _items(bundle_id, "sourcemap_only") + [
            d for d in _decoys(bundle_id) if DECOY_HIDING[str(d["id"])] == "sourcemap_only"
        ]
        assert len(entries) >= 2, bundle_id  # 정답 하나 이상 + 미끼 하나
        for entry in entries:
            anchor = str(entry["anchor"])
            files = _location_files(entry)
            assert files and all(f.endswith(".js.map") for f in files), entry["id"]
            for rel in files:
                content = json.loads(texts[rel])["sourcesContent"][0]
                assert anchor in content, entry["id"]
                assert anchor not in texts[rel.removesuffix(".map")], entry["id"]
            others = [t for rel, t in texts.items() if rel not in files]
            assert not any(anchor in t for t in others), entry["id"]


def test_F_B02_hard_split() -> None:
    """`split` 정답(과 나눔을 거치는 미끼): 이어 붙인 값은 번들에 글로도 글자 코드로도 없고,
    조각은 배열에 따로 있으며 이웃 조각을 이은 글을 든 배열 칸은 없다.
    닻은 조각 하나의 글자 코드."""
    for bundle_id in HARD:
        decoded = _obfuscated(bundle_id)
        texts = list(_texts(bundle_id).values())
        generated = _generated(bundle_id)
        entries = _items(bundle_id, "split") + [
            d for d in _decoys(bundle_id) if DECOY_HIDING[str(d["id"])] == "split"
        ]
        assert len(entries) >= 2, bundle_id
        for entry in entries:
            entry_id = str(entry["id"])
            if entry_id in HAND_SPLIT:
                pieces = list(HAND_SPLIT[entry_id])
            else:
                pieces = _pieces_in_array(generated[entry_id], decoded.stored)
            whole = "".join(pieces)
            if "decoded_anchor" in entry:
                assert entry["decoded_anchor"] == _expected_decoded(bundle_id, entry, whole), (
                    entry_id
                )
            assert all(p in decoded.stored for p in pieces), entry_id
            assert not any(whole in t or obfuscate.char_codes(whole) in t for t in texts)
            for left, right in itertools.pairwise(pieces):
                assert not any(left + right in e for e in decoded.stored), entry_id
            plain = _unescape(str(entry["anchor"]))
            assert any(p.startswith(plain) or plain in p for p in pieces), entry_id


def _pieces_in_array(value: str, stored: tuple[str, ...]) -> list[str]:
    """`fake.split_value` 조각이 모두 배열 칸으로 있는 조각 수의 조각들."""
    for parts in range(2, fake.SPLIT_MAX_PARTS + 1):
        pieces = fake.split_value(value, parts)
        if all(p in stored for p in pieces):
            return pieces
    raise AssertionError("조각이 배열에 없음")


def test_F_B02_hard_obfuscated·sourcemap_only·split_모두있음() -> None:
    """F-B02 3: hard 줄의 방법이 번들마다 모두 한 번 이상, 그 밖은 none만."""
    for bundle_id in HARD:
        hidings = {str(item["hiding"]) for item in _items(bundle_id)}
        assert hidings - {"none"} == HIDING_BY_DIFFICULTY["hard"], bundle_id


def test_F_B02_hard_숨긴방법마다_미끼() -> None:
    """번들에 쓴 숨기는 방법(obfuscated·split·sourcemap_only)마다 그 방법을 거치는 미끼가 있다.

    '난독화 배열에 있으면 문제' 같은 겉모양 규칙으로 정밀도를 지킬 수 없게 — 풀어 본 뒤 내용으로
    가르는지를 잰다. 난독화 미끼의 닻은 정답처럼 배열 글의 글자 코드다.
    """
    for bundle_id in HARD:
        decoys = _decoys(bundle_id)
        used = {str(i["hiding"]) for i in _items(bundle_id)} - {"none"}
        assert {DECOY_HIDING[str(d["id"])] for d in decoys} == used, bundle_id
        code = _texts(bundle_id)[_obfuscated_path(bundle_id)]
        for decoy in decoys:
            if DECOY_HIDING[str(decoy["id"])] in {"obfuscated", "split"}:
                anchor = str(decoy["anchor"])
                assert CHAR_CODES.fullmatch(anchor) and anchor in code, decoy["id"]


# --- 결과물 꼴 (F-B01, 설계 2.7) ----------------------------------------------------------------


def test_F_B01_hard_한줄_해시이름() -> None:
    """압축(한 줄): JS는 코드 한 줄(+ 맵이 있으면 `sourceMappingURL` 한 줄), HTML·CSS·맵은 한 줄,
    JS·CSS 이름에 해시. 남기는 주석은 `/*!` 배너뿐이다."""
    for bundle_id in HARD:
        bundle = BUNDLES_DIR / bundle_id
        for path in sorted(bundle.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if path.suffix in {".js", ".css"}:
                assert HASHED.fullmatch(path.name), path.name
            if path.suffix in {".html", ".css", ".map"}:
                assert count_lines(data) == 1, path.name
            if path.suffix == ".js":
                lines = data.decode("utf-8").split(chr(0x0A))
                has_map = path.with_name(path.name + ".map").is_file()
                assert count_lines(data) == (2 if has_map else 1), path.name
                if has_map:
                    assert MAP_LINE.fullmatch(lines[1]), path.name
                code = lines[0].replace("/*!", "")
                assert "/*" not in code and "//" not in code.replace("://", ""), path.name


def test_F_B01_hard_난독화파일_계획과같음() -> None:
    """plan.json의 난독화 대상이 이 시험이 보는 파일과 같고, 그 파일에는 소스맵이 없다
    (맵의 sourcesContent는 난독화 전 원본이라 붙이면 난독화가 무너진다)."""
    for bundle_id in HARD:
        plan = _plan(bundle_id)
        assert plan["plugins"] == ["obfuscate"]
        assert plan["steps"] == [{"step": "obfuscate", "files": [OBFUSCATED[bundle_id]]}]
        sourcemaps = plan["sourcemaps"]
        assert isinstance(sourcemaps, list) and sourcemaps
        assert OBFUSCATED[bundle_id] not in sourcemaps


def test_F_B01_난독화_같은시드_같은바이트(tmp_path: Path) -> None:
    """같은 원본·같은 시드면 같은 글, 시드가 다르면 다른 돌리기·이름. 번들을 두 번 빌드해도 같다."""
    first = obfuscate.obfuscate_js(SAMPLE, "hard-1/assets/index.js")
    assert first == obfuscate.obfuscate_js(SAMPLE, "hard-1/assets/index.js")
    assert first != obfuscate.obfuscate_js(SAMPLE, "hard-2/assets/index.js")
    for bundle_id in HARD:
        sources = tmp_path / bundle_id / "sources"
        sources.mkdir(parents=True)
        shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
        one = build(bundle_id, sources, tmp_path / bundle_id / "b1").bundle_manifest_sha256
        two = build(bundle_id, sources, tmp_path / bundle_id / "b2").bundle_manifest_sha256
        assert one == two == _answers(bundle_id)["bundle_manifest_sha256"]


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node가 없어 문법 검사를 건너뜀(PATH에 node)")
    return node


def _node_check(node: str, path: Path) -> subprocess.CompletedProcess[bytes]:
    # 글을 읽고 문법만 본다(--check는 실행하지 않는다). 셸 없이, 인자는 고정 + 임시 파일 경로뿐
    return subprocess.run(  # noqa: S603
        [node, "--check", str(path)], capture_output=True, timeout=60, check=False
    )


def test_F_B01_난독화결과_문법검사_통과(tmp_path: Path) -> None:
    """어려움 번들의 모든 JS와 시험 원본의 난독화 결과가 JS 문법(모듈)으로 읽힌다.

    `node --check`(실행하지 않고 읽기만).
    """
    node = _node()
    files = {"sample.mjs": obfuscate.obfuscate_js(SAMPLE, "t/sample.js").encode("utf-8")}
    for bundle_id in HARD:
        for rel, text in _texts(bundle_id).items():
            if rel.endswith(".js"):
                files[f"{bundle_id}-{Path(rel).stem}.mjs"] = text.encode("utf-8")
    assert len(files) == 1 + 2 + 3  # 시험 원본 + hard-1 JS 둘 + hard-2 JS 셋
    for name, data in files.items():
        path = tmp_path / name
        path.write_bytes(data)
        result = _node_check(node, path)
        assert result.returncode == 0, name


def test_F_B01_난독화_틀린결과는_문법검사가_잡음(tmp_path: Path) -> None:
    """문법 검사 시험이 헛돌지 않는지: 괄호 하나를 지운 결과는 실패한다."""
    node = _node()
    path = tmp_path / "broken.mjs"
    path.write_bytes(obfuscate.obfuscate_js(SAMPLE, "t/sample.js").replace(")", "", 1).encode())
    assert _node_check(node, path).returncode != 0


# --- 정답지 (F-B03) ---------------------------------------------------------------------------


def test_F_B03_hard_닻_번들에서_한곳만() -> None:
    """압축 파일은 한 줄이라 F-B07 6으로는 정답끼리 가르지 못한다(설계 2.5). 그래서 더 본다:
    ㉮ 닻이 나오는 파일은 모두 그 정답(미끼)의 위치 파일 ㉯ 숨긴 정답·미끼의 닻은 나오는 파일마다
    꼭 한 번 ㉰ 닻이 다른 정답·미끼의 닻 안에 들지 않는다."""
    for bundle_id in HARD:
        answers = _answers(bundle_id)
        entries = _entries(answers, "items") + _entries(answers, "decoys")
        texts = _texts(bundle_id)
        anchors = {str(e["id"]): str(e["anchor"]) for e in entries if e["anchor"] is not None}
        assert len(anchors) == len(entries)
        for entry in entries:
            entry_id, anchor = str(entry["id"]), anchors[str(entry["id"])]
            counts = {rel: _occurrences(t, anchor) for rel, t in texts.items()}
            found_in = {rel for rel, n in counts.items() if n}
            assert found_in and found_in <= _location_files(entry), entry_id
            if entry.get("hiding", DECOY_HIDING.get(entry_id)) in HIDDEN:
                assert all(counts[rel] == 1 for rel in found_in), entry_id
            for other_id, other in anchors.items():
                assert other_id == entry_id or anchor not in other, (entry_id, other_id)


def test_F_B03_hard_소스맵_닻은_맵이름() -> None:
    """줄로 못 가르는 위치라 닻으로만 맞는다. 맵 파일 이름을 닻으로(번들에 한 번, T23 반려 1 1)."""
    for bundle_id in HARD:
        (item,) = [i for i in _items(bundle_id) if i["categories"] == ["source_map"]]
        anchor = str(item["anchor"])
        texts = _texts(bundle_id)
        assert anchor.endswith(".js.map") and f"assets/{anchor}" in texts
        assert sum(_occurrences(t, anchor) for t in texts.values()) == 1


def test_F_B03_hard_숨긴정답만_풀어낸값() -> None:
    """F-B03 6: 숨긴 정답(split·obfuscated)에는 풀어낸 값, 그 밖(sourcemap_only·none)은 null."""
    for bundle_id in HARD:
        for item in _items(bundle_id):
            assert (item["decoded_anchor"] is not None) == (item["hiding"] in HIDDEN), item["id"]


def test_F_B03_hard_planted에_가짜생성() -> None:
    """F-B02 7: 규칙 4로 만든 값이 닻이나 풀어낸 값인 정답만 planted에 '가짜(생성)'.

    심기 계획의 값은 모두 정답이나 미끼에 쓰인다(미끼에는 planted 칸이 없다)."""
    for bundle_id in HARD:
        generated = _generated(bundle_id)
        item_ids = {str(i["id"]) for i in _items(bundle_id)}
        decoy_ids = {str(d["id"]) for d in _decoys(bundle_id)}
        assert set(generated) <= item_ids | decoy_ids, bundle_id
        for item in _items(bundle_id):
            entry_id = str(item["id"])
            assert ("가짜(생성)" in str(item["planted"])) == (entry_id in generated), entry_id
            if entry_id in generated:
                # 그 값이 닻이나 풀어낸 값과 같다 — 64자를 넘고 줄로 가를 수 없는 위치가 있을 때만
                # F-B03 5의 앞 조각(`expected_short`)과 같다
                value = generated[entry_id]
                answers = _answers(bundle_id)
                texts = bundle_texts(BUNDLES_DIR / bundle_id)
                matched = [
                    key
                    for key in ("anchor", "decoded_anchor")
                    if item[key] is not None
                    and item[key]
                    == short_or_none(value, item, answers, texts, decoded=key == "decoded_anchor")
                ]
                assert matched, entry_id


def test_F_B03_hard_두번들합쳐_키·토큰·비밀번호() -> None:
    """F-B02 4의 세 꼴을 어려움 두 번들에 모두 심는다. 만든 값은 규칙 5를 지킨다."""
    values = [v for bundle_id in HARD for v in _generated(bundle_id).values()]
    assert {fake.rule4_form(v) for v in values} == {"key", "token", "password"}
    for value in values:
        assert fake.fake_value_problems(value) == []
    token = next(v for v in values if fake.rule4_form(v) == "token")
    assert token[-1] in fake.SIGNATURE_LAST_CHARS  # 4ⓑ 서명 끝 글자는 표준 꼴


def test_F_B03_hard_접두어_앞번들과_안겹침() -> None:
    """키 접두어는 허용 목록에서만, 번들 안에서 겹치지 않고 앞서 쓴 번들의 접두어와도 다르다
    (같은 접두어 하나가 실험 전체의 검색 표식이 되지 않게, F-B02 근거 4②)."""
    earlier = {"zelto_", "quvar_", "mirtak_", "fenzo_", "lumac_", "cablo_", "trimba_", "korvel_"}
    seen: set[str] = set()
    for bundle_id in HARD:
        for value in _generated(bundle_id).values():
            prefix = fake.key_prefix(value)
            if prefix is None:
                continue
            assert prefix in fake.FAKE_PREFIXES and prefix not in earlier | seen, prefix
            seen.add(prefix)
    assert len(seen) == 3


@pytest.mark.parametrize("bundle_id", HARD)
def test_F_B03_hard_정답지_명령으로_다시만들면_같음(bundle_id: str, tmp_path: Path) -> None:
    """정답지는 원본 + 명령 하나(`answers <id>`)로 같은 바이트가 다시 나온다(T22 반려 1 3)."""
    sources = tmp_path / "sources"
    sources.mkdir()
    shutil.copytree(SOURCES_DIR / bundle_id, sources / bundle_id)
    path, _ = write_answers(bundle_id, sources, tmp_path / "bundles", tmp_path / "answers")
    assert path.read_bytes() == (REPO_ROOT / "bench" / "answers" / f"{bundle_id}.json").read_bytes()


@pytest.mark.parametrize("bundle_id", HARD)
def test_F_B04_hard_지문같음(bundle_id: str) -> None:
    """정답지·빌드 기록의 지문 = 저장소 번들의 지문(F-B01 3)."""
    expected = _answers(bundle_id)["bundle_manifest_sha256"]
    assert bundle_manifest_sha256(BUNDLES_DIR / bundle_id) == expected
    record = json.loads((SOURCES_DIR / bundle_id / "build.json").read_text(encoding="utf-8"))
    assert record["bundle_manifest_sha256"] == expected


# --- 공정성 (겉모양으로 정답·미끼를 가르지 않게) ---------------------------------------------


def test_F_B02_hard_가짜주소() -> None:
    """F-B02 6: 번들 글·배열 글·풀어낸 값의 IP는 RFC 1918 안, 호스트는 그 IP나 정해 둔 공개 CDN,
    예약 이름은 쓰지 않는다. 내부 주소 정답은 번들마다 있다."""
    for bundle_id in HARD:
        texts = list(_texts(bundle_id).values()) + list(_obfuscated(bundle_id).stored)
        texts += [str(i["decoded_anchor"]) for i in _items(bundle_id) if i["decoded_anchor"]]
        ips: set[str] = set()
        for text in texts:
            assert not any(s in text for s in RESERVED_SUFFIXES), bundle_id
            for ip in IPV4.findall(text):
                ips.add(ip)
                assert any(ipaddress.ip_address(ip) in net for net in PRIVATE_NETWORKS), ip
            for host in URL_HOST.findall(text):
                assert IPV4.fullmatch(host) or host in PUBLIC_HOSTS, host
        assert ips, bundle_id


def test_F_B02_hard_미끼낱말_번들에없음() -> None:
    """F-B02 5㉰의 낱말이 번들 글에도, 풀어낸 배열 글에도 없다 — 미끼에만 있으면 단서가 된다."""
    for bundle_id in HARD:
        for rel, text in _texts(bundle_id).items():
            assert not fake.has_decoy_word(text), rel
        for entry in _obfuscated(bundle_id).stored:
            assert not fake.has_decoy_word(entry), bundle_id


def test_F_B02_hard_바깥주소는_누른뒤에만() -> None:
    """공개 CDN 주소를 쓰는 코드는 버튼 click 처리 안에만 있다(T23 반려 1 8 — 번들을 띄워도
    열자마자 바깥에 요청하지 않게). 배열 글로 찾기 번호를 얻고 그 번호가 나오는 자리를 본다."""
    for bundle_id in HARD:
        decoded = _obfuscated(bundle_id)
        hosts = [i for i, v in enumerate(decoded.logical) if v.startswith("https://")]
        assert len(hosts) == 1, bundle_id  # 바깥 주소 글은 설정 값 하나
        assert _occurrences(decoded.body, f"{decoded.lookup_name}({hosts[0]:#x})") == 1
        key = f"[{decoded.lookup_name}({decoded.logical.index(HOST_KEYS[bundle_id]):#x})]"
        assert _occurrences(decoded.body, key) == 2, bundle_id  # 설정 열쇠 + 읽는 곳 하나
        use = decoded.body.rfind(key)
        click = f"{decoded.lookup_name}({decoded.logical.index('click'):#x})"
        handler = decoded.body.rfind(click, 0, use)
        assert handler >= 0 and "}" not in decoded.body[handler:use], bundle_id


# --- 구성 검사 (F-B07) ------------------------------------------------------------------------


def test_F_B07_hard1_구성통과() -> None:
    report = check_target(repo_target("hard-1"))
    assert report.problems == ()


def test_F_B07_hard2_구성통과() -> None:
    report = check_target(repo_target("hard-2"))
    assert report.problems == ()


def test_F_B07_어려움_범주8개() -> None:
    """F-B07 4: 난이도마다(번들 둘을 합쳐) 8개 모두. 번들 하나에 모두 넣지 않는다(설계 2.7)."""
    reports = [check_target(repo_target(bundle_id)) for bundle_id in HARD]
    for report in reports:
        assert 6 <= len(report.categories) < ALL_CATEGORIES, report.bundle_id
    assert len(reports[0].categories | reports[1].categories) == ALL_CATEGORIES


def test_F_B07_hard_줄허용범위_기록() -> None:
    """F-B07 13 확인 기록: 압축 JS·맵의 위치는 모두 줄 허용 범위가 파일을 덮는다(T = 2)."""
    for bundle_id in HARD:
        report = check_target(repo_target(bundle_id))
        assert report.cover_rows
        assert all(row.covers for row in report.cover_rows), bundle_id
