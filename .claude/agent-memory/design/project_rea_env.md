---
name: project-rea-env
description: REA 실험 환경 결정(2026-11-21) — 휴대용 Node 24.22.3 + rea-agents 6.10.1을 .tools/에, rea setup 금지, MCP는 --strict-mcp-config와 도구 묶음으로
metadata:
  type: project
---

2026-11-21 재설계(목적: REA 효과·병렬 효율 실험) 0단계에서 REA 환경을 정했다. 자세한 값·근거는 `docs/설계/REA환경.md`.

- `.tools/`는 git에 안 넣고 `ops/scripts/setup_rea.py` + `ops/scripts/rea/package-lock.json`으로만 재현한다. worktree에서 깐 것은 worktree와 사라진다.
- `rea setup`은 사용자 전체 클라이언트 설정(~/.claude.json 등)에 REA를 등록해 조건 A를 오염시키므로 돌리지 않는다.
- REA는 분석 자식에게 NODE_OPTIONS를 지운다 → 네트워크 확인은 netstat 겹이 꼭 필요하다.

**Why:** 사용자가 "모든 기준에는 근거가 있어야 해"(2026-11-21)라고 했고, 실험 공정성(조건 A·B는 REA만 다름)이 성공 기준이다.

**How to apply:** R4 실행기·조건 설정 요청이 오면 이 문서의 명령 꼴과 도구 묶음 측정에서 시작한다. 버전을 바꾸면 setup_rea.py 고정값과 문서 2절을 같이 고친다. 관련: [[feedback-security-allowlist]]
