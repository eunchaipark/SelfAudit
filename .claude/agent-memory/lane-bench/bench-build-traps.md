---
name: bench-build-traps
description: 번들 레인 함정 — ruff가 _build를 건너뜀, check_bench가 시험 글도 훑음, 한글 줄 길이, worktree 명령 막힘 (T21, 2026-11-22)
metadata:
  type: project
---

T21(2026-11-22)에서 걸린 것. 다음 번들 태스크(T22~T25, T36)가 먼저 알아야 한다.

- ruff 기본 제외 목록에 `_build`가 있어 `check.py` 실험린트·형식이 `bench/sources/_build/`를 건너뛴다. 설계가 pyproject를 고치기 전에는 `cd bench; uv run --frozen --offline ruff check sources/_build`와 `ruff format --check sources/_build`를 따로 돌린다.
  **Why:** 검사가 통과로 보였는데 실제로는 31개 위반이 있었다. **How to apply:** `_build`에 파일을 더하거나 고치면 매번 따로 돌린다. 설계가 고쳤는지는 `check.py` 실험형식의 파일 수가 mypy 파일 수와 같은지로 본다.
- `bench/sources/__init__.py`가 없으면 mypy가 같은 파일을 두 이름으로 읽어 멈춘다. 지우지 않는다.
- `check_bench.py`는 `bench/tests/`의 글도 훑는다. 서비스 꼴 키를 걸리게 하는 시험 값은 `"AK" + "IA" + …`처럼 조각을 이어 만든다.
- ruff E501은 한글을 2칸으로 센다. 문서 문자열·주석은 한글 약 45자에서 줄을 바꾼다.
- 이 worktree에서는 `&&`와 heredoc·mkdir·`git -C`를 섞은 Bash 명령이 막힌다. 파일은 Write로 만들고, git 명령은 하나씩 돌린다.
- 번들 검사는 `sources._build.verify.check_target(repo_target(id))`, 빌드는 `python -m sources._build build <id>`다. 더하는 변환은 `_build/<이름>.py`의 `FILTERS`·`STEPS`로 만들고 `plan.json` `plugins`에 이름을 적는다(`build.py`는 고치지 않는다). [[bench-fake-values]]
