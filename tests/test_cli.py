"""가짜 기록(tests/fixtures/projects)으로만 시험한다. 진짜 기록은 쓰지 않는다."""

import json
from datetime import date
from pathlib import Path

import pytest

from ccusage_lens.cli import group, main
from ccusage_lens.reader import scan

FIX = Path(__file__).parent / "fixtures" / "projects"


def rows_of(by_key, **kw):
    return {r["key"]: r for r in group(scan(FIX, **kw).records, by_key)}


def test_project_totals():
    rows = rows_of("project")
    assert rows["C--demo-alpha"]["total"] == 18900
    assert rows["C--demo-beta"]["total"] == 7777


def test_duplicate_message_id_counted_once():
    res = scan(FIX)
    assert res.stats.duplicate_lines == 1
    main_alpha = [r for r in res.records if r.project == "C--demo-alpha" and r.agent == "main"]
    assert sum(r.tokens[0] for r in main_alpha) == 11  # msg_1 의 10 + msg_2 의 1, 두 번 세지 않음


def test_broken_line_skipped_and_counted():
    res = scan(FIX)
    assert res.stats.broken_lines == 1
    assert res.stats.lines == 13
    assert res.stats.assistant_lines == 8
    # 깨진 줄 뒤의 줄도 읽는다
    assert rows_of("day")[date(2026, 11, 25).isoformat()]["total"] == 10


def test_agent_attribution():
    rows = rows_of("agent")
    assert rows["main"]["total"] == 11120 + 7777
    assert rows["reviewer"]["total"] == 5555  # 부모 Agent 호출의 subagent_type, 결과 줄 agentId 로 이음
    assert rows["general-purpose"]["total"] == 3  # subagent_type 없음 → 기본값, meta 보다 부모 호출이 우선
    assert rows["Explore"]["total"] == 2222  # 부모 호출을 못 찾으면 meta.json agentType
    assert "wrong-type" not in rows


def test_subagent_file_shares_parent_session():
    rows = rows_of("session")
    assert set(rows) == {"sess-a", "sess-b"}
    assert rows["sess-a"]["total"] == 18900


def test_since_until_and_project_filter():
    rows = rows_of("day", since=date(2026, 11, 25), until=date(2026, 11, 26))
    assert set(rows) == {"2026-11-25", "2026-11-26"}
    rows = rows_of("project", project="beta")
    assert set(rows) == {"C--demo-beta"}


def test_empty_folder(tmp_path, capsys):
    assert main(["--root", str(tmp_path)]) == 0
    assert "no usage found" in capsys.readouterr().out
    assert main(["--root", str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rows"] == [] and data["total"]["total"] == 0


def test_missing_folder(tmp_path):
    assert main(["--root", str(tmp_path / "nope")]) == 2


def test_json_numbers(capsys):
    assert main(["--root", str(FIX), "--by", "agent", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total"]["total"] == 26677
    assert data["total"]["messages"] == 7
    for r in data["rows"]:
        assert set(r) == {
            "key", "messages", "input_tokens", "output_tokens",
            "cache_creation_input_tokens", "cache_read_input_tokens", "total",
        }
        assert all(isinstance(r[k], int) for k in r if k != "key")


def test_top_folds_rest(capsys):
    assert main(["--root", str(FIX), "--by", "agent", "--top", "2"]) == 0
    out = capsys.readouterr().out
    assert "(other 2)" in out and "TOTAL" in out


@pytest.mark.parametrize("key", ["project", "session", "day", "agent"])
@pytest.mark.parametrize("fmt", [[], ["--json"]])
def test_body_never_printed(key, fmt, capsys):
    assert main(["--root", str(FIX), "--by", key, "--top", "0", *fmt]) == 0
    out = capsys.readouterr().out
    assert "SECRET-BODY" not in out
    assert "review" not in out.replace("reviewer", "")
