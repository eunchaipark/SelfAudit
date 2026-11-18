"""명세가 정한 기준값 (F-I01, D-015). 바꾸려면 명세부터 바꾼다."""

MAX_UPLOAD_BYTES = 209_715_200  # 올리는 zip 200MB
MAX_UNPACKED_BYTES = 209_715_200  # 풀린 크기 합 200MB
MAX_FILES = 20_000
MAX_FILE_BYTES = 52_428_800  # 파일 하나 50MB, 넘으면 그 파일만 건너뜀
BOMB_MIN_BYTES = 1_048_576  # 압축 폭탄 판정: 풀린 크기 1MB 초과이면서
BOMB_MAX_RATIO = 100  # 압축률 100배 초과
TARGET_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".css", ".html", ".htm", ".json", ".map"})
APP_NAME_MAX = 40
CONSENT_VERSION = "v1"
REA_PROBE_SECONDS = 5
REA_RUN_SECONDS = 120
