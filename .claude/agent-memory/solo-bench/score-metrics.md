---
name: score-metrics
description: 채점기 F-G03~G06(T27, 2026-11-27)의 짜임·함정 — 분수로 셈·반올림, 표·SVG·사례 후보, score 명령, 시험 만들기 함수 공유 방법. 지표·표·보고서 검사·사례를 고칠 때
metadata:
  type: project
---

T27(2026-11-27, 작업 쌍 D 한 세션 쪽)에서 정한 것과 걸린 것. [[score-match]]의 다음 단계.

- 흐름: `recompute.score_results(dirs, answers)` → `read_runs` → `metrics.score_run`(짝짓기+실행 하나) → `aggregate.build_report` → `tables.build_tables`·`svg.build_figures`·`cases.select_cases/read_details`. `__main__.main(argv, repo_root=…)`이 `--out`에 `표.md`·`사례후보.md`·`요약.md`·SVG 셋을 쓴다.
  **Why:** 명세 F-R09 2 명령. **How to apply:** 새 표는 `TABLE_NAMES`에 넣어야 F-G05가 '만들 수 있는 이름'으로 본다.
- 값은 끝까지 `Fraction`으로 들고 보일 때 한 번만 `fmt_fixed`(반올림 0.5 올림을 정수 셈으로). float·Decimal 나눗셈을 쓰면 20.0%p 경계(셋째 권고)와 x.x5 반올림이 흔들린다. run.json의 float은 `Fraction(repr(x))`.
- 정밀도 분모는 `len(findings) − other`를 직접 센다(`MatchResult.wrong`은 ㉰만). reason은 `Finding`에 없어 `cases._reasons`가 findings.json을 다시 읽는다.
- `조건별` 표의 '상한에 걸린 실행 수'는 심은 번들만, `상태별`은 대상 실행 전부(Juice Shop·내 앱 포함) — 줄 안 묶음을 맞추려고.
- 시험 만들기 함수는 `tests/score/test_f_g03.py`에 두고 다른 시험이 `from tests.score.test_f_g03 import …`로 쓴다. `from test_f_g03 import`는 pytest는 되지만 mypy가 못 찾는다(`tests/score/__init__.py` 없음, 허용 범위 밖).
- Windows에서 `Path.write_text`는 `\n`을 CRLF로 바꾼다 — 보고서 글을 시험에서 쓸 때는 `write_bytes`. F-G05는 CR도 글자로 보아 실패시키고 까닭에 'CRLF'를 적는다.
- 헤드리스 Edge(`msedge --headless=new --screenshot`)는 창 너비 ~500px 아래로 줄지 않는다 — 390px 확인은 374px 너비 div에 넣어 찍었다.
- 보이지 않는 글자를 다루는 시험은 `chr(0x200B)`로 만든다 — 소스에 \u 꼴을 쓰면 도구가 실제 글자로 넣어 숨은글자 검사에 걸린다(T27에서 한 번). 옛 서버 시험 test_F_S01 키워드창(절대 5초)은 이 PC에서 따로 돌려도 실패 — 실험 변경과 무관.
