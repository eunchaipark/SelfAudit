"""`python -m sources.build_tools <명령> <대상 ID>`.

- `build` — 번들 빌드(F-B01)
- `answers` — 번들을 다시 빌드하고 원본의 `answers.in.json`으로 정답지를 쓴 뒤 검사(F-B03·F-B07)
- `check` — 번들 하나 구성 검사(F-B07)

`bench/` 폴더에서 `uv run --frozen --offline python -m sources.build_tools …`로 부른다.
찍는 글에 값은 없다(대상 ID·정답 ID·경로·규칙 번호만).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from common.contracts import ContractJsonError, ContractViolationError
from sources.build_tools.build import BuildError, BuildResult, build
from sources.build_tools.locate import LocateError, write_answers
from sources.build_tools.verify import check_target, format_cover_table, repo_target


def main(argv: Sequence[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="python -m sources.build_tools")
    parser.add_argument("command", choices=("build", "answers", "check"))
    parser.add_argument("bundle_id")
    args = parser.parse_args(argv)
    if args.command == "build":
        try:
            result = build(args.bundle_id)
        except BuildError as e:
            print(f"빌드 실패: {e}")
            return 1
        _print_built(result)
        return 0
    if args.command == "answers":
        try:
            path, result = write_answers(args.bundle_id)
        except (BuildError, LocateError) as e:
            print(f"정답지를 만들 수 없음: {e}")
            return 1
        _print_built(result)
        print(f"정답지: {path.name}")
    return _check(args.bundle_id)


def _print_built(result: BuildResult) -> None:
    for warning in result.warnings:
        print(f"경고: {warning}")
    print(f"{result.bundle_id}: 파일 {len(result.files)}개, 지문 {result.bundle_manifest_sha256}")


def _check(bundle_id: str) -> int:
    try:
        report = check_target(repo_target(bundle_id))
    except (ContractJsonError, ContractViolationError, LookupError) as e:
        print(f"검사할 수 없음: {e}")
        return 1
    for problem in report.problems:
        print(f"{report.bundle_id} {problem}")  # F-B07 출력: 번들 ID·정답 ID·규칙 번호
    for line in format_cover_table(report.cover_rows):
        print(line)
    print(f"{report.bundle_id}: 문제 {len(report.problems)}곳")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
