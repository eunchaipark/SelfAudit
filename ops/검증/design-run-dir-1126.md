# 검증 — 설계 실행 폴더·내 앱 지문·가림 경계·검토자 카드 (`design/run-dir-1126`, 30a6491..47e69a6)

## 결과: 통과 → 병합 (총괄, 2026-11-27)
- `task-reviewer` 하나(옛 정의 sha256 0261257…): 높음 0 · 중간 0 · 낮음 6 | 명세 일치 7 · 명세에 없음 1. main check.py 16/16(실험테스트 1045).
- 확인: `os.mkdir(…, 0o700)` 맨 위 = SYSTEM·Administrators·OWNER RIGHTS만(P 플래그), 기존 폴더 권한 우회 셋 거절, 정션 바꿔치기(TOCTOU) 거절, ㉢ 적힌·푼 경로·CLAUDE.local.md, 기존 targets.json 통과, 가림 22꼴 약해짐 없음(JSON `\/`·`\uXXXX`+`/`·file URI 새로 가림), escape #1 같은 꼴, 시험 뒤 C:\SelfAudit-* 0개, 처리량 선형·메모리 입력의 1.5배.
- task-reviewer 정의가 이 병합으로 바뀜: 0261257573a1… → 851d3c2e56a5a984ab2dc34c2c094752bd788e745541d53dd2e10d85203295dc. 쌍 A·B 독립 검토는 옛 정의, 쌍 C·D는 새 정의 + 지시 틀 2판(blob sha256 694186a3f217…) — 쌍 안은 같은 잣대.

## 후속 (낮음)
- workdir.py:203 `ensure_runs_root`가 부모(C:\) DACL을 안 봄 — 이 PC C:\에 지워진 로컬 계정 SID(RID 1003)가 (OI)(CI)(F)로 남아 있음(살아 있는 계정 아님). 부모에 남의 DC·F 허용이 있으면 멈추거나 8.9 1 근거에 가정 적기.
- store.py:214 두 겹 JSON 이스케이프 꼴(`C:\\Users\\u`) 안 가림(main도 같음) — `home_left`에 역슬래시 1~4개 꼬리 꼴.
- test_f_r02.py 문서 문자열이 '드라이브 맨 위 상속 조건과 같다'고 과하게 말함.
- SystemDrive 꼴 멈춤·목록 지문≠정답지 지문·내 앱 지문 칸 없음 멈춤이 8.9 '옮길 줄'에 없음 → 문서 배정에 넣음.
- test_F_R02_작업폴더_자리가 명세 예시와 어긋남(문서가 옮길 때까지) → 문서 배정.
- `<LOCAL_REL>` 채움·미끼 닿음 미리 확인 → T32 details·testStrategy에 넣음.
