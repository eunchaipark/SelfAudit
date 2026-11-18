"""검사 묶음 실행기. ops/checks.json의 명령을 차례로 돌리고, 결과는 한 줄씩만 보여 준다.
실패한 검사만 마지막 몇 줄을 보여 주고, 전체 출력은 로그 폴더에 남긴다.
(에이전트가 테스트 로그 수백 줄을 읽지 않게 해서 토큰을 아낀다.)

사용 (저장소 맨 위에서):
  python ops/scripts/check.py                    # 전부
  python ops/scripts/check.py --only 서버테스트   # 이름으로 골라서 (쉼표로 여러 개)
  python ops/scripts/check.py --tail 50          # 실패 출력 줄 수 (기본 30)
  python ops/scripts/check.py --fail-fast        # 처음 실패에서 멈춤

종료 코드: 0 모두 통과, 1 실패 있음, 2 설정 문제
"""

from __future__ import annotations

import argparse
import json
import locale
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oplib import use_utf8_output  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def decode(data: bytes) -> str:
    for enc in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def last_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:160]
    return "(출력 없음)"


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name) or "check"


def run_check(check: dict, log_dir: Path) -> dict:
    name = check["이름"]
    cwd = ROOT / check.get("폴더", ".")
    limit = int(check.get("제한초", 600))
    start = time.monotonic()
    if not cwd.is_dir():
        # Windows에서는 없는 cwd가 FileNotFoundError가 아닌 NotADirectoryError로 와서 예외로 끝났다
        text, ok, note = f"폴더가 없습니다: {cwd}", False, "폴더 없음"
        return _result(name, check, cwd, log_dir, start, text, ok, note)
    try:
        proc = subprocess.run(check["명령"], shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=limit)
        text, ok, note = ANSI.sub("", decode(proc.stdout)), proc.returncode == 0, ""
        if not ok:
            note = f"종료 코드 {proc.returncode}"
    except subprocess.TimeoutExpired as e:
        text, ok, note = ANSI.sub("", decode(e.stdout or b"")), False, f"시간 초과 {limit}초"
    except OSError as e:
        text, ok, note = str(e), False, "폴더 또는 명령 없음"
    return _result(name, check, cwd, log_dir, start, text, ok, note)


def _result(name: str, check: dict, cwd: Path, log_dir: Path, start: float, text: str, ok: bool, note: str) -> dict:
    secs = time.monotonic() - start
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{safe_name(name)}.log"
    log.write_text(f"$ {check['명령']}  (폴더: {cwd})\n\n{text}", encoding="utf-8", newline="\n")
    return {"이름": name, "통과": ok, "초": secs, "요약": last_line(text), "메모": note, "로그": log, "출력": text}


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    ap = argparse.ArgumentParser(description="검사 묶음 실행 (요약만 출력)")
    ap.add_argument("--config", default=str(ROOT / "ops" / "checks.json"))
    ap.add_argument("--only", default="", help="이름 목록 (쉼표)")
    ap.add_argument("--tail", type=int, default=30)
    ap.add_argument("--fail-fast", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        checks = cfg["검사"]
    except (OSError, ValueError, KeyError) as e:
        print(f"설정을 읽을 수 없습니다 ({args.config}): {e}", file=sys.stderr)
        return 2
    if args.only:
        wanted = [w.strip() for w in args.only.split(",") if w.strip()]
        unknown = [w for w in wanted if w not in {c["이름"] for c in checks}]
        if unknown:
            print("없는 검사 이름: " + ", ".join(unknown), file=sys.stderr)
            return 2
        checks = [c for c in checks if c["이름"] in wanted]
    log_dir = ROOT / cfg.get("로그폴더", ".ops-logs")

    results = []
    for check in checks:
        results.append(run_check(check, log_dir))
        if args.fail_fast and not results[-1]["통과"]:
            break

    failed = [r for r in results if not r["통과"]]
    total = sum(r["초"] for r in results)
    print(f"검사 {len(results)}개 — 통과 {len(results) - len(failed)}, 실패 {len(failed)} (총 {total:.1f}초)")
    width = max((len(r["이름"]) for r in results), default=4)
    for r in results:
        mark = "통과" if r["통과"] else "실패"
        memo = f" [{r['메모']}]" if r["메모"] else ""
        print(f"{mark}  {r['이름']:<{width}}  {r['초']:6.1f}초  | {r['요약']}{memo}")
    for r in failed:
        tail = [ln for ln in r["출력"].splitlines() if ln.strip()][-args.tail :]
        rel = r["로그"].relative_to(ROOT) if r["로그"].is_relative_to(ROOT) else r["로그"]
        print(f"\n---- {r['이름']} 실패 출력 (마지막 {len(tail)}줄, 전체: {rel})")
        print("\n".join(tail))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
