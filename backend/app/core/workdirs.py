"""격리 폴더 `<데이터 폴더>/work/<점검ID>/` 지우기 (F-I01 11, F-P03 2, 점검 지우기).

앱 지우기와 점검 지우기가 같은 것을 쓴다. 지우기 전에 그 경로가 work 바로 아래의 실제 폴더인지
확인한다: 심볼릭 링크·정션이면 따라가 work 밖을 지울 수 있으므로 지우지 않는다(보안규칙 5장).
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

log = logging.getLogger("selfaudit")


def _is_own_folder(work_root: Path, folder: Path) -> bool:
    """folder가 링크가 아닌 실제 폴더이고, 풀어 낸 경로가 work 바로 아래인지."""
    if folder.is_symlink() or os.path.isjunction(folder) or not folder.is_dir():
        return False
    return folder.resolve().parent == work_root.resolve()


def remove_work_dir(work_root: Path, scan_id: int) -> bool:
    """점검 하나의 격리 폴더를 지운다. 없으면 아무것도 하지 않는다. 지웠으면 True.

    못 지우면(사용 중인 파일 등) 오류로 올리지 않고 로그만 남긴다. 남은 폴더는 서버가 다음에
    시작할 때 지운다(F-I01 12). 링크이거나 work 밖이면 지우지 않고 로그를 남긴다.
    """
    folder = work_root / str(scan_id)
    if not folder.exists() and not folder.is_symlink():
        return False
    if not _is_own_folder(work_root, folder):
        log.warning("격리 폴더가 아니어서 지우지 않았습니다: 점검 %d", scan_id)
        return False
    try:
        shutil.rmtree(folder)
    except OSError as err:
        log.warning("격리 폴더를 지우지 못했습니다: 점검 %d (%s)", scan_id, type(err).__name__)
        return False
    return True


def remove_work_dirs(work_root: Path, scan_ids: Iterable[int]) -> None:
    """F-P03 2 점검 여럿의 격리 폴더를 지운다 (앱 지우기). DB를 지운 뒤에 부른다."""
    for scan_id in scan_ids:
        remove_work_dir(work_root, scan_id)
