---
name: scripts-via-write
description: 백슬래시·따옴표가 든 python 시제품·문서 고침 스크립트는 Bash heredoc 말고 Write로 scratchpad에 써서 돌린다 (spec-editor)
metadata:
  type: feedback
---

Bash heredoc(`<<'EOF'`)으로 넘긴 python에서 `\\`가 `\`로 바뀌어 문자열이 깨졌다(2026-11-20, `'pwd=>"a\\'` SyntaxError, `\'` 시험 글이 엉뚱하게 됨). 백슬래시가 든 글은 `chr(92)`로 만들거나, 스크립트를 Write로 scratchpad에 쓰고 `python -I <경로>`로 돌린다.
**Why:** 명세 예시(`\"` 이스케이프 등)를 시제품으로 확인할 때 입력이 바뀌면 틀린 결과를 맞다고 볼 수 있다.
**How to apply:** 예시 확인·문서 일괄 고침 스크립트는 Write → 실행. bench 코드를 부를 때는 `cd bench && uv run python -I <스크립트>`(스크립트 안에서 `sys.path.insert(0, bench)`). 한글을 찍는 `python -c`는 cp949 오류가 나므로 `PYTHONIOENCODING=utf-8`을 앞에 붙이거나 `ascii()`로 찍는다. 보이지 않는 글자 검사도 `chr(0x202e)` 꼴로 쓴다. [[commit-in-shared-main]]
