"""F-R02 실행 폴더 (R4) 시험. 기능명세 F-R02 예시를 옮겼다(값은 가상).

폴더는 시험이 만든 임시 폴더에만 만든다.
진짜 `%LOCALAPPDATA%`·설정 폴더·`~/.claude`는 건드리지 않는다.
㉢(위쪽 `CLAUDE.md`·`.claude`)은 위쪽까지 보므로, 위쪽이 깨끗한 임시 자리(`clean_base`)를 쓴다.
"""

from __future__ import annotations

import _winapi
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from common.fingerprint import bundle_manifest_sha256
from run import env as renv
from run import workdir as rw
from run.plan import Target
from tests.conftest import MakeBundle

BENCH = Path(__file__).resolve().parents[2]
ROOT = BENCH.parent
BATCH = "20261123-0130-first24"
RUN = "easy-1-a-1-3f2a9c10"
BUNDLE = {"assets/app.js": b"console.log('fake');\n", "index.html": b"<p>fake</p>\n"}
FAKE_CREDENTIALS = b'{"fake": "not-a-real-login"}'


def _has_marker_upward(folder: Path) -> bool:
    return any(
        os.path.lexists(d / name) for d in (folder, *folder.parents) for name in rw.UPWARD_MARKERS
    )


@pytest.fixture
def clean_base(tmp_path: Path) -> Iterator[Path]:
    """위쪽 폴더 어디에도 `CLAUDE.md`·`.claude`가 없는 임시 자리.

    이 PC의 pytest 임시 폴더는 홈 아래라 `~/.claude`가 위쪽에 있다(보고서 '요청' 1).
    그러면 드라이브의
    `Temp` 폴더에 새 임시 폴더를 만든다. 둘 다 안 되면 건너뛰지 않고 실패한다.
    """
    if not _has_marker_upward(tmp_path):
        yield tmp_path
        return
    drive_temp = Path(os.environ.get("SYSTEMDRIVE", "C:") + "\\") / "Temp"
    if not drive_temp.is_dir() or _has_marker_upward(drive_temp):
        pytest.fail("위쪽이 깨끗한 임시 자리를 찾지 못함(㉢ 시험 불가)")
    base = Path(tempfile.mkdtemp(prefix="sa-t30-", dir=drive_temp))
    try:
        yield base
    finally:
        shutil.rmtree(base)


def places_at(base: Path) -> rw.BenchPlaces:
    repo = base / "repo"
    repo.mkdir(exist_ok=True)
    return rw.BenchPlaces(repo_root=repo, local_app_data=base / "Local", user_profile=base / "home")


def prepare(
    places: rw.BenchPlaces,
    bundle: Path,
    *,
    run_id: str = RUN,
    condition: str = "A",
    expected: str | None = None,
) -> rw.PreparedRun:
    return rw.prepare_run(
        places,
        BATCH,
        run_id,
        source=bundle,
        expected=expected if expected is not None else bundle_manifest_sha256(bundle),
        condition=condition,
        python_exe=Path(sys.executable),
    )


# --- 예시 ------------------------------------------------------------------------------------


def test_F_R02_작업폴더_자리() -> None:
    places = rw.BenchPlaces(
        repo_root=Path(r"C:\project\SelfAudit"),
        local_app_data=Path(r"C:\Users\u\AppData\Local"),
        user_profile=Path(r"C:\Users\u"),
    )
    want = (
        r"C:\Users\u\AppData\Local\SelfAudit-bench-runs"
        r"\20261123-0130-first24\easy-1-a-1-3f2a9c10\target"
    )
    assert str(places.runs_root / BATCH / RUN / rw.TARGET_DIR_NAME) == want
    assert places.config_dir.name == "SelfAudit-bench-claude"
    assert places.private_dir.name == "SelfAudit-private"
    assert places.archive_dir.name == "SelfAudit-bench-archive"


def test_F_R02_실행폴더_저장소밖(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    got = prepare(places, make_bundle(BUNDLE))
    assert not rw.is_inside(got.run.run_dir, places.repo_root)
    assert got.run.target == places.runs_root / BATCH / RUN / "target"
    assert bundle_manifest_sha256(got.run.target) == got.manifest_sha256
    inside = rw.BenchPlaces(
        repo_root=places.repo_root,
        local_app_data=places.repo_root / "bench" / "Local",
        user_profile=places.user_profile,
    )
    with pytest.raises(rw.BatchStop, match="저장소 안"):
        rw.create_run_dir(inside, BATCH, RUN)


def test_F_R02_실행폴더_정션으로_저장소안이면_거절(clean_base: Path) -> None:
    places = places_at(clean_base)
    (places.repo_root / "runs").mkdir()
    places.local_app_data.mkdir()
    _winapi.CreateJunction(str(places.repo_root / "runs"), str(places.runs_root))
    with pytest.raises(rw.BatchStop, match="저장소 안"):
        rw.create_run_dir(places, BATCH, RUN)


@pytest.mark.parametrize(
    ("batch", "run"), [("../x", RUN), (BATCH, "..\\..\\x"), (BATCH, "Easy-1-a-1-3f2a9c10")]
)
def test_F_R02_ID꼴_아니면_거절(clean_base: Path, batch: str, run: str) -> None:
    with pytest.raises(rw.BatchStop, match="꼴"):
        rw.create_run_dir(places_at(clean_base), batch, run)


def test_F_R02_복사본지문_다르면_멈춤(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    bundle = make_bundle(BUNDLE)
    with pytest.raises(rw.BatchStop) as e:
        prepare(places, bundle, expected="0" * 64)
    assert e.value.rule == "㉡"


def test_F_R02_정답지지문과_맞춤(clean_base: Path, make_bundle: MakeBundle) -> None:
    bundle = make_bundle(BUNDLE)
    answers = clean_base / "answers.json"
    doc = json.loads((ROOT / "bench" / "answers" / "easy-1.json").read_text("utf-8"))
    doc["bundle_manifest_sha256"] = bundle_manifest_sha256(bundle)
    answers.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    target = Target(id="easy-1", kind="planted", bundle=bundle, answers=answers)
    assert rw.expected_manifest(target, bundle) == bundle_manifest_sha256(bundle)
    practice = Target(id="easy-1", kind="practice", bundle=bundle, answers=answers)
    with pytest.raises(rw.BatchStop, match="origin"):
        rw.expected_manifest(practice, bundle)
    mine = Target(id="blog", kind="mine", bundle=bundle, answers=None)
    assert rw.expected_manifest(mine, bundle) == bundle_manifest_sha256(bundle)


def test_F_R02_진짜번들_복사본지문_정답지와같음(clean_base: Path) -> None:
    places = places_at(clean_base)
    bundle = ROOT / "bench" / "bundles" / "easy-1"
    target = Target("easy-1", "planted", bundle, ROOT / "bench" / "answers" / "easy-1.json")
    got = prepare(places, bundle, expected=rw.expected_manifest(target, bundle))
    assert bundle_manifest_sha256(got.run.target) == rw.expected_manifest(target, bundle)


def test_F_R02_복사는_파일만_정션은_따라가지않음(clean_base: Path, make_bundle: MakeBundle) -> None:
    decoy = clean_base / "decoy"
    decoy.mkdir()
    (decoy / "marker.txt").write_text("FAKE-MARKER", encoding="utf-8")
    bundle = make_bundle(BUNDLE)
    _winapi.CreateJunction(str(decoy), str(bundle / "assets" / "jlink"))
    target = clean_base / "copy"
    target.mkdir()
    rw.copy_bundle(bundle, target)
    assert not (target / "assets" / "jlink").exists()
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == [
        "assets/app.js",
        "index.html",
    ]


def test_F_R02_target안_정션이면_멈춤(clean_base: Path) -> None:
    decoy = clean_base / "decoy"
    decoy.mkdir()
    target = clean_base / "target"
    (target / "assets").mkdir(parents=True)
    _winapi.CreateJunction(str(decoy), str(target / "assets" / "jlink"))
    with pytest.raises(rw.BatchStop) as e:
        rw.check_no_reparse(target)
    assert e.value.rule == "㉠"
    assert "assets/jlink" in e.value.detail


@pytest.mark.parametrize("marker", ["CLAUDE.md", ".claude", "claude.md"])
def test_F_R02_위쪽에_CLAUDE_md있으면_멈춤(
    clean_base: Path, make_bundle: MakeBundle, marker: str
) -> None:
    places = places_at(clean_base)
    places.runs_root.mkdir(parents=True)
    if marker == ".claude":
        (places.runs_root / marker).mkdir()
    else:
        (places.runs_root / marker).write_text("fake", encoding="utf-8")
    with pytest.raises(rw.BatchStop) as e:
        prepare(places, make_bundle(BUNDLE))
    assert e.value.rule == "㉢"
    assert "위로 3단계" in e.value.detail  # target → 실행 → 배치 → runs 맨 위
    assert str(clean_base) not in str(e.value)


def test_F_R02_target안_맨위_CLAUDE_md도_멈춤(clean_base: Path, make_bundle: MakeBundle) -> None:
    bundle = make_bundle({**BUNDLE, "CLAUDE.md": b"fake"})
    with pytest.raises(rw.BatchStop) as e:
        prepare(places_at(clean_base), bundle)
    assert (e.value.rule, "위로 0단계" in e.value.detail) == ("㉢", True)


def test_F_R02_배치폴더에_지난실행_남으면_멈춤(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    (places.runs_root / BATCH / "easy-2-b-1-00000001").mkdir(parents=True)
    with pytest.raises(rw.BatchStop) as e:
        prepare(places, make_bundle(BUNDLE))
    assert e.value.rule == "㉣"
    assert "easy-2-b-1-00000001" in e.value.detail


def test_F_R02_같은실행폴더_있으면_멈춤(clean_base: Path) -> None:
    places = places_at(clean_base)
    (places.runs_root / BATCH / RUN).mkdir(parents=True)
    with pytest.raises(rw.BatchStop) as e:
        rw.create_run_dir(places, BATCH, RUN)
    assert e.value.rule == "㉣"


def test_F_R02_빈실행_target은_빈폴더(clean_base: Path) -> None:
    places = places_at(clean_base)
    got = rw.prepare_run(
        places,
        BATCH,
        "empty-a-1-0123abcd",
        source=None,
        expected=rw.EMPTY_MANIFEST_SHA256,
        condition="A",
        python_exe=Path(sys.executable),
    )
    assert list(got.run.target.iterdir()) == []
    (got.run.target / "x.js").write_bytes(b"x")
    with pytest.raises(rw.BatchStop, match="비어 있지 않음"):
        rw.check_manifest(got.run.target, rw.EMPTY_MANIFEST_SHA256)


def test_F_R02_실행뒤_target지움(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    got = prepare(places, make_bundle(BUNDLE))
    rw.remove_run_dir(places, got.run)
    assert not got.run.run_dir.exists()
    assert list(got.run.batch_dir.iterdir()) == []
    second = prepare(places, make_bundle(BUNDLE, name="b2"), run_id="easy-1-a-2-00000002")
    assert second.run.target.is_dir()  # ㉣이 지난 실행을 보지 않음


def test_F_R02_지울자리_아니면_지우지않음(clean_base: Path) -> None:
    places = places_at(clean_base)
    other = clean_base / "keep" / BATCH / RUN
    other.mkdir(parents=True)
    fake = rw.RunDir(batch_dir=other.parent, run_dir=other, target=other / "target")
    with pytest.raises(rw.BatchStop):
        rw.remove_run_dir(places, fake)
    assert other.is_dir()


def test_F_R02_실행폴더가_정션이면_지우지않음(clean_base: Path) -> None:
    places = places_at(clean_base)
    keep = clean_base / "keep"
    keep.mkdir()
    (keep / "x.txt").write_text("keep", encoding="utf-8")
    batch = places.runs_root / BATCH
    batch.mkdir(parents=True)
    _winapi.CreateJunction(str(keep), str(batch / RUN))
    run = rw.RunDir(batch_dir=batch, run_dir=batch / RUN, target=batch / RUN / "target")
    with pytest.raises(rw.BatchStop):
        rw.remove_run_dir(places, run)
    assert (keep / "x.txt").is_file()


def test_F_R02_실행폴더가_같은배치안을_가리키는_정션이면_지우지않음(clean_base: Path) -> None:
    places = places_at(clean_base)
    batch = places.runs_root / BATCH
    other = batch / "easy-2-b-1-00000001"
    other.mkdir(parents=True)
    (other / "x.txt").write_text("keep", encoding="utf-8")
    _winapi.CreateJunction(str(other), str(batch / RUN))
    run = rw.RunDir(batch_dir=batch, run_dir=batch / RUN, target=batch / RUN / "target")
    with pytest.raises(rw.BatchStop, match="재분석"):
        rw.remove_run_dir(places, run)
    assert (other / "x.txt").is_file()


# --- settings.json ---------------------------------------------------------------------------


def test_F_R02_내앱원자료_거절규칙_꼴() -> None:
    forms = rw.deny_rule_forms(Path(r"C:\Users\u\AppData\Local\SelfAudit-private"))
    assert forms == (
        "//C:/Users/u/AppData/Local/SelfAudit-private/**",
        "//c/Users/u/AppData/Local/SelfAudit-private/**",
    )
    assert rw.deny_rules([Path(r"C:\Users\u\AppData\Local\SelfAudit-private")]) == [
        "Read(//C:/Users/u/AppData/Local/SelfAudit-private/**)",
        "Read(//c/Users/u/AppData/Local/SelfAudit-private/**)",
        "Grep(//C:/Users/u/AppData/Local/SelfAudit-private/**)",
        "Grep(//c/Users/u/AppData/Local/SelfAudit-private/**)",
        "Glob(//C:/Users/u/AppData/Local/SelfAudit-private/**)",
        "Glob(//c/Users/u/AppData/Local/SelfAudit-private/**)",
    ]


@pytest.mark.parametrize(
    "path", [r"C:\a[1]\b", r"C:\a*\b", r"C:\a(b)", "relative\\x", r"\\server\share"]
)
def test_F_R02_규칙글자_든경로_멈춤(path: str) -> None:
    with pytest.raises(rw.BatchStop):
        rw.deny_rule_forms(Path(path))


def _settings(places: rw.BenchPlaces) -> dict[str, object]:
    value = json.loads((places.config_dir / "settings.json").read_text("utf-8"))
    assert isinstance(value, dict)
    return value


def test_F_R02_settings_거절7곳·훅없음(clean_base: Path) -> None:
    places = places_at(clean_base)
    places.config_dir.mkdir(parents=True)
    (places.config_dir / ".credentials.json").write_bytes(FAKE_CREDENTIALS)
    run = rw.create_run_dir(places, BATCH, RUN)
    sibling = run.batch_dir / "easy-2-b-1-00000001"
    sibling.mkdir()  # 치우기가 실패해 남은 형제(㉣이 멈추게 하지만 거절 규칙은 둘째 층으로 남긴다)
    rw.write_settings(places, run)
    value = _settings(places)
    assert set(value) == {"hooks", "enabledPlugins", "permissions"}
    assert value["hooks"] == {} and value["enabledPlugins"] == {}
    deny = value["permissions"]["deny"]  # type: ignore[index]
    places_7 = [
        places.config_dir,
        places.private_dir,
        places.archive_dir,
        places.repo_root,
        places.user_profile / ".claude",
        places.user_profile / ".ssh",
        sibling,
    ]
    assert deny == rw.deny_rules(places_7)
    assert len(deny) == 7 * 3 * 2
    top = rw.deny_rule_forms(places.runs_root)[0]
    assert not any(top in rule for rule in deny), "실행 폴더 맨 위는 거절하지 않는다"
    assert not any(rw.deny_rule_forms(run.run_dir)[0] in rule for rule in deny)
    # 로그인 정보 파일은 그대로, 설정 폴더에는 settings.json만 더해짐
    assert (places.config_dir / ".credentials.json").read_bytes() == FAKE_CREDENTIALS
    assert sorted(p.name for p in places.config_dir.iterdir()) == [
        ".credentials.json",
        "settings.json",
    ]


def test_F_R02_형제없는_보통실행_형제줄0개(clean_base: Path) -> None:
    places = places_at(clean_base)
    run = rw.create_run_dir(places, BATCH, RUN)
    rw.write_settings(places, run)
    assert len(_settings(places)["permissions"]["deny"]) == 6 * 3 * 2  # type: ignore[index]


def test_F_R02_settings_실행마다_다시씀_문지기_미끼더함(clean_base: Path) -> None:
    places = places_at(clean_base)
    run = rw.create_run_dir(places, BATCH, RUN)
    decoy = places.local_app_data / "SelfAudit-bench-decoy"
    rw.write_settings(places, run, extra_deny=[decoy])
    with_decoy = _settings(places)["permissions"]["deny"]  # type: ignore[index]
    assert with_decoy[-6:] == rw.deny_rules([decoy])
    rw.write_settings(places, run)
    assert len(_settings(places)["permissions"]["deny"]) == 36  # type: ignore[index]
    assert not (places.config_dir / "settings.json.tmp").exists()


# --- mcp.json --------------------------------------------------------------------------------


def test_F_R02_조건A_mcp(clean_base: Path, make_bundle: MakeBundle) -> None:
    got = prepare(places_at(clean_base), make_bundle(BUNDLE))
    assert json.loads(got.mcp.path.read_text("utf-8")) == {"mcpServers": {}}
    assert got.mcp.path == got.run.run_dir / "mcp.json"


def test_F_R02_조건B_mcp_자리표시_풀림(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    got = prepare(places, make_bundle(BUNDLE), condition="B")
    value = json.loads(got.mcp.path.read_text("utf-8"))
    server = value["mcpServers"]["rea"]
    assert server["command"] == sys.executable
    args = server["args"]
    assert args[args.index("--target") + 1] == str(got.run.target)
    assert args[args.index("--env-dir") + 1] == str(got.run.run_dir / "rea-env")
    assert args[1] == str(places.repo_root / "bench" / "run" / "rea_mcp_filter.py")
    assert "<" not in got.mcp.path.read_text("utf-8")
    template = (BENCH / "run" / "mcp-B.json").read_bytes()
    assert got.mcp.template_sha256 == __import__("hashlib").sha256(template).hexdigest()


def test_F_R02_AB_틀만다름(clean_base: Path, make_bundle: MakeBundle) -> None:
    places = places_at(clean_base)
    a = prepare(places, make_bundle(BUNDLE), condition="A")
    rw.remove_run_dir(places, a.run)
    b = prepare(places, make_bundle(BUNDLE, name="b2"), run_id="easy-1-b-1-00000003", condition="B")
    assert a.mcp.template_sha256 != b.mcp.template_sha256
    assert a.mcp.path.name == b.mcp.path.name == "mcp.json"
    assert a.settings_path == b.settings_path


# --- 환경 ------------------------------------------------------------------------------------


def _source_env() -> dict[str, str]:
    real = {k: v for k, v in os.environ.items() if k.upper() in {n.upper() for n in renv.ENV_PASS}}
    return {
        **real,
        "ANTHROPIC_API_KEY": "fake-key-not-real",
        "GITHUB_TOKEN": "fake-token-not-real",
        "PATH": r"C:\evil;C:\Windows\System32",
        "PYTHONPATH": r"C:\evil",
        "NODE_OPTIONS": "--require evil",
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }


def test_F_R02_환경_허용목록만·PATH_System32(tmp_path: Path) -> None:
    config = tmp_path / "SelfAudit-bench-claude"
    env = renv.claude_env(_source_env(), config)
    allowed = {n.upper() for n in renv.ENV_PASS} | {
        "PATH",
        "CLAUDE_CONFIG_DIR",
        "DISABLE_AUTOUPDATER",
    }
    assert {k.upper() for k in env} <= allowed
    assert env["PATH"] == os.path.join(os.environ["SYSTEMROOT"], "System32")
    assert (env["CLAUDE_CONFIG_DIR"], env["DISABLE_AUTOUPDATER"]) == (str(config), "1")
    # 띄운 프로세스가 받는 환경도 같은지(셸 없이, 인자 목록으로)
    code = "import os, json, sys; sys.stdout.write(json.dumps(sorted(os.environ)))"
    out = subprocess.run(  # noqa: S603 - 시험이 고른 실행 파일·인자
        [sys._base_executable, "-I", "-S", "-c", code],  # type: ignore[attr-defined]
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    assert {k.upper() for k in json.loads(out)} == {k.upper() for k in env}


def test_F_R02_환경_이름대소문자_맞춤() -> None:
    env = renv.claude_env(
        {"systemroot": r"C:\Windows", "userprofile": r"C:\Users\u"}, Path(r"C:\c")
    )
    assert env["SystemRoot"] == r"C:\Windows" and env["USERPROFILE"] == r"C:\Users\u"
    assert env["PATH"] == r"C:\Windows\System32"


@pytest.mark.parametrize("source", [{}, {"SystemRoot": "Windows"}])
def test_F_R02_환경_SystemRoot없으면_멈춤(source: dict[str, str]) -> None:
    with pytest.raises(renv.EnvError):
        renv.claude_env(source, Path(r"C:\c"))
