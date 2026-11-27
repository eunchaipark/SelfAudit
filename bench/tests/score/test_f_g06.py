"""F-G06 사례 뽑기 (R1) 시험. 기능명세 F-G06 예시를 옮겼다(값은 가상).

만들기 함수는 `test_f_g03`의 것(그 파일 머리 문서). 대화 기록은 stream-json 꼴의 가짜 줄이다.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from common.contracts import Json
from score.cases import (
    Candidate,
    Hit,
    cases_markdown,
    find_in_transcript,
    read_details,
    select_cases,
)
from score.metrics import RunScore
from score.recompute import score_results
from tests.score.test_f_g03 import answers_doc, finding, hit, miss, record, scored, write_run


def runs_for(
    answers: dict[str, Json],
    target: str,
    condition: str,
    matched: list[list[int]],
    kind: str = "planted",
) -> list[RunScore]:
    """차례마다 `matched`의 정답 차례들을 맞힌 실행(하나도 없으면 틀린 결과 하나)."""
    return [
        scored(answers, target, condition, r, [hit(k) for k in ks] or [miss(0)], kind=kind)
        for r, ks in enumerate(matched, start=1)
    ]


def test_F_G06_B만찾음_B1번이상_A0번() -> None:
    hard = answers_doc("hard-1", 5, difficulty="hard")
    # H1-04 = 정답 차례 3: B 3번 중 2번 짝, A 3번 모두 짝 없음 / H1-05 = 차례 4: B 1번, A 1번
    runs = runs_for(hard, "hard-1", "B", [[3], [3, 4], []]) + runs_for(
        hard, "hard-1", "A", [[], [4], []]
    )
    cases = select_cases(runs, {"hard-1": hard})
    assert cases == (
        Candidate(
            "B만 찾은 정답",
            "hard-1",
            "HARD-1-04",
            "plain",
            (Hit("hard-1-b-1-ab12ab12", 0), Hit("hard-1-b-2-ab12ab12", 0)),
        ),
    )


def test_F_G06_A만찾음() -> None:
    easy = answers_doc("easy-2", 4)
    runs = runs_for(easy, "easy-2", "A", [[2], []]) + runs_for(easy, "easy-2", "B", [[], []])
    cases = select_cases(runs, {"easy-2": easy})
    assert [(c.kind, c.entry_id, len(c.hits)) for c in cases] == [("A만 찾은 정답", "EASY-2-03", 1)]


def test_F_G06_한조건_실행이없으면_보지않음() -> None:
    easy = answers_doc("easy-2", 4)
    assert select_cases(runs_for(easy, "easy-2", "B", [[0]]), {"easy-2": easy}) == ()


def test_F_G06_JuiceShop·내앱은_뽑지않음() -> None:
    juice = answers_doc("juice-shop", 4, origin="practice")
    runs = runs_for(juice, "juice-shop", "B", [[0]], kind="practice")
    runs += runs_for(juice, "juice-shop", "A", [[]], kind="practice")
    assert select_cases(runs, {"juice-shop": juice}) == ()


def tool_line(text: str) -> bytes:
    block = {"type": "tool_result", "tool_use_id": "t1", "content": text}
    msg = {"type": "user", "message": {"role": "user", "content": [block]}}
    return json.dumps(msg, ensure_ascii=False).encode() + b"\n"


def assistant_line(text: str) -> bytes:
    msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    return json.dumps(msg, ensure_ascii=False).encode() + b"\n"


def test_F_G06_B미끼헛짚음_실행ID_대화줄(tmp_path: Path) -> None:
    normal = answers_doc("normal-1", 3, difficulty="normal", decoys=1)
    evidence = "apiKey: \"가짜_키_'x'\""
    transcript = (
        b'{"type":"system","subtype":"init"}\n'
        + assistant_line(evidence)  # 에이전트 글에 먼저 나와도 도구 결과가 아니면 세지 않는다
        + tool_line("다른 글")
        + tool_line(f"   15→{evidence}")
        + tool_line(evidence)
    )
    root = tmp_path / "2026-11-27"
    decoyed = miss(0, evidence=evidence)  # miss(0)은 미끼 D1의 줄
    assert isinstance(decoyed, dict)
    decoyed["reason"] = "키 | 꼴"
    b_found = [hit(0), decoyed]
    write_run(root, record("normal-1", "B", 1), b_found, transcript)
    write_run(root, record("normal-1", "A", 1), [hit(0)], b"")
    result = score_results([root], {"normal-1": normal})
    cases = select_cases(result.report.runs, {"normal-1": normal})
    assert [(c.kind, c.entry_id, c.hiding, c.hits) for c in cases] == [
        ("B의 미끼 헛짚음", "NORMAL-1-D1", "comment", (Hit("normal-1-b-1-ab12ab12", 1),))
    ]
    details, notes = read_details(result.report.runs, cases)
    detail = details[("normal-1-b-1-ab12ab12", 1)]
    assert (detail.evidence, detail.reason, detail.where, notes) == (evidence, "키 | 꼴", "4", ())
    text = cases_markdown(cases, details)
    row = next(line for line in text.split("\n") if line.startswith("| normal-1 |"))
    assert row == (
        "| normal-1 | NORMAL-1-D1 | comment | normal-1-b-1-ab12ab12 | 1 "
        "| apiKey: \"가짜\\_키\\_'x'\" | 키 \\| 꼴 | 4 |"
    )


def test_F_G06_MCP결과_JSON글안에서도_찾음() -> None:
    """REA(MCP) 결과는 JSON 글이라 따옴표가 `\\"`로 실린다 — 조건 B만 `-`가 되지 않게."""
    evidence = 'k: "가짜값"'
    inner = json.dumps({"snippet": evidence}, ensure_ascii=True)  # 한글도 \\uXXXX로
    line = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": [{"type": "text", "text": inner}]},
            ]
        },
    }
    data = tool_line("없음") + json.dumps(line).encode() + b"\n"
    assert find_in_transcript(data, {0: evidence, 1: "어디에도 없음"}) == {0: 2, 1: None}


def test_F_G06_대화기록이_저장소밖이면_sha256만(tmp_path: Path) -> None:
    easy = answers_doc("easy-1", 3)
    archive_sha = "cd34" * 16
    root = tmp_path / "2026-11-27"
    rec = record("easy-1", "B", 1, stored="archive", transcript_sha=archive_sha)
    write_run(root, rec, [hit(1)])
    write_run(root, record("easy-1", "A", 1), [miss(0)], b"")
    result = score_results([root], {"easy-1": easy})
    cases = select_cases(result.report.runs, {"easy-1": easy})
    details, _ = read_details(result.report.runs, cases)
    assert details[("easy-1-b-1-ab12ab12", 0)].where == f"sha256:{archive_sha}"
    assert not (root / "easy-1-b-1-ab12ab12" / "transcript.jsonl").exists()


def test_F_G06_대화기록_지문이다르면_줄없이_알림(tmp_path: Path) -> None:
    easy = answers_doc("easy-1", 3)
    root = tmp_path / "2026-11-27"
    run_dir = write_run(root, record("easy-1", "B", 1), [hit(1)], tool_line("value_1"))
    write_run(root, record("easy-1", "A", 1), [miss(0)], b"")
    (run_dir / "transcript.jsonl").write_bytes(tool_line("value_1 바뀜"))
    result = score_results([root], {"easy-1": easy})
    cases = select_cases(result.report.runs, {"easy-1": easy})
    details, notes = read_details(result.report.runs, cases)
    assert details[("easy-1-b-1-ab12ab12", 0)].where == "-"
    assert notes == ("easy-1-b-1-ab12ab12: 대화 기록 sha256이 run.json과 다름",)


def test_F_G06_목록차례_고정() -> None:
    a1, a2 = answers_doc("easy-1", 4), answers_doc("easy-2", 4, decoys=2)
    runs = (
        runs_for(a2, "easy-2", "B", [[1, 0], [0]])
        + runs_for(a2, "easy-2", "A", [[3]])
        + runs_for(a1, "easy-1", "B", [[2]])
        + runs_for(a1, "easy-1", "A", [[]])
        + [scored(a2, "easy-2", "B", 3, [miss(1), miss(0), finding("secret", 999, "zz")])]
    )
    want = select_cases(runs, {"easy-1": a1, "easy-2": a2})
    assert [(c.kind, c.target_id, c.entry_id) for c in want] == [
        ("B만 찾은 정답", "easy-1", "EASY-1-03"),
        ("B만 찾은 정답", "easy-2", "EASY-2-01"),
        ("B만 찾은 정답", "easy-2", "EASY-2-02"),
        ("A만 찾은 정답", "easy-2", "EASY-2-04"),
        ("B의 미끼 헛짚음", "easy-2", "EASY-2-D1"),
        ("B의 미끼 헛짚음", "easy-2", "EASY-2-D2"),
    ]
    assert [h.run_id for h in want[1].hits] == ["easy-2-b-1-ab12ab12", "easy-2-b-2-ab12ab12"]
    rng = random.Random(27)  # noqa: S311 — 시험의 섞기만(채점기는 난수를 쓰지 않는다)
    for _ in range(5):
        shuffled = runs[:]
        rng.shuffle(shuffled)
        assert select_cases(shuffled, {"easy-1": a1, "easy-2": a2}) == want


def test_F_G06_후보0개면_사례후보없음() -> None:
    text = cases_markdown((), {})
    assert text.count("사례 후보 없음") == 3
    assert "## B만 찾은 정답 (후보 0개, 줄 0개)" in text
