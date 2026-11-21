# REA 실험 환경 (재설계 0단계)

작성 2026-11-21 · 주인: 설계 · 근거 문서: `ops/계획/재설계-초안.md` 5절 · 사용자 허락(2026-11-21, 채팅): "휴대용 Node로 설치"

> 결론: **REA 6.10.1은 이 PC(Windows 11, x64)에서 휴대용 Node 24.22.3으로 돈다.** `analyze-javascript-application`과 `audit-release-exposure`(CLI), `rea mcp`(MCP stdio)가 모두 정상 종료했고, 시험 실행 중 바깥 네트워크 시도는 보지 못했다(두 겹으로 봄, 4절). WSL은 지금 필요 없다(7절).
> 이 문서의 모든 숫자는 2026-11-21 밤 이 PC에서 잰 값이다. 추정인 것은 '추정'이라고 적고 확인 방법을 붙였다.

## 1. 다시 만드는 법

```
python -I ops/scripts/setup_rea.py          # .tools/node(휴대용 Node) + .tools/rea(rea-agents) 를 만든다
python -I ops/scripts/rea_smoke.py --out <요약 JSON 절대 경로> [--keep] [--operation audit-release-exposure]
```

- `setup_rea.py`는 이미 맞게 깔려 있으면 건너뛴다. 새로 깔면 Node zip 약 38MB와 npm 패키지를 받는다(처음 설치 237초, 빈 폴더에 `setup_rea.py`로 다시 깔기 348초(같은 버전·해시로 끝남)).
- **worktree에서 깐 `.tools/`는 worktree를 지우면 같이 사라진다.** 병합 뒤 실험을 돌릴 폴더(main)에서 `setup_rea.py`를 한 번 돌린다. 근거: `.tools/`는 git에 넣지 않으므로(용량 약 360MB: node 107MB, rea 208MB, npm 캐시 45MB) 폴더마다 따로 깔아야 한다.
- 관리자 권한, 시스템 PATH, 설치된 Node 22.19.0(`C:\Program Files\nodejs`)은 건드리지 않는다. 휴대용 Node는 REA를 부를 때 그 프로세스의 환경에서만 PATH 앞에 붙인다.

| 파일 | 하는 일 |
|---|---|
| `.gitignore` `.tools/` | 휴대용 Node·REA·npm 캐시를 git에 넣지 않는다 |
| `ops/scripts/setup_rea.py` | 받기 → sha256 두 번 맞추기 → 안전하게 풀기 → `npm ci --ignore-scripts` → 버전 확인 |
| `ops/scripts/rea/package.json`, `package-lock.json` | rea-agents 6.10.1과 하위 패키지 175개의 버전·sha512를 고정한다 |
| `ops/scripts/rea_netguard.cjs` | Node 미리 읽기 파일. 바깥 TCP·UDP·이름 풀기를 막고 기록한다 (4절) |
| `ops/scripts/rea_smoke.py` | 가짜 시험 번들을 만들고 REA를 셸 없이 돌려 시간·크기·필드·네트워크를 요약한다 |

## 2. 버전과 해시

| 무엇 | 값 | 근거 |
|---|---|---|
| Node | **v24.22.3** (2026-11-10, LTS Krypton, 보안 릴리스), npm 11.19.1 | 아래 '왜 24.x' |
| Node zip | `node-v24.22.3-win-x64.zip` 37,762,649바이트, sha256 `e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f` | 받은 파일의 sha256 = `https://nodejs.org/dist/v24.22.3/SHASUMS256.txt`의 값(직접 맞춤). 스크립트에 고정해 다음 설치에서 값이 바뀌면 멈춘다 |
| rea-agents | **6.10.1** (`npm view rea-agents dist-tags.latest`, 2026-11-21 22시 기준. 패키지 마지막 수정 2026-11-20T06:52Z) | 배정문 ③. 초안 5절: 실험 중 버전이 바뀌면 차이가 REA 때문인지 알 수 없다 |
| rea-agents 묶음 | integrity `sha512-3AWrfFEXppvC98FWhZR2Tzulnqs5xJQrSKmAub6+QME/I58Pr3h8pHqqwM30z2DvlnIx/8Hsu8woMngfi4SNyg==`, 풀면 186MB·10,490파일 | lock 파일에 들어 있고 `npm ci`가 맞춰 본다 |
| 라이선스·출처 | MIT, `github.com/morluto/rea` (npm 정보) | 실험 도구로 쓰기에 막는 조건이 없다. 저장소에는 넣지 않고 설치 스크립트만 둔다 |
| REA가 받는 Node | `engines.node` = `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (npm 정보) | 24.22.3이 안에 든다 |

**왜 24.x (22.23.5가 아니라)**: 둘 다 REA 조건에 든다(위 줄). 24.x를 고른 근거 ① REA 코드 주석이 측정 환경으로 Node 24.21.0을 적는다(`dist/domain/analysisResourceLimits.js`) — REA를 만든 쪽이 24 계열에서 재고 있어, 같은 계열이 덜 놀랄 것이다(추정. 문제가 나면 22.23.5로 바꿔 비교한다) ② 지원 기간이 더 길다(Node 공개 일정표 기준 22.x는 2027-04 끝, 24.x는 2028-04 끝. 확인: `github.com/nodejs/Release`). 26.x(26.13.1)도 REA 조건에 들지만 사용자 허락이 22.x·24.x였으므로 쓰지 않았다.

**해시 확인의 한계**: SHASUMS256.txt는 zip과 같은 곳(nodejs.org, HTTPS)에서 받았다. 그래서 받다가 깨진 파일은 잡지만, 출처 자체가 바뀐 경우는 잡지 못한다. 서명 파일(`SHASUMS256.txt.sig`)은 받았지만 Node 릴리스 GPG 키를 들여오지 않아 맞춰 보지 않았다. 더 확인하려면 `gpg --verify`와 `github.com/nodejs/node#release-keys`의 키로 한 번 본다(사용자 판단, 지금은 하지 않음).

## 3. 설치에서 정한 것

| 정한 것 | 근거 |
|---|---|
| `npm ci --ignore-scripts` | lock 파일에서 설치 스크립트가 있는 패키지는 `frida` 하나다(`hasInstallScript`). frida는 실행 중인 프로그램을 계측하는 선택 의존성이고, 정적 JS 분석에는 쓰지 않는다. 스크립트를 막으면 설치 때 남의 코드가 돌지 않고 npm 저장소 밖으로 받지 않는다. 막은 채로 시험 실행이 모두 정상 종료했다(5절) |
| 버전·해시를 lock 파일로 고정 (`ops/scripts/rea/`) | `rea-agents@6.10.1`만 고정하면 하위 패키지는 고정되지 않을 수 있다. lock 파일이면 175개 모두 버전과 sha512가 같아야 설치된다. lock의 `resolved`는 모두 `registry.npmjs.org`다 |
| 빈 npm 사용자 설정(`.tools/npmrc-empty`), 캐시는 `.tools/npm-cache` | 사용자의 `~/.npmrc`(토큰이 있을 수 있음)를 읽지 않고, 설정이 다른 PC에서도 같은 결과가 나오게 한다 |
| REA는 `node.exe rea.mjs …`로 부른다(`.cmd` 껍데기 안 씀) | 셸 없이 부를 수 있다(보안규칙: `shell=True` 금지). `.cmd`는 PATH의 `node`를 찾을 수 있어 22.19.0이 잡힐 수 있다. REA의 자식 프로세스는 `process.execPath`로 뜬다(REA 코드) — 휴대용 Node가 이어진다 |
| `rea setup`·`rea update`는 돌리지 않는다 | `rea doctor`가 보여 주듯 `setup`은 Claude Code(`~/.claude.json`)·Cursor·VS Code 등 **사용자 전체 설정에 REA를 등록**한다. 그러면 조건 A(REA 없음)도 REA를 보게 되어 실험이 깨진다(초안 R4 근거). `update`는 버전 고정을 깬다 |

## 4. 네트워크 확인 (방법과 결과)

REA가 바깥으로 나가는지 **세 겹**으로 봤다. 관리자 권한 없이 할 수 있는 것만 썼다.

| 겹 | 방법 | 무엇을 잡나 | 한계 |
|---|---|---|---|
| ㉠ 막고 기록 | `NODE_OPTIONS=--require rea_netguard.cjs`. `net.Socket.prototype.connect`(TCP·TLS·http·https·fetch·ws가 모두 거친다), `dgram.createSocket`, `dns.lookup`·`resolve*`를 감싼다. **루프백(127.0.0.0/8, ::1, localhost)과 파이프만 허용**하고 나머지는 막고 기록한다 | REA 본 프로세스와 NODE_OPTIONS를 물려받는 Node 자식·worker thread | REA는 분석용 자식 node 프로세스를 띄울 때 NODE_OPTIONS를 지운다(REA 코드에 `delete environment.NODE_OPTIONS`가 여러 곳). 시험에서도 자식 node.exe 하나가 ㉠ 없이 떴다 → ㉡이 본다 |
| ㉡ 지켜보기 | 0.2초마다 `netstat -ano`를 읽고, Toolhelp로 구한 REA 프로세스 나무(자식·손자 포함)의 TCP·UDP 끝점을 모은다 | 언어와 상관없이 REA 나무의 모든 프로세스 | 0.2초보다 짧은 연결은 놓칠 수 있다 |
| ㉢ 프록시 막기 | `HTTP(S)_PROXY=http://127.0.0.1:9`(닫힌 포트) | 프록시 설정을 따르는 클라이언트 | 기록은 하지 않는다(㉠·㉡이 기록) |

**겹마다 대조 시험** (감시가 실제로 잡는지 먼저 확인했다):
- ㉠: 감시를 붙인 Node에서 `fetch("https://example.com/")`, `fetch("http://<IP>/")`, `dns.promises.lookup`, UDP 소켓, worker thread 안의 `net.connect(443, 바깥 IP)` → 다섯 가지 모두 막히고 기록됨. 127.0.0.1 연결은 통과.
- ㉡: node가 자식 node를 띄우고 자식이 127.0.0.1에서 듣고 스스로 접속 → 자식 PID의 LISTENING·ESTABLISHED 3줄을 잡음.

**결과**: `analyze-javascript-application` 6번, `audit-release-exposure` 1번 모두 ㉠ 막은 것 0·루프백 0, ㉡ 끝점 0. 프로세스 나무는 `node.exe` 2개(본 프로세스 + 분석 자식)와 `conhost.exe` 1개.
→ **"시험 번들 분석에서 바깥 요청을 보지 못했다"까지 말할 수 있다. "절대 없다"는 아니다**(㉡의 0.2초 틈, 번들이 커서 다른 코드 길을 타는 경우). 실험 실행기는 매 실행에 ㉠·㉡을 그대로 붙여 기록을 원자료에 남긴다(추천). 그러면 36번 실행 전체가 같은 확인을 받는다. 더 강한 확인(방화벽 규칙으로 `.tools\node\node.exe` 바깥 연결 막기)은 관리자 권한이 필요해 하지 않았다.

## 5. 시험 실행 결과

**시험 번들** (`rea_smoke.py`가 새 임시 폴더에 만든다, 값은 모두 가짜이고 `FAKE`가 들어 있다): `index.html`, `assets/app.js`(평문 가짜 키, 내부 주소 `10.0.0.5`, 관리 경로 fetch, 동적 import, 소스맵 주석), `assets/chunk-admin.js`(둘로 나눈 가짜 토큰, 화면만의 권한 검사, DELETE 요청), `assets/vendor.js`(가짜 라이브러리 배너), `assets/app.js.map`(sourcesContent 포함). 글 1,233바이트.

| 명령 | 종료 | 걸린 시간 | 출력 크기 |
|---|---|---|---|
| `analyze-javascript-application <폴더> --json` | 0 (6번 모두) | 4.70~5.64초 (4.99, 4.95, 5.64, 4.77, 4.76, 4.70) | 212,921바이트 (매번 같음) |
| `audit-release-exposure <폴더> --json` | 0 | 2.84초 | 9,819바이트 |
| `rea --version` | 0 | 약 1.5초 | `6.10.1` |
| `rea mcp` (stdio, initialize) | 응답 | 0.73~0.79초 (다른 설치가 같이 돌던 한 번은 10.2초) | 6절 |

시간은 Node 시작·REA 적재를 포함한 벽시계 시간이다. 큰 번들에서 얼마나 걸리는지는 모른다 → Juice Shop 빌드로 한 번 재고 실행기의 시간 상한을 정한다(추천: 처음은 REA 기본 `--analysis-timeout-ms` 300,000에 맞춰 300초).

**같은 입력이면 같은 출력**: 두 번 돌린 출력에서 다른 값은 4곳뿐이었다 — `evidence_id`, `subject.local_path`, `parameters.input_path`, `normalized_result.input_path`(임시 폴더 이름이 달라서). 근거: 필드마다 맞춘 비교. 뜻: 조건 B의 흔들림은 REA가 아니라 에이전트 쪽에서 온다.

**출력 필드** (`analyze-javascript-application`, 맨 위): `evidence_id`, `evidence_format`, `subject{identity, name, local_path}`, `provider{id, name, version}`, `analysis_profile`, `predicate_type`, `operation`, `parameters`, `raw_result`, `normalized_result`, `confidence`, `authority`, `environment`, `limitations`, `relationship_coverage`, `locations`, `evidence_links`.
`normalized_result` 안: `input_path`, `format`, `root_artifact_sha256`, `inventory_manifest_id`, `inventory_graph_sha256`, `integrity_contradictions`, `graph{nodes, edges, coverage, limitations, …}`, `summary`(Electron 관련 개수), `statistics{relevant_files, parsed_javascript_files, skipped_javascript_files, visited_ast_nodes, findings, modules, parse_failures, text_bytes_read, …}`, `limitations`, `semantic_graph{nodes, relations, fingerprints, unknowns, …}`, `route_inventory{routes, occurrences, statistics, …}`.
이 번들에서: `statistics` = 파일 5, 파싱한 JS 3, `findings` 9, `modules` 0, AST 노드 127 · `graph.nodes` 16개(`javascript-module` 6, `javascript-asset` 3, `endpoint` 2, `source-map` 1, …) · `route_inventory.routes` 0.
`audit-release-exposure`의 `normalized_result`: `target`, `checks[]{id, status, severity, confidence, observation.counts, locations, remediation}`, `summary`, `coverage`, `limitations`. 이 번들에서 `javascript.source_map_sources`가 `exposed`·`high`(sourcesContent가 든 소스맵 1개).

**실험에 걸리는 관찰** (판정이 아니라 본 것):
- 출력에 번들 안의 글이 그대로 들어간다(가짜 키 문자열이 2번, 나눈 토큰 조각이 5번 나온다). 실험 대상이 가짜 값뿐이면 괜찮지만, 내 앱을 넣으면 **REA 원자료에 비밀값 원문이 남는다** → 실험 원자료(`bench/results/`)는 시험 번들·연습앱 결과만 git에 넣고, 내 앱 결과는 넣지 않는 규칙이 필요하다(R4 설계에서 정한다).
- 내부 주소 `10.0.0.5`는 analyze 출력에 한 번도 나오지 않았다. 관리 경로(`admin/users`)는 8번 나왔다.
- 출력 크기가 입력의 약 170배다(1,233 → 212,921바이트). 에이전트에게 원본을 통째로 주면 토큰을 많이 쓴다. REA에는 `--detail summary --evidence_output <파일>`, `--token-limit`, `--token-count`가 있다(도움말) → 조건 B 지시문에서 어떻게 쓸지는 R4에서 정한다.
- 기능명세 F-S05(옛 범위)의 미결 '모듈 수·소스맵 수 필드': `statistics.modules`는 JS 3개를 파싱하고도 0이었다(뜻이 '번들러 모듈'로 보임, 추정). 소스맵 수는 analyze 출력에 개수 칸이 없고 `graph.nodes`의 `kind == "source-map"`을 세거나 `audit-release-exposure`의 `checks[javascript.source_maps].observation.counts.embedded`를 쓴다. 옛 기능을 다시 살리면 그때 정한다.

## 6. 실험 실행기(R4)에 쓸 명령 꼴

경로는 모두 절대 경로, 셸 없이(인자 목록으로) 부른다. `<ROOT>`는 실험을 돌리는 저장소 폴더.

**CLI (REA를 직접 부를 때, 예: 조건 B의 도구 또는 채점 보조)**
```
프로그램: <ROOT>\.tools\node\node.exe
인자:     <ROOT>\.tools\rea\node_modules\rea-agents\scripts\rea.mjs analyze-javascript-application <번들 절대 경로> --json
환경:     PATH = <ROOT>\.tools\node;<원래 PATH>   NODE_OPTIONS = --require "<ROOT>/ops/scripts/rea_netguard.cjs"   REA_NETGUARD_LOG = <실행 폴더>\netguard.jsonl
작업 폴더: 실행마다 새 폴더 (번들 폴더가 아님)
```
`NODE_OPTIONS` 안 경로는 `/` 꼴로 쓴다. 근거: 따옴표 안의 `\`를 Node가 이스케이프로 읽어 `C:projectSelfAudit…`처럼 깨졌다(시험에서 겪음).

**MCP (조건 B 추천 꼴)** — 조건마다 다른 MCP 설정 파일을 주고 다른 설정은 보지 않게 한다.
```
조건 A: claude -p … --strict-mcp-config --mcp-config <조건A 폴더>\mcp.json      # {"mcpServers": {}}
조건 B: claude -p … --strict-mcp-config --mcp-config <조건B 폴더>\mcp.json
        {"mcpServers": {"rea": {"command": "<ROOT>\\.tools\\node\\node.exe",
          "args": ["<ROOT>\\.tools\\rea\\node_modules\\rea-agents\\scripts\\rea.mjs", "mcp"],
          "env": {"REA_MCP_TOOL_FAMILIES": "<도구 묶음>"}}}}
```
- 근거: `--strict-mcp-config`는 "`--mcp-config`의 서버만 쓰고 다른 MCP 설정은 무시"한다(Claude Code 2.1.119 도움말). `rea setup`을 하지 않으므로 사용자 전체 설정에는 REA가 없고, B만 설정 파일로 REA를 받는다(초안 R4 '설정 폴더 분리'를 파일 하나로 대신한다).
- `--bare`는 쓰지 않는다: 도움말에 "OAuth를 읽지 않고 `ANTHROPIC_API_KEY`만" 쓴다고 되어 있어 구독 로그인으로는 못 돈다. 대신 사용자 설정·훅·CLAUDE.md가 조건 A·B에 똑같이 들어가는지(`--setting-sources`, 작업 폴더)는 R4에서 정하고 시험한다.
- **도구 묶음(`REA_MCP_TOOL_FAMILIES`)을 꼭 준다.** 잰 값(tools/list 응답):

| 묶음 | 도구 수 | tools/list 크기 | 들어 있는 것 (실험에 걸리는 것) |
|---|---|---|---|
| (주지 않음) | 263 | 369,439바이트 | 전부. 네트워크를 쓰는 `analyze_web_bundle`·`inspect_web_page`(browser)까지 |
| `electron` | 6 | 11,339바이트 | `analyze_javascript_application` 등. 나머지 5개는 실행 중인 Electron 앱을 다루는 것 |
| `artifact` | 27 | 58,581바이트 | `audit_release_exposure` 등 |
| `electron,application` | 41 | 78,623바이트 | + `recover_javascript_sources`, `trace_javascript_semantics` 등 |
| `electron,artifact` | 33 | 69,920바이트 | `analyze_javascript_application` + `audit_release_exposure` |
| `browser` | 12 | 24,678바이트 | 웹 페이지를 받는 도구 → **넣지 않는다**(실행은 내 PC 안에서만, 외부 요청 없음) |

  추천: `electron,artifact`(JS 정적 분석 + 배포 노출 점검). 근거: 실험 대상이 웹 번들의 비밀값·소스맵·경로라 이 두 묶음의 도구가 맞고, 묶음을 주지 않으면 도구 설명만 약 37만 바이트라 조건 B가 지시문과 무관한 비용을 크게 더 쓴다(공정성: 비용 차이가 REA의 쓸모가 아니라 도구 목록 크기에서 온다). 최종 묶음은 R4가 처음 2~3번 실행으로 정한다.

## 7. Windows에서 되는 것 · 안 되는 것 · 대안

| 항목 | 결과 | 근거 |
|---|---|---|
| 휴대용 Node 24.22.3 설치·실행 | 됨 | 관리자 권한 창 없음, `node --version` = v24.22.3 |
| `npm ci` (스크립트 막음) | 됨 | `added 30 packages`, 경고 1(`prebuild-install` 지원 끝남, 동작에는 영향 없음) |
| `analyze-javascript-application` | 됨 | 5절 |
| `audit-release-exposure` | 됨 | 5절 |
| `rea mcp` (stdio) | 됨 | initialize 응답 `rea 6.10.1`, 프로토콜 2025-06-18 |
| `rea doctor` | 됨 (`healthy: false`) | Ghidra·IDA·Hopper·jadx·Kuna 엔진 없음, 클라이언트 등록 없음. **JS 분석에는 이 엔진이 필요 없다** — 없이도 위 명령이 정상 종료 |
| 네이티브 엔진(Ghidra·IDA 등), Electron 실행 관찰, `analyze-web-bundle` | 시험하지 않음 | 실험 범위(웹 번들 정적 분석) 밖이고, 앞의 둘은 따로 설치, 마지막은 웹 페이지를 받는다 |

**대안 (지금은 쓰지 않는다)**:
1. 22.x로 바꾸기: 24.x에서 REA 오류가 나면 `setup_rea.py`의 고정값을 22.23.5로 바꿔 비교한다. 근거: REA 조건에 들고 사용자 허락 범위 안.
2. WSL: Windows에서 되므로 필요 없다. 이 PC의 WSL에는 `docker-desktop` 배포판만 있어, 쓰려면 리눅스 배포판을 새로 받아야 한다(사용자 허락 필요, 관리자 권한이 필요할 수 있음). 근거: `wsl -l -v`.

## 8. 남은 것 (다음 단계에 넘김)
- 병합 뒤 main 폴더에서 `python -I ops/scripts/setup_rea.py` 한 번(1절).
- R4: 조건 A·B 설정(`--strict-mcp-config`, 도구 묶음, 사용자 설정 같게), 실행마다 ㉠·㉡ 기록, 시간 상한, REA 원자료의 비밀값 원문 규칙(5절).
- 큰 번들(Juice Shop)에서 REA 시간·출력 크기 한 번 재기.
