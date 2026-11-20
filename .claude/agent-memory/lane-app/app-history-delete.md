---
name: app-history-delete
description: T2(F-P02 점검 기록·F-P03 앱 지우기)에서 배운 함정 — confirm 쿼리 파싱, IdPath와 계약 검사, 공통 501 테스트, 지우기 방식
metadata:
  type: project
---

T2(2026-11-20)에서 걸린 것. 앱 레인의 다음 태스크가 같은 곳을 만지면 먼저 본다.

- `confirm: Literal[True]` 쿼리는 `?confirm=true`를 받지 못한다(pydantic Literal은 글을 참으로 안 바꿔 400). `apps/api.py`의 `Confirm`(BeforeValidator로 정확히 "true"만 참)을 쓴다. 설계에 `core/deps.py` 공용으로 옮겨 달라고 요청함 — 옮겨졌으면 그것을 쓴다.
  **Why:** 뼈대 계약이 실제 요청을 받는지 시험된 적이 없었다.
  **How to apply:** 쿼리의 Literal·bool 인자는 TestClient로 실제 문자열을 보내 확인한다.
- `IdPath`를 쓰면 openapi.json에 min/max가 붙어 검사 '계약'이 레인 브랜치에서 실패한다. 생성 파일은 총괄이 병합 뒤 다시 만든다 — 보고서 요청에 적고 넘어간다.
- API의 문서 문자열이 openapi `description`이 된다. 문서 문자열을 고치면 계약 검사가 깨지므로 api.py 함수 문서 문자열은 그대로 둔다.
- `tests/core/test_security.py`의 501 테스트가 `GET /api/v1/apps`를 썼다(설계에 바꿔 달라 요청). 빈 API를 채우면 공통 테스트가 그 API에 기대는지 grep한다.
- 앱 지우기는 `delete(App)` 한 문장 + DB `ON DELETE CASCADE`. ORM `session.delete`는 발견을 다 읽어 느리다. 진행 중 확인은 같은 문장의 `~exists()`로 한 번 더.
- 점검 행은 DB에 바로 넣어 시험한다: `tests/apps/conftest.py`의 `add_app`·`add_scan`.
- Bash에서 `cd … && python - <<EOF` 같은 여러 줄 명령은 worktree 격리 검사에 막힌다. 스크립트는 scratchpad 파일로 쓰고 실행하거나 Edit 도구를 쓴다. Python으로 파일을 쓸 땐 `newline="\n"`(아니면 CRLF).
