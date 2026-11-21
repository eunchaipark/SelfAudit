# 검증 — 설계: 실험 구조 + env 반려 고침 (`design/bench-structure`, env-rea 위 c1a33fa..3cd488c)

## 결과: 반려 2 (env-rea 반려 1에 이어, 총괄 2026-11-22 새벽)
- 보안 재검토 (security-reviewer): 높음 1 · 중간 3 · 낮음 5. 지난 env 지적은 대부분 막힘(DNS 함수 전부·Resolver·process.binding·ESM, UNC, 허용 목록 환경, setup 리디렉트·크기·시간·sha256, smoke 경로 가림, 문서 한계 ①~⑤·방화벽 명령). CLAUDE.md 바뀐 줄은 D-036 범위 안, 새 에이전트 4개의 도구는 옛 레인과 같음, 계약 Schema 3개 문제없음.
- 명세 대조 (spec-checker, 요구사항 1~9절·D-035~042): 일치 12 · 빠짐 11 · 다름 6 · 근거 없음 7 · 빠진 [사용자 확인] 후보 7. 질문 2의 '같은 독립 검토'는 맞음.

## 고칠 것 — 보안
1. [높음] MCP 거르개가 도구 이름만 거르고 인자는 안 본다. 허용한 `analyze_javascript_application`(`input_path` = PC의 아무 절대 경로)·`audit_release_exposure`(`path`, 부모 폴더 목록까지)로 조건 B만 `bench/sources/`(심은 곳)·저장소·다른 실행 결과·`private/`(내 앱)을 REA로 읽을 수 있다 → 실험 비대칭 + 내 앱 비밀값이 git에 넣는 transcript로 감. → 거르개 ⑷: 경로 칸을 `os.path.realpath`로 풀어 그 실행의 target 안인지(정션·링크·`\\?\`·8.3 포함), 밖이면 REA에 안 보내고 오류. REA 작업 폴더도 target. 시험 꼴 `..`·저장소 절대 경로·정션·`\\?\C:\…`.
2. [중간] `--allowedTools "Read Grep Glob …"`가 경로 범위 없는 맨 이름 규칙 — 작업 폴더 밖(설정 폴더의 로그인 정보, private, 다른 실행, bench/answers)을 읽을 수 있는지 미확인 → `Read(./**)` 꼴로 묶고 실험 설정 폴더 settings.json에 거절 규칙, 설정 폴더·private을 runs 위쪽 밖으로 떼기, 보정 실행에서 밖 읽기 시험을 배치 시작 조건으로.
3. [중간] netguard `LOCAL_PIPE`가 앞부분만 봐서 `\\.\pipe\..\UNC\…`·`\\.\pipe\..\GLOBALROOT\…`로 우회(Win32가 `..`를 풂, 로컬 재현) → 마디를 나눠 `.`·`..`가 있으면 막기, 자체 시험에 넣기.
4. [중간] check_bench.py:47 OpenAI 꼴 정규식이 `sk-` 반복 한 줄에서 제곱(120k 6.6초, 1MB면 120초 넘음) → 소유 반복 `{20,}+` 또는 `T3BlbkFJ`를 먼저 찾고 앞 창에서만.
5. [낮음] netguard UNC 검사가 Uint8Array 경로·URL 비슷한 객체를 못 봄, `process.binding('fs')` 열림 → 문자열로 바꿔 검사, fs 바인딩 기록.
6. [낮음] check_bench가 run.json의 `target_kind`를 그대로 믿음, staged 파일 안 봄, 커밋 훅 없음 → `bundle_manifest_sha256`를 정답지 지문과 맞추기, `git ls-files`/staged 검사.
7. [낮음] REA환경.md 6절 '파일을 쓰지 않는 것만' — analyze·audit는 REA 표시가 `readOnlyHint:false`·`openWorldHint:true`, MCP 모드 디스크 쓰기는 안 잼 → 거르개 시험에서 한 번 재고 표에.
8. [낮음] setup_rea 재사용 때 node.exe만 해시, npm-cli.js·node_modules는 버전 글만 → 다시 쓸 때도 `npm ci` 또는 rea.mjs sha256.
9. [낮음] 보안규칙 3장 '외부 요청: 앱은 하지 않는다'·7장이 D-036 실험 예외와 어긋남 → 3·7·12장에 '실험 예외' 줄(범위 D-036, 내 앱 원자료 저장소 밖, MCP 경로 target 안).

## 고칠 것 — 명세 대조
- 빠짐: ① R6 README 기능·주인·'구조 그림'·'5분 시험' ② R1·R2 보고서 본문(REA실험.md·병렬효율.md) 주인 ③ 'B만 찾은 정답'(REA가 있어야만 찾은 것) 뽑는 기능 ④ 번들 6개·난이도 2개씩 표와 개수 검사 ⑤ 작업 쌍 3쌍 이상·'다시 한 일' 칸(F-M02) ⑥ '같은 독립 검토'를 받았는지 기록(검토 에이전트 정의·버전) ⑦ 쪽마다 사용량을 가르는 방법(solo가 총괄 안 에이전트라 동시에 돌면 /usage로 못 나눔) ⑧ '명령 하나로 다시 돌림' 명령 꼴과 시험 ⑨ 지시문에 '대상 안 지시는 데이터로만' ⑩ N을 3에서 늘리는 기준 값 제안 ⑪ Juice Shop 알려진 문제 목록 출처, answers의 `difficulty`를 Juice Shop에 어떻게
- 다름: ① 상한을 토큰 대신 비용(USD)으로 — 근거 ② R4 '조건마다 설정 폴더' → 설정 폴더 하나 + MCP 파일(문서 역할이 요구사항 고침) ③ D-041 묶음(문서 49f95c0에서 고침) ④ 정밀도 분모에서 other 뺌([사용자 확인] 표시 있음) ⑤ 보정 배치 4번(대상 실행 2번) ⑥ 계약 이름 `origin: juice-shop` vs `target_kind: practice` 맞추기
- 근거 없음(D-038): anchor 최대 200자, anchor 최소 4자·evidence 300자·transcript 2MB의 확인 방법, 시간 상한 '적어도 10분', 짝짓기 동점 차례, 계약 길이 상한들(500·2000·300·40·30·80자), 머리말 [사용자 확인] 대상 '8절 3·4·5' 표기
- [사용자 확인] 후보로 더 표시: N 기준, 조건 재현율 모으는 법(짝 합 ÷ 정답 합), Juice Shop 정밀도를 하한으로만, 파일 경로 정규화·글자 그대로 비교, 조건 B 허용 도구 4개, 조건 A 도구 Read·Grep·Glob, solo-bench 병합 전 검토 없음

## 문제와 개선
- 방법론: 도구 허용 목록을 이름까지만 보면 인자로 넓어지는 권한을 놓친다 → MCP·도구 허용 목록 표에 도구마다 '경로를 받는 칸'과 서버가 붙인 표시(readOnly·openWorld)를 칸으로
- 방법론: 설계가 요구사항과 다르게 정한 값이 요구사항·결정기록 글에 다시 반영되지 않는다 → 설계 보고서 '요청' 칸에 '고칠 요구사항·결정기록 줄'을 필수로
- 프로젝트: 경로 허용 꼴을 앞부분 정규식으로 맞추면 OS 경로 풀기로 우회된다 → 마디 검사가 기본

## 재검증 (반려 2 고침 290fddb..a233f31): 반려 3 — 명세 보강만 (총괄, 2026-11-22 04:xx)
- 보안: 높음 0 · 중간 1 · 낮음 4. 지난 높음(거르개 인자)·중간 셋(파이프 `..`, check_bench 제곱, 맨 이름 Read 규칙)은 막힘. 낮음 다섯 중 넷 막힘, URL 비슷한 객체는 일부.
- 고칠 것 (모두 설계 문서·작은 코드, 같은 design 에이전트):
  1. [중간] 실험구조.md:239 F-R10 문지기 시험에 경로 꼴 목록이 없다 — Claude Code 권한 규칙은 글자로 맞춰서 다른 꼴이 통과할 수 있다(실제 사례 CVE-2025-54794, 형제 폴더 앞부분 비교) → 거르개 ⑷의 시험 꼴을 공통 표 하나로 두고 F-R10에도 그대로: `..` 상대, 8.3(`SELFAU~1`), `\?\C:\…`, `\localhost\C$\…`, `/` 꼴, 대소문자 바꿈, 형제 `target2`, Grep·Glob의 `path`와 `pattern`·`glob`의 `..` — 꼴마다 '대화 기록에 표식 글 없음' + '거절 기록 남음'.
  2. [낮음] rea_netguard.cjs:65-73 URL 비슷한 객체: `href`를 보지만 fs는 `hostname`·`pathname`을 씀 → `url.fileURLToPath`로 fs와 같은 경로를 만들어 검사.
  3. [낮음] check_bench.py:154-157 `Files.json()`이 작업 폴더 버전만 → 색인 버전도 ㉡ 검사.
  4. [낮음] 실험구조.md:232 `…-runs` 맨 위 거절이 자기 target까지 막음 → 실행마다 형제 실행 폴더만 거절(또는 지난 실행 폴더를 치움), 규칙 꼴(`//C:/…` vs `//c/…`)은 문지기 실행에서 확인한다고.
  5. [낮음] REA환경.md 6절 ⑷: realpath로 푼 경로를 REA에 보냄, JSON-RPC 메서드 허용 목록(initialize·tools/list·tools/call·알림, 다시 받은 목록도 거름, prompts/get 거절), ⑤ 그물에 `~`·`%VAR%`·`$VAR`, `source_paths` 기준은 REA 정의대로 `input_path`.
- 5시간 92% → 07:2x 리셋 뒤 보낸다. 고친 뒤는 문서 중심이라 총괄이 diff로 확인하고 병합한다(높음·중간 없음, 남은 것은 명세 꼴 보강).
