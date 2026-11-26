---
name: score-match
description: 채점기 F-G01·F-G02(T26, 2026-11-26)의 짜임·함정 — score.read/score.match API, 최대 짝 차례 셈법, 시험 모양. F-G03~G06이나 다시 채점할 때
metadata:
  type: project
---

T26(2026-11-26, 작업 쌍 B 한 세션 쪽)에서 정한 것과 걸린 것.

- `score.read.read_run(run_dir, answers|None)` → `RunRead(status, findings|None, record, problems)`. `read_runs(dirs, {대상: 정답지|None})`는 정답지가 빠진 대상이면 `ScoreError`(지문 대기를 몰래 건너뛰지 않게). 지문 다름은 그 대상 전체를 `stopped_targets`로 빼고 counts에서도 뺀다.
  **Why:** F-G01 5 '그 대상의 채점을 멈춘다'. **How to apply:** F-G03은 `RunRead.record`의 `run_kind`·`metrics`를 읽으면 된다(다시 읽지 않는다).
- `score.match.match_run(findings, answer_key(answers), target_root=None, rules=Rules())`. `Rules(tolerance, location_anchors)`로 T 0·2·5와 위치 닻 끄기를 다시 채점한다(설계 7절 '사용자 확인 전').
- 규칙 5(열쇠 차례로 '그래도 M을 이루나')를 글 그대로 하면 짝마다 최대 짝을 다시 구해 제곱이다. 교대 경로 그래프(짝 아닌 변 결과→정답, 짝 변 정답→결과)의 강한 연결 요소 + 짝 없는 꼭짓점 도달로 '어떤 최대 짝에 드는 변'을 한 번에 구하고, 그 집합이 줄기만 한다는 성질로 옛 집합에 없는 변은 다시 구하지 않는다. 시험 `빠른짝짓기가_명세차례와_같음`이 글 그대로 셈(완전 탐색)과 400개 무작위 그래프로 맞대 본다 — 단순 욕심 짝은 그중 52개에서 달랐다(시험이 헛돌지 않음).
- 비용의 대부분은 짝짓기가 아니라 결과 × 그 파일의 위치 수(후보 검사)다. 계약 최악(결과 100 × 위치 4,000)이 약 1.7초.
- 실제 정답지 닻 110개는 모두 글 안(URL·base64)이라 꾸민(beautify) 코드에서도 글자 그대로 남는다 — 거친 정규식은 7개를 잘못 걸렀다(값을 직접 봐야 했다).
- `tests/score/__init__.py`가 허용 범위에 없어 만들지 않았다. 없어도 pytest·mypy는 지난다(파일 이름이 겹치지 않을 때만).
