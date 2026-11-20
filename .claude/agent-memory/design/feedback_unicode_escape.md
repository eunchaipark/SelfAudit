---
name: feedback-unicode-escape
description: 문서에 방향 문자 등을 `\u202E` 글로 적을 때 Edit 도구·heredoc이 실제 글자로 바꾼다 — python chr(92)+'u202E'로 쓰고 숨은글자 검사로 확인
metadata:
  type: feedback
---

문서에 보이지 않는 글자를 글로 적을 때(`\u202E` 등)는 Edit 도구나 셸 heredoc으로 쓰지 않는다. 둘 다 그 표기를 실제 글자(U+202E)로 바꾼다. python에서 `chr(92) + 'u202E'`로 넣고, `python -I ops/scripts/check_hidden.py`로 확인한다.

**Why:** 2026-11-20에 보안규칙 67줄과 코드규칙 10장에 실제 U+202E가 두 번 들어갔다. 한 번은 보안 검토가 낮음으로 잡았고, 한 번은 새 검사가 잡았다.

**How to apply:** `\x..`·`\u....` 꼴이 든 문서를 고칠 때마다 커밋 전에 숨은글자 검사를 돌린다. 관련: [[feedback-security-allowlist]]
