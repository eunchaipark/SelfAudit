---
name: commit-in-shared-main
description: main 폴더를 총괄과 같이 쓸 때 새 파일 커밋·병합 중 상태·줄바꿈 주의 (spec-editor)
metadata:
  type: feedback
---

새 파일(CR 등)은 `git commit -- <경로>`만으로 안 된다(pathspec 오류). 먼저 `git status`로 병합 중(`All conflicts fixed but you are still merging`)이 아닌지 보고, 아니면 `git add -- <내 파일>` 뒤 경로 지정 커밋.
**Why:** 2026-11-19 총괄이 main에서 설계 브랜치를 병합하던 중 `git add`를 해 내 CR이 병합 인덱스에 섞였다(`git restore --staged`로 되돌림).
**How to apply:** 병합 중이면 커밋하지 말고 파일만 남긴 뒤 총괄에게 알린다. 파이썬으로 docs를 고칠 때는 `open(..., newline='')`로 써서 CRLF가 생기지 않게 한다(`.gitattributes`는 LF). 표 칸 안 코드에 `|`가 있으면 `\|`로 쓴다.
