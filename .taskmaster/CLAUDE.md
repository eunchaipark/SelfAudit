# Taskmaster 명령

작업 규칙은 저장소 맨 위 `CLAUDE.md`와 `ops/역할/관제.md`가 기준이다. 여기는 명령만 정리한다.
**태스크를 만들고 상태를 바꾸는 것은 관제만 한다.** 다른 역할은 읽기 명령만 쓴다.

## 읽기 (누구나)

```bash
task-master list                       # 전체 태스크와 상태
task-master list --with-subtasks       # 하위 작업까지
task-master show 5                     # 태스크 상세 (하위 작업은 5.2처럼)
python ops/scripts/tm_parallel.py      # 지금 시작할 수 있는 것, 배치안, 보류 이유
```

## 쓰기 (관제만, main 폴더에서)

```bash
task-master set-status --id=5 --status=in-progress
task-master set-status --id=5 --status=review      # 레인이 완료 보고
task-master set-status --id=5 --status=done        # main에 병합된 뒤
task-master set-status --id=5 --status=blocked     # 미결·명세 문제 (이유는 총괄에게)
task-master add-task --title="돈: 이번 달 살 것 (F-A16)" --description="한 줄" --details="영역: 돈
목적: 월급날 무엇을 몇 주 살지 바로 알 수 있게
읽을 문서: 기능명세 F-A16
고칠 파일: backend/app/money/**, frontend/src/features/money/**" --dependencies=4,5 --priority=high
task-master add-subtask --parent=5 --title="..." --description="..." --details="..."
task-master add-dependency --id=25 --depends-on=24
task-master validate-dependencies
git commit -m "[관제] T5 in-progress" -- .taskmaster/tasks/tasks.json
```

- AI를 부르는 명령(`parse-prd`, `expand`, `update`, `update-task`, `update-subtask`, `research`, `analyze-complexity`, `add-task --prompt`)은 쓰지 않는다.
- details 맨 위 머리줄(영역·목적·읽을 문서·고칠 파일·계약)은 `tm_parallel.py`가 읽는다. 형식을 지킨다. 목적이 없으면 배치에 들어가지 않는다.
- 머리줄에 더 쓰는 줄: `명세 기준: <커밋>`(in-progress로 바꿀 때), `변경: CR-<번호>`(변경 요청으로 고치거나 만든 태스크). 스크립트는 이 줄들을 건드리지 않는다.
- details·testStrategy를 고칠 때와 CLI가 멈출 때는 `tasks.json`을 직접 고친다. 고친 뒤 `task-master validate-dependencies`.

상태: `pending`, `in-progress`, `review`, `done`, `blocked`, `deferred`, `cancelled`
