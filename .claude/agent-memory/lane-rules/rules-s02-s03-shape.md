---
name: rules-s02-s03-shape
description: T6 뒤 F-S02(sourcemaps.py)·F-S03(endpoints.py) 출력 모양, S01 걸림을 받아 근거 조각을 만드는 hit_snippet, 관리 경로 찾기가 느렸던 함정
metadata:
  type: project
---

T6(2026-11-20)에서 `sourcemaps.scan_file(path, content, in_bundle=, s01_spans=) -> SourcemapScan(findings, not_sourcemap)`, `endpoints.scan_file(path, content, s01_spans=) -> EndpointsScan(findings, stopped)`를 만들었다. 둘 다 `secrets.scan_file(...).spans`를 받는다. 안내는 `sourcemaps.skipped_notice(intake.skipped)`, '번들에 있음'은 `sourcemaps.bundle_paths(targets, skipped)`.

**Why:** T8이 S01 → S02 → S03 차례로 부르고 건너뜀 한 줄(`NOT_SOURCEMAP` 또는 `TOO_MANY_HITS`)을 만든다. 근거 조각 ②에 같은 글의 S01 걸림이 필요해서다(CR-003).

**How to apply:**
- S01이 아닌 걸림의 근거 조각은 `text.hit_snippet(글, S01걸림, 시작, 끝, edits)`로 만든다. edits는 걸린 곳을 값 모양으로 바꾸는 곳(`****@`, `?` 뒤 지우기, `…`)이다. 겹치거나 걸친 S01 걸림은 가린 값으로 바뀌고 걸린 곳이 넓어진다. S01 목록은 복사하지 않고 `_Spliced` 보기로 끼운다. 복사하면 발견마다 선형이 되어 제곱이 된다.
- `.map` JSON은 `text.load_sourcemap`(BOM을 뗌) 하나로 판정한다. S01·S02·S03이 어긋나지 않게 하기 위해서다.
- 선형이어도 파이썬 반복이 후보마다 돌면 느리다. `"/` 반복 6MB가 8.5초였다. 후보 정규식을 걸림 꼴까지 좁혀(`따옴표 + /admin… + (/ 또는 같은 따옴표)`) 반복 수를 걸림 상한으로 묶었다. [[rules-regex-linear]]
- S02·S03 값 칸에 S01 원문이 들어가는 꼴(주소 속 비밀번호, URL 경로 속 키)은 명세대로 남겨 두고 보고서 요청 2로 올렸다. CR이 나오면 값에도 ②를 적용한다. [[rules-s01-output-cap]]
- Bash 도구는 `cd … && 여러 명령`·heredoc을 worktree 밖으로 볼 수 있다며 막는다. 스크립트는 scratchpad에 Write로 쓰고 `cd backend && PYTHONPATH=. uv run python <파일>`로 돌린다. 새 파일은 `git add <경로>`를 먼저 한다.
