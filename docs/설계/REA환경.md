# REA 실험 환경 (재설계 0단계)

작성 2026-11-21 · 고침 1 2026-11-22 · 주인: 설계 · 근거 문서: `ops/계획/재설계-초안.md` 5절 · 사용자 허락(2026-11-21, 채팅): "휴대용 Node로 설치"

> 결론: **REA 6.10.1은 이 PC(Windows 11, x64)에서 휴대용 Node 24.22.3으로 돈다.** `analyze-javascript-application`과 `audit-release-exposure`(CLI), `rea mcp`(MCP stdio)가 모두 정상 종료했고, 시험 실행 중 바깥 네트워크 연결은 **기록되지 않았다**(두 겹으로 기록, 덮는 범위와 한계는 4절). WSL은 지금 필요 없다(7절).
> 고침 1 (2026-11-22, 보안 검토 반려 1 `ops/검증/design-env-rea.md`): 감시 범위를 넓히고 한계를 적었다(4절), 조건 B 도구를 허용 목록으로 정했다(6절), REA·npm에 허용 목록 환경만 넘기고 설치에 상한을 두었다(3절), 내 앱 규칙(8절).
> 이 문서의 모든 숫자는 2026-11-21~22 밤 이 PC에서 잰 값이다. 추정인 것은 '추정'이라고 적고 확인 방법을 붙였다.

## 1. 다시 만드는 법

```
python -I ops/scripts/setup_rea.py          # .tools/node(휴대용 Node) + .tools/rea(rea-agents) 를 만든다
python -I ops/scripts/rea_smoke.py --out <요약 JSON 절대 경로> [--keep] [--operation audit-release-exposure]
.tools/node/node.exe --require ./ops/scripts/rea_netguard.cjs ops/scripts/rea_netguard_selftest.mjs   # 감시 자체 시험
```

- `setup_rea.py`는 이미 맞게 깔려 있으면 건너뛴다(node.exe sha256까지 맞춘다). 새로 깔면 Node zip 약 38MB와 npm 패키지를 받는다(처음 설치 237초, 빈 폴더에 `setup_rea.py`로 다시 깔기 348초, 같은 버전·해시로 끝남).
- **worktree에서 깐 `.tools/`는 worktree를 지우면 같이 사라진다.** 병합 뒤 실험을 돌릴 폴더(main)에서 `setup_rea.py`를 한 번 돌린다. 근거: `.tools/`는 git에 넣지 않으므로(용량 약 360MB: node 107MB, rea 208MB, npm 캐시 45MB) 폴더마다 따로 깔아야 한다.
- 관리자 권한, 시스템 PATH, 설치된 Node 22.19.0(`C:\Program Files\nodejs`)은 건드리지 않는다. 휴대용 Node는 REA를 부를 때 그 프로세스의 환경에서만 PATH에 둔다.

| 파일 | 하는 일 |
|---|---|
| `.gitignore` `.tools/` | 휴대용 Node·REA·npm 캐시를 git에 넣지 않는다 |
| `ops/scripts/setup_rea.py` | 받기(허용 주소·크기·시간 상한) → sha256 두 번 맞추기 → 안전하게 풀기 → `npm ci --ignore-scripts` → node.exe sha256·버전 확인 |
| `ops/scripts/rea/package.json`, `package-lock.json` | rea-agents 6.10.1과 하위 패키지의 버전을 고정한다. lock 항목 175개 중 30개는 자기 sha512로, 145개는 rea-agents 묶음 안에 든 것(`inBundle`)이라 묶음의 sha512로 확인된다 |
| `ops/scripts/rea_netguard.cjs` | Node 미리 읽기 파일. 바깥 TCP·UDP·이름 풀기·원격 파이프·UNC 경로를 기록하고, 보이는 것은 막는다 (4절) |
| `ops/scripts/rea_netguard_selftest.mjs` | 위 파일의 자체 시험 35개(감싼 길마다 하나, 허용 꼴 확인 포함) |
| `ops/scripts/rea_smoke.py` | 가짜 시험 번들을 만들고 REA를 셸 없이, 허용 목록 환경으로 돌려 시간·크기·필드·네트워크·디스크 쓰기를 요약한다 |

## 2. 버전과 해시

| 무엇 | 값 | 근거 |
|---|---|---|
| Node | **v24.22.3** (2026-11-10, LTS Krypton, 보안 릴리스), npm 11.19.1 | 아래 '왜 24.x' |
| Node zip | `node-v24.22.3-win-x64.zip` 37,762,649바이트, sha256 `e612af99f626ab415ea225af6bce5c971feb448cb5cae250bb1c3fa50c5f7d9f` | 받은 파일의 sha256 = `https://nodejs.org/dist/v24.22.3/SHASUMS256.txt`의 값(직접 맞춤). 스크립트에 크기와 함께 고정해 다음 설치에서 바뀌면 멈춘다 |
| node.exe | sha256 `86fc4785327db5f5c7558dc6156c543b433c313e813a222e088086222ab4afa6` | 이미 깔린 `.tools/node/node.exe`를 '이미 있음'으로 넘기기 전에 맞춘다. 버전 글(`--version`)만 보면 바뀐 실행 파일을 가르지 못한다 |
| rea-agents | **6.10.1** (`npm view rea-agents dist-tags.latest`, 2026-11-21 22시 기준. 패키지 마지막 수정 2026-11-20T06:52Z) | 실험 중 버전이 바뀌면 차이가 REA 때문인지 알 수 없다(요구사항 5.1) |
| rea-agents 묶음 | integrity `sha512-3AWrfFEXppvC98FWhZR2Tzulnqs5xJQrSKmAub6+QME/I58Pr3h8pHqqwM30z2DvlnIx/8Hsu8woMngfi4SNyg==`, 풀면 186MB·10,490파일 | lock 파일에 들어 있고 `npm ci`가 맞춰 본다 |
| 라이선스·출처 | rea-agents MIT, `github.com/morluto/rea` (npm 정보). lock 항목 176개(맨 위 포함) 중 MIT 131, ISC 15, Apache-2.0 10, BSD 계열 10 등. 눈여겨볼 것: `frida` LGPL-2.0 WITH WxWindows-exception-3.1, `openpgp` LGPL-3.0+, `commander` 라이선스 칸 없음 | 이 저장소는 REA와 하위 패키지를 **설치만 하고 배포하지 않는다**(`.tools/`는 git 제외, 저장소에는 설치 스크립트와 lock만). LGPL의 소스 제공·재링크 의무는 배포할 때 생기므로 지금은 걸리지 않는다. 결과물(R1~R6)에 REA 코드를 넣지 않는다. 배포하게 되면 다시 본다 |
| REA가 받는 Node | `engines.node` = `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (npm 정보) | 24.22.3이 안에 든다 |

**왜 24.x (22.23.5가 아니라)**: 둘 다 REA 조건에 든다(위 줄). 24.x를 고른 근거 ① REA 코드 주석이 측정 환경으로 Node 24.21.0을 적는다(`dist/domain/analysisResourceLimits.js`). REA를 만든 쪽이 24 계열에서 재고 있어 같은 계열이 덜 놀랄 것이다(추정. 문제가 나면 22.23.5로 바꿔 비교한다) ② 지원 기간이 더 길다(Node 공개 일정표 기준 22.x는 2027-04 끝, 24.x는 2028-04 끝. 확인: `github.com/nodejs/Release`). 26.x(26.13.1)도 REA 조건에 들지만 사용자 허락이 22.x·24.x였으므로 쓰지 않았다.

**해시 확인의 한계**: 처음 고정할 때(2026-11-21) SHASUMS256.txt는 zip과 같은 곳(nodejs.org, HTTPS)에서 받았다. 그래서 **그때** 출처 자체가 바뀌어 있었다면 잡지 못했다. 고정한 뒤의 설치는 스크립트의 고정 sha256·크기와 맞춰 보므로, 그 뒤에 출처가 바뀌면 멈춘다. 서명 파일(`SHASUMS256.txt.sig`)은 받았지만 Node 릴리스 GPG 키를 들여오지 않아 맞춰 보지 않았다. 처음 고정분까지 확인하려면 `gpg --verify`와 `github.com/nodejs/node#release-keys`의 키로 한 번 본다(사용자 판단, 지금은 하지 않음).

## 3. 설치에서 정한 것

| 정한 것 | 근거 |
|---|---|
| `npm ci --ignore-scripts` | lock 파일에서 설치 스크립트가 있는 패키지는 `frida` 하나다(`hasInstallScript`). frida는 실행 중인 프로그램을 계측하는 선택 의존성이고, 정적 JS 분석에는 쓰지 않는다. 스크립트를 막으면 설치 때 남의 코드가 돌지 않고 npm 저장소 밖으로 받지 않는다. 막은 채로 시험 실행이 모두 정상 종료했다(5절) |
| 버전·해시를 lock 파일로 고정 (`ops/scripts/rea/`) | `rea-agents@6.10.1`만 고정하면 하위 패키지는 고정되지 않을 수 있다. lock 파일이면 따로 받는 30개는 자기 sha512가, 묶음 안 145개(`inBundle`)는 rea-agents 묶음의 sha512가 같아야 설치된다. lock의 `resolved`는 모두 `registry.npmjs.org`다 |
| 빈 npm 사용자 설정(`.tools/npmrc-empty`), 캐시는 `.tools/npm-cache` | 사용자의 `~/.npmrc`(토큰이 있을 수 있음)를 읽지 않고, 설정이 다른 PC에서도 같은 결과가 나오게 한다 |
| npm·REA에 **허용 목록 환경**만 넘긴다 (`setup_rea.py`·`rea_smoke.py`의 `ENV_PASS`) | 사용자 환경 전체를 넘기면 `NPM_TOKEN`·`GITHUB_TOKEN`·API 키 같은 변수가 REA와 그 자식에게 간다. 넘기는 것은 Windows에서 프로세스를 띄우는 데 필요한 것(SystemRoot·ComSpec·PATHEXT 등), 임시·홈 폴더, 새로 만든 PATH(휴대용 Node + System32)뿐이다. `rea_smoke.py`는 홈·APPDATA·TEMP도 새 빈 폴더로 돌린다(5절 '디스크 쓰기') |
| 받기 상한 (`setup_rea.py`) | 허용 주소는 `https://nodejs.org/dist/`뿐이고 **리디렉트도 그 안으로만** 따라간다. zip은 고정 크기(37,762,649바이트)와 정확히 같아야 하고 SHASUMS는 64KB 안(실제 3,171바이트). 소켓 읽기 60초, 받기 전체 600초, `npm ci` 1,800초. 근거: 이 PC에서 zip 받기 1.8초, `npm ci` 237초·348초(두 번 잼). 600초는 38MB를 약 0.5Mbps에서도 받는 시간, 1,800초는 잰 가장 긴 값의 약 5배다(추정 — 느린 날에도 멈추지 않을 만큼, 그러나 끝없이 기다리지는 않게. 넘으면 다시 돌리면 이미 맞은 단계를 건너뛴다). 허용 밖 주소·크기가 다른 파일은 받기를 거부하는 것을 시험했다 |
| REA는 `node.exe rea.mjs …`로 부른다(`.cmd` 껍데기 안 씀) | 셸 없이 부를 수 있다(보안규칙: `shell=True` 금지). `.cmd`는 PATH의 `node`를 찾을 수 있어 22.19.0이 잡힐 수 있다. REA의 자식 프로세스는 `process.execPath`로 뜬다(REA 코드) — 휴대용 Node가 이어진다 |
| `rea setup`·`rea update`는 돌리지 않는다 | `rea doctor`가 보여 주듯 `setup`은 Claude Code(`~/.claude.json`)·Cursor·VS Code 등 **사용자 전체 설정에 REA를 등록**한다. 그러면 조건 A(REA 없음)도 REA를 보게 되어 실험이 깨진다(요구사항 R4 근거). `update`는 버전 고정을 깬다 |

## 4. 네트워크 기록 (방법 · 덮는 범위 · 한계 · 결과)

REA가 바깥으로 나가는지 **두 겹으로 기록**했다(셋째 겹은 기록 없이 막기만 한다). 관리자 권한 없이 할 수 있는 것만 썼다. **이것은 차단 장치가 아니라 기록 장치다** — ㉠이 보는 길은 막지만, ㉠이 못 보는 길(아래 한계)은 ㉡이 기록만 한다. 실제로 막으려면 방화벽 규칙이 필요하다(아래, 사용자 확인).

| 겹 | 방법 | 덮는 것 |
|---|---|---|
| ㉠ 프로세스 안 기록 (보이면 막음) | `NODE_OPTIONS=--require rea_netguard.cjs`. 허용 꼴만 통과: 루프백(127.0.0.0/8, ::1, localhost), 로컬 파이프(`\\.\pipe\`·`\\?\pipe\`), 로컬 파일 경로(드라이브·상대·`\\?\C:\` 꼴). 나머지는 기록하고 막는다 | 이 파일을 읽은 Node 프로세스와 그 worker thread의 JS 코드 |
| ㉡ 프로세스 밖 기록 | `POLL_S`(0.2)초마다 `netstat -ano`를 읽고, Toolhelp로 구한 REA 프로세스 나무의 TCP·UDP 끝점을 모은다. 0.2초 근거: `netstat -ano` 한 번이 이 PC에서 0.04~0.07초(5번 잼)라 한 코어의 약 20~35%만 쓴다. 더 짧으면 감시가 분석 시간을 늘리고, 더 길면 놓치는 짧은 연결이 는다 | REA 나무의 모든 프로세스(언어 무관), 폴링 순간에 열려 있던 끝점 |
| ㉢ 프록시 | `HTTP(S)_PROXY=http://127.0.0.1:9`(닫힌 포트) | 프록시 설정을 따르는 클라이언트. 기록은 없다 |

**㉠이 감싼 것** (자체 시험 `rea_netguard_selftest.mjs` 35개가 하나씩 확인. 바깥 주소는 RFC 5737 문서용 주소 192.0.2.1과 RFC 2606 `.invalid` 이름이라 감시가 뚫려도 실제 기기에 닿지 않는다):

| 길 | 감싼 함수 | 시험 |
|---|---|---|
| TCP·TLS·http·https·fetch·ws | `net.Socket.prototype.connect` (모두 이것을 거친다) | fetch 바깥 IP, net.connect, worker thread 안 net.connect → 막힘 · 루프백 → 통과 |
| UDP·QUIC | `dgram.createSocket` (만들기부터 막음) | 막힘 |
| 이름 풀기 | `dns`·`dns.promises`의 **통과 목록 밖 모든 함수**(lookup, lookupService, resolve, resolve4·6·Any·Caa·Cname·Mx·Naptr·Ns·Ptr·Soa·Srv·Tlsa·Txt, reverse …)와 `dns.Resolver`·`dns.promises.Resolver`의 메서드. 통과 목록은 이름을 풀지 않는 설정 함수뿐: getServers·setServers·setDefaultResultOrder·getDefaultResultOrder·setLocalAddress·cancel | lookup, resolveMx·Txt·Soa, lookupService, reverse, Resolver.resolve4, promises.Resolver.resolveNs, ESM 이름 가져오기, `util.promisify(dns.lookup)`, `node:dns/promises` 동적 가져오기 → 모두 막힘 |
| 파이프 | `connect({path})` — 로컬 파이프만 허용하고, **이름 쪽 마디에 `.`·`..`·빈 마디가 있으면 막음**. `\\호스트\pipe\…`는 SMB로 다른 기기에 붙으므로 막음 | 원격 파이프 막힘, 로컬 파이프 통과, `\\.\pipe\..\UNC\…`·`\\.\pipe\..\GLOBALROOT\…`·`\\?\pipe\.\x` 막힘 |
| UNC 파일 | `fs`·`fs.promises`의 경로 받는 함수(앞 두 인자, 글·Buffer·Uint8Array·URL·URL 비슷한 객체). `\\호스트\공유`, `//호스트/`, `\\?\UNC\…`, `file://호스트/`, 그리고 `.`·`..` 마디가 든 장치 경로(`\\.\C:\..\UNC\…`) 막음 | 꼴마다 막힘, 로컬 파일·`\\?\C:\` 꼴 통과, `fs.realpathSync.native` 같은 덧붙은 속성 유지 |
| 우회 | `process.binding('tcp_wrap'·'udp_wrap'·'pipe_wrap'·'tls_wrap'·'cares_wrap'·'stream_wrap'·'js_stream'·'fs'·'fs_dir')` | 막힘 |

장치 경로를 마디로 보는 근거(반려 2): Win32는 `\\.\` 경로의 `..`를 풀어 `\\.\UNC\`·`\\.\GLOBALROOT\`로 옮길 수 있어, 앞부분(`\\.\pipe\`)만 맞추는 정규식은 우회된다. 허용 꼴을 '앞부분'이 아니라 '모든 마디'로 정한다.
| ESM | 감싼 뒤 `module.syncBuiltinESMExports()` — `import { lookup } from "node:dns"`도 감싼 함수를 본다 | 위 ESM 시험 |

**한계 (두 겹이 덮지 못하는 것)**

| # | 한계 | 무엇이 남나 | 이 실험에서 |
|---|---|---|---|
| ① | REA는 분석용 자식 node를 띄울 때 NODE_OPTIONS를 지운다(REA 코드에 `delete environment.NODE_OPTIONS` 여러 곳). 시험에서도 node.exe 2개 중 1개만 ㉠을 읽었다 | 그 자식의 연결은 ㉡만 기록하고 막지 못한다 | ㉡ 기록 0 |
| ② | DNS 질의는 Windows DNS 클라이언트 서비스(svchost)가 대신 보낸다 | ㉠ 밖에서 푼 이름 질의는 REA 나무에 보이지 않는다. 나가는 것은 이름뿐이고, 내용을 보내려면 연결이 필요하다(①·㉡이 기록) | 확인할 방법 없음(관리자 권한 필요) |
| ③ | ㉠이 읽히기 전에 잡아 둔 함수 참조, 네이티브 애드온(C++)이 여는 소켓, Node가 아닌 자식 프로그램 | ㉡만 기록 | ㉡ 기록 0 |
| ④ | `process.binding`은 막았지만 Node 안쪽 `internalBinding`, `--expose-internals` 같은 길 | ㉡만 기록 | REA `dist`·`scripts`에서 `internalBinding`·`expose-internals`·`process.binding(`을 찾았고 0곳(하위 패키지 node_modules는 찾지 않음) |
| ⑤ | ㉡은 폴링이라 0.2초보다 짧게 열렸다 닫힌 연결, 폴링 사이에 TIME_WAIT로 넘어간 연결, 폴링 사이에 떴다 사라진 손자 프로세스를 놓칠 수 있다. SMB(UNC)는 커널(PID 4)이 맺어 REA 나무에 안 보인다 | 기록 누락 | UNC 길은 아래 '소스맵 확인'으로 따로 봄 |

**소스맵 확인 (UNC 길)**: REA가 `.map`의 `sources`를 디스크에서 따라 읽으면, 원격 경로가 든 소스맵 하나로 SMB 연결이 생길 수 있다(⑤). 그래서 시험 번들에 `sourcesContent` 없는 `ext.js.map`을 넣고 `sources`에 ㉮ 번들 밖 상대 경로 ㉯ 번들 밖 절대 경로(둘 다 표식 글이 든 파일) ㉰ `\\192.0.2.1\share\x.ts`를 적었다. 결과: 표식 글이 출력에 **나오지 않았다**(analyze·audit 모두) → REA 6.10.1은 이 번들에서 sources를 디스크에서 따라 읽지 않았다. ㉰는 analyze 출력에 글로만 나온다(데이터). ㉠ 기록에 UNC 시도 0.

**실제로 막는 방법 (사용자 확인 — 관리자 권한)**: Windows 방화벽에 휴대용 node.exe의 바깥 연결을 막는 규칙을 둔다. 같은 node.exe를 쓰는 분석 자식(①)과 네이티브 연결(③)까지 막힌다. 루프백은 Windows 방화벽이 거르지 않으므로 MCP stdio·로컬 파이프는 그대로 된다(추정 — 규칙을 둔 뒤 `rea_smoke.py`가 정상 종료하는지로 확인).
```
# 관리자 PowerShell에서, 설치를 끝낸 뒤 (npm ci도 이 node.exe로 돌아 함께 막힌다)
New-NetFirewallRule -DisplayName "SelfAudit REA node 바깥 막기" -Direction Outbound -Action Block -Program "<ROOT>\.tools\node\node.exe"
# 다시 설치할 때 잠깐 끄기 / 지우기
Disable-NetFirewallRule -DisplayName "SelfAudit REA node 바깥 막기"
Remove-NetFirewallRule  -DisplayName "SelfAudit REA node 바깥 막기"
```
이 규칙도 덮지 못하는 것: ② svchost DNS 질의, ⑤ 커널 SMB. 근거: 프로그램 규칙은 그 실행 파일이 연 연결에만 걸린다. 규칙을 두면 실행기가 실행마다 `Get-NetFirewallRule`로 켜져 있는지 원자료에 기록한다(추천).

**결과**: `analyze-javascript-application` 10번(옛 번들 6번 + 소스맵 확인 번들 4번), `audit-release-exposure` 2번 모두 ㉠ 기록 0(막은 것 0·루프백 0), ㉡ 끝점 0. 프로세스 나무는 `node.exe` 2개(본 프로세스 + 분석 자식, audit은 1개)와 `conhost.exe` 1개.
→ 말할 수 있는 것: **"시험 번들 분석에서 바깥 연결이 기록되지 않았다(㉠·㉡)."** 말할 수 없는 것: "바깥 연결이 없다" — 한계 ①~⑤ 때문. 실험 실행기는 매 실행에 ㉠·㉡을 붙여 기록을 원자료에 남긴다. 그러면 36번 실행 전체가 같은 확인을 받는다.

## 5. 시험 실행 결과

**시험 번들** (`rea_smoke.py`가 새 임시 폴더에 만든다, 값은 모두 가짜이고 `FAKE`가 들어 있다): `index.html`, `assets/app.js`(평문 가짜 키, 내부 주소 `10.0.0.5`, 관리 경로 fetch, 동적 import, 소스맵 주석), `assets/chunk-admin.js`(둘로 나눈 가짜 토큰, 화면만의 권한 검사, DELETE 요청), `assets/vendor.js`(가짜 라이브러리 배너), `assets/app.js.map`(sourcesContent 포함). 글 1,233바이트. 2026-11-22부터 `assets/ext.js`·`ext.js.map`(4절 소스맵 확인)이 더해졌다.

| 명령 | 종료 | 걸린 시간 | 출력 크기 |
|---|---|---|---|
| `analyze-javascript-application <폴더> --json` (옛 번들) | 0 (6번 모두) | 4.70~5.64초 (4.99, 4.95, 5.64, 4.77, 4.76, 4.70) | 212,921바이트 (매번 같음) |
| 같은 명령 (소스맵 확인 번들, 허용 목록 환경) | 0 (4번 모두) | 3.63, 3.65, 4.30, 28.75초 | 243,050바이트 (매번 같음) |
| `audit-release-exposure <폴더> --json` | 0 | 2.84초 (옛 번들), 2.2초 (새 번들) | 9,819 / 10,014바이트 |
| `rea --version` | 0 | 약 1.5초 | `6.10.1` |
| `rea mcp` (stdio, initialize) | 응답 | 0.73~0.79초 (다른 설치가 같이 돌던 한 번은 10.2초) | 6절 |

28.75초는 한 번뿐이고 바로 다시 돌리면 3.6초였다. 처음 보는 파일을 백신이 검사하는 등 바깥 요인으로 보인다(추정 — 실행기 원자료에서 첫 실행만 느린지로 확인). 시간은 Node 시작·REA 적재를 포함한 벽시계 시간이다. 큰 번들에서 얼마나 걸리는지는 모른다 → Juice Shop 빌드로 한 번 재고 실행기의 시간 상한을 정한다.

**같은 입력이면 같은 출력**: 두 번 돌린 출력에서 다른 값은 4곳뿐이었다 — `evidence_id`, `subject.local_path`, `parameters.input_path`, `normalized_result.input_path`(임시 폴더 이름이 달라서). 근거: 필드마다 맞춘 비교. 뜻: 조건 B의 흔들림은 REA가 아니라 에이전트 쪽에서 온다.

**출력 필드** (`analyze-javascript-application`, 맨 위): `evidence_id`, `evidence_format`, `subject{identity, name, local_path}`, `provider{id, name, version}`, `analysis_profile`, `predicate_type`, `operation`, `parameters`, `raw_result`, `normalized_result`, `confidence`, `authority`, `environment`, `limitations`, `relationship_coverage`, `locations`, `evidence_links`.
`normalized_result` 안: `input_path`, `format`, `root_artifact_sha256`, `inventory_manifest_id`, `inventory_graph_sha256`, `integrity_contradictions`, `graph{nodes, edges, coverage, limitations, …}`, `summary`(Electron 관련 개수), `statistics{relevant_files, parsed_javascript_files, skipped_javascript_files, visited_ast_nodes, findings, modules, parse_failures, text_bytes_read, …}`, `limitations`, `semantic_graph{nodes, relations, fingerprints, unknowns, …}`, `route_inventory{routes, occurrences, statistics, …}`.
옛 번들에서: `statistics` = 파일 5, 파싱한 JS 3, `findings` 9, `modules` 0, AST 노드 127 · `graph.nodes` 16개(`javascript-module` 6, `javascript-asset` 3, `endpoint` 2, `source-map` 1, …) · `route_inventory.routes` 0.
`audit-release-exposure`의 `normalized_result`: `target`, `checks[]{id, status, severity, confidence, observation.counts, locations, remediation}`, `summary`, `coverage`, `limitations`. 옛 번들에서 `javascript.source_map_sources`가 `exposed`·`high`(sourcesContent가 든 소스맵 1개).

**실험에 걸리는 관찰** (판정이 아니라 본 것):
- 출력에 번들 안의 글이 그대로 들어간다(가짜 키 문자열이 2번, 나눈 토큰 조각이 5번 나온다). 내 앱을 넣으면 **REA 원자료에 비밀값 원문이 남는다** → 8절 규칙.
- 내부 주소 `10.0.0.5`는 analyze 출력에 한 번도 나오지 않았다. 관리 경로(`admin/users`)는 8번 나왔다.
- 출력 크기가 입력의 약 170배다(1,233 → 212,921바이트). 에이전트에게 원본을 통째로 주면 토큰을 많이 쓴다. REA에는 `--detail summary --evidence_output <파일>`, `--token-limit`, `--token-count`가 있다(도움말) → 조건 B에서 어떻게 쓸지는 R4에서 정한다.
- **디스크 쓰기**: 홈(`USERPROFILE`·`HOME`)·`APPDATA`·`LOCALAPPDATA`·`TEMP`를 새 빈 폴더로 돌리고 돌린 결과, REA는 그 폴더들에 **아무 파일도 쓰지 않았다**(analyze·audit 모두). 처음 시험들(진짜 환경으로 돌림) 뒤에도 진짜 `%APPDATA%`·`%LOCALAPPDATA%`·홈 아래 두 단계 안에 REA 이름의 새 폴더는 없었다(`find -newermt`로 확인. 남은 것은 시험이 만든 `Temp\rea-smoke-*`뿐이었고 지웠다).
- 기능명세 F-S05(옛 범위)의 미결 '모듈 수·소스맵 수 필드': `statistics.modules`는 JS 3개를 파싱하고도 0이었다(뜻이 '번들러 모듈'로 보임, 추정). 소스맵 수는 analyze 출력에 개수 칸이 없고 `graph.nodes`의 `kind == "source-map"`을 세거나 `audit-release-exposure`의 `checks[javascript.source_maps].observation.counts.embedded`를 쓴다.

## 6. 실험 실행기(R4)에 쓸 명령 꼴

경로는 모두 절대 경로, 셸 없이(인자 목록으로) 부른다. `<ROOT>`는 실험을 돌리는 저장소 폴더. 실행기의 나머지(설정 폴더, 같은 지시문·모델, 비용 재기)는 `docs/설계/실험구조.md` 3절.

**CLI (REA를 직접 부를 때, 예: 채점 보조)**
```
프로그램: <ROOT>\.tools\node\node.exe
인자:     <ROOT>\.tools\rea\node_modules\rea-agents\scripts\rea.mjs analyze-javascript-application <번들 절대 경로> --json
환경:     허용 목록(rea_smoke.py ENV_PASS) + PATH=<ROOT>\.tools\node;<SystemRoot>\System32;<SystemRoot>
          NODE_OPTIONS=--require "<ROOT>/ops/scripts/rea_netguard.cjs"   REA_NETGUARD_LOG=<실행 폴더>\netguard.jsonl
          USERPROFILE·HOME·APPDATA·LOCALAPPDATA·TEMP·TMP = 실행 폴더 안 빈 폴더
작업 폴더: 실행마다 새 폴더 (번들 폴더가 아님)
```
`NODE_OPTIONS` 안 경로는 `/` 꼴로 쓴다. 근거: 따옴표 안의 `\`를 Node가 이스케이프로 읽어 `C:projectSelfAudit…`처럼 깨졌다(시험에서 겪음).

**MCP (조건 B)** — 조건마다 다른 MCP 설정 파일을 주고 다른 MCP 설정은 보지 않게 한다.
```
조건 A: claude -p … --strict-mcp-config --mcp-config <A 폴더>\mcp.json      # {"mcpServers": {}}
조건 B: claude -p … --strict-mcp-config --mcp-config <B 폴더>\mcp.json
  {"mcpServers": {"rea": {
     "command": "<bench 파이썬 절대 경로>",
     "args": ["-I", "<ROOT>\\bench\\run\\rea_mcp_filter.py",
              "--allow", "analyze_javascript_application,audit_release_exposure,trace_javascript_semantics,trace_application_feature",
              "--netguard-log", "<실행 폴더>\\netguard.jsonl",
              "--", "<ROOT>\\.tools\\node\\node.exe", "<ROOT>\\.tools\\rea\\node_modules\\rea-agents\\scripts\\rea.mjs", "mcp"],
     "env": {"REA_MCP_TOOL_FAMILIES": "electron,artifact,application"}}}}
```
- `rea_mcp_filter.py`(MCP 거르개, F-R04가 만든다): Claude Code와 REA 사이에서 stdio를 잇는 작은 표준 라이브러리 프로그램. ⑴ REA를 **허용 목록 환경**으로, **작업 폴더 = 그 실행의 target**으로 띄우고 ㉠(`NODE_OPTIONS`·`REA_NETGUARD_LOG`)과 빈 홈·TEMP 폴더를 넣는다 ⑵ `tools/list` 응답에서 허용 4개만 남긴다 ⑶ 허용 밖 `tools/call`은 REA에 보내지 않고 오류로 돌려준다 **⑷ 허용 도구의 인자도 허용 꼴만 보낸다** (아래 '인자 거르기'). ㉡(netstat)은 실행기가 `<ROOT>\.tools\node\node.exe` 이미지인 프로세스와 그 자손에 감싼다(Claude Code 자신의 Anthropic API 연결은 실험의 일부라 REA 기록에서 뺀다).
- **인자 거르기 ⑷ (반려 2, 높음)**: 도구 이름만 거르면 `analyze_javascript_application`의 `input_path`·`audit_release_exposure`의 `path`(파일을 주면 부모 폴더 목록까지 읽음)에 PC의 아무 경로나 넣을 수 있다. 그러면 조건 B만 `bench/sources/`(심은 곳)·저장소·다른 실행 결과·내 앱 원자료를 REA로 읽어 실험이 비대칭이 되고, 내 앱 비밀값이 git에 넣는 대화 기록으로 간다. 그래서:
  1. 도구마다 **받는 인자 이름 허용 목록**(아래 표)을 두고, 그 밖의 인자가 하나라도 있으면 오류.
  2. **경로 칸**(`input_path`, `path`)은 이 꼴만 받는다: 드라이브 문자 절대 경로(`C:\…`)나 target 기준 상대 경로, 또는 `\\?\C:\…`(앞 4자를 떼고 본다). UNC(`\\호스트\…`, `\\?\UNC\…`), 그 밖의 장치 경로(`\\.\…`), 드라이브 상대(`C:x`), 드라이브 뒤의 `:`(ADS), NUL 글자는 거절. 그다음 `os.path.realpath(…, strict=True)`로 정션·심볼릭 링크·8.3 짧은 이름·`..`을 모두 푼 경로가 **같은 방법으로 푼 target과 같거나 그 아래**(`normcase` 뒤 `target + "\"`로 시작)일 때만 보낸다. 없는 경로·풀 수 없는 경로는 거절. `audit_release_exposure`의 `path`가 파일이면 그 부모도 target 안이어야 한다(부모 목록을 읽으므로).
  3. `source_paths`(배열)는 target 기준 상대 경로 글만, 각각 2번과 같이 풀어 target 안. 
  4. trace 두 도구의 `application`은 **같은 세션의 참조만** 받는다(그 안에 경로 꼴 글이 있으면 거절). 참조의 정확한 꼴은 F-R04 첫 시험에서 REA 응답으로 정하고 그 키만 허용한다. 근거: 넣은 Evidence(inline)는 `subject.local_path` 같은 경로를 실어 나를 수 있다.
  5. 모든 인자의 글 값을 훑어, 경로 꼴(드라이브 문자로 시작, `\\`·`//`로 시작, `file:`, `..` 마디)인 글은 2번을 통과해야 한다 — 1~4가 놓친 칸의 그물.
  - 시제품 측정 (2026-11-22, scratchpad, 관리자 권한 없이): target 안 상대·절대·`\\?\`·8.3 짧은 이름·target 자신·`안/../안` → 허용 / `..`로 밖, 밖 절대, 저장소 절대(`C:\project\SelfAudit\CLAUDE.md`), **target 안 정션이 밖을 가리킴**, `\\?\` 밖, `\\?\UNC`, UNC, `\\.\C:\…` 밖, 8.3 밖, ADS, `/` 꼴 밖, 없는 파일, `C:x`, `target2`(이름 앞부분만 같은 형제) → 모두 거절. 심볼릭 링크는 이 PC에서 관리자 권한·개발자 모드 없이 만들 수 없어 재지 못했다(realpath가 정션과 같이 푼다 — 추정, F-R04 시험에서 개발자 모드가 켜진 환경이면 넣는다).
  - **F-R04 시험 꼴** (명세 예시로 옮긴다): 위 목록 전부 + `source_paths`에 `../x`, 인자 목록 밖의 키(`evidence_output` 등), trace `application`에 inline Evidence.
- 근거: `--strict-mcp-config`는 "`--mcp-config`의 서버만 쓰고 다른 MCP 설정은 무시"한다(Claude Code 2.1.119 도움말). `rea setup`을 하지 않으므로 사용자 전체 설정에는 REA가 없고, B만 설정 파일로 REA를 받는다. Claude Code가 MCP 서버에 자기 환경을 얼마나 물려주는지는 확인하지 않았다(추정: 물려준다) — 그래서 거르개가 REA 환경을 새로 만든다.
- `--bare`는 쓰지 않는다: 도움말에 "OAuth를 읽지 않고 `ANTHROPIC_API_KEY`만" 쓴다고 되어 있어 구독 로그인으로는 못 돈다.

**조건 B에 허용하는 REA 도구 (허용 목록) [사용자 확인]** — `electron`·`artifact`·`application` 세 묶음 68개를 하나씩 보고, 웹 번들 정적 분석에 쓰는 것만 남겼다. 허용 넷의 '경로를 받는 칸'과 REA가 붙인 표시(MCP annotations)도 적었다:

| 허용 | 도구 | 받는 인자 (허용 목록) · 경로 칸 | REA 표시 | 근거 |
|---|---|---|---|---|
| 예 | `analyze_javascript_application` | `input_path`(**경로**, 필수), `source_paths`(**경로 배열**), `format`, `integrity_policy`, `semantic_precision`, `max_semantic_nodes`·`max_semantic_nodes_per_file`·`max_semantic_unknowns`·`max_semantic_unknowns_per_file`, `max_heap_mb`, `analysis_timeout_ms`, `detail`, `view` | readOnly 아님·openWorld | 웹 번들 폴더를 실행하지 않고 정적 그래프로 만든다(5절에서 시험). 질문 1의 핵심 도구 |
| 예 | `audit_release_exposure` | `path`(**경로**, 필수 — 파일이면 부모 폴더 목록도 읽음), `max_file_bytes` | readOnly 아님·openWorld | 배포물의 소스맵·sourcesContent 노출을 점검한다(5절에서 시험). 시험 번들의 '소스맵' 문제와 맞다 |
| 예 | `trace_javascript_semantics` | `application`(객체 — 같은 세션 참조만), `query` | readOnly 아님·openWorld 아님 | 위 그래프에서 데이터 흐름·호출을 따라간다. 나눠 쓴·숨긴 비밀값(어려움 단계)을 찾는 데 REA다운 쓸모가 있다 |
| 예 | `trace_application_feature` | `application`(같은 세션 참조만), `seed`, `direction`, `semantic_page`, `view`, `native_observations` | readOnly 아님·openWorld 아님 | 같은 그래프에서 글자 씨앗(예: 경로 글)을 따라간다. 숨은 API 라우트·권한 검사 찾기에 쓴다 |

REA 표시가 넷 모두 `readOnlyHint: false`이고 앞의 둘은 `openWorldHint: true`라, 표시만으로는 '쓰지 않는다·밖을 보지 않는다'를 믿을 수 없다. 그래서 **MCP 모드에서 디스크 쓰기를 직접 쟀다**(2026-11-22, 가짜 번들, 홈·APPDATA·LOCALAPPDATA·TEMP를 빈 폴더로, 작업 폴더 = 번들): `analyze_javascript_application`(7.9초, 응답 522,802바이트)·`audit_release_exposure`를 부른 뒤 실행 폴더 전체(번들·홈·TEMP)에 **새로 생기거나 바뀐 파일 0개**(㉠ 기록 파일만). ㉠ 기록에 바깥 시도 0. 경로 밖으로 나가는 것은 ⑷가 막는다.
- 관찰: MCP 응답이 CLI 출력(212~243KB)보다 크다(본문 글과 `structuredContent`가 같이 온다, 추정). 조건 B의 비용에 바로 들어가므로 보정 실행(`실험구조.md` 3.5)에서 잰다.
| 아니오 | `list_electron_targets`, `inspect_electron_page`, `reconcile_javascript_runtime`, `capture_electron_scenario` | **실행 중인 Electron 앱**(CDP 연결)을 다루거나 앱을 띄운다(`capture_electron_scenario`는 destructiveHint). 실험 대상은 실행하지 않는 웹 빌드 결과물이다(요구사항 5.1) |
| 아니오 | `inspect_electron_fuses` | Electron 실행 파일 전용. 웹 번들에는 없다 |
| 아니오 | `extract_artifact`, `export_web_scripts`, `recover_javascript_sources` | 출력 폴더에 파일을 쓴다. 마지막은 Linux·Wakaru가 필요해 Windows에서 못 돈다(도구 설명) |
| 아니오 | `trace_web_source_location`, `trace_web_module_imports` | 웹 캡처(`export_web_scripts` 결과)를 입력으로 받는다. 실험에는 캡처가 없다 |
| 아니오 | 나머지 54개 (Apple·Go·Rust·EVM·WASM·APK·.pyc·NuGet·BEAM·Maven·SQLite·패킷·신호·GPU·모델 파일, 빌드 컴퓨터, 비교·설정 도구 등) | 웹 번들과 다른 형식이다. 쓸 일이 없는 도구를 주면 도구 설명만큼 비용이 늘고 에이전트가 헛짚을 길이 는다 |

잰 크기: 세 묶음 68개의 tools/list는 137,204바이트, 허용 4개만이면 8,249바이트.
**두 층에서 거른다**: ⑴ MCP 거르개가 허용 4개만 보이고 부른다 ⑵ Claude Code `--permission-mode dontAsk --allowedTools "Read(./**) Grep(./**) Glob(./**) mcp__rea__analyze_javascript_application …(4개)"`로 허용 목록 밖은 묻지 않고 거절한다(`실험구조.md` 3.3). 근거: 허용 꼴만 통과시키는 것을 두 층에 두면 한 층의 설정이 틀려도 다른 층이 막는다. 거르개는 도구 설명 비용도 137KB → 8KB로 줄인다(조건 B의 비용이 REA의 쓸모가 아니라 도구 목록 크기 때문에 커지지 않게).

| 묶음 (참고, 거르개 없이) | 도구 수 | tools/list 크기 | 들어 있는 것 |
|---|---|---|---|
| (주지 않음) | 263 | 369,439바이트 | 전부. 네트워크를 쓰는 `analyze_web_bundle`·`inspect_web_page`(browser)까지 |
| `electron` | 6 | 11,339바이트 | `analyze_javascript_application` + 실행 중 Electron 도구 5개 |
| `artifact` | 27 | 58,581바이트 | `audit_release_exposure` 등 |
| `application` | 35 | 67,284바이트 | `trace_javascript_semantics`·`trace_application_feature` 등 |
| `electron,artifact,application` | 68 | 137,204바이트 | 위 셋 |
| `browser` | 12 | 24,678바이트 | 웹 페이지를 받는 도구 → **넣지 않는다** |

## 7. Windows에서 되는 것 · 안 되는 것 · 대안

| 항목 | 결과 | 근거 |
|---|---|---|
| 휴대용 Node 24.22.3 설치·실행 | 됨 | 관리자 권한 창 없음, `node --version` = v24.22.3 |
| `npm ci` (스크립트 막음) | 됨 | `added 30 packages`, 경고 1(`prebuild-install` 지원 끝남, 동작에는 영향 없음) |
| `analyze-javascript-application` | 됨 | 5절 |
| `audit-release-exposure` | 됨 | 5절 |
| `rea mcp` (stdio) | 됨 | initialize 응답 `rea 6.10.1`, 프로토콜 2025-06-18 |
| `rea doctor` | 됨 (`healthy: false`) | Ghidra·IDA·Hopper·jadx·Kuna 엔진 없음, 클라이언트 등록 없음. **JS 분석에는 이 엔진이 필요 없다** — 없이도 위 명령이 정상 종료 |
| 네이티브 엔진(Ghidra·IDA 등), Electron 실행 관찰, `analyze-web-bundle`, `recover_javascript_sources` | 시험하지 않음 | 실험 범위(웹 번들 정적 분석) 밖이다. 앞의 둘은 따로 설치, 셋째는 웹 페이지를 받고, 넷째는 Linux 전용 |

**대안 (지금은 쓰지 않는다)**:
1. 22.x로 바꾸기: 24.x에서 REA 오류가 나면 `setup_rea.py`의 고정값을 22.23.5로 바꿔 비교한다. 근거: REA 조건에 들고 사용자 허락 범위 안.
2. WSL: Windows에서 되므로 필요 없다. 이 PC의 WSL에는 `docker-desktop` 배포판만 있어, 쓰려면 리눅스 배포판을 새로 받아야 한다(사용자 허락 필요, 관리자 권한이 필요할 수 있음). 근거: `wsl -l -v`.

## 8. 내 앱을 넣을 때의 규칙 (REA 출력·요약)

REA 출력에는 번들 안의 글이 그대로 들어간다(5절). 시험 번들은 가짜 값뿐이라 괜찮지만 내 앱은 아니다.

| 규칙 | 근거 |
|---|---|
| `rea_smoke.py`는 자기가 만든 가짜 번들만 돌린다(바깥 경로를 받지 않는다). 내 앱은 실행기(F-R)로만 돌린다 | 시험 도구로 내 앱이 들어갈 길을 없앤다 |
| 내 앱의 REA 출력·에이전트 결과·stderr는 **저장소 밖**(`%LOCALAPPDATA%\SelfAudit-private\`, 실행 폴더들과 떨어진 곳)에만 쓰고 git에 넣지 않는다. 검사 `check_bench.py`가 `bench/results/`에 내 앱 결과가 없음을 본다 | 공개 저장소에 비밀값 원문이 올라가지 않게(CLAUDE.md '하지 않는 것'). 규칙과 검사는 `docs/설계/실험구조.md` 4절 |
| 요약에 남는 경로는 `<WORK>`·`<HOME>`으로 가린다(`rea_smoke.py` `mask`). stderr는 앞 2,000자만 남기고 같은 가림을 거친다. 프로세스는 이름만 남긴다(PID 없음) | 절대 경로에 사용자 이름이 들어간다. REA stderr는 진행 기록(파일 이름)이라 내 앱이면 파일 구조가 드러난다. 2,000자는 진행 기록(한 줄 약 150자)의 처음 10여 줄로, 어디서 멈췄는지 보기에 충분하다(추정) |
| `--keep`의 REA 원본(`*.rea.json`)은 가짜 번들 결과뿐이고, 그래도 git에 넣지 않는다(scratchpad에 둔다) | 원본에는 임시 폴더 절대 경로가 그대로 있다(가리지 않음) |
| 실행기도 홈·APPDATA·TEMP를 실행 폴더 안 빈 폴더로 돌린다 | REA가 이 셋에 쓰지 않음은 이 번들에서만 확인했다(5절). 돌려 두면 다른 번들에서 쓰더라도 실행 폴더 안에 남아 함께 관리된다 |

## 9. 남은 것 (다음 단계에 넘김)
- 병합 뒤 main 폴더에서 `python -I ops/scripts/setup_rea.py` 한 번(1절).
- 사용자 확인: 방화벽 규칙(4절, 관리자 권한), Node SHASUMS GPG 확인(2절).
- R4: MCP 거르개, 실행마다 ㉠·㉡ 기록, 시간 상한 — `docs/설계/실험구조.md` 3절.
- 큰 번들(Juice Shop)에서 REA 시간·출력 크기 한 번 재기.
