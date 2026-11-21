# 검증 — 설계: REA 환경 (`design/env-rea`, dee345a..c68b008)

## 결과: 반려 1 (총괄, 2026-11-22 새벽)
- 보안 (security-reviewer): 높음 0 · 중간 3 · 낮음 5. 내려받기 https 고정, sha256 세 겹 일치, zip 풀기 경로 확인, lock 175개 모두 registry.npmjs.org·sha512, `--ignore-scripts`, `.tools/` 밖에 안 씀, 사용자 설정 안 건드림, 커밋에 진짜 비밀값 없음 — 문제없음.
- 같은 에이전트가 이어 하는 design/bench-structure(env-rea 위) 브랜치에 고침 커밋을 더하고, 그 브랜치를 한 번에 검토·병합한다(총괄 판단: 브랜치 둘을 따로 고치면 같은 파일이 두 번 바뀐다).

## 고칠 것
1. [중간] netguard가 파이프 경로를 조건 없이 통과 — `\\원격\pipe\x`는 SMB로 다른 기기에 연결되고 커널(PID 4)이 맺어 netstat 감시도 못 본다. UNC 파일 읽기도 두 겹 다 못 본다 → 로컬 파이프(`\\.\pipe\`·`\\?\pipe\`)만 허용, REA가 `.map` sources·sourceRoot를 디스크에서 따라 읽는지 확인, 한계 칸에 적음.
2. [중간] '두 겹으로 봤다'가 실제 범위보다 넓게 쓰임 — ① NODE_OPTIONS를 지운 자식엔 ㉠ 없음 ② DNS 질의는 svchost가 보냄 ③ 감싸지 않은 DNS 함수(lookupService, resolveMx 등, dns.Resolver) ④ `process.binding('tcp_wrap')` 우회 ⑤ 0.2초보다 짧은 연결·TIME_WAIT·손자 프로세스 → ㉠에 DNS 함수·Resolver 추가, 문서 4절 한계 칸에 ①~⑤, '막는다'가 아니라 '기록한다'로. 실제로 막는 방화벽 규칙은 사용자 확인(관리자 권한).
3. [중간] 조건 B의 MCP 명령에 감시 설정이 없고 Claude Code 환경 전체를 물려받음. `electron,artifact` 묶음에 실행 중인 Electron 앱을 다루는 도구 5개 → 33개 도구를 하나씩 보고 정적 분석 도구만 허용 목록으로(근거 함께), MCP env에 ㉠, ㉡은 실행기가 감쌈.
4. [낮음] `dict(os.environ)` 전체를 REA·npm에 넘김 → 허용 목록 환경(SystemRoot·PATH·TEMP·TMP·USERPROFILE 등).
5. [낮음] setup_rea.py: 리디렉트 주소 검사, 받는 크기·전체 시간 상한, 이미 있는 node.exe의 sha256 비교.
6. [낮음] 문서: '175개 모두 sha512'는 145개가 inBundle(묶음 integrity로만) — 문장 고침. 라이선스(frida LGPL-2.0 WITH WxWindows, openpgp LGPL-3.0+, commander 라이선스 없음) 검토 한 줄(설치만 하고 배포하지 않는다는 근거).
7. [낮음] 문서: '출처가 바뀐 경우를 못 잡는다'는 처음 고정 때만의 한계로 고침. 근거 없는 값(0.2초 간격, DOWNLOAD_TIMEOUT 120초, NPM_TIMEOUT 1800초)에 근거나 '추정'과 확인 방법(D-038).
8. [낮음] smoke 요약에 stderr 2000자·임시 폴더 절대 경로·프로세스 목록, `--keep`이 REA 원본을 남김 → 내 앱을 넣을 때의 규칙(경로·stderr 가림, 원본은 git에 안 넣음)을 문서 8절에. REA가 `%USERPROFILE%`·`%APPDATA%`에 쓰는지 확인.

## 문제와 개선
- 방법론: 감시·차단 도구를 검토할 기준(무엇을 덮는가)이 없었다 → 감시 도구 설계 문서에 '감싼 함수 / 감싸지 않은 함수' 목록과 로컬 우회 시험을 함께 싣는다
