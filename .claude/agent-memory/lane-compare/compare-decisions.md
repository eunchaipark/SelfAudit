---
name: compare-decisions
description: F-C02 비교(T10)에서 정한 것 — 지문은 다시 계산, 같은 지문은 저장 순서로 짝짓기, 앱 이름은 계약에 없어 useScan으로 우회, 탭 개수는 정보 보기를 따름
metadata:
  type: project
---

F-C02는 `backend/app/compare/engine.py`의 `compare_scans(ScanSide, ScanSide)`가 한다 (T10, 2026-11-20). service가 DB 행을 `Finding`으로 바꿔 넘긴다.
- 지문은 DB `fingerprint` 칸을 쓰지 않고 `fingerprint()`로 다시 계산한다. F-C01이 바뀌어도 두 점검을 같은 기준으로 맞추려는 것이다.
- 같은 지문이 여럿이면 저장된 `order` 순서대로 짝짓는다. 남음 항목은 후의 발견을 보이고 `severity_changed`를 붙인다.
- 묶음 정렬은 F-S06 키를 따르되 경로는 정규화 경로로 비교한다.
- 예외 차례: 같은 ID → 없는 점검 404 → 다른 앱 → 완료 아님 (명세 예외 칸 차례).

**Why:** 명세가 짝짓는 방법과 정렬에 쓸 경로를 정하지 않았다. 목적(전후를 안정적으로 비교)에 맞춰 골랐고, 보고서 `ops/보고/T10.md`에 적었다.
**How to apply:** 비교를 고칠 때는 `test_F_C02_*`(엔진 성능 테스트 포함)를 지킨다. 계약 `ComparisonOut`에 앱 이름이 없다. 그래서 화면 `features/compare/api.ts`의 `useScan`이 `GET /scans/{beforeId}`를 불러 제목을 채운다. 설계에 `appName`을 요청해 두었으니, 계약이 바뀌면 `useScan`을 지운다.

함정: Bash 한 번에 heredoc으로 여러 파일을 쓰면 worktree 격리 검사가 막는다. 파일은 Write로 쓰고 git 명령은 따로 돌린다. 새 파일은 `git commit -- <경로>` 전에 `git add -- <경로>`부터 한다.
