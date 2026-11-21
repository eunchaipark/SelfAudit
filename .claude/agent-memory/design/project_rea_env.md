---
name: project-rea-env
description: REA 실험 환경과 실험 구조 결정(2026-11-21~22) — 휴대용 Node 24.22.3 + rea-agents 6.10.1, 감시는 기록 장치, 조건 B는 MCP 거르개로 REA 도구 4개만, 실험 전용 Claude 설정 폴더
metadata:
  type: project
---

2026-11-21 재설계(목적: REA 효과·병렬 효율 실험)에서 정한 것. 값·근거는 `docs/설계/REA환경.md`, `docs/설계/실험구조.md`.

- `.tools/`는 git에 안 넣고 `ops/scripts/setup_rea.py` + `ops/scripts/rea/package-lock.json`으로만 재현한다. worktree에서 깐 것은 worktree와 사라진다.
- `rea setup`은 사용자 전체 클라이언트 설정에 REA를 등록해 조건 A를 오염시키므로 돌리지 않는다.
- 네트워크 감시(`rea_netguard.cjs` + netstat)는 **차단 장치가 아니라 기록 장치**로 쓴다. REA는 분석 자식에게 NODE_OPTIONS를 지운다. 실제 차단은 방화벽(관리자, 사용자 확인).
- 조건 B: 세 묶음(electron·artifact·application) 68개 중 정적 분석 4개만(analyze_javascript_application, audit_release_exposure, trace_javascript_semantics, trace_application_feature). MCP 거르개 + `--allowedTools` 두 층.
- Claude Code는 npm 전역 설치의 `bin\claude.exe`를 셸 없이 부른다. `--bare`는 구독 로그인 불가 → 실험 전용 `CLAUDE_CONFIG_DIR` 하나(A·B 공유, 사용자가 한 번 로그인).

**Why:** 사용자가 "모든 기준에는 근거가 있어야 해"(2026-11-21). env 브랜치가 보안 검토 반려 1(중간 3·낮음 5)을 받았다 — '두 겹으로 막았다'는 과장, MCP 도구 범위, 환경 전체 넘김이 지적됐다.

**How to apply:** 감시·차단 도구를 설계할 때는 '감싼 것 / 못 덮는 것' 표와 로컬 우회 자체 시험을 같이 낸다. 실행기·채점기 요청이 오면 실험구조.md 2·3절에서 시작한다. 관련: [[feedback-security-allowlist]]
