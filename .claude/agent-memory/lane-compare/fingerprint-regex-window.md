---
name: fingerprint-regex-window
description: F-C01 지문 정규식은 명세 그대로 걸면 제곱 시간이라 이름 끝 창에만 건다. 비교(F-C02)는 app.compare.fingerprint를 쓴다
metadata:
  type: project
---

F-C01 지문은 `backend/app/compare/engine.py`에 있고 `app.compare.fingerprint`로 다시 내보낸다 (T9, 2026-11-19).
명세 정규식 `^(.*)\.[0-9a-f]{8,32}(\.[A-Za-z0-9.]+)$`를 이름 전체에 걸면 `(.*)` 되짚기로 제곱 시간이다(점이 많은 30,000자 0.5초). 그래서 이름 끝의 `[A-Za-z0-9.]` 구간 + 그 앞 9자(Vite 조각 `-`+8자) 창에만 건다. `test_F_C01_좁힌창이_명세정규식과_같다`가 전체 정규식과 같은지 지킨다.

**Why:** 레인 카드가 정규식 선형을 요구한다(규칙 레인 T5가 이 문제로 반려됨).
**How to apply:** 정규식을 고치면 창 계산(`_match_window_start`)도 같이 맞추고 대조 테스트를 돌린다. F-C02는 지문마다 개수를 세서 비교한다.

함정: worktree에는 `frontend/node_modules`가 없다. `check.py` 전에 `cd frontend; npm ci` 한 번(백엔드는 `uv run`이 알아서 .venv를 만든다). 테스트에서 `random`을 쓰면 ruff S311 — 고정 씨앗이면 `# noqa: S311`에 이유를 단다.
