---
name: project-run-dir-outside-home
description: 실행 폴더는 홈 밖 %SystemDrive%\SelfAudit-bench-runs (2026-11-27 총괄 대리) — 맨 위는 os.mkdir 0o700로 보호 DACL, 미끼는 %LOCALAPPDATA%에 남김, 시험은 드라이브 맨 위 mkdtemp
metadata:
  type: project
---

실행 폴더 자리를 `%LOCALAPPDATA%` → `%SystemDrive%\SelfAudit-bench-runs`로 옮겼다(실험구조 8.9 1). 설정·내 앱 원자료·보관·미끼 폴더는 `%LOCALAPPDATA%`에 그대로.

**Why:** 홈에 `~/.claude`가 있어 F-R02 2㉢(위쪽에 `.claude` 없음)이 모든 배치를 멈췄다. ㉢에 예외를 두는 안(㉯)은 Claude Code가 위쪽 `.claude/CLAUDE.md`를 읽는지 모름(추정)이라 버림.

**How to apply:**
- 드라이브 맨 위(`C:\`)는 Authenticated Users가 폴더를 만들고 '수정'을 물려준다. 파이썬 3.13+ Windows의 `os.mkdir(p, 0o700)`은 보호 DACL(SY·BA·OW)로 한 번에 만든다 — 새 라이브러리 없이 권한 문제를 푸는 길. 이미 있으면 SDDL을 허용 꼴로만 확인하고 고치지 않는다(`workdir.ensure_runs_root`).
- 미끼는 진짜 `SelfAudit-private`의 쌍둥이라 자리를 옮기지 않았고, escape #1은 `<LOCAL_REL>` 자리 표시로 닿게 했다 — 문지기(T32)가 채운다.
- ㉢이 걸리는 시험은 pytest 임시 폴더(홈 아래)가 아니라 드라이브 맨 위 `mkdtemp`를 쓴다.
관련: [[project-rea-env]], [[feedback-security-allowlist]]
