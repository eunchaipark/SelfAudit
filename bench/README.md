# bench — REA 실험 도구

같은 Claude Code가 웹 빌드 결과물을 보안 점검할 때 REA를 쥐여 주면(조건 B) 쥐여 주지 않을 때(조건 A)보다 더 많이·더 정확히 찾는지를 재는 도구다(D-035·D-036). 설계는 `docs/설계/실험구조.md`, 무엇을 만들지는 `docs/02_기능명세.md`의 F-B·F-R·F-G·F-M.

## 준비와 검사

```
cd bench
uv sync --locked                                 # 처음 한 번(받기). 실행 의존성 없음, 개발 도구만(ruff·mypy·pytest·pytest-socket)
uv run --frozen --offline pytest -q              # 시험. 그 뒤로는 바깥에 나가지 않는다
uv run --frozen --offline pytest tests/<영역> -q # 영역 하나
```
저장소 맨 위에서 `python ops/scripts/check.py --only 실험린트,실험형식,실험타입,실험테스트` — 커밋 전에는 `check.py` 전체. `bench/.venv`가 없으면 `check.py`가 먼저 `uv sync --locked`를 한 번 돌린다.
- Python 3.13 표준 라이브러리만 쓴다. 새 라이브러리는 사용자 확인이 필요하다(실험구조 1절).
- `uv sync --locked`: `pyproject.toml`과 `uv.lock`이 어긋나면 멈춘다. `--frozen --offline`: lock 그대로, 받으러 나가지 않음(실험구조 2.9 '검사 명령').
- **바깥 접속 막기의 한계**: pytest-socket(`--allow-hosts=127.0.0.1,::1`)은 시험 프로세스 안의 `connect`만 막는다. DNS 이름 풀기·UDP·시험이 띄운 자식 프로세스는 막지 않는다. 그래서 시험에서 실제 `claude.exe`·REA·네트워크를 쓰는 프로그램을 띄우지 않는다.

## 폴더

| 폴더 | 무엇 | 주인 |
|---|---|---|
| `contracts/` | 정답지·결과·실행 원자료·대상 목록 JSON Schema (`answers`·`findings`·`run`·`targets`) | 설계 |
| `common/` | 공통 함수 (아래) | 설계 |
| `sources/`, `bundles/`, `answers/`, `targets.json` | 시험 번들 원본·결과물·정답지·대상 목록. 가짜 값만. `bundles/`는 바이트 그대로(`.gitattributes` `-text`) | 번들 레인 |
| `run/` | 실행기·MCP 거르개·지시문 | 실행기 레인 |
| `score/`, `measure/` | 채점기·질문 2 측정 | 채점 레인 |
| `results/<날짜>/<실행 ID>/` | 원자료 (시험 번들·연습앱만. 내 앱은 저장소 밖) | 실행기가 만든다 |
| `tests/<영역>/` | 시험(폴더마다 `__init__.py`). `tests/conftest.py`·`tests/common/`은 설계 | 그 영역 레인 |

## 공통 함수 (`common/`, 실험구조 2.9·2.10)

같은 원자료면 늘 같은 숫자가 나오게, 세 레인이 이 함수만 쓴다. 다시 만들지 않는다. import는 `bench/` 기준(`from common.contracts import read_contract`).

| 함수 | 하는 일 |
|---|---|
| `common.contracts.read_contract(name, path)` | 파일을 읽어 계약(`"answers"`·`"findings"`·`"run"`·`"targets"`)과 뜻 규칙으로 검증. 어긋나면 `ContractViolationError`(`.errors`) |
| `common.contracts.validate_contract(name, value)` | 이미 읽은 값을 검증. 어긋난 곳 목록(`ContractError(where, rule)`, 100곳까지), 맞으면 빈 목록 |
| `common.contracts.read_json(path)` | 엄격한 JSON 읽기(4 MiB·같은 키·NaN·`1e999`·깊이 64 거절, `ContractJsonError`) |
| `common.contracts.check_answers_semantics(answers)` · `check_targets_semantics(targets)` | 뜻 규칙만(줄 범위·ID 고유·종류). `validate_contract`가 이미 부른다 |
| `common.fingerprint.bundle_manifest_sha256(bundle_dir)` | 번들 지문(F-B04). `manifest_lines`는 그 줄들, `format_manifest(digests)`는 차례 짓기만. 못 내면 `ManifestError`(번들 안 경로를 알림) |
| `common.paths.is_bundle_relpath(path)` | 번들 경로 허용 꼴(2.2)인지. 계약의 `format: bundle-relpath`가 이것 |
| `common.paths.resolve_in_bundle(bundle_dir, rel)` | 번들 안 파일의 디스크 경로. 허용 꼴이 아니거나 풀어 보니 밖이면 `BundlePathError`. **번들 파일을 열 때는 늘 이것** |
| `common.paths.normalize_finding_path(file, target_root)` | 결과 경로를 정답지 꼴로(2.5 조건 2, F-G02 1, 글자 그대로) |
| `common.lines.count_lines(data)` · `window_covers_file(...)` | 정답지 `file_lines` 셈(끝 줄바꿈 하나는 새 줄 아님) · 줄 허용 범위가 파일 전체를 덮는지(덮으면 줄로 못 가름, 2.5 ㉢) |

- 오류 글에는 값이 없다(위치와 규칙만). 결과·정답지의 글은 비밀값일 수 있어서다. 레인도 로그에 이 꼴을 쓴다.
- 검증기는 JSON 뜻이라 `"line": 12.0`도 정수로 통과한다. 줄 번호를 쓸 때는 `int`로 바꾼다.
- 시험 픽스처: `make_bundle({"assets/a.js": b"..."})` → 임시 번들 폴더(`tests/conftest.py`). 가상 계약 값은 `tests/common/examples.py`.

## 지킬 것

- 시험 번들·정답지의 값은 이 프로젝트만의 가짜 꼴로 만든다(D-043 ㉯). 서비스 키 꼴(AWS·GitHub·Stripe 등)을 쓰지 않는다(실험구조 2.2·4절, 검사 '실험자료'가 찾는다).
- 내 앱(`mine`) 결과는 저장소 밖(`%LOCALAPPDATA%\SelfAudit-private`)에만 둔다(실험구조 4절).
- 시험에서 실제 `claude.exe`·REA를 부르지 않는다.
