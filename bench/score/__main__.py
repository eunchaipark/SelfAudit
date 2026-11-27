"""채점 명령 (F-G01~G06, F-R09 2): 원자료만으로 채점·표·그림·사례 후보 (모델을 부르지 않는다).

    cd bench
    uv run python -m score --results results/<날짜> --out ../docs/보고서/그림
    uv run python -m score --results results/<날짜> --out <폴더> --check ../docs/보고서/REA실험.md

`--out`에 쓰는 것(같은 원자료면 같은 바이트): `표.md`(표마다 보고서 표식 꼴), 그림 셋(`*.svg`),
`사례후보.md`(F-G06), `요약.md`(셋째 권고·다시 돌릴 실행·대상별·실행별 숫자·Juice Shop 짝 없는
결과).
`--check`는 보고서의 표가 새로 만든 표와 글자까지 같은지 본다(F-G05). 다르면 끝 코드 1.
`--tolerance`는 줄 허용 T를 바꿔 다시 채점한다(설계 2.5 '확인': 0·2·5).
화면에는 수·이름·까닭만 찍는다(결과·정답지의 글은 파일로만, 보안코딩 '실험').
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Final

from common.contracts import REPO_ROOT
from score.aggregate import Report, Spread, TargetStats
from score.cases import cases_markdown, read_details, select_cases
from score.match import TOLERANCE, Rules
from score.metrics import NO_VALUE, RunScore, fmt_fixed, fmt_percent
from score.read import ReadSummary, ScoreError
from score.recompute import Scored, check_report_file, load_answers, score_results
from score.svg import build_figures
from score.tables import build_tables, fmt_range, marked, md_cell, md_table

TABLES_FILE: Final = "표.md"
CASES_FILE: Final = "사례후보.md"
SUMMARY_FILE: Final = "요약.md"
DEFAULT_TARGETS: Final = Path("bench") / "targets.json"  # 저장소 맨 위 기준
EXIT_OK: Final = 0
EXIT_CHECK_FAILED: Final = 1
EXIT_STOPPED: Final = 2
_TOKEN_LABELS: Final = ("입력 토큰", "출력 토큰", "캐시 만듦 토큰", "캐시 읽음 토큰")


def main(argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    """`repo_root`는 대상 목록의 정답지 경로(`bench/answers/<id>.json`)를 푸는 저장소 맨 위."""
    args = _parser().parse_args(argv)
    rules = Rules(tolerance=args.tolerance)
    try:
        answers = load_answers(args.targets or [repo_root / DEFAULT_TARGETS], repo_root)
        scored = score_results(args.results, answers, rules)
        tables = build_tables(scored.report)
        candidates = select_cases(scored.report.runs, answers)
        details, notes = read_details(scored.report.runs, candidates)
        outputs = {
            TABLES_FILE: marked(tables),
            CASES_FILE: cases_markdown(candidates, details),
            SUMMARY_FILE: summary_markdown(scored, rules, notes),
            **{f"{name}.svg": text for name, text in build_figures(scored.report).items()},
        }
        _write_all(args.out, outputs)
        checks = [(path, check_report_file(path, tables)) for path in args.check]
    except ScoreError as e:
        print(f"채점 멈춤: {e}", file=sys.stderr)
        return EXIT_STOPPED
    _print_summary(scored, len(candidates), args.out, outputs)
    failed = False
    for path, check in checks:
        print(f"보고서 {path.name}: 검사한 표 {len(check.checked)}개, 실패 {len(check.failures)}개")
        for failure in check.failures:
            print(f"  {failure}")
        failed = failed or not check.ok
    return EXIT_CHECK_FAILED if failed else EXIT_OK


def summary_markdown(scored: Scored, rules: Rules, notes: Sequence[str]) -> str:
    """`요약.md`: 표에 넣지 않는 숫자와 알림(F-G01 6, F-G03 1·4·7·8·10)."""
    report, summary = scored.report, scored.summary
    parts = [
        "# 채점 요약 (F-G01~G06)",
        "",
        *_head_lines(summary, report, rules),
        "",
        "## 셋째 차례 권고 (F-G03 10)",
        "",
        *([f"- {line}" for line in report.advice] or ["- 없음"]),
        "",
        "## 다시 돌릴 실행 (F-G01 2)",
        "",
        md_table(
            ("실행", "조건", "대상", "상태"),
            [(r.run_id, r.condition, r.target_id, r.status) for r in report.rerun],
        )
        if report.rerun
        else "없음",
        "",
        "## 읽지 못한 실행 폴더 (F-G01 예외)",
        "",
        md_table(
            ("폴더", "까닭"),
            [(md_cell(u.run_dir.name), md_cell(u.reason)) for u in summary.unreadable],
        )
        if summary.unreadable
        else "없음",
        "",
        "## 대상별 (F-G03 4·8, 최소~최대 (가운데))",
        "",
        _by_target_table(report),
        "",
        "## 실행별 (F-G03 1)",
        "",
        _by_run_table(report.runs),
        "",
        "## Juice Shop 짝 안 된 결과 (F-G03 7, 사람이 본다)",
        "",
        _practice_unmatched(report.runs),
        "",
        "## 사례 후보 알림 (F-G06)",
        "",
        *([f"- {md_cell(n)}" for n in notes] or ["- 없음"]),
        "",
    ]
    return "\n".join(parts)


# --- 요약 조각 -------------------------------------------------------------------------------


def _head_lines(summary: ReadSummary, report: Report, rules: Rules) -> list[str]:
    skipped = ", ".join(f"{k} {n}" for k, n in report.skipped_kinds.items()) or "없음"
    stopped = ", ".join(summary.stopped_targets) or "없음"
    return [
        f"- 채점한 대상 실행 {len(report.runs)}개 · 다시 돌릴 실행 {len(report.rerun)}개 · "
        f"읽지 못한 폴더 {len(summary.unreadable)}개",
        f"- 지표에 넣지 않은 실행 종류(F-G03 0): {skipped}",
        f"- 지문이 달라 채점을 멈춘 대상(F-G01 5): {stopped}",
        f"- 줄 허용 T = {rules.tolerance}, 위치 닻 {'씀' if rules.location_anchors else '안 씀'}",
    ]


def _by_target_table(report: Report) -> str:
    header = (
        "조건",
        "대상",
        "실행 수",
        "재현율",
        "정밀도",
        "결과 수",
        "시간(분)",
        "비용(USD)",
        *_TOKEN_LABELS,
        "도구 호출",
    )
    rows = [(c, target, *_target_cells(stats)) for (c, target), stats in report.by_target.items()]
    return md_table(header, rows) if rows else "없음"


def _target_cells(stats: TargetStats) -> tuple[str, ...]:
    return (
        str(stats.runs),
        fmt_range(stats.recall),
        fmt_range(stats.precision),
        _number_range(stats.results, 0),
        _number_range(stats.minutes, 1),
        _number_range(stats.cost_usd, 2),
        *(_number_range(t, 0) for t in stats.tokens),
        _number_range(stats.tool_calls, 0),
    )


def _by_run_table(runs: Sequence[RunScore]) -> str:
    header = (
        "실행",
        "조건",
        "대상",
        "차례",
        "상태",
        "재현율",
        "정밀도",
        "위치 정확도",
        "짝",
        "결과",
        "중복",
        "미끼 헛짚음",
        "other",
    )
    rows = [
        (
            s.run_id,
            s.condition,
            s.target_id,
            str(s.repeat),
            s.status,
            fmt_percent(s.recall),
            fmt_percent(s.precision),
            fmt_percent(s.location_accuracy),
            str(s.matched) if s.answered else NO_VALUE,
            NO_VALUE if s.results is None else str(s.results),
            str(s.duplicates) if s.answered else NO_VALUE,
            str(s.decoy_misses) if s.answered else NO_VALUE,
            str(s.others),
        )
        for s in runs
    ]
    return md_table(header, rows) if rows else "없음"


def _practice_unmatched(runs: Sequence[RunScore]) -> str:
    rows = []
    for s in runs:
        if not s.answered or s.complete or s.match is None:
            continue
        for index, (finding, verdict) in enumerate(zip(s.findings, s.match.verdicts, strict=True)):
            if verdict == "match":
                continue
            rows.append(
                (
                    s.run_id,
                    str(index),
                    finding.category,
                    verdict,
                    md_cell(finding.file),
                    NO_VALUE if finding.line is None else str(finding.line),
                    md_cell(finding.evidence),
                )
            )
    header = ("실행", "결과 차례", "범주", "판정", "파일", "줄", "evidence")
    return md_table(header, rows) if rows else "없음"


def _number_range(value: Spread | None, places: int) -> str:
    if value is None:
        return NO_VALUE
    low, high, mid = (_number(v, places) for v in (value.low, value.high, value.mid))
    return f"{low}~{high} ({mid})"


def _number(value: Fraction, places: int) -> str:
    """정수 칸의 가운데 값이 .5가 될 수 있어 그때만 소수 한 자리."""
    if places == 0 and value.denominator != 1:
        return fmt_fixed(value, 1)
    return fmt_fixed(value, places)


# --- 바깥과 닿는 곳 --------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m score", description="원자료만으로 채점·표·그림·사례 후보 (F-G01~G06)"
    )
    parser.add_argument(
        "--results", type=Path, action="append", required=True, help="원자료 폴더(여럿 가능)"
    )
    parser.add_argument("--out", type=Path, required=True, help="표·그림·사례 후보를 쓸 폴더")
    parser.add_argument(
        "--targets", type=Path, action="append", help="대상 목록(기본 bench/targets.json)"
    )
    parser.add_argument(
        "--check", type=Path, action="append", default=[], help="표를 대 볼 보고서(F-G05)"
    )
    parser.add_argument("--tolerance", type=int, default=TOLERANCE, help="줄 허용 T(기본 2)")
    return parser


def _write_all(out: Path, outputs: dict[str, str]) -> None:
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name, text in outputs.items():
            (out / name).write_bytes(text.encode("utf-8"))
    except OSError as e:
        raise ScoreError(f"결과를 쓰지 못함 ({type(e).__name__})") from None


def _print_summary(scored: Scored, candidates: int, out: Path, outputs: dict[str, str]) -> None:
    report, summary = scored.report, scored.summary
    print(
        f"채점: 대상 실행 {len(report.runs)}개, 다시 돌릴 실행 {len(report.rerun)}개, "
        f"읽지 못함 {len(summary.unreadable)}개, 멈춘 대상 {len(summary.stopped_targets)}개"
    )
    for line in report.advice:
        print(f"  권고 {line}")
    print(f"사례 후보 {candidates}개")
    print(f"썼음: {out} — {', '.join(outputs)}")


if __name__ == "__main__":
    raise SystemExit(main())
