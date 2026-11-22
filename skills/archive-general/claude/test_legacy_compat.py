"""Real 1.0.0 fixtures read by the rebuild. Missing originals are explicit skips."""
import concurrent.futures
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import pytest

from test_support import Env as CurrentEnv, SCRIPT, require_history


class Env(CurrentEnv):
    def __init__(self, tmp_path, frozen):
        super().__init__(tmp_path)
        self.frozen = frozen
        self.env.pop("ICLOUD_ARCHIVE_FILE_LIMIT", None)
        self.env.pop("ICLOUD_ARCHIVE_MIN_AGE", None)
        self.env.update(ICLOUD_ARCHIVE_PACK_THRESHOLD=str(1024**2), ICLOUD_ARCHIVE_PART_SIZE=str(256 * 1024))

    def run(self, *args, script=None, **kwargs):
        return super().run(*args, script=script or (self.frozen if args and args[0] == "archive" else SCRIPT), **kwargs)

    def write(self, path, data=b"hello\n"):
        return super().write(path, data)

    @property
    def root(self):
        return self.base


@pytest.fixture
def e(tmp_path):
    return Env(tmp_path, require_history("1.0.0"))


def cloud(e):
    text = (e.repo / "ICLOUD.md").read_text()
    return Path(re.search(r"^Root:\s*`([^`]+)`", text, re.M)[1]).expanduser()


def archive(e, rel="a", data=b"legacy\n"):
    p = e.write(rel, data)
    info = p.stat()
    e.ok("archive", rel)
    return info


def test_file_roundtrip_preserves_bytes_mtime_mode(e):
    p = e.write("a", b"exact bytes\0\xff")
    p.chmod(0o750)
    info = p.stat()
    e.ok("archive", "a")
    e.ok("restore", "a")
    assert p.read_bytes() == b"exact bytes\0\xff"
    assert p.stat().st_mtime_ns == info.st_mtime_ns
    assert p.stat().st_mode & 0o777 == 0o750


def test_dir_roundtrip_with_nested_empty_dir(e):
    e.write("d/sub/a", "data")
    (e.repo / "d/empty/deeper").mkdir(parents=True)
    e.ok("archive", "d")
    e.ok("restore", "d")
    assert (e.repo / "d/sub/a").read_text() == "data"
    assert (e.repo / "d/empty/deeper").is_dir()


def test_zero_byte_file(e):
    archive(e, data=b"")
    e.ok("restore", "a")
    assert (e.repo / "a").read_bytes() == b""


def test_multiple_paths_partial_failure_reports_each(e):
    e.write("a", "data")
    e.refused("archive", "a", "missing")
    assert not (e.repo / "a").exists()
    assert "`a`" in (e.repo / "ICLOUD.md").read_text()


def test_restore_recreates_missing_parents(e):
    archive(e, "d/sub/a")
    (e.repo / "d/sub").rmdir()
    (e.repo / "d").rmdir()
    e.ok("restore", "d/sub/a")
    assert (e.repo / "d/sub/a").read_bytes() == b"legacy\n"


def test_index_stays_sorted_and_light(e):
    for rel in ("z", "a", "m"):
        archive(e, rel)
    text = (e.repo / "ICLOUD.md").read_text()
    assert text.index("`a`") < text.index("`m`") < text.index("`z`")
    assert len(text) < 10000


@pytest.mark.parametrize("name", ["with space/file name.csv", "emoji 📦/✓.txt", "a|b.txt", "-leading-dash.txt", "deep/" * 20 + "long_" * 20 + ".txt"])
def test_odd_names_roundtrip(e, name):
    archive(e, name)
    e.ok("restore", "./" + name)
    assert (e.repo / name).read_bytes() == b"legacy\n"


def test_unicode_nfd_archive_nfc_restore(e):
    name = unicodedata.normalize("NFD", "café.txt")
    archive(e, name)
    e.ok("restore", "café.txt")
    assert (e.repo / "café.txt").read_bytes() == b"legacy\n"


def test_backtick_and_newline_refused(e):
    for name in ("bad`name", "bad\nname"):
        e.write(name, "keep")
        before = e.snapshot()
        e.refused("archive", name)
        assert e.snapshot() == before


def test_case_only_clash_refused_on_case_insensitive_fs(e):
    archive(e, "A")
    e.write("a", "other")
    before = e.snapshot()
    e.refused("archive", "a")
    assert e.snapshot() == before


def test_refusals_have_no_side_effects(e):
    e.write("a", "keep")
    before = e.snapshot()
    for rel in ("missing", "../outside", ".git/config", "."):
        e.refused("archive", rel)
        assert e.snapshot() == before


def test_archiving_index_itself_refused(e):
    archive(e)
    before = e.snapshot()
    e.refused("archive", "ICLOUD.md")
    assert e.snapshot() == before


def test_no_project_root_refused(e):
    directory = e.tmp / "no-project"
    directory.mkdir()
    (directory / "a").write_text("keep")
    e.refused("archive", "a", cwd=directory)
    assert (directory / "a").read_text() == "keep"


def test_non_git_root_from_claude_md(e):
    directory = e.tmp / "plain-project"
    directory.mkdir()
    e.repo = directory
    e.write("CLAUDE.md", "plain project")
    archive(e)
    e.ok("restore", "a")


def test_non_git_explicit_repo(e):
    directory = e.tmp / "plain-project"
    directory.mkdir()
    e.repo = directory
    e.write("a", "data")
    e.ok("--repo", directory, "archive", "a", script=e.frozen)
    e.ok("--repo", directory, "restore", "a")
    assert (directory / "a").read_text() == "data"


def test_already_archived_refused(e):
    archive(e)
    before = e.snapshot()
    e.refused("archive", "a")
    assert e.snapshot() == before


def test_restore_refuses_to_overwrite_local(e):
    archive(e)
    e.write("a", "new local")
    before = e.snapshot()
    e.refused("restore", "a")
    assert e.snapshot() == before


def test_archive_refuses_when_icloud_already_has_it(e):
    archive(e)
    (cloud(e) / "b").write_text("unknown")
    e.write("b", "different")
    before = e.snapshot()
    e.refused("archive", "b")
    assert e.snapshot() == before


def test_restore_when_icloud_copy_missing(e):
    archive(e)
    (cloud(e) / "a").unlink()
    before = e.snapshot()
    e.refused("restore", "a")
    assert e.snapshot() == before


def test_run_from_subdir_stores_repo_relative(e):
    e.write("d/a", "data")
    e.ok("archive", "a", cwd=e.repo / "d")
    assert "`d/a`" in (e.repo / "ICLOUD.md").read_text()


def test_same_dir_name_different_repos_get_different_ids(e):
    archive(e)
    first = cloud(e)
    other = e.tmp / "other/repo"
    other.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    e.repo = other
    archive(e)
    assert cloud(e) != first


def test_same_remote_shares_id(e):
    remote = "https://example.invalid/shared.git"
    subprocess.run(["git", "-C", str(e.repo), "config", "remote.origin.url", remote], check=True)
    archive(e)
    first = cloud(e)
    other = e.tmp / "other/repo"
    other.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    subprocess.run(["git", "-C", str(other), "config", "remote.origin.url", remote], check=True)
    e.repo = other
    archive(e, "b")
    assert cloud(e) == first


def test_root_line_in_index_is_source_of_truth(e):
    archive(e)
    root = cloud(e)
    target = e.base / "moved-root"
    root.rename(target)
    index = e.repo / "ICLOUD.md"
    index.write_text(index.read_text().replace(str(root), str(target)))
    e.ok("restore", "a")
    assert (e.repo / "a").read_bytes() == b"legacy\n"


def test_hand_written_prose_is_preserved(e):
    archive(e)
    index = e.repo / "ICLOUD.md"
    index.write_text("User's own note.\n" + index.read_text())
    e.write("b", "data")
    e.ok("sync", "b")
    assert index.read_text().startswith("User's own note.\n")


def test_malformed_index_refuses_everything(e):
    archive(e)
    index = e.repo / "ICLOUD.md"
    index.write_text(index.read_text().replace("Root:", "Missing:"))
    before = e.snapshot()
    e.refused("read", "a")
    e.refused("restore", "a")
    assert e.snapshot() == before


def test_large_file_is_packed_into_parts_and_restores_identically(e):
    data = os.urandom(2 * 1024**2)
    archive(e, data=data)
    assert len(list((cloud(e) / "a.packed").glob("part-*"))) > 1
    e.ok("restore", "a")
    assert (e.repo / "a").read_bytes() == data


def test_compressible_file_and_fast_mode(e):
    data = b"compressible\n" * 100000
    e.write("a", data)
    e.ok("archive", "a", "--fast")
    e.ok("restore", "a")
    assert (e.repo / "a").read_bytes() == data


def test_small_sqlite_db_is_always_packed(e):
    archive(e, "a.sqlite", b"SQLite format 3\0" + b"x" * 100)
    assert "zst×" in (e.repo / "ICLOUD.md").read_text()


def test_read_packed_decompresses_to_temp(e):
    archive(e, data=b"x\n" * 600000)
    location = Path(e.ok("read", "a").splitlines()[0])
    assert location.read_bytes() == b"x\n" * 600000
    assert not (e.repo / "a").exists()


@pytest.mark.parametrize("damage", ["corrupt", "missing", "manifest"])
def test_damaged_pack_refuses_restore_and_changes_nothing(e, damage):
    archive(e, data=b"x\n" * 600000)
    pack = cloud(e) / "a.packed"
    part = next(pack.glob("part-*.zst"))
    if damage == "corrupt":
        part.write_bytes(b"bad")
    elif damage == "missing":
        part.unlink()
    else:
        (pack / "MANIFEST.json").write_text("{}")
    before = e.snapshot()
    e.refused("restore", "a")
    assert e.snapshot() == before


def test_open_file_refused(e):
    path = e.write("a", "open")
    with path.open():
        e.refused("archive", "a", overrides={"ICLOUD_ARCHIVE_LSOF": "lsof"})
    assert path.exists()


def test_sqlite_sidecar_refused(e):
    e.write("a.db", "db")
    e.write("a.db-wal", "wal")
    e.refused("archive", "a.db")
    assert (e.repo / "a.db").exists()


def test_no_delete_rule_requires_explicit_flag(e):
    e.write("CLAUDE.md", "Never delete anything.")
    e.write("a", "data")
    before = e.snapshot()
    e.refused("archive", "a")
    assert e.snapshot() == before
    e.ok("archive", "a", "--allow-protected")


def test_dir_with_large_file_refused(e):
    e.write("d/a", os.urandom(2 * 1024**2))
    before = e.snapshot()
    e.refused("archive", "d")
    assert e.snapshot() == before


def test_not_enough_space_refused_up_front(e):
    e.write("a", "data")
    before = e.snapshot()
    e.refused("archive", "a", overrides={"ICLOUD_ARCHIVE_MARGIN": str(10**18)})
    assert e.snapshot() == before


@pytest.mark.parametrize("packed", [False, True])
def test_disk_fills_mid_copy_original_untouched(e, packed):
    if sys.platform != "darwin" or not shutil.which("hdiutil"):
        pytest.skip("macOS disk image fixture unavailable")
    image, mount = e.tmp / "disk.dmg", e.tmp / "volume"
    subprocess.run(["hdiutil", "create", "-quiet", "-size", "8m", "-fs", "HFS+", "-volname", "archive-test", str(image)], check=True)
    mount.mkdir()
    subprocess.run(["hdiutil", "attach", "-quiet", "-mountpoint", str(mount), str(image)], check=True)
    try:
        # The estimate is small for a compressible prefix; the random suffix fills
        # the tiny test volume while streaming. The source must survive ENOSPC.
        data = (b"x" * 32 * 1024**2 + os.urandom(12 * 1024**2)) if packed else os.urandom(12 * 1024**2)
        e.write("a", data)
        out = e.run("archive", "a", overrides={"ICLOUD_ARCHIVE_ROOT": str(mount / "archive"), "ICLOUD_ARCHIVE_MARGIN": "0"})
        assert out.returncode == 1
        assert (e.repo / "a").read_bytes() == data
    finally:
        subprocess.run(["hdiutil", "detach", "-quiet", str(mount)], check=True)


@pytest.mark.parametrize("kind", ["file", "dir", "packed"])
@pytest.mark.parametrize("step", ["after-copy", "after-rename", "after-index"])
def test_crash_during_archive_is_recoverable(e, step, kind):
    rel, data = ("d", b"data") if kind == "dir" else ("a", os.urandom(2 * 1024**2) if kind == "packed" else b"data")
    e.write("d/a" if kind == "dir" else rel, data)
    assert e.run("archive", rel, overrides={"ICLOUD_ARCHIVE_FAULT": step}).returncode == 99
    e.ok("verify", "--fix")
    if (e.repo / rel).exists():
        e.ok("archive", rel)
    e.ok("restore", rel)
    assert (e.repo / ("d/a" if kind == "dir" else rel)).read_bytes() == data


@pytest.mark.parametrize("step", ["restore-after-rename", "restore-after-index"])
def test_crash_during_restore_is_recoverable(e, step):
    archive(e)
    assert e.run("restore", "a", overrides={"ICLOUD_ARCHIVE_FAULT": step}).returncode == 99
    e.ok("verify", "--fix")
    if not (e.repo / "a").exists():
        e.ok("restore", "a")
    assert (e.repo / "a").read_bytes() == b"legacy\n"


def test_verify_never_touches_differing_copies(e):
    archive(e)
    e.write("a", "different")
    before = e.snapshot()
    assert e.run("verify", "--fix").returncode == 2
    assert e.snapshot() == before


def test_unknown_orphan_left_alone(e):
    archive(e)
    orphan = cloud(e) / "unknown"
    orphan.write_text("unknown")
    assert e.run("verify", "--fix").returncode == 2
    assert orphan.read_text() == "unknown"


def test_finder_litter_is_ignored(e):
    archive(e)
    (cloud(e) / ".DS_Store").write_text("finder")
    e.ok("verify")


def test_parallel_archives_of_different_files_lose_nothing(e):
    e.write("a", "a")
    e.write("b", "b")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda p: e.run("archive", p), ("a", "b")))
    assert all(r.returncode == 0 for r in results)
    e.ok("restore", "a", "b")
    assert (e.repo / "a").read_text() == "a" and (e.repo / "b").read_text() == "b"


def test_parallel_archives_of_same_file_exactly_one_wins(e):
    e.write("a", "a")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: e.run("archive", "a"), range(2)))
    assert sorted(r.returncode for r in results) == [0, 1]
    e.ok("restore", "a")


def test_archive_restore_race_ends_consistent(e):
    archive(e)
    e.write("b", "b")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = [pool.submit(e.run, "archive", "b"), pool.submit(e.run, "restore", "a")]
        assert all(f.result().returncode == 0 for f in results)
    e.ok("verify")
    assert (e.repo / "a").read_bytes() == b"legacy\n"


def test_parallel_restores_of_different_files(e):
    archive(e, "a")
    archive(e, "b")
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda p: e.run("restore", p), ("a", "b")))
    assert all(r.returncode == 0 for r in results)
    assert (e.repo / "a").exists() and (e.repo / "b").exists()


def test_lock_timeout_refuses_cleanly(e):
    import fcntl
    archive(e)
    e.locks.mkdir(exist_ok=True)
    with (e.locks / ("icloud-archive-" + cloud(e).name + ".lock")).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        out = e.run("archive", "missing", overrides={"ICLOUD_ARCHIVE_LOCK_TIMEOUT": "0.1"})
        assert out.returncode == 1 and "REFUSED" in out.stderr


def test_archive_summary_confirms_files_from_disk(e):
    e.write("a", "data")
    assert "checked on disk: all files are where they should be" in e.ok("archive", "a")


def test_restore_summary_after_last_entry_removes_index(e):
    archive(e)
    assert "restored: 1" in e.ok("restore", "a")
    assert not (e.repo / "ICLOUD.md").exists()


def test_summary_counts_refusals(e):
    e.write("a", "a")
    output = e.refused("archive", "a", "missing")
    assert "refused: 1" in output


def test_upload_status_and_evict_do_not_apply_outside_icloud(e):
    archive(e)
    assert "not in iCloud Drive" in e.ok("upload-status")
    assert "not in iCloud Drive" in e.ok("evict")


def test_read_file_inside_archived_dir(e):
    e.write("d/a", "data")
    e.ok("archive", "d")
    assert str(cloud(e) / "d/a") in e.ok("read", "d/a")


def test_read_head_streams_packed(e):
    archive(e, data=b"header\n" + b"row\n" * 500000)
    output = e.ok("read", "--head", "1", "a")
    assert output.startswith("header\n")
    assert not (e.repo / "a").exists()
