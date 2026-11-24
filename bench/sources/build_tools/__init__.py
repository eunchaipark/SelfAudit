"""시험 번들 빌드·심기 도구 (F-B01·F-B02·F-B04 틀, F-B07 번들 하나 검사).

자리 `bench/sources/build_tools/`(T21 반려 1, 총괄 판단: ruff 기본 제외 목록의 `_build`를 피함).
대상 ID 꼴(`^[a-z0-9][a-z0-9-]…`)에 `_`가 없어 원본 폴더 `bench/sources/<대상 ID>/`와 섞이지 않는다.

- `build` — 원본 → 결과물(펼침·압축·해시 이름·소스맵), 빌드 기록 `build.json`
- `fake` — 가짜 값(키·토큰·비밀번호) 만들기, 가짜 값 규칙(F-B02 5), 나눔
- `minify` · `sourcemap` — 압축(한 줄)과 소스맵
- `rename` — 이름 줄이기(normal·hard, F-B01 6 — 빌드 설정의 줄일 이름 표)
- `verify` — 번들 하나 구성 검사(F-B07 2~13)
- 더하는 변환(T23 `encode.py`, T24 `obfuscate.py`)은 이 폴더에 파일만 더하고 원본의 `plan.json`
  `plugins`에 이름을 적는다. `build.py`는 고치지 않는다(`build.py` 머리글의 '더하는 변환').

부르기: `cd bench; uv run --frozen --offline python -m sources.build_tools build <대상 ID>`
"""
