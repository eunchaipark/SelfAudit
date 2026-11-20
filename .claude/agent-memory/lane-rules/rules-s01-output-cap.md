---
name: rules-s01-output-cap
description: T18 뒤 F-S01 출력 모양(SecretsScan: 발견·글마다 걸림 범위·멈춤)과 걸림 상한·근거 조각 ㉠㉡이 어디 있는지, T6·T8이 이어 쓰는 법
metadata:
  type: project
---

T18(2026-11-20, CR-003·005)에서 `secrets.scan_file`이 `list[Finding]` 대신 `SecretsScan(findings, spans, stopped)`을 돌려준다. `spans`는 글마다(날글 1개, `.map`은 `parse_sourcemap` 항목 차례, 멈춘 뒤 항목은 빈 튜플) BOM을 뗀 글 기준 범위다.

**Why:** S03(T6) 근거 조각 ②가 같은 글의 S01 걸림 범위를 넣어야 하고, T8은 멈춤을 건너뜀 `TOO_MANY_HITS`로 바꿔야 한다(CR-003 기술 검토). 상한은 "10,000개 받은 뒤 받아들일 걸림이 하나 더 나오면" 멈춘다(CR-005). 겹쳐 버려지는 후보는 세지 않는다.

**How to apply:**
- 공용 값·함수는 `rules/text.py`: `GENERIC_KEYWORD`·`IDENT_RUN`(규칙과 ㉠이 함께 씀, 두 곳에 적지 말 것), `mask_assignments`(㉠), `mask_url_userinfo`(㉡), `map_prefix`. `build_snippet`이 ② → ㉠㉡ → ③을 앞·뒤에만 한다.
- 걸림 상한 `HIT_LIMIT`·값 상한 `VALUE_MAX`는 `core/limits.py`에 있다(T6 반려 고침에서 옮김). 규칙 레인은 import만 한다.
- ㉠은 명세가 정규식이 아니라 문장이다. 테스트 `SPEC_SNIPPET_KV`가 그 문장을 옮긴 기준 정규식이고 무작위 대조를 한다. 뜻을 바꾸면 거기부터 고친다.
- 정규식·백틱이 많이 든 코드는 Bash heredoc 말고 Edit 도구로 쓴다(heredoc이 두 번 깨졌다). [[rules-regex-linear]]
