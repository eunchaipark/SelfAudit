---
name: filter-and-escape-cases
description: 실행기 레인 T31(F-R04 MCP 거르개)에서 배운 함정과 정한 것 — python -I, 가짜 REA 띄우기, REA 참조 꼴, escape_cases.json 쓰는 법
metadata:
  type: project
---

T31(2026-11-22)에서 `bench/run/rea_mcp_filter.py`·`escape_cases.json`·`mcp-B.json`을 만들었다.

- 거르개는 `python -I`로 띄운다 → 스크립트 폴더가 sys.path에 없어 `common`을 import할 수 없다. 독립 파일로 둔다.
  **Why:** -I는 -P를 포함한다. **How to apply:** mcp.json으로 띄우는 스크립트는 표준 라이브러리만.
- 시험에서 가짜 실행 파일을 띄울 때 `sys._base_executable`을 쓴다. venv `python.exe`는 대리라 `__PYVENV_LAUNCHER__`를 환경에 더한다(허용 목록 환경 시험이 깨진다).
- REA 6.10.1 같은 세션 참조 꼴 = `{"kind":"retained-evidence","evidence_id":"ev_<소문자 sha256>"}` (`.tools/rea/node_modules/rea-agents/dist/domain/evidenceReference.js`). 도구 4개의 실제 인자 이름은 REA환경.md 6절 표와 같았다(진짜 REA tools/list로 확인).
- REA는 `\Users\…`(드라이브 없는 루트 기준)도 절대 경로로 받는다(`dist/domain/localPath.js`) → 경로 검사에서 이 꼴을 꼭 거절.
- `escape_cases.json`은 실험구조 3.10 표 그대로(#1~#18, 2026-11-23 설계 5b03082). 거르개 전용 꼴은 시험 파일에 둔다(표에 더하면 문지기 F-R10도 돌려야 함, 설계 결정).
- **경계 시험의 '밖' 자리는 늘 미끼 폴더**(`%LOCALAPPDATA%\SelfAudit-bench-decoy\<배치>\p·j`). 첫 판에서 진짜 `SelfAudit-private`을 가리켜 T31이 반려됐다(검증 중간). 시험은 tmp에 같은 깊이 layout을 만들고, 거절 예가 진짜 표식에 닿는지(`open`)도 본다 — 없는 경로를 가리키는 예는 '없어서' 거절돼 꼴을 재지 못한다.
  **How to apply:** 경로 거절 시험은 오류 코드뿐 아니라 규칙 이름(`RULE_…`)까지 보고, 망가뜨려 돌리기(mutation)로 시험이 잡는지 확인한다.
- 거르개는 target 아래 재분석 지점이 있으면 띄우지 않는다(검증 T31 6) → F-R10 문지기 B에 정션을 두면 B가 늘 연결 안 됨. 설계에 요청해 둠(T31 보고).
- 8.3·정션 시험은 `GetShortPathNameW`(ctypes)·`_winapi.CreateJunction`으로, 관리자 권한 없이 된다. 못 만들면 건너뛰지 말고 실패.
- 격리 worktree 훅: `git -C`, heredoc+git 한 명령, 긴 `&&` 묶음은 막힌다. git은 한 명령씩. 파일을 고치는 임시 스크립트는 heredoc 말고 Write로 scratchpad에 만들어 `python -I`로(heredoc 안 `\\`·`\n`이 깨진 적 있음).
- 띄운 프로세스 나무 끝내기는 kill-on-close Job Object(ctypes)가 기본이다. taskkill /T는 부모가 먼저 끝난 고아를 못 찾는다(T31 재검증 ③). 큰 입력을 다루는 글 함수는 N·2N·4N 시간 비율 시험(gc 끄고 최소값)을 붙인다 — `strip().strip()` 되풀이가 제곱이었다(재검증 ①).
- (닫힘, T32) 문지기 B에는 정션을 두지 않는다(총괄 판단) — #12는 A에서만 기록. REA가 정션을 따라가는지는 보정에서 잰다. [[lane-run-f-r10]]
