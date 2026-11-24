"""F-R06 원자료 저장 (R4) 시험. 기능명세 F-R06 예시를 옮겼다(값은 가상).

저장소·`%LOCALAPPDATA%`·홈은 모두 시험이 만든 임시 폴더다
(진짜 `bench/results/`·`SelfAudit-private`에 쓰지 않는다).
대화 기록은 가짜 stream-json 줄이다(필드 이름은 추정, 실험구조 3.3).
"""

from __future__ import annotations

import dataclasses
import gc
import hashlib
import json
import time
import tracemalloc
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from common.contracts import read_contract
from common.fingerprint import bundle_manifest_sha256
from run import store as rs
from run import workdir as rw
from tests.conftest import MakeBundle

KST = timezone(timedelta(hours=9))
DAY = date(2026, 11, 23)
BATCH = "20261123-0130-first24"
RUN = "easy-1-a-1-3f2a9c10"
SHA = "a" * 64
LINEAR_RATIO_LIMIT = 8.0  # 선형 4N/N 약 4, 제곱 약 16의 가운데(test_f_r01과 같은 근거)


@dataclasses.dataclass(frozen=True)
class Layout:
    places: rw.BenchPlaces
    run_dir: Path
    target: Path


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    home = tmp_path / "Users" / "u"
    places = rw.BenchPlaces(
        repo_root=tmp_path / "repo",
        local_app_data=home / "AppData" / "Local",
        user_profile=home,
    )
    places.repo_root.mkdir(parents=True)
    run_dir = places.runs_root / BATCH / RUN
    (run_dir / "target").mkdir(parents=True)
    return Layout(places=places, run_dir=run_dir, target=run_dir / "target")


def facts(**over: Any) -> rs.RunFacts:
    base: dict[str, Any] = {
        "run_kind": "target",
        "run_id": RUN,
        "batch_id": BATCH,
        "target_id": "easy-1",
        "target_kind": "planted",
        "bundle_manifest_sha256": SHA,
        "condition": "A",
        "repeat_index": 1,
        "started_at": datetime(2026, 11, 23, 1, 30, tzinfo=KST),
        "ended_at": datetime(2026, 11, 23, 1, 34, 10, tzinfo=KST),
        "versions": {
            "claude_code": "2.1.119",
            "model": "claude-test-model-1",
            "rea": None,
            "node": None,
            "prompt_sha256": SHA,
            "findings_schema_sha256": SHA,
            "mcp_config_sha256": SHA,
            "plan_sha256": SHA,
        },
        "settings": {
            "effort": "high",
            "timeout_s": 780,
            "max_budget_usd": 2.52,
            "tools": ["Read", "Grep", "Glob"],
            "allowed_tools": ["Read(./**)", "Grep(./**)", "Glob(./**)"],
            "rea_tools": [],
            "order_seed": 20261123,
            "firewall_rule": "unknown",
            "deny_rule_forms": ["//C:/"],
        },
        "status": "ok",
        "exit_code": 0,
        "init_check": "passed",
        "detail": "",
        "wall_s": 250.0,
        "network": {
            "netguard_blocked": 0,
            "netguard_local": 0,
            "netstat_endpoints": 0,
            "guarded_processes": 0,
            "rea_processes": 0,
        },
    }
    base.update(over)
    return rs.RunFacts(**base)


def finding(file: str, **over: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "category": "secret",
        "file": file,
        "line": 3,
        "evidence": "fake-evidence",
        "reason": "가짜 이유",
        "confidence": "high",
    }
    item.update(over)
    return item


def stream(
    layout: Layout, structured: Any = None, extra: list[dict[str, Any]] | None = None
) -> bytes:
    lines: list[dict[str, Any]] = [
        {"type": "system", "subtype": "init", "cwd": str(layout.target)},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]},
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]},
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "t2", "name": "Grep", "input": {}}]},
        },
        *(extra or []),
        {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.84,
            "duration_ms": 250000,
            "duration_api_ms": 200000,
            "num_turns": 7,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
                "cache_creation_input_tokens": 30,
                "cache_read_input_tokens": 40,
            },
            "structured_output": structured,
        },
    ]
    return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines).encode("utf-8")


def store(layout: Layout, data: bytes, **over: Any) -> rs.StoredRun:
    return rs.store_run(
        layout.places,
        facts(**over),
        batch_date=DAY,
        run_dir=layout.run_dir,
        target=layout.target,
        stream=data,
    )


# --- 예시 ------------------------------------------------------------------------------------


def test_F_R06_run_json_계약통과(layout: Layout) -> None:
    got = store(layout, stream(layout, {"findings": []}))
    assert got.out_dir == layout.places.repo_root / "bench" / "results" / "2026-11-23" / RUN
    assert sorted(p.name for p in got.out_dir.iterdir()) == sorted(rs.RAW_FILES)
    record = read_contract("run", got.out_dir / "run.json")
    assert record["run_kind"] == "target"
    assert record["metrics"] == {
        "wall_s": 250.0,
        "duration_ms": 250000,
        "duration_api_ms": 200000,
        "num_turns": 7,
        "total_cost_usd": 0.84,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "cache_creation_input_tokens": 30,
            "cache_read_input_tokens": 40,
        },
        "tool_calls": {"Read": 1, "Grep": 1},
    }
    loose: Any = record
    assert loose["settings"]["order_seed"] == 20261123
    assert loose["versions"]["plan_sha256"] == SHA
    assert record["started_at"] == "2026-11-23T01:30:00+09:00"


def test_F_R06_result줄없으면_지표null_findings없음(layout: Layout) -> None:
    data = json.dumps({"type": "system", "subtype": "init"}).encode() + b"\n{not json\n"
    got = store(layout, data, status="error", exit_code=1)
    assert not (got.out_dir / "findings.json").exists()
    metrics = got.record["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["total_cost_usd"] is None and metrics["num_turns"] is None
    assert rs.read_stream(data).bad_lines == 1


def test_F_R06_findings경로_상대로(layout: Layout) -> None:
    absolute = str(layout.target / "assets" / "a.js")
    structured = {"findings": [finding(absolute), finding("./index.html"), finding("assets\\b.js")]}
    got = store(layout, stream(layout, structured))
    saved = json.loads((got.out_dir / "findings.json").read_text("utf-8"))
    assert [f["file"] for f in saved["findings"]] == ["assets/a.js", "index.html", "assets/b.js"]
    assert saved["findings"][0]["evidence"] == "fake-evidence"
    assert got.record["outcome"] == {
        "status": "ok",
        "exit_code": 0,
        "init_check": "passed",
        "detail": "",
    }


def test_F_R06_findings_계약밖이면_format_failure_남김(layout: Layout) -> None:
    structured = {"findings": [finding("a.js", category="nope")]}
    got = store(layout, stream(layout, structured))
    outcome = got.record["outcome"]
    assert isinstance(outcome, dict)
    assert outcome["status"] == "format_failure"
    assert "category" in str(outcome["detail"]) and "nope" not in str(outcome["detail"])
    saved = json.loads((got.out_dir / "findings.json").read_text("utf-8"))
    assert saved["findings"][0]["category"] == "nope"  # 받은 결과는 남긴다


def test_F_R06_대화기록_절대경로_RUN으로가림(layout: Layout) -> None:
    home = str(layout.places.user_profile)
    extra = [
        {"type": "user", "note": f"거절됨 {home}\\.ssh"},
        {"type": "user", "p": str(layout.target).replace("\\", "/")},
    ]
    got = store(layout, stream(layout, {"findings": []}, extra))
    text = (got.out_dir / "transcript.jsonl").read_text("utf-8")
    assert '"cwd": "<RUN>\\\\target"' in text
    assert '"거절됨 <HOME>\\\\.ssh"' in text
    assert '"p": "<RUN>/target"' in text
    assert home not in text and home.replace("\\", "\\\\") not in text


def test_F_R06_가림차례_RUN먼저() -> None:
    home = r"C:\Users\u"
    run = r"C:\Users\u\AppData\Local\SelfAudit-bench-runs\20261123-0130-first24\easy-1-a-1-3f2a9c10"
    line = json.dumps({"cwd": run + r"\target"})
    assert rs.mask_paths(line, run, home) == '{"cwd": "<RUN>\\\\target"}'
    assert rs.mask_paths(r"C:\\Users\\u\\.ssh", run, home) == r"<HOME>\\.ssh"


def test_F_R06_홈경로_소문자남으면_error_배치멈춤(layout: Layout) -> None:
    home = str(layout.places.user_profile)
    extra = [{"type": "user", "note": home.lower() + "\\x"}]
    with pytest.raises(rs.StoreError) as e:
        store(layout, stream(layout, {"findings": []}, extra))
    out = e.value.written
    assert out is not None
    assert sorted(p.name for p in out.iterdir()) == [
        "run.json"
    ]  # 홈 경로가 든 파일은 저장소로 안 감
    record = read_contract("run", out / "run.json")
    outcome, transcript = record["outcome"], record["transcript"]
    assert isinstance(outcome, dict) and isinstance(transcript, dict)
    assert (outcome["status"], transcript["stored"]) == ("error", "archive")
    assert (layout.places.archive_dir / f"{RUN}.jsonl").is_file()
    assert home.lower() not in (out / "run.json").read_text("utf-8").lower()


def test_F_R06_결과글에_홈경로_가림(layout: Layout) -> None:
    home = str(layout.places.user_profile)
    structured = {"findings": [finding("a.js", evidence=f"{home}\\secret.txt")], "notes": home}
    got = store(layout, stream(layout, structured))
    text = (got.out_dir / "findings.json").read_text("utf-8")
    assert "<HOME>" in text and home.replace("\\", "\\\\") not in text


def _limit_stream(layout: Layout, size: int) -> bytes:
    data = stream(layout, {"findings": []})
    masked_len = len(
        rs.mask_paths(data.decode(), str(layout.run_dir), str(layout.places.user_profile)).encode()
    )
    pad = size - masked_len - len(b'{"type":"pad","x":""}\n')
    assert pad > 0
    return b'{"type":"pad","x":"' + b"p" * pad + b'"}\n' + data


def test_F_R06_2MB는_그대로(layout: Layout) -> None:
    got = store(layout, _limit_stream(layout, rs.TRANSCRIPT_LIMIT_BYTES))
    path = got.out_dir / "transcript.jsonl"
    assert path.stat().st_size == 2_097_152
    assert got.record["transcript"] == {
        "stored": "results",
        "bytes": 2_097_152,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_F_R06_대화기록_2MB넘으면_밖에·sha256(layout: Layout) -> None:
    got = store(layout, _limit_stream(layout, rs.TRANSCRIPT_LIMIT_BYTES + 1))
    assert not (got.out_dir / "transcript.jsonl").exists()
    archived = layout.places.archive_dir / f"{RUN}.jsonl"
    assert got.transcript_path == archived
    data = archived.read_bytes()
    assert got.record["transcript"] == {
        "stored": "archive",
        "bytes": 2_097_153,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    assert len(data) == 2_097_153


def test_F_R06_mine_저장소밖(layout: Layout) -> None:
    got = store(
        layout,
        stream(layout, {"findings": []}),
        run_id="mine-blog-a-1-0000beef",
        target_id="blog",
        target_kind="mine",
    )
    want = layout.places.private_dir / "results" / "2026-11-23" / "mine-blog-a-1-0000beef"
    assert got.out_dir == want
    assert not (layout.places.repo_root / "bench" / "results").exists()


def test_F_R06_mine_실행ID_mine접두_아니면_거절(layout: Layout) -> None:
    with pytest.raises(rs.StoreError, match="mine-"):
        store(layout, b"", run_id="blog-a-1-0000beef", target_id="blog", target_kind="mine")


def _inside_repo(layout: Layout) -> rw.BenchPlaces:
    p = layout.places
    return rw.BenchPlaces(
        repo_root=p.repo_root,
        local_app_data=p.repo_root / "bench" / "results",
        user_profile=p.user_profile,
    )


@pytest.mark.parametrize(
    ("run_kind", "target_id", "target_kind", "run_id"),
    [
        ("target", "blog", "mine", "mine-blog-a-1-0000beef"),
        ("empty", "empty", "planted", "empty-a-1-0000beef"),
        ("gate", "gate", "planted", "gate-b-1-0000beef"),
    ],
    ids=["mine", "빈", "문지기"],
)
def test_F_R06_mine에_저장소경로_거절(
    layout: Layout, run_kind: str, target_id: str, target_kind: str, run_id: str
) -> None:
    manifest = rw.EMPTY_MANIFEST_SHA256 if run_kind == "empty" else SHA
    one = facts(
        run_kind=run_kind,
        target_id=target_id,
        target_kind=target_kind,
        run_id=run_id,
        bundle_manifest_sha256=manifest,
    )
    with pytest.raises(rs.StoreError, match="저장소 안"):
        rs.store_run(
            _inside_repo(layout),
            one,
            batch_date=DAY,
            run_dir=layout.run_dir,
            target=layout.target,
            stream=b"",
        )
    with pytest.raises(rs.StoreError, match="저장소 안"):
        rs.check_out_dir(
            layout.places.repo_root / "bench" / "results",
            run_kind=run_kind,
            target_kind=target_kind,
            repo_root=layout.places.repo_root,
        )
    assert not (layout.places.repo_root / "bench" / "results" / "results").exists()
    assert list(layout.places.repo_root.rglob("*")) == []


def test_F_R06_출력자리가_정션으로_저장소안이면_거절(layout: Layout) -> None:
    import _winapi

    private = layout.places.private_dir
    private.parent.mkdir(parents=True, exist_ok=True)
    (layout.places.repo_root / "bench").mkdir()
    _winapi.CreateJunction(str(layout.places.repo_root / "bench"), str(private))
    with pytest.raises(rs.StoreError, match="저장소 안"):
        store(layout, b"", run_id="mine-blog-a-1-0000beef", target_id="blog", target_kind="mine")
    assert list((layout.places.repo_root / "bench").iterdir()) == []


def test_F_R06_실행ID_80자넘으면_거절(layout: Layout) -> None:
    long_id = "easy-1-a-1-" + "0" * 70
    assert len(long_id) == 81
    with pytest.raises(rs.StoreError, match="80자"):
        store(layout, b"", run_id=long_id)
    ok_id = "easy-1-a-1-" + "0" * 69
    assert store(layout, b"", run_id=ok_id, status="error").out_dir.name == ok_id


def test_F_R06_빈·문지기실행_저장소밖_보관(layout: Layout, make_bundle: MakeBundle) -> None:
    empty = store(
        layout,
        stream(layout, {"findings": []}),
        run_kind="empty",
        run_id="empty-a-1-0000beef",
        target_id="empty",
        batch_id="20261123-0130-calib",
        bundle_manifest_sha256=rw.EMPTY_MANIFEST_SHA256,
    )
    assert empty.out_dir == layout.places.archive_dir / "20261123-0130-calib" / "empty-a-1-0000beef"
    assert (
        rw.EMPTY_MANIFEST_SHA256
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    record = read_contract("run", empty.out_dir / "run.json")
    assert (record["run_kind"], record["target_id"], record["target_kind"]) == (
        "empty",
        "empty",
        "planted",
    )
    gate_target = bundle_manifest_sha256(make_bundle({"deny-probe-1/x": b"fake-probe"}))
    gate = store(
        layout,
        stream(layout, {"findings": []}),
        run_kind="gate",
        run_id="gate-b-1-0000cafe",
        target_id="gate",
        condition="B",
        bundle_manifest_sha256=gate_target,
    )
    assert gate.out_dir == layout.places.archive_dir / BATCH / "gate-b-1-0000cafe"
    assert gate.record["bundle_manifest_sha256"] == gate_target
    assert not (layout.places.repo_root / "bench" / "results").exists()


@pytest.mark.parametrize(
    "over",
    [
        {
            "run_kind": "empty",
            "target_id": "easy-1",
            "bundle_manifest_sha256": rw.EMPTY_MANIFEST_SHA256,
        },
        {"run_kind": "gate", "target_id": "gate", "target_kind": "mine"},
        {"run_kind": "empty", "target_id": "empty", "bundle_manifest_sha256": SHA},
    ],
    ids=["빈_target_id", "문지기_종류", "빈_지문"],
)
def test_F_R06_빈·문지기_칸_어긋나면_거절(layout: Layout, over: dict[str, Any]) -> None:
    with pytest.raises(rs.StoreError):
        store(layout, b"", **{"run_id": "empty-a-1-0000beef", **over})


def test_F_R06_원자료폴더_이미있으면_멈춤(layout: Layout) -> None:
    store(layout, stream(layout, {"findings": []}))
    with pytest.raises(rs.StoreError, match="이미 있음"):
        store(layout, stream(layout, {"findings": []}))


def test_F_R06_run_json_계약밖이면_안씀(layout: Layout) -> None:
    with pytest.raises(rs.StoreError, match="계약"):
        store(layout, b"", status="weird")
    assert not (layout.places.repo_root / "bench" / "results").exists()


def test_F_R06_도구이름_꼴밖은_한데셈() -> None:
    line = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": "x", "name": "a b\n"}]},
    }
    assert rs.read_stream(json.dumps(line).encode()).tool_calls == {rs.OTHER_TOOL: 1}


# --- 처리량 (보안규칙 5장, 실험구조 8.1 ⑤) -------------------------------------------------


def _seconds(fn: Callable[[], object]) -> float:
    """세 번 돌린 가운데 가장 짧은 시간(gc 끔). 메모리 재기는 시간을 흔들어 따로 한다."""
    best = float("inf")
    for _ in range(3):
        gc.collect()
        gc.disable()
        start = time.perf_counter()
        try:
            fn()
            best = min(best, time.perf_counter() - start)
        finally:
            gc.enable()
    return best


def _peak(fn: Callable[[], object]) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _lines(n: int) -> bytes:
    rows = (
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": f"T{i % 50}"}]},
            }
        )
        for i in range(n)
    )
    return ("\n".join(rows) + "\n").encode()


def test_F_R06_처리량_대화기록줄_1만_2만() -> None:
    data = {n: _lines(n) for n in (10_000, 20_000, 40_000)}
    t1 = _seconds(lambda: rs.read_stream(data[10_000]))
    t4 = _seconds(lambda: rs.read_stream(data[40_000]))
    m1 = _peak(lambda: rs.read_stream(data[10_000]))
    m2 = _peak(lambda: rs.read_stream(data[20_000]))
    assert t4 / t1 < LINEAR_RATIO_LIMIT, (t1, t4)
    assert m2 / m1 < 3.0, (m1, m2)


def test_F_R06_처리량_가림_입력2배4배() -> None:
    home, run = r"C:\Users\u", r"C:\Users\u\AppData\Local\SelfAudit-bench-runs\b\r"
    unit = "".join(
        f'{{"n":{i},"p":"C:\\\\Users\\\\u\\\\f{i}","q":"c:/users/U/{i}"}}\n' for i in range(5_000)
    )
    texts = {k: unit * k for k in (1, 2, 4)}

    def work(k: int) -> None:
        rs.home_left(rs.mask_paths(texts[k], run, home), home)

    t1, t4 = _seconds(lambda: work(1)), _seconds(lambda: work(4))
    assert t4 / t1 < LINEAR_RATIO_LIMIT, (t1, t4)


def test_F_R06_처리량_결과정규화_1만_2만(tmp_path: Path) -> None:
    root = str(tmp_path)
    values: dict[int, Any] = {
        n: {"findings": [finding(f"{root}\\assets\\f{i}.js") for i in range(n)]}
        for n in (10_000, 20_000, 40_000)
    }
    t1 = _seconds(lambda: rs.normalize_findings(values[10_000], root))
    t4 = _seconds(lambda: rs.normalize_findings(values[40_000], root))
    m1 = _peak(lambda: rs.normalize_findings(values[10_000], root))
    m2 = _peak(lambda: rs.normalize_findings(values[20_000], root))
    assert t4 / t1 < LINEAR_RATIO_LIMIT, (t1, t4)
    assert m2 / m1 < 3.0, (m1, m2)
