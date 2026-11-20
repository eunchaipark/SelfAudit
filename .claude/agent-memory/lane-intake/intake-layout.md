---
name: intake-layout
description: 입력 레인 코드 배치(engine 순수 분류, service의 write_bundle을 zip이 재사용)와 T4가 이어 쓸 자리
metadata:
  type: project
---

T3(2026-11-20)에서 정한 배치. zip(T4)은 이것을 이어 쓴다.

- `intake/engine.py`: `IntakeLimits`(기본값 core/limits, 테스트만 작은 값), `Entry(path,size,kind)`, `is_target`, `skip_reason`(링크 → 종류 아닌 것 → 크기 초과 → 대상 아님 차례), `check_totals`, 문구 `MSG_TOO_LARGE`·`MSG_OTHER`.
- `intake/service.py`: `receive_folder(source, dest, *, limits)` = `make_quarantine` → `scan_folder` → `write_bundle(entries, opener, root, limits)`. `write_bundle`은 opener(경로 → read(n)가 있는 컨텍스트)만 받으므로 zip은 `lambda p: zf.open(info_by_path[p])`로 넘기면 된다. 실제 바이트 제한, `xb`, resolve 검사가 그 안에 있다.
- `app/intake/__init__.py`가 `receive_folder`를 내보낸다(계약 표기 `intake.receive_folder`). T4는 `receive_zip`을 같은 식으로 더한다.

**Why:** 공통 분류·제한을 한 곳에 두어 폴더와 zip 결과가 어긋나지 않게.
**How to apply:** T4는 zip 항목 검사(2ⓐ~ⓔ)·맨 위 폴더 벗김(3)만 새로 짜고 Entry 목록을 만들어 write_bundle에 넘긴다. 이름 겹침 건너뜀은 Entry 목록을 만들 때 처리(write_bundle에는 그 이유가 없다).

함정:
- Windows에서 `DirEntry.is_dir(follow_symlinks=False)`가 정션에 참이다. 링크·정션 검사를 먼저 한다.
- 이 PC는 일반 권한으로 심볼릭 링크를 못 만든다(WinError 1314). 테스트는 `_winapi.CreateJunction`으로 정션을 쓰고 symlink 테스트는 skip된다.
- 파일 하나 여는 데 OS가 약 10ms(백신 검사로 보임). 파일마다 `resolve()`하면 5ms가 더 붙어서 폴더마다 한 번만 한다. 5,001개 폴더 39초, 그냥 복사 26초.
- Bash에서 python으로 파일을 고쳐 쓰면 CRLF가 된다. git이 LF로 바꾼다는 경고만 나온다.
