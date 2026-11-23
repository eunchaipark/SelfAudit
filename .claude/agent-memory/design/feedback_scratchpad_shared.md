---
name: scratchpad-shared-names
description: 세션 scratchpad는 레인 에이전트와 같이 쓰여 같은 파일 이름이면 덮인다 — 임시 파일 이름 앞에 design- 을 붙인다
metadata:
  type: feedback
---

scratchpad 임시 파일은 이름 앞에 `design-`을 붙이고, 쓴 뒤 바로 쓰고 다시 쓰지 않는다.

**Why:** 2026-11-23 설계 작은 묶음에서 내 `splice.py`가 같은 scratchpad를 쓰던 실행기 레인의 스크립트로 덮였다(같은 총괄 세션 아래 에이전트끼리 scratchpad 폴더가 같다).

**How to apply:** scratchpad에 스크립트·조각 파일을 Write할 때마다. 한 번 돌린 스크립트를 다시 돌리기 전에는 내용을 다시 확인한다. [[feedback_worktree_git_cwd]]
