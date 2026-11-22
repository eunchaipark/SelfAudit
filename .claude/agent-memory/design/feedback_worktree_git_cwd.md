---
name: worktree-git-cwd
description: 격리 worktree에서는 하위 폴더로 cd한 뒤 git을 부르면 거절된다 — git은 worktree 맨 위에서, bench 명령은 따로 부른다
metadata:
  type: feedback
---

worktree에 갇힌 에이전트는 한 명령 안에서 `cd <worktree>/bench && … && cd .. && git …`처럼 하위 폴더를 거쳐 git을 부르면 도구가 통째로 거절한다.

**Why:** 하네스가 "실행 중에 계산된 위치로 cd한 뒤 git"을 worktree 밖 git으로 보고 막는다(T20에서 두 번 걸림).

**How to apply:** `uv run …`(bench 폴더)과 `git …`(worktree 맨 위)을 다른 Bash 호출로 나눈다. Git Bash heredoc 안 python으로 역슬래시 든 글을 찾아 바꾸면 어긋나기 쉬우니 그런 글은 Edit 도구로 고친다. [[feedback_unicode_escape]]와 같은 갈래.
