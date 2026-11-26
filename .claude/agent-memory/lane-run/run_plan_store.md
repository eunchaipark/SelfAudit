---
name: lane-run-plan-store
description: 실행기 레인 T30(F-R01 계획·F-R02 실행 폴더·F-R06 원자료)에서 정한 것과 함정 — ㉢이 홈 아래에서 늘 멈춤, 시험 임시 자리, 계획 칸 이름, store 멈춤 꼴
metadata:
  type: project
---

T30(2026-11-25)에서 `bench/run/plan.py`·`workdir.py`·`env.py`·`store.py`·`mcp-A.json`을 만들었다. T32·T34가 이것을 부른다.

- **㉢(위쪽 CLAUDE.md·.claude)**: 홈 아래에서 늘 멈춰서 설계 8.9 1이 실행 폴더를 `%SystemDrive%\SelfAudit-bench-runs`로 옮겼다(2026-11-27). 시험 자리는 드라이브 맨 위의 새 임시 폴더 `SelfAudit-bench-test-*`(`clean_base`, T32의 `gate_base`).
  **How to apply:** 위쪽 확인·권한을 시험할 때는 pytest tmp_path(홈 아래)를 쓰지 않는다.
- 계획 파일 칸 이름은 T30이 정했다: `name`, `targets: [{id, n?}]`, `default_n`, `conditions`, `model`, `effort`, `timeout_s`, `max_budget_usd`, `order_seed`, `first_repeat?`, `source?`. 모르는 칸은 거절. 조건 차례는 파일 차례가 아니라 A→B 고정(같은 시드 → 같은 차례).
- 실행 ID 8자는 `assign_run_ids(runs, targets, existing_run_names(bench/results), token)` — 지난 실행 이름의 **8자**와도 안 겹치게. 난수는 주입(시험은 세는 함수).
- `store_run`이 배치를 멈추는 꼴은 모두 `StoreError`(쓰기 전 거절, 또는 홈 경로가 남아 run.json만 쓰고 멈춤 — `.written`에 폴더). `workdir`은 `BatchStop(rule, detail)`. 글에 홈 경로를 싣지 않는다(㉢은 '위로 N단계'만).
- `mcp.json` 틀 sha256(`McpConfig.template_sha256`)은 조건마다 같고, 쓴 바이트는 `<RUN>` 때문에 실행마다 다르다. `versions.mcp_config_sha256`에 어느 쪽을 적을지는 T32가 정한다(추천: 틀).
- 구조화 결과 칸 이름 `structured_output`, init·result 줄 칸은 추정 — 첫 보정에서 확인.
- 처리량 시험은 시간(gc 끔, 세 번 최소)과 메모리(tracemalloc 한 번)를 **따로** 잰다. 같이 재면 tracemalloc이 시간을 5배쯤 늘려 시험이 10초를 넘었다.
- **반려 1(2026-11-26)**: ① 가림이 드라이브 절대 경로 꼴만 덮어 `//c/Users/…`(우리 거절 규칙 꼴)·`/c/…`·`\\localhost\C$`·URL 인코딩이 남았다 → 꼴을 넓히고 남음 검사는 드라이브 없는 꼬리 `Users\<이름>`를 찾는다. ② `casefold()`가 한글 글에서 입력의 14배 메모리 → 가림은 **바이트 그대로**, 찾기는 바이트 정규식 IGNORECASE.
  **How to apply:** 경로 꼴을 새로 만드는 코드(거절 규칙 등)를 쓰면 가림 꼴 목록과 맞춰 본다. 처리량 잼·시험 입력에는 한글 줄을 섞는다(ASCII만이면 str이 1바이트/글자라 배수가 가려진다).
- 망가뜨려 돌리기 스크립트(scratchpad `mutate.py` 꼴): 지킴 19개 중 겹친 지킴 2개만 못 잡음 → 하나는 지우고 하나는 시험을 더했다. [[filter-and-escape-cases]]
