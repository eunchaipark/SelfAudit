---
name: lead-decisions-in-tasks
description: 레인 보고서가 '총괄 판단'이라고만 적은 결정의 근거는 tasks.json details에 있다 — 고침 모음 때 python으로 찾는다 (spec-editor)
metadata:
  type: reference
---

레인 보고서의 '(총괄 판단)'(예: T32 'B 문지기에 정션을 두지 않음')은 결정기록·CR이 아니라 `.taskmaster/tasks/tasks.json`의 태스크 details 글에만 근거가 있다.
**Why:** 2026-11-27 고침 모음에서 이 판단이 명세 F-R10 근거 11과 부딪힌 채 병합돼 있었고, 근거를 찾으려고 보드·검증을 헤맸다. `grep -rn`으로 `.claude/worktrees`까지 훑으면 120초를 넘겨 멈춘다.
**How to apply:** `python -I -c` 로 tasks.json을 읽어 details에서 '총괄 판단' 낱말 둘레만 찍는다(한글은 `PYTHONIOENCODING=utf-8`). 찾은 근거는 명세에 '(총괄 판단, T<n> 넘김)'으로 옮긴다. [[commit-in-shared-main]]
