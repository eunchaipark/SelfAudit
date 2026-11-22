---
name: bench-fake-values
description: 가짜 값 규칙의 해석 — F-B07 10은 secret 정답만, ㉯는 값 자체만, 다시 만들기는 ㉮㉯㉰ 모두 (T21 '고른 것' 9·10, 문서 확인 대기)
metadata:
  type: project
---

F-B02 5와 F-B07 10의 '가짜 값' 범위를 명세가 정하지 않아, T21에서 이렇게 읽고 문서에 확인을 요청했다(ops/보고/T21.md 요청 2).

- F-B07 10은 `secret` 범주 정답의 `anchor`·`decoded_anchor`에만 건다. ㉯(실제 서비스 접두어)는 값 자체(풀어낸 값이 있으면 그것)에만 건다.
  **Why:** F-B02 6이 허용한 가짜 주소 `.test`·`.example`가 ㉰ 낱말에 걸린다. 나눈 조각의 앞 글자는 접두어가 아니다.
  **How to apply:** 내부 주소·경로 정답에는 `.test` 주소를 써도 된다. 비밀값 정답에는 fake·test·demo 같은 낱말을 넣지 않는다. 문서가 명세를 고쳤으면 `verify._check_fake_values`를 거기에 맞춘다.
- 값은 `random.Random("<대상 ID>/<정답 ID>")`로 만든다. 정답 ID를 바꾸면 값도 바뀐다. 무작위 부분이 규칙 5의 어디에 걸리든 시드에 `#n`을 붙여 다시 만든다.
- 접두어는 정답마다 다른 지어낸 이름(`^[a-z]{4,6}_`)으로 둔다. 쓴 것: `zelto_`(명세 예시), `korvel_`(mini-1 시험 번들). [[bench-build-traps]]
