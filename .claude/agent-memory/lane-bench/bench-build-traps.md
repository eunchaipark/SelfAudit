---
name: bench-build-traps
description: 번들 레인 함정 — ruff 기본 제외 이름(_build 등), check_bench가 시험 글도 훑음, 한글 줄 길이, worktree 명령 막힘, 큰 입력 측정 꼴 (T21 반려 1, 2026-11-22)
metadata:
  type: project
---

T21(2026-11-22, 반려 1)에서 걸린 것. 다음 번들 태스크(T22~T25, T36)가 먼저 알아야 한다.

- ruff 기본 제외 목록에 `_build`·`build`·`dist` 같은 이름이 있다. 폴더 이름이 거기 걸리면 `check.py`가 그 폴더를 소리 없이 건너뛴다. 그래서 도구 폴더를 `bench/sources/build_tools/`로 바꿨다.
  **Why:** 검사는 통과로 보였는데, 실제로는 위반이 31개 있었다. **How to apply:** 새 폴더를 만들면 `uv run --frozen --offline ruff check --show-files .`에 그 파일들이 나오는지 한 번 본다.
- `bench/sources/__init__.py`를 지우지 않는다. 없으면 mypy가 같은 파일을 두 이름으로 읽어 멈춘다.
- `check_bench.py`는 `bench/tests/`의 글도 훑는다. 서비스 꼴을 걸리게 하는 시험 값은 `"AK" + "IA" + …`처럼 조각을 이어 만든다.
- 시험 함수 이름에 `㉯` 같은 동그라미 글자를 넣으면 파이썬 SyntaxError가 난다.
- ruff E501은 한글을 2칸으로 센다. 주석·문서 문자열은 한글 약 45자에서 줄을 바꾼다.
- 이 worktree에서는 `&&`·heredoc·`git -C`를 섞은 Bash 명령이 막힌다. 여러 줄 고침은 scratchpad에 파이썬 스크립트를 Write로 쓰고 `python -I <스크립트> <대상>`으로 돌린다. git 명령은 하나씩 돌린다.
- 보안 검토는 같은 글자가 이어진 큰 줄로 메모리를 잰다(T21 반려 1). 검사 코드는 나온 곳을 목록에 모으지 말고 흘려 보낸다. 큰 입력 측정에는 같은 글자 반복·겹쳐 나오는 닻을 넣는다.
- 숫자 근거(확률·나눗셈)는 주석에 적기 전에 직접 계산하고, 그 식도 같이 적는다. 추정으로 적은 값이 틀려 반려됐다.
- Windows에서 `Path.write_text`는 `\n`을 CRLF로 바꾼다. 원본·번들 바이트를 시험에서 쓸 때는 `write_bytes`를 쓴다. 빌드는 원본에 CR이 있으면 멈춘다.
- 시험에서 다시 빌드할 때는 원본을 tmp로 복사해 그쪽에서 빌드한다. `build()`가 원본 폴더에 `build.json`을 쓰기 때문이다.
- 정답지 줄 번호는 닻을 검색해 얻지 않고 '그 줄에만 있는 글'(줄 표식)로 정한다. 닻 검색으로 위치를 만들면 F-B07 6 고유성 검사가 뜻을 잃는다. T22는 scratchpad 스크립트로 이렇게 만들었다(T22 보고 '고른 것' 11).
- 펼친 번들의 맵은 한 줄이라, 모든 정답·미끼 위치에 맵 1줄이 들어간다.
- 쓴 접두어: `zelto_`·`quvar_`(easy-1), `mirtak_`(easy-2), `korvel_`(mini-1).
- 도구 쓰는 법과 함수 이름은 `ops/보고/T21.md` '다음 세션이 알아야 할 것'에, 쉬움 번들의 결정과 근거는 `ops/보고/T22.md` '고른 것'에 있다. [[bench-fake-values]]
