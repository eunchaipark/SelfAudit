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
- `escape_cases.json`은 실험구조 3.10 표 그대로(#1~#14). 거르개 전용 꼴은 시험 파일에 둔다(표에 더하면 문지기 F-R10도 돌려야 함, 설계 결정).
- 8.3·정션 시험은 `GetShortPathNameW`(ctypes)·`_winapi.CreateJunction`으로, 관리자 권한 없이 된다. 못 만들면 건너뛰지 말고 실패.
- 격리 worktree 훅: `git -C`, heredoc+git 한 명령은 막힌다. git은 한 명령씩, 임시 스크립트는 Write로 scratchpad에.
- 열린 일: F-R10 문지기 B에서 target 안 정션 + 허용된 `input_path:<T>`로 REA가 밖을 읽을 수 있다(보고서 T31 요청). [[lane-run-f-r10]]
