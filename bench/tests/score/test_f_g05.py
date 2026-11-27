"""F-G05 다시 계산 검사 (R1·R5) 시험. 기능명세 F-G05 예시를 옮겼다(값은 가상).

원자료는 시험이 tmp_path 아래에 만든다(진짜 `bench/results/`를 쓰지 않는다). 만들기 함수는
`test_f_g03`의 것(그 파일 머리 문서).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from common.contracts import Json
from score.__main__ import main
from score.read import ScoreError
from score.recompute import check_report, score_results
from score.svg import build_figures
from score.tables import TABLE_NAMES, build_tables, marked
from tests.score.test_f_g03 import answers_doc, hit, miss, record, write_run


def answers_set() -> dict[str, dict[str, Json] | None]:
    return {
        "easy-1": answers_doc("easy-1", 4),
        "hard-1": answers_doc("hard-1", 5, difficulty="hard"),
    }


def make_raw(root: Path, *, names: dict[str, str] | None = None) -> Path:
    """조건 A·B × 대상 둘 × 두 차례. `names`로 실행 폴더 이름을 바꿀 수 있다(읽는 차례가 바뀜)."""
    for c, ks in (("A", (1, 2)), ("B", (3, 4))):
        for r, k in enumerate(ks, start=1):
            for target in ("easy-1", "hard-1"):
                rec = record(target, c, r, cost=0.5 + k / 10, wall_s=300.0 + 60 * k)
                found = [hit(i) for i in range(k)] + [miss(0)]
                name = (names or {}).get(str(rec["run_id"]))
                write_run(root, rec, found, name=name)
    return root


def tables_of(*roots: Path) -> dict[str, str]:
    return build_tables(score_results(list(roots), answers_set()).report)


def test_F_G05_같은원자료_두번_같은숫자(tmp_path: Path) -> None:
    root = make_raw(tmp_path / "2026-11-27")
    one, two = score_results([root], answers_set()), score_results([root], answers_set())
    assert build_tables(one.report) == build_tables(two.report)
    assert build_figures(one.report) == build_figures(two.report)


def test_F_G05_파일차례바꿔도_같은숫자(tmp_path: Path) -> None:
    straight = make_raw(tmp_path / "a" / "2026-11-27")
    # 폴더 이름 앞에 거꾸로 된 차례를 붙여 읽는 차례를 뒤집고, 두 원자료 폴더로 나눠 준다
    ids = sorted(p.name for p in straight.iterdir())
    names = {run_id: f"{len(ids) - i:02d}-{run_id}" for i, run_id in enumerate(ids)}
    shuffled = make_raw(tmp_path / "b" / "2026-11-27", names=names)
    later = tmp_path / "b" / "2026-11-28"
    later.mkdir()
    for run_dir in sorted(shuffled.iterdir())[::2]:
        run_dir.rename(later / run_dir.name)
    assert tables_of(straight) == tables_of(later, shuffled)


def test_F_G05_조건이름을_바꾸면_칸만바뀜(tmp_path: Path) -> None:
    """공정성: 채점기는 A·B 어느 쪽도 따로 다루지 않는다 — 이름을 바꾸면 줄만 바뀐다."""
    root = make_raw(tmp_path / "x")
    swapped = tmp_path / "y"
    swapped.mkdir()
    for run_dir in root.iterdir():
        rec = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        rec["condition"] = {"A": "B", "B": "A"}[rec["condition"]]
        found = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))["findings"]
        write_run(swapped, rec, found, name=run_dir.name)
    one, two = tables_of(root)["조건별"].split("\n"), tables_of(swapped)["조건별"].split("\n")
    assert one[2].replace("| A |", "| B |") == two[3]
    assert one[3].replace("| B |", "| A |") == two[2]


def test_F_G05_보고서표_글자같으면_통과(tmp_path: Path) -> None:
    tables = tables_of(make_raw(tmp_path / "r"))
    report = "# 실험 보고서\n\n글.\n\n" + marked(tables) + "\n끝.\n"
    check = check_report(report, tables)
    assert check.ok
    assert check.checked == TABLE_NAMES


def test_F_G05_한글자다르면_실패(tmp_path: Path) -> None:
    tables = tables_of(make_raw(tmp_path / "r"))
    report = "# 보고서\n\n" + marked({"조건별": tables["조건별"]})
    lines = report.split("\n")
    row = next(i for i, line in enumerate(lines) if line.startswith("| B |"))
    cells = lines[row].split(" | ")
    assert cells[1] == "66.7~88.9% (77.8%)"
    lines[row] = lines[row].replace("66.7~88.9% (77.8%)", "67~89% (78%)")
    check = check_report("\n".join(lines), tables)
    assert not check.ok
    assert [(f.name, f.line) for f in check.failures] == [("조건별", row + 1)]


def test_F_G05_줄이모자라거나_남으면_실패() -> None:
    tables = {"조건별": "| a |\n|---|\n| 1 |"}
    short = "<!-- 표:조건별 -->\n| a |\n|---|\n<!-- /표 -->"
    long = "<!-- 표:조건별 -->\n| a |\n|---|\n| 1 |\n| 2 |\n<!-- /표 -->"
    assert [(f.name, f.line) for f in check_report(short, tables).failures] == [("조건별", 4)]
    assert [(f.name, f.line) for f in check_report(long, tables).failures] == [("조건별", 5)]


def test_F_G05_없는이름이면_실패() -> None:
    check = check_report("<!-- 표:요약 -->\n| a |\n<!-- /표 -->\n", {"조건별": "| a |"})
    assert [(f.name, f.line, f.why) for f in check.failures] == [
        ("요약", 1, "만들 수 없는 표 이름")
    ]


def test_F_G05_표식없으면_실패() -> None:
    """여는 표식만 있고 끝 표식이 없거나, 끝 표식만 있거나, 표식 꼴이 틀리면 실패."""
    tables = {"조건별": "| a |"}
    no_end = check_report("<!-- 표:조건별 -->\n| a |\n", tables)
    assert [(f.name, f.line, f.why) for f in no_end.failures] == [("조건별", 1, "끝 표식 없음")]
    no_start = check_report("| a |\n<!-- /표 -->\n", tables)
    assert [f.why for f in no_start.failures] == ["여는 표식 없는 끝 표식"]
    crooked = check_report("<!--표:조건별-->\n| a |\n<!-- /표 -->\n", tables)
    assert not crooked.ok
    crlf = check_report("<!-- 표:조건별 -->\r\n| a |\r\n<!-- /표 -->\r\n", tables)
    assert not crlf.ok  # 글자까지 같아야 한다(CR도 글자)
    assert crlf.failures[0].why.startswith("줄 끝이 CRLF")


def test_F_G05_표식이_하나도없으면_통과하고_0개() -> None:
    check = check_report("# 보고서\n\n표 없음.\n", {"조건별": "| a |"})
    assert check.ok
    assert check.checked == ()


def test_F_G05_원자료없음_실패(tmp_path: Path) -> None:
    with pytest.raises(ScoreError, match="원자료 폴더가 없음"):
        score_results([tmp_path / "없음"], {})
    (tmp_path / "빈").mkdir()
    with pytest.raises(ScoreError, match="원자료 없음"):
        score_results([tmp_path / "빈"], {})


def write_targets(path: Path, root: Path) -> Path:
    """시험용 대상 목록과 정답지(저장소 맨 위 = `root`)."""
    answers_dir = root / "bench" / "answers"
    answers_dir.mkdir(parents=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for target, doc in answers_set().items():
        (answers_dir / f"{target}.json").write_text(json.dumps(doc), encoding="utf-8")
        entries.append(
            {
                "id": target,
                "kind": "planted",
                "bundle": f"bench/bundles/{target}",
                "answers": f"bench/answers/{target}.json",
            }
        )
    path.write_text(
        json.dumps({"schema": "selfaudit-bench/targets@1", "targets": entries}), encoding="utf-8"
    )
    return path


def run_cli(tmp_path: Path, out: Path, *extra: str) -> int:
    """시험용 저장소(대상 목록·정답지)와 원자료를 한 번 만들고 채점 명령을 부른다."""
    repo = tmp_path / "repo"
    targets = repo / "bench" / "targets.json"
    if not repo.exists():
        write_targets(targets, repo)
    raw = tmp_path / "raw" / "2026-11-27"
    if not raw.exists():
        make_raw(raw)
    return main(["--results", str(raw), "--out", str(out), *extra], repo_root=repo)


def test_F_G05_score명령_두번_같은바이트(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(tmp_path, tmp_path / "out1") == 0
    assert run_cli(tmp_path, tmp_path / "out2") == 0
    files = sorted(p.name for p in (tmp_path / "out1").iterdir())
    assert files == sorted(
        [
            "표.md",
            "사례후보.md",
            "요약.md",
            "난이도별_재현율.svg",
            "비용_재현율.svg",
            "범주별_재현율.svg",
        ]
    )
    for name in files:
        one = hashlib.sha256((tmp_path / "out1" / name).read_bytes()).hexdigest()
        assert one == hashlib.sha256((tmp_path / "out2" / name).read_bytes()).hexdigest()
    printed = capsys.readouterr().out
    assert "value_" not in printed and "miss_" not in printed  # 결과의 글을 화면에 찍지 않는다


def test_F_G05_score명령_보고서검사(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli(tmp_path, tmp_path / "out") == 0
    good = tmp_path / "REA실험.md"
    good.write_bytes(b"# R1\n\n" + (tmp_path / "out" / "표.md").read_bytes())  # LF 그대로
    assert run_cli(tmp_path, tmp_path / "out", "--check", str(good)) == 0
    bad = tmp_path / "틀림.md"
    bad.write_bytes(good.read_bytes().replace(b"| A |", b"| A  |", 1))
    assert run_cli(tmp_path, tmp_path / "out", "--check", str(bad)) == 1
    assert "표 조건별" in capsys.readouterr().out


def test_F_G05_score명령_원자료없으면_멈춤(tmp_path: Path) -> None:
    code = main(["--results", str(tmp_path / "없음"), "--out", str(tmp_path / "out")])
    assert code == 2
