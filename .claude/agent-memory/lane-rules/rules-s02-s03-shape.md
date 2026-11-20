---
name: rules-s02-s03-shape
description: T6 뒤 F-S02(sourcemaps.py)·F-S03(endpoints.py) 출력 모양, 값 가리기 mask_hit·hit_snippet·HMAC 묶기(CR-007), 관리 경로 찾기가 느렸던 함정
metadata:
  type: project
---

T6(2026-11-20, 반려 고침 CR-007·D-033·D-034 포함)에서 만든 것:
- `sourcemaps.scan_file(path, content, in_bundle=, s01_spans=) -> SourcemapScan(findings, not_sourcemap)`
- `endpoints.scan_file(path, content, key, s01_spans=) -> EndpointsScan(findings, stopped)`

둘 다 `secrets.scan_file(...).spans`를 받는다. 안내는 `sourcemaps.skipped_notice(intake.skipped)`, '번들에 있음'은 `sourcemaps.bundle_paths(targets, skipped)`.

**Why:** T8이 S01 → S02 → S03 차례로 부르고 건너뜀 한 줄을 만든다. 값 칸·근거 조각에서 같은 글의 S01 걸림을 가려야 한다(CR-003·007).

**How to apply:**
- S01이 아닌 걸림(S02 2·4, S03, 나중 S04)의 값은 아래 차례로 만든다.
  1. `text.value_edits`(㈀ 사용자 정보 `****@`, ㈁ `?`·`#` 뒤 지움)
  2. `text.mask_hit(content, spans, start, end, edits, keep=)`: ㈂ S01 가린 값(걸치면 넓힘), ㈃ ㉠, 그다음 200자 + `…`
  3. 근거 조각은 `text.hit_snippet(content, spans, hit)`. 걸린 곳 = 값 칸 글이다.
- 자르기는 '앞부분을 가린 글 = 전체를 가린 글의 앞부분' 성질로, 읽는 창을 두 배씩 늘려 가린 뒤 200자까지만 읽는다.
- S03 묶기·증거키는 ㈀㈁만 한 글(`text.plain_value`)의 HMAC이다(`keyed_digest` 전체가 묶음 열쇠, 앞 12자가 증거키).
- 첫 구현 때 명세가 값 칸을 '주소 그대로'로 정해 원문이 남아 반려됐다. 새 규칙 값 칸을 만들 때는 같은 글의 S01 가리기부터 본다. [[rules-s01-output-cap]]
- 선형이어도 파이썬 반복이 후보마다 돌면 느리다(`"/` 반복 6MB 8.5초). 후보 정규식을 걸림 꼴까지 좁혀 반복 수를 걸림 상한으로 묶었다. [[rules-regex-linear]]
- 시간 테스트는 잴 함수만 잰다(S03 테스트가 S01 시간까지 재다가 부하 때 실패함). PC에 다른 프로그램이 돌면 모든 시간이 5배쯤 된다.
- Bash 도구 요령:
  - `cd … && 여러 명령`·heredoc은 worktree 밖으로 볼 수 있다며 막힌다. 스크립트는 scratchpad에 `t<id>_` 이름으로 Write하고(다른 세션이 같은 이름 파일을 덮었다) `cd backend && PYTHONPATH=. uv run python <파일>`로 돌린다.
  - 새 파일은 `git add <경로>`를 먼저 한다.
  - 파이썬 heredoc 안의 `"\\n"`이 진짜 줄바꿈으로 들어간 적이 있다. 코드 조각은 Edit 도구로 넣는다.
