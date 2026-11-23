"""F-R04 MCP 거르개 (R4, 조건 B) 시험. 진짜 REA 대신 fake_rea/server.py를 띄운다(실험구조 3.9).

경로 꼴은 `bench/run/escape_cases.json`(실험구조 3.10 공통 표) 전부를 돌린다.
표에서 거르개 기대가 있는 꼴을 하나라도 돌리지 않으면 `test_F_R04_공통표_모든꼴을_돌림`이 실패한다.
"""

from __future__ import annotations

import _winapi
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from run import rea_mcp_filter as rmf
from tests.conftest import MakeBundle

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parent
FILTER = BENCH / "run" / "rea_mcp_filter.py"
FAKE_REA = Path(__file__).resolve().parent / "fake_rea" / "server.py"
CASES: dict[str, Any] = json.loads((BENCH / "run" / "escape_cases.json").read_text("utf-8"))
MARKER = CASES["marker_text"]
ALLOWED = (
    "analyze_javascript_application",
    "audit_release_exposure",
    "trace_javascript_semantics",
    "trace_application_feature",
)
TABLE_IDS = set(range(1, 15))  # 실험구조 3.10의 #1~#14
GATE_ONLY_IDS = {8, 9}  # 3.10 표에서 거르개 기대가 '해당 없음'인 줄
REFERENCE = {"kind": "retained-evidence", "evidence_id": "ev_" + "0" * 64}
SPEC_REPO_FILE = r"C:\project\SelfAudit\CLAUDE.md"  # F-R04 예시의 글 그대로
RESPONSE_WAIT_S = 20.0
NUL = chr(0)

# 경로 칸 셋: 두 경로 칸(②)과 경로 칸이 아닌 글 칸(그물 ⑤)
PATH_FIELDS = (
    ("analyze_javascript_application", "input_path"),
    ("audit_release_exposure", "path"),
)
NET_FIELD = ("trace_javascript_semantics", "query")


# ---------------------------------------------------------------- 시험 자리


@dataclass(frozen=True)
class Layout:
    run_dir: Path
    target: str
    values: dict[str, str]

    def fill(self, text: str) -> str:
        for name, value in self.values.items():
            text = text.replace(name, value)
        assert "<" not in text, "바꾸지 못한 자리 표시가 남음"
        return text


def short_path(path: str) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel32.GetShortPathNameW(path, buffer, len(buffer))
    if length == 0:
        raise OSError(ctypes.get_last_error(), "GetShortPathNameW 실패")
    return str(buffer.value)


def relative_posix(path: str, start: str) -> str:
    return os.path.relpath(path, start).replace("\\", "/")


@pytest.fixture
def layout(make_bundle: MakeBundle, tmp_path: Path) -> Layout:
    """escape_cases.json의 layout대로 만든다.

    배치/실행/target, 형제 실행, 앞부분만 같은 형제, 밖 미끼 폴더의 표식, 전용 미끼 폴더를 가리키는
    정션. 밖의 자리는 모두 tmp_path 안에 새로 만든 미끼다(decoy_rule).
    """
    marker = MARKER.encode()
    files = {rel: text.encode() for rel, text in CASES["layout"]["inside_files"].items()}
    bundle = make_bundle({**files, "index.html": b"<html></html>\n"})
    batch = tmp_path / "batch-20261123-0130-first36"
    run_dir = batch / "easy-1-b-1-3f2a9c10"
    run_dir.mkdir(parents=True)
    target_dir = run_dir / "target"
    bundle.rename(target_dir)
    for name in ("target2", "target-old"):
        (run_dir / name).mkdir()
        (run_dir / name / "marker.txt").write_bytes(marker)
    sib = "easy-2-a-1-0a1b2c3d"
    (batch / sib).mkdir()
    (batch / sib / "x").write_bytes(marker)
    outside_dir = tmp_path / "outside-marker-decoy"  # 8자를 넘어 8.3 이름이 따로 생긴다
    outside_dir.mkdir()
    (outside_dir / "marker.txt").write_bytes(marker)
    decoy = tmp_path / "junction-decoy"
    decoy.mkdir()
    (decoy / "marker.txt").write_bytes(marker)
    _winapi.CreateJunction(str(decoy), str(target_dir / "jlink"))

    target = os.path.realpath(target_dir)
    outside = os.path.realpath(outside_dir / "marker.txt")
    assert outside[1:3] == ":\\"
    values = {
        "<T_LOWER>": target.lower(),
        "<T_UPPER>": target.upper(),
        "<T_SHORT>": short_path(target),
        "<T>": target,
        "<P_DIR>": os.path.dirname(outside),
        "<DECOY_DIR>": os.path.realpath(decoy),
        "<P_FROM_HOME_POSIX>": relative_posix(outside, os.environ["USERPROFILE"]),
        "<P_FROM_LOCALAPPDATA>": os.path.relpath(outside, os.environ["LOCALAPPDATA"]),
        "<P_FROM_LOCALAPPDATA_POSIX>": relative_posix(outside, os.environ["LOCALAPPDATA"]),
        "<P_POSIX>": outside.replace("\\", "/"),
        "<P_SHORT>": short_path(outside),
        "<P_SWAPCASE>": outside.swapcase(),
        "<P_REL>": os.path.relpath(outside, target).replace("\\", "/"),
        "<P_TAIL>": outside[3:],
        "<DRIVE>": outside[0],
        "<SIB>": sib,
        "<P>": outside,
        "<ROOT>": str(ROOT),
    }
    # 8.3 이름이 긴 이름과 같으면 #2를 시험하지 못한 것이다(건너뛰지 않고 실패)
    assert values["<P_SHORT>"] != outside, "8.3 짧은 이름을 만들 수 없음(#2 미시험)"
    assert values["<T_SHORT>"] != target, "8.3 짧은 이름을 만들 수 없음(안쪽 8.3 미시험)"
    return Layout(run_dir=run_dir, target=target, values=values)


def make_router(layout: Layout) -> rmf.Router:
    return rmf.Router(rmf.Policy(allow=frozenset(ALLOWED), target=layout.target), rea_running=True)


def body(item: rmf.Outgoing) -> dict[str, Any]:
    return cast(dict[str, Any], item.message)


def line(message: dict[str, Any]) -> bytes:
    return json.dumps(message).encode()


def call_line(name: str, arguments: Any, msg_id: int = 1) -> bytes:
    params = {"name": name, "arguments": arguments}
    return line({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": params})


def call(router: rmf.Router, name: str, arguments: Any, msg_id: int = 1) -> list[rmf.Outgoing]:
    return router.from_client(call_line(name, arguments, msg_id))


def assert_error_to_client(out: list[rmf.Outgoing], msg_id: Any, code: int) -> dict[str, Any]:
    """REA에 보낸 것이 없고, Claude Code에 JSON-RPC 오류 하나가 남는다."""
    assert [o.to for o in out] == ["client"]
    message = body(out[0])
    assert message["id"] == msg_id
    assert message["error"]["code"] == code
    return message


def assert_rejected(out: list[rmf.Outgoing], layout: Layout, msg_id: int = 1) -> None:
    message = assert_error_to_client(out, msg_id, rmf.INVALID_PARAMS)
    text = json.dumps(message, ensure_ascii=False)
    # 오류 글에는 값이 없다(위치와 규칙만, 보안코딩 '실험')
    assert layout.values["<P>"] not in text
    assert layout.target not in text
    assert MARKER not in text


def sent_arguments(out: list[rmf.Outgoing]) -> dict[str, Any]:
    assert [o.to for o in out] == ["rea"]
    message = body(out[0])
    assert message["method"] == "tools/call"
    arguments: dict[str, Any] = message["params"]["arguments"]
    return arguments


def path_arguments(tool: str, field: str, value: str) -> dict[str, Any]:
    if tool == NET_FIELD[0]:
        return {"application": REFERENCE, field: value}
    return {field: value}


# ---------------------------------------------------------------- 공통 표 (3.10)


def table_examples() -> Iterator[Any]:
    for case in CASES["cases"]:
        for index, example in enumerate(case["examples"]):
            if example["filter"] is None:
                continue
            yield pytest.param(case["id"], example, id=f"{case['id']}-{index}")


def test_F_R04_공통표_모든꼴을_돌림() -> None:
    """표의 #1~#14가 모두 있고, 거르개 기대가 있는 꼴은 모두 아래 시험이 돌린다."""
    ids = {case["id"] for case in CASES["cases"]}
    assert ids == TABLE_IDS
    with_filter = {
        case["id"] for case in CASES["cases"] if any(e["filter"] for e in case["examples"])
    }
    assert with_filter == TABLE_IDS - GATE_ONLY_IDS
    tried = {param.values[0] for param in table_examples()}
    assert tried == with_filter
    for case in CASES["cases"]:
        for example in case["examples"]:
            assert example["filter"] in {"allow", "reject", None}
            assert (example["filter"] == "allow") == ("resolved" in example)


def test_F_R04_공통표_밖자리는_미끼뿐() -> None:
    """진짜 개인 폴더를 가리키는 예·layout이 없다. 정션은 <P_DIR>과 다른 전용 미끼를 가리킨다."""
    used = json.dumps([CASES["layout"], CASES["cases"]], ensure_ascii=False)
    for real in ("SelfAudit-private", ".ssh", ".claude", "SelfAudit-bench-claude"):
        assert real not in used
    assert CASES["layout"]["junction"]["points_to"] == "<DECOY_DIR>"
    assert "<DECOY_DIR>" in CASES["placeholders"]


@pytest.mark.parametrize(("case_id", "example"), list(table_examples()))
@pytest.mark.parametrize(("tool", "field"), [*PATH_FIELDS, NET_FIELD])
def test_F_R04_공통표_꼴(
    layout: Layout, case_id: int, example: dict[str, Any], tool: str, field: str
) -> None:
    value = layout.fill(example["value"])
    out = call(make_router(layout), tool, path_arguments(tool, field, value))
    if example["filter"] == "reject":
        assert_rejected(out, layout)
        return
    arguments = sent_arguments(out)
    if field == NET_FIELD[1]:
        assert arguments[field] == value  # 경로 칸이 아니면 글을 바꾸지 않는다
    else:
        assert arguments[field] == layout.fill(example["resolved"])  # REA에는 푼 경로


# ---------------------------------------------------------------- 경로 칸 (②)

ALLOW_SIX = [
    pytest.param("assets/app.js", "<T>\\assets\\app.js", id="안-상대"),
    pytest.param("<T>\\assets\\app.js", "<T>\\assets\\app.js", id="안-절대"),
    pytest.param("\\\\?\\<T>\\assets\\app.js", "<T>\\assets\\app.js", id="안-긴접두"),
    pytest.param("<T_SHORT>\\assets\\app.js", "<T>\\assets\\app.js", id="안-8.3"),
    pytest.param("<T>", "<T>", id="target자신"),
    pytest.param("assets/../assets/app.js", "<T>\\assets\\app.js", id="안-점점-안"),
]

REJECT_FOURTEEN = [
    pytest.param("../../<SIB>/x", id="점점으로밖"),
    pytest.param("<P>", id="밖절대"),
    pytest.param("<ROOT>\\CLAUDE.md", id="저장소절대"),
    pytest.param("<T>\\jlink\\marker.txt", id="안쪽정션이밖"),
    pytest.param("\\\\?\\<P>", id="긴접두밖"),
    pytest.param("\\\\?\\UNC\\localhost\\<DRIVE>$\\<P_TAIL>", id="긴접두UNC"),
    pytest.param("\\\\localhost\\<DRIVE>$\\<P_TAIL>", id="UNC"),
    pytest.param("\\\\.\\<P>", id="장치경로밖"),
    pytest.param("<P_SHORT>", id="8.3밖"),
    pytest.param("<T>\\assets\\app.js:hidden", id="ADS"),
    pytest.param("<P_POSIX>", id="슬래시꼴밖"),
    pytest.param("<T>\\assets\\nope.js", id="없는파일"),
    pytest.param("<DRIVE>:assets\\app.js", id="드라이브상대"),
    pytest.param("<T>2\\marker.txt", id="형제target2"),
]

# 3.10 표·시험 전략에 없지만 ② 허용 꼴 밖이라 거절해야 하는 꼴
REJECT_MORE = [
    pytest.param("assets/app.js" + NUL, id="NUL"),
    pytest.param("\\<P_TAIL>", id="루트기준-역슬래시"),
    pytest.param("/<P_TAIL>", id="루트기준-슬래시"),
    pytest.param("//?/<P>", id="슬래시긴접두"),
    pytest.param("\\\\?\\GLOBALROOT\\??\\<P>", id="GLOBALROOT"),
    pytest.param("\\\\.\\<T>\\assets\\app.js", id="장치경로안"),
    pytest.param("<T>-old\\marker.txt", id="형제target-old"),
    pytest.param("<T>\\assets\\app.js::$DATA", id="ADS-DATA"),
    pytest.param("", id="빈글"),
]


@pytest.mark.parametrize(("value", "resolved"), ALLOW_SIX)
@pytest.mark.parametrize(("tool", "field"), PATH_FIELDS)
def test_F_R04_경로칸_허용_6가지(
    layout: Layout, value: str, resolved: str, tool: str, field: str
) -> None:
    out = call(make_router(layout), tool, {field: layout.fill(value)})
    assert sent_arguments(out) == {field: layout.fill(resolved)}


@pytest.mark.parametrize("value", REJECT_FOURTEEN + REJECT_MORE)
@pytest.mark.parametrize(("tool", "field"), PATH_FIELDS)
def test_F_R04_경로칸_거절(layout: Layout, value: str, tool: str, field: str) -> None:
    out = call(make_router(layout), tool, {field: layout.fill(value)})
    assert_rejected(out, layout)


def test_F_R04_예시_assets_푼경로로보냄(layout: Layout) -> None:
    out = call(make_router(layout), "analyze_javascript_application", {"input_path": "assets"})
    assert sent_arguments(out) == {"input_path": layout.target + "\\assets"}


def test_F_R04_예시_긴접두_앞4자를떼고풂(layout: Layout) -> None:
    value = "\\\\?\\" + layout.target + "\\assets\\app.js"
    out = call(make_router(layout), "analyze_javascript_application", {"input_path": value})
    assert sent_arguments(out) == {"input_path": layout.target + "\\assets\\app.js"}


def test_F_R04_audit_path_target와_파일(layout: Layout) -> None:
    router = make_router(layout)
    out = call(router, "audit_release_exposure", {"path": layout.target, "max_file_bytes": 1000})
    assert sent_arguments(out) == {"path": layout.target, "max_file_bytes": 1000}
    file_value = layout.target + "\\assets\\app.js"
    out = call(router, "audit_release_exposure", {"path": file_value}, msg_id=2)
    assert sent_arguments(out) == {"path": file_value}


def test_F_R04_경로칸_없음_거절(layout: Layout) -> None:
    out = call(make_router(layout), "analyze_javascript_application", {"detail": "summary"})
    assert_rejected(out, layout)


def test_F_R04_경로칸_글아님_거절(layout: Layout) -> None:
    out = call(make_router(layout), "audit_release_exposure", {"path": ["assets"]})
    assert_rejected(out, layout)


# ---------------------------------------------------------------- source_paths (③)


def test_F_R04_source_paths_점점_거절(layout: Layout) -> None:
    arguments = {"input_path": "assets", "source_paths": ["../x"]}
    assert_rejected(call(make_router(layout), "analyze_javascript_application", arguments), layout)


@pytest.mark.parametrize(
    "item",
    [
        pytest.param("../index.html", id="input밖-target안"),
        pytest.param("../jlink/marker.txt", id="정션"),
        pytest.param("<T>\\assets\\app.js", id="절대"),
        pytest.param("/app.js", id="루트기준"),
        pytest.param("app.js:hidden", id="ADS"),
        pytest.param("~/app.js", id="홈펼침"),
        pytest.param(".", id="input자신"),
        pytest.param("nope.js", id="없는파일"),
    ],
)
def test_F_R04_source_paths_input밖_거절(layout: Layout, item: str) -> None:
    arguments = {"input_path": "assets", "source_paths": ["app.js", layout.fill(item)]}
    assert_rejected(call(make_router(layout), "analyze_javascript_application", arguments), layout)


def test_F_R04_source_paths_정규화해보냄(layout: Layout) -> None:
    items = ["assets\\app.js", "./assets/../assets/app.js", "index.html"]
    arguments = {"input_path": layout.target, "source_paths": items}
    out = call(make_router(layout), "analyze_javascript_application", arguments)
    sent = sent_arguments(out)
    assert sent["source_paths"] == ["assets/app.js", "assets/app.js", "index.html"]
    assert sent["input_path"] == layout.target


@pytest.mark.parametrize("value", [[], "app.js", [1]], ids=["빈배열", "글", "숫자"])
def test_F_R04_source_paths_꼴아님_거절(layout: Layout, value: Any) -> None:
    arguments = {"input_path": "assets", "source_paths": value}
    assert_rejected(call(make_router(layout), "analyze_javascript_application", arguments), layout)


# ---------------------------------------------------------------- 인자 이름 (①)


def test_F_R04_인자목록밖_evidence_output_거절(layout: Layout) -> None:
    arguments = {"input_path": "assets", "evidence_output": "out.json"}
    assert_rejected(call(make_router(layout), "analyze_javascript_application", arguments), layout)


def test_F_R04_인자목록_안이면_그대로(layout: Layout) -> None:
    arguments = {
        "input_path": "assets",
        "format": "directory",
        "detail": "summary",
        "max_heap_mb": 512,
        "analysis_timeout_ms": 60000,
    }
    out = call(make_router(layout), "analyze_javascript_application", arguments)
    assert sent_arguments(out) == {**arguments, "input_path": layout.target + "\\assets"}


@pytest.mark.parametrize("arguments", ["assets", ["assets"], None], ids=["글", "배열", "null"])
def test_F_R04_인자_객체아님_거절(layout: Layout, arguments: Any) -> None:
    assert_rejected(call(make_router(layout), "audit_release_exposure", arguments), layout)


def test_F_R04_params_목록밖_키_거절(layout: Layout) -> None:
    params = {"name": "audit_release_exposure", "arguments": {"path": "assets"}, "extra": 1}
    out = make_router(layout).from_client(
        line({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    )
    assert_rejected(out, layout)


def test_F_R04_meta는_progressToken만_넘김(layout: Layout) -> None:
    meta = {"progressToken": 7, "other": layout.values["<P>"]}
    params = {"name": "audit_release_exposure", "arguments": {"path": "assets"}, "_meta": meta}
    out = make_router(layout).from_client(
        line({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
    )
    assert [o.to for o in out] == ["rea"]
    assert body(out[0])["params"]["_meta"] == {"progressToken": 7}


# ---------------------------------------------------------------- trace (④)


def inline_evidence(layout: Layout) -> dict[str, Any]:
    return {
        "evidence_id": "ev_" + "1" * 64,
        "evidence_format": "rea-evidence",
        "subject": {"identity": "x", "name": "app", "local_path": layout.target + "\\assets"},
        "operation": "analyze_javascript_application",
    }


@pytest.mark.parametrize("tool", ["trace_javascript_semantics", "trace_application_feature"])
def test_F_R04_trace_inline_Evidence_거절(layout: Layout, tool: str) -> None:
    arguments = {"application": inline_evidence(layout)}
    assert_rejected(call(make_router(layout), tool, arguments), layout)


@pytest.mark.parametrize(
    "application",
    [
        pytest.param({"kind": "evidence-file", "path": "<T>\\e.json"}, id="evidence-file"),
        pytest.param({"kind": "retained-evidence", "evidence_id": "ev_" + "A" * 64}, id="대문자"),
        pytest.param({"kind": "retained-evidence", "evidence_id": "ev_" + "0" * 63}, id="63자"),
        pytest.param(
            {"kind": "retained-evidence", "evidence_id": "ev_" + "0" * 64 + "\n"}, id="줄바꿈"
        ),
        pytest.param({**REFERENCE, "path": "<T>"}, id="키더함"),
        pytest.param("ev_" + "0" * 64, id="글"),
        pytest.param(None, id="없음"),
    ],
)
def test_F_R04_trace_참조꼴아님_거절(layout: Layout, application: Any) -> None:
    if isinstance(application, dict):
        application = {k: layout.fill(v) for k, v in application.items()}
    arguments = {} if application is None else {"application": application}
    assert_rejected(call(make_router(layout), "trace_javascript_semantics", arguments), layout)


def test_F_R04_trace_같은세션참조_허용(layout: Layout) -> None:
    router = make_router(layout)
    query = {"seed": {"kind": "semantic-node", "node_id": "jsrg_node_" + "0" * 64}}
    arguments = {"application": REFERENCE, "query": query}
    assert sent_arguments(call(router, "trace_javascript_semantics", arguments)) == arguments
    feature = {
        "application": REFERENCE,
        "seed": {"kind": "string", "value": "/api/admin/users"},
        "direction": "both",
        "native_observations": [REFERENCE],
    }
    out = call(router, "trace_application_feature", feature, msg_id=2)
    assert sent_arguments(out) == feature


def test_F_R04_trace_native_observations_inline_거절(layout: Layout) -> None:
    arguments = {"application": REFERENCE, "native_observations": [inline_evidence(layout)]}
    assert_rejected(call(make_router(layout), "trace_application_feature", arguments), layout)


# ---------------------------------------------------------------- 그물 (⑤)


def test_F_R04_query에_저장소경로_거절(layout: Layout) -> None:
    for msg_id, value in enumerate([SPEC_REPO_FILE, str(ROOT / "CLAUDE.md")], start=1):
        arguments = {"application": REFERENCE, "query": value}
        out = call(make_router(layout), "trace_javascript_semantics", arguments, msg_id)
        assert_rejected(out, layout, msg_id)


@pytest.mark.parametrize(
    "value",
    ["~/x", "%TEMP%\\x", "$HOME/x", "${HOME}/x", "$(whoami)", "~"],
)
def test_F_R04_펼침꼴_늘거절(layout: Layout, value: str) -> None:
    router = make_router(layout)
    nested = {"application": REFERENCE, "query": {"seed": {"value": value}}}
    assert_rejected(call(router, "trace_javascript_semantics", nested), layout)
    seeded = {"application": REFERENCE, "seed": {"kind": "string", "value": value}}
    assert_rejected(call(router, "trace_application_feature", seeded, msg_id=2), layout, 2)


def test_F_R04_그물_깊은칸과_키도_훑음(layout: Layout) -> None:
    router = make_router(layout)
    deep = {"application": REFERENCE, "query": {"a": [{"b": [layout.values["<P>"]]}]}}
    assert_rejected(call(router, "trace_javascript_semantics", deep), layout)
    keyed = {"application": REFERENCE, "query": {layout.values["<P>"]: 1}}
    assert_rejected(call(router, "trace_javascript_semantics", keyed, msg_id=2), layout, 2)


def test_F_R04_그물_경로꼴아닌글은_그대로(layout: Layout) -> None:
    seed = {"kind": "string", "value": "/api/admin/users?x=1"}
    arguments = {"application": REFERENCE, "seed": seed, "direction": "forward"}
    out = call(make_router(layout), "trace_application_feature", arguments)
    assert sent_arguments(out) == arguments


# ---------------------------------------------------------------- 메서드·도구 이름


def test_F_R04_허용밖_호출_REA로안감_오류(layout: Layout) -> None:
    out = call(make_router(layout), "extract_artifact", {"input_path": "assets"})
    assert_rejected(out, layout)


@pytest.mark.parametrize(
    "method",
    [
        "prompts/get",
        "resources/read",
        "prompts/list",
        "resources/list",
        "completion/complete",
        "logging/setLevel",
    ],
)
def test_F_R04_허용밖_메서드_32601(layout: Layout, method: str) -> None:
    out = make_router(layout).from_client(
        line({"jsonrpc": "2.0", "id": 9, "method": method, "params": {"name": "x"}})
    )
    assert_error_to_client(out, 9, rmf.METHOD_NOT_FOUND)


def test_F_R04_허용밖_알림은_버림(layout: Layout) -> None:
    out = make_router(layout).from_client(
        line({"jsonrpc": "2.0", "method": "notifications/roots/list_changed"})
    )
    assert out == []


def test_F_R04_허용알림은_넘김(layout: Layout) -> None:
    out = make_router(layout).from_client(
        line({"jsonrpc": "2.0", "method": "notifications/initialized"})
    )
    assert [(o.to, body(o)["method"]) for o in out] == [("rea", "notifications/initialized")]


def test_F_R04_취소는_보낸요청만_넘김(layout: Layout) -> None:
    router = make_router(layout)
    router.from_client(line({"jsonrpc": "2.0", "id": 3, "method": "ping"}))
    cancel = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 3}}
    assert [o.to for o in router.from_client(line(cancel))] == ["rea"]
    cancel["params"] = {"requestId": 4}
    assert router.from_client(line(cancel)) == []


def tools_list_response(msg_id: int) -> bytes:
    names = [*ALLOWED, "extract_artifact", "capture_electron_scenario"]
    names += [f"other_{i}" for i in range(68 - len(names))]
    tools = [{"name": name, "inputSchema": {"type": "object"}} for name in names]
    return line({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools, "nextCursor": "c"}})


def test_F_R04_tools_list_4개만(layout: Layout) -> None:
    router = make_router(layout)
    assert [
        o.to for o in router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    ] == ["rea"]
    out = router.from_rea(tools_list_response(1))
    assert [o.to for o in out] == ["client"]
    result = body(out[0])["result"]
    assert [t["name"] for t in result["tools"]] == list(ALLOWED)
    assert result["nextCursor"] == "c"


def test_F_R04_list_changed_뒤_다시받은목록도_4개(layout: Layout) -> None:
    router = make_router(layout)
    router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    router.from_rea(tools_list_response(1))
    changed = router.from_rea(
        line({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
    )
    assert [(o.to, body(o)["method"]) for o in changed] == [
        ("client", "notifications/tools/list_changed")
    ]
    router.from_client(line({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
    out = router.from_rea(tools_list_response(2))
    assert [t["name"] for t in body(out[0])["result"]["tools"]] == list(ALLOWED)


def test_F_R04_tools_list_꼴아님_오류(layout: Layout) -> None:
    router = make_router(layout)
    router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    out = router.from_rea(line({"jsonrpc": "2.0", "id": 1, "result": {"tools": "all"}}))
    assert_error_to_client(out, 1, rmf.INTERNAL_ERROR)


def test_F_R04_initialize_응답은_tools능력만(layout: Layout) -> None:
    router = make_router(layout)
    request = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"capabilities": {}}}
    assert [o.to for o in router.from_client(line(request))] == ["rea"]
    capabilities = {"tools": {"listChanged": True}, "prompts": {}, "resources": {}, "logging": {}}
    response = {"jsonrpc": "2.0", "id": 0, "result": {"capabilities": capabilities, "x": 1}}
    out = router.from_rea(line(response))
    assert body(out[0])["result"] == {"capabilities": {"tools": {"listChanged": True}}, "x": 1}


@pytest.mark.parametrize(
    "method", ["sampling/createMessage", "roots/list", "elicitation/create", "ping"]
)
def test_F_R04_REA가_거는요청은_넘기지않고_오류로답함(layout: Layout, method: str) -> None:
    out = make_router(layout).from_rea(line({"jsonrpc": "2.0", "id": "r1", "method": method}))
    assert [o.to for o in out] == ["rea"]
    assert body(out[0])["id"] == "r1"
    assert body(out[0])["error"]["code"] == rmf.METHOD_NOT_FOUND


def test_F_R04_모르는id의_REA응답은_버림(layout: Layout) -> None:
    out = make_router(layout).from_rea(line({"jsonrpc": "2.0", "id": 5, "result": {}}))
    assert out == []


def test_F_R04_Claude_Code의_응답은_버림(layout: Layout) -> None:
    out = make_router(layout).from_client(line({"jsonrpc": "2.0", "id": "r1", "result": {}}))
    assert out == []


# ---------------------------------------------------------------- JSON 글


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        b'{"jsonrpc":"2.0","id":1,"method":"tools/call","method":"ping"}',
        b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":NaN}}',
        b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":1e999}}',
        b"\xff\xfe",
        b"[" * 100 + b"]" * 100,
    ],
    ids=["깨짐", "같은키", "NaN", "무한", "UTF8아님", "깊이"],
)
def test_F_R04_읽을수없는_JSON_넘기지않고_오류(layout: Layout, raw: bytes) -> None:
    assert_error_to_client(make_router(layout).from_client(raw), None, rmf.PARSE_ERROR)


@pytest.mark.parametrize(
    "message",
    [
        [{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
        {"id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1.5, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1, "method": 3},
    ],
    ids=["배치", "jsonrpc없음", "id참거짓", "id실수", "method숫자"],
)
def test_F_R04_요청꼴아님_32600(layout: Layout, message: Any) -> None:
    out = make_router(layout).from_client(line(message))
    assert [o.to for o in out] == ["client"]
    assert body(out[0])["error"]["code"] == rmf.INVALID_REQUEST


def test_F_R04_끝나지않은_같은id_거절(layout: Layout) -> None:
    router = make_router(layout)
    assert [
        o.to for o in router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    ] == ["rea"]
    out = router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "ping"}))
    assert_error_to_client(out, 1, rmf.INVALID_REQUEST)
    # 첫 요청의 응답은 여전히 tools/list로 걸러진다
    assert len(body(router.from_rea(tools_list_response(1))[0])["result"]["tools"]) == 4


def test_F_R04_REA가_끝나면_남은요청에_오류(layout: Layout) -> None:
    router = make_router(layout)
    router.from_client(line({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    out = router.rea_stopped()
    assert_error_to_client(out, 1, rmf.SERVER_ERROR)
    later = router.from_client(line({"jsonrpc": "2.0", "id": 2, "method": "ping"}))
    assert_error_to_client(later, 2, rmf.SERVER_ERROR)


# ---------------------------------------------------------------- 띄우기 (규칙 1)


def test_F_R04_REA환경_허용목록(tmp_path: Path) -> None:
    environ = {
        "SystemRoot": "C:\\Windows",
        "PATHEXT": ".EXE",
        "FAKE_SECRET_FOR_TEST": "x",
        "PATH": "C:\\elsewhere",
        "USERPROFILE": "C:\\Users\\u",
        "REA_MCP_TOOL_FAMILIES": "electron,artifact,application",
    }
    env_dir = tmp_path / "rea-env"
    env = rmf.build_rea_env(
        environ, "C:\\tools\\node\\node.exe", env_dir, "C:\\run\\netguard.jsonl"
    )
    assert env["PATH"] == "C:\\tools\\node;C:\\Windows\\System32;C:\\Windows"
    assert env["SystemRoot"] == "C:\\Windows"
    assert "FAKE_SECRET_FOR_TEST" not in env
    assert env["REA_MCP_TOOL_FAMILIES"] == "electron,artifact,application"
    for name in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        assert env[name] == str(env_dir / "home" / name)
    assert env["TEMP"] == env["TMP"] == str(env_dir / "tmp")
    netguard = (ROOT / "ops" / "scripts" / "rea_netguard.cjs").as_posix()
    assert env["NODE_OPTIONS"] == f'--require "{netguard}"'
    assert env["REA_NETGUARD_LOG"] == "C:\\run\\netguard.jsonl"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(
            {"--allow": "analyze_javascript_application,extract_artifact"}, id="모르는도구"
        ),
        pytest.param({"--target": "<RUN>\\nope"}, id="없는target"),
        pytest.param({"--env-dir": "<RUN>\\target\\rea-env"}, id="env가target안"),
        pytest.param({"--netguard-log": "<RUN>\\target\\netguard.jsonl"}, id="기록이target안"),
        pytest.param({"--netguard-log": "netguard.jsonl"}, id="기록상대경로"),
        pytest.param({"program": "node.exe"}, id="프로그램상대경로"),
    ],
)
def test_F_R04_설정이상하면_뜨지않음(layout: Layout, change: dict[str, str]) -> None:
    options = {
        "--allow": ",".join(ALLOWED),
        "--target": "<RUN>\\target",
        "--netguard-log": "<RUN>\\netguard.jsonl",
        "--env-dir": "<RUN>\\rea-env",
        "program": sys.executable,
    }
    options.update(change)
    run = str(layout.run_dir)
    argv: list[str] = []
    for name in ("--allow", "--target", "--netguard-log", "--env-dir"):
        argv += [name, options[name].replace("<RUN>", run)]
    argv += ["--", options["program"]]
    with pytest.raises(rmf.ConfigError):
        rmf.load_config(argv)


def test_F_R04_mcp_B_설정틀이_거르개인자와_맞음(layout: Layout) -> None:
    config = json.loads((BENCH / "run" / "mcp-B.json").read_text("utf-8"))
    assert list(config["mcpServers"]) == ["rea"]
    server = config["mcpServers"]["rea"]
    assert server["env"] == {"REA_MCP_TOOL_FAMILIES": "electron,artifact,application"}
    args = [
        a.replace("<ROOT>", str(ROOT)).replace("<RUN>", str(layout.run_dir)) for a in server["args"]
    ]
    assert args[:2] == ["-I", str(FILTER)]
    loaded = rmf.load_config(args[2:])
    assert loaded.policy.allow == frozenset(ALLOWED)
    assert loaded.policy.target == layout.target
    assert loaded.command[1:] == [
        str(ROOT / ".tools/rea/node_modules/rea-agents/scripts/rea.mjs").replace("/", "\\"),
        "mcp",
    ]


# ---------------------------------------------------------------- 실제 프로세스로 (가짜 REA)


class FilterProcess:
    """거르개를 가짜 REA와 함께 띄우고 줄 단위로 주고받는다."""

    def __init__(self, layout: Layout, program: str, extra_env: dict[str, str]) -> None:
        run = layout.run_dir
        self.record = run / "rea-record.jsonl"
        self.env_out = run / "rea-env.json"
        command = [
            sys.executable,
            "-I",
            str(FILTER),
            "--allow",
            ",".join(ALLOWED),
            "--target",
            layout.target,
            "--netguard-log",
            str(run / "netguard.jsonl"),
            "--env-dir",
            str(run / "rea-env"),
            "--",
            program,
            "-I",
            str(FAKE_REA),
            "--record",
            str(self.record),
            "--env-out",
            str(self.env_out),
        ]
        self._stderr = (run / "filter-stderr.txt").open("wb")
        self.proc = subprocess.Popen(  # noqa: S603 — 시험이 만든 인자 목록, 셸 없음
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            env={**os.environ, **extra_env},
        )
        self._lines: queue.Queue[bytes] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            self._lines.put(raw)

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line(message) + b"\n")
        self.proc.stdin.flush()

    def receive(self) -> dict[str, Any]:
        message: dict[str, Any] = json.loads(self._lines.get(timeout=RESPONSE_WAIT_S))
        return message

    def request(
        self, msg_id: int, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self.receive()

    def close(self) -> list[dict[str, Any]]:
        """끝내고 가짜 REA가 받은 줄 전부를 돌려준다."""
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        self.proc.wait(timeout=RESPONSE_WAIT_S)
        self._stderr.close()
        if not self.record.exists():
            return []
        text = self.record.read_text("utf-8")
        return [json.loads(raw) for raw in text.splitlines() if raw]


def base_python() -> str:
    # venv의 python.exe는 진짜 실행 파일을 띄우는 대리라 환경 변수를 더한다.
    # 가짜 REA는 진짜 실행 파일로 띄운다
    return str(getattr(sys, "_base_executable", sys.executable))


def test_F_R04_REA환경_빈홈_TEMP_netguard(layout: Layout) -> None:
    extra = {"FAKE_SECRET_FOR_TEST": "x", "REA_MCP_TOOL_FAMILIES": "electron,artifact,application"}
    process = FilterProcess(layout, base_python(), extra)
    response = process.request(0, "initialize", {"capabilities": {}})
    assert response["result"]["capabilities"] == {"tools": {"listChanged": True}}
    process.close()
    state = json.loads(process.env_out.read_text("utf-8"))
    environ = {k.upper(): v for k, v in state["environ"].items()}
    assert os.path.normcase(state["cwd"]) == os.path.normcase(layout.target)
    assert "FAKE_SECRET_FOR_TEST" not in environ
    env_dir = layout.run_dir / "rea-env"
    for name in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA"):
        assert environ[name] == str(env_dir / "home" / name)
        assert list(Path(environ[name]).iterdir()) == []
    assert environ["TEMP"] == environ["TMP"] == str(env_dir / "tmp")
    netguard = (ROOT / "ops" / "scripts" / "rea_netguard.cjs").as_posix()
    assert environ["NODE_OPTIONS"] == f'--require "{netguard}"'
    assert environ["REA_NETGUARD_LOG"] == str(layout.run_dir / "netguard.jsonl")
    assert environ["REA_MCP_TOOL_FAMILIES"] == "electron,artifact,application"
    allowed = set(rmf.ENV_PASS) | {
        "PATH",
        "USERPROFILE",
        "HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "NODE_OPTIONS",
        "REA_NETGUARD_LOG",
        "REA_MCP_TOOL_FAMILIES",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    }
    assert set(environ) <= {name.upper() for name in allowed}


def test_F_R04_REA가_뜨지않으면_initialize_오류(layout: Layout) -> None:
    process = FilterProcess(layout, str(layout.run_dir / "no-such-rea.exe"), {})
    response = process.request(0, "initialize", {"capabilities": {}})
    assert response["error"]["code"] == rmf.SERVER_ERROR
    assert process.close() == []


def test_F_R04_가짜REA와_한세션_공통표전부(layout: Layout) -> None:
    """한 세션에서 공통 표 전부를 보내고, 가짜 REA가 받은 것이 허용 꼴의 푼 경로뿐인지 본다."""
    process = FilterProcess(layout, base_python(), {})
    assert "result" in process.request(0, "initialize", {"capabilities": {"roots": {}}})
    process.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    listed = process.request(1, "tools/list")
    assert [t["name"] for t in listed["result"]["tools"]] == list(ALLOWED)

    expected_sent: list[str] = []
    msg_id = 100
    for param in table_examples():
        _case_id, example = param.values
        msg_id += 1
        value = layout.fill(example["value"])
        params = {"name": "analyze_javascript_application", "arguments": {"input_path": value}}
        response = process.request(msg_id, "tools/call", params)
        assert response["id"] == msg_id
        if example["filter"] == "reject":
            assert response["error"]["code"] == rmf.INVALID_PARAMS
            continue
        resolved = layout.fill(example["resolved"])
        echoed = json.loads(response["result"]["content"][0]["text"])
        assert echoed == {"input_path": resolved}
        expected_sent.append(resolved)

    denied = process.request(2, "tools/call", {"name": "extract_artifact", "arguments": {}})
    assert denied["error"]["code"] == rmf.INVALID_PARAMS
    prompt = process.request(3, "prompts/get", {"name": "x"})
    assert prompt["error"]["code"] == rmf.METHOD_NOT_FOUND

    # 가짜 REA는 ping에 앞서 sampling·roots 요청과 list_changed를 보낸다
    process.send({"jsonrpc": "2.0", "id": 4, "method": "ping"})
    first = process.receive()
    assert first["method"] == "notifications/tools/list_changed"
    assert process.receive() == {"jsonrpc": "2.0", "id": 4, "result": {}}
    relisted = process.request(5, "tools/list")
    assert [t["name"] for t in relisted["result"]["tools"]] == list(ALLOWED)

    received = process.close()
    methods = [m.get("method") for m in received if "method" in m]
    assert set(methods) <= {
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "ping",
    }
    sent_paths = [
        m["params"]["arguments"]["input_path"] for m in received if m.get("method") == "tools/call"
    ]
    assert sent_paths == expected_sent
    # REA가 건 요청 두 개에는 거르개가 오류로 답했다
    answered = {m["id"]: m["error"]["code"] for m in received if "error" in m}
    assert answered == {"rea-1": rmf.METHOD_NOT_FOUND, "rea-2": rmf.METHOD_NOT_FOUND}
    assert MARKER not in json.dumps(received)
