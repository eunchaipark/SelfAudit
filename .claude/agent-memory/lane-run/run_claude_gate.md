---
name: lane-run-f-r10
description: 실행기 레인 T32(F-R03 명령줄·F-R05 조건 확인·F-R07 네트워크 기록·F-R10 문지기)에서 정한 것과 함정 — 가짜 claude, 시도 목록 파일, 거절 기록 추정, 대소문자 꼴 가림, 시험 속도
metadata:
  type: project
---

T32(2026-11-27)에서 `bench/run/claude_cmd.py`·`condition.py`·`netwatch.py`·`gate.py`·`prompt.md`·`prompt-gate.md`와
가짜 `bench/tests/run/fake_claude/claude.py`를 만들었다. 배치(T34)는 이것들을 이어 붙이기만 하면 된다.

- **문지기 지시문은 A·B 같은 글**이어야 해서(F-R03 4) 꼴 값(실행마다 다른 경로)을 지시문에 넣지 않고
  `target\gate-cases.json`(시도 번호·도구·인자만, 기대는 싣지 않음)에 쓴다. 판정은 도구 이름 + 인자 글자 그대로 맞춤.
- **거절 기록 = result 줄 `permission_denials[].tool_use_id`(추정) 또는 REA 도구의 오류 글에 `rmf.RULE_…`**. 그 밖의
  오류(파일 없음)는 거절이 아니다. 보정 첫 문지기에서 칸 이름이 다르면 문지기가 늘 실패한다(안전한 쪽) — 그때
  `gate.DENIALS_KEY`·`_scan`을 고친다. **How to apply:** 보정 결과를 받으면 먼저 이 칸부터 확인.
- `<P_SWAPCASE>`(#6)는 홈 아래 경로를 대소문자만 바꾼 꼴이라 store의 가림(글자 그대로)이 못 가리고 남음 검사가
  늘 멈춘다 → `gate.mark_injected`가 그 글(글자·JSON 한 겹·두 겹)을 자리 표시로 되돌린 뒤 store_run에 넘긴다.
- B에는 정션(#12)을 두지 않는다(총괄 판단). #12는 A에서 읽혔는지만 run.json `outcome.detail`·`GatePass.junction_read`에.
- A 문지기가 실패하면 B는 띄우지 않는다(비용). 대상 실행의 `deny_rule_forms`는 `gate.target_settings(…, GatePass, 배치 ID)`로만.
- 끝내기는 taskkill /T /F + kill-on-close Job Object 둘 다(망가뜨려 돌리기에서 taskkill만 빼면 못 잡음 = 겹친 지킴).
- 시험 함정: 큰 가짜 대화 기록을 `bytes +=`로 만들면 제곱이라 pytest가 몇 분 멈춘다 → 목록에 모아 `b"".join`.
  가짜 claude는 `sys._base_executable -I`로, stdout은 `sys.stdout.buffer`에 UTF-8 바이트로(코드 페이지 피함).
- ruff 줄 길이는 한글을 2칸으로 센다 → 문서 문자열은 한글 기준 약 48자에서 접는다(scratchpad `wrap.py` 꼴).
- 격리 worktree 훅은 `python - <<EOF` 꼴과 `&&` 섞인 긴 명령을 막는다 → 고치기는 Edit, 스크립트는 scratchpad 파일로.
- 열린 일: run.json에 claude.exe sha256 칸이 없다(계약 `versions.claude_code`는 글 하나) — T32 보고 요청. [[filter-and-escape-cases]] [[lane-run-plan-store]]
