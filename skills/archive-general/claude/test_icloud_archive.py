import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from test_support import Env, SCRIPT, SKILL, require_history, mirror, split, own_history_copy


@pytest.fixture
def e(tmp_path):
    return Env(tmp_path)


def test_folder_sync_moves_files_and_parks_folders(e):
    data = {"m/a.csv": b"a\n", "m/sub/b.csv": b"b\n"}
    for name, value in data.items():
        e.write(name, value)
    e.ok("sync", "m")
    assert not (e.repo / "m").exists()
    assert (e.repo / "_archive/m/sub").is_dir()
    for name, value in data.items():
        assert (e.root / "files" / name).read_bytes() == value
        assert e.records()[name]["sha256"] == hashlib.sha256(value).hexdigest()


def test_later_sync_adds_only_new_files(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    original = e.records()["m/a"]
    e.write("m/b", "b")
    e.ok("sync", "m")
    assert set(e.records()) == {"m/a", "m/b"}
    assert e.records()["m/a"] == original


def test_archive_is_sync_without_update(e):
    e.write("a", "old")
    e.ok("archive", "a")
    e.write("a", "new")
    text = e.ok("archive", "a")
    assert "changed, not updated: 1" in text
    assert (e.repo / "a").read_text() == "new"
    assert (e.root / "files/a").read_text() == "old"
    assert e.run("archive", "a", "--update").returncode == 2


def test_read_file_and_folder_in_place(e):
    e.write("m/a", "sample")
    e.ok("sync", "m")
    before = e.snapshot()
    assert str(e.root / "files/m/a") in e.ok("read", "m/a")
    assert str(e.root / "files/m") in e.ok("read", "m")
    assert e.snapshot() == before


def test_restore_one_file_from_a_folder(e):
    e.write("m/a", "a")
    e.write("m/b", "b")
    e.ok("sync", "m")
    e.ok("restore", "m/a")
    assert (e.repo / "m/a").read_text() == "a"
    assert set(e.records()) == {"m/b"}
    assert not (e.root / "files/m/a").exists()


def test_file_over_limit_is_compressed_into_one_part(e):
    e.write("m/big", b"compressible\n" * 9000)
    e.ok("sync", "m")
    assert e.records()["m/big"]["form"] == "zst×1"
    e.ok("restore", "m")
    assert (e.repo / "m/big").read_bytes() == b"compressible\n" * 9000


def test_incompressible_file_over_limit_is_split(e):
    data = os.urandom(200000)
    e.write("big", data)
    e.ok("sync", "big", "--fast")
    assert e.records()["big"]["form"] == "zst×4"
    assert all(p.stat().st_size <= 65536 for p in (e.root / ".big/big").glob("part-*.zst"))
    e.ok("restore", "big")
    assert (e.repo / "big").read_bytes() == data


def test_small_file_stays_raw(e):
    e.write("a", "tiny")
    e.ok("sync", "a")
    assert e.records()["a"]["form"] == "file"
    assert (e.root / "files/a").stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize("names", [["files", ".big", ".versions"], [".manifest.jsonl", "MANIFEST.json"], ["part-000.zst", "SHA256SUMS"]])
def test_internal_looking_names_roundtrip(e, names):
    for name in names:
        e.write("data/" + name, name)
    e.ok("sync", "data")
    e.ok("restore", "data")
    assert all((e.repo / "data" / name).read_text() == name for name in names)


def test_case_only_clash_refused(e):
    e.write("A.csv", "a")
    e.ok("sync", "A.csv")
    e.write("a.csv", "b")
    before = e.snapshot()
    assert "case-only clash" in e.refused("sync", "a.csv")
    assert e.snapshot() == before


def test_recently_changed_file_is_skipped(e):
    e.write("a", "live", age=0)
    text = e.ok("sync", "a", "--min-age", "10")
    assert "skipped" in text
    assert not e.records() and (e.repo / "a").exists()


def test_folder_with_cursor_file_is_left_alone(e):
    e.write("data/a", "live")
    e.write("data/job.cursor", "page")
    e.ok("sync", "data")
    assert not e.records()
    assert (e.repo / "data/a").exists()


def test_file_named_alone_in_busy_folder_is_skipped(e):
    e.write("data/a", "live")
    e.write("data/job.tmp-1", "working")
    e.ok("sync", "data/a")
    assert not e.records()


def test_open_file_is_skipped(e):
    path = e.write("data/a", "open")
    with path.open() as stream:
        text = e.ok("sync", "data", overrides={"ICLOUD_ARCHIVE_LSOF": "lsof", "ICLOUD_ARCHIVE_LSOF_TIMEOUT": "20"})
        assert stream.read() == "open"
    assert "skipped" in text and path.exists() and not e.records()


def test_database_with_sidecar_is_skipped(e):
    e.write("data/a.db", "db")
    e.write("data/a.db-wal", "wal")
    e.ok("sync", "data")
    assert not e.records()


def test_open_sqlite_connection_is_skipped(e):
    import sqlite3
    path = e.repo / "trace.db"
    with sqlite3.connect(str(path)) as db:
        db.execute("pragma journal_mode=wal")
        db.execute("create table t (n integer)")
        db.commit()
        e.ok("sync", "trace.db")
        assert path.exists() and not e.records()


def test_changed_file_reported_then_updated_with_old_copy_kept(e):
    e.write("a", "old")
    e.ok("sync", "a")
    e.write("a", "changed")
    e.ok("sync", "a")
    assert (e.root / "files/a").read_text() == "old"
    assert (e.repo / "a").read_text() == "changed"
    e.ok("sync", "a", "--update")
    assert (e.root / "files/a").read_text() == "changed"
    assert [p.read_text() for p in (e.root / ".versions/a").iterdir()] == ["old"]


def test_status_reports_every_state(e):
    for name in ("good", "changed", "interrupted", "missing", "lost", "corrupt", "unknown"):
        e.write(name, "hello")
        e.ok("sync", name)
    e.write("changed", "different")
    e.write("interrupted", "hello")
    record = e.records()["interrupted"]
    os.utime(e.repo / "interrupted", ns=(record["mtime_ns"], record["mtime_ns"]))
    e.write("missing", "local")
    for name in ("missing", "lost"):
        (e.root / "files" / name).unlink()
    p = e.root / "files/corrupt"
    p.chmod(0o644)
    p.write_text("bad")
    record = dict(e.records()["unknown"], format=99, op="add")
    with (e.repo / "ICLOUD.manifest.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    (e.root / "files/orphan").write_text("unknown")
    e.write("new", "new")
    out = e.run("status")
    assert out.returncode == 2
    for state in ("changed", "interrupted", "missing-remote", "lost", "corrupt", "orphan", "unknown-format"):
        assert "[" + state + "]" in out.stdout
    assert "[new]" in out.stdout


def test_status_is_read_only(e):
    e.write("m/a", "data")
    e.ok("sync", "m")
    before = e.snapshot()
    e.ok("status")
    assert e.snapshot() == before


def test_nested_claude_md_does_not_split_the_index(e):
    e.repo = e.tmp / "plain-project"
    e.repo.mkdir()
    e.write("CLAUDE.md", "root")
    e.write("pull/CLAUDE.md", "pulls")
    e.write("pull/month/CLAUDE.md", "month")
    e.write("pull/month/data/a", "data")
    e.ok("sync", "data", cwd=e.repo / "pull/month")
    assert "pull/month/data/a" in e.records()
    assert not (e.repo / "pull/ICLOUD.md").exists()


def test_existing_icloud_md_wins_over_git(e):
    e.write("docs/a", "root")
    e.ok("sync", "docs")
    nested = e.repo / "child"
    nested.mkdir()
    subprocess.run(["git", "init", "-q", str(nested)], check=True)
    e.write("child/data/a", "a")
    e.ok("sync", "data", cwd=nested)
    assert "child/data/a" in e.records()
    assert not (nested / "ICLOUD.md").exists()


def test_explicit_repo_is_used_as_is(e):
    other = e.tmp / "plain"
    other.mkdir()
    (other / "a").write_text("outside git")
    e.ok("--repo", other, "sync", "a", cwd=other)
    assert (other / "ICLOUD.md").is_file()


def test_exclude_globs_and_prefixes(e):
    for name in ("a/good", "a/skip/x", "a/z.tmp"):
        e.write(name, name)
    e.ok("sync", "a", "--exclude", "a/skip", "--exclude", "**/*.tmp")
    assert set(e.records()) == {"a/good"}
    assert (e.repo / "a/skip/x").exists() and (e.repo / "a/z.tmp").exists()


def test_refusals_have_no_side_effects(e):
    e.write("a", "a")
    before = e.snapshot()
    for path in (".", "../outside", ".git/config", "ICLOUD.md", "ICLOUD.manifest.jsonl", "bad`name", "bad\nname"):
        e.refused("sync", path)
        assert e.snapshot() == before


def test_no_delete_rule_requires_flag(e):
    e.write("AGENTS.md", "Never delete or remove anything under data/.")
    e.write("data/a", "precious")
    before = e.snapshot()
    assert "AGENTS.md:1:" in e.refused("sync", "data")
    assert e.snapshot() == before
    e.ok("sync", "data", "--allow-protected")
    assert "data/a" in e.records()


def test_symlink_inside_folder_is_skipped(e):
    e.write("data/regular", "real")
    outside = e.tmp / "outside"
    outside.write_text("do not touch")
    (e.repo / "data/link").symlink_to(outside)
    e.ok("sync", "data")
    assert set(e.records()) == {"data/regular"}
    assert outside.read_text() == "do not touch"
    assert (e.repo / "data/link").is_symlink()


@pytest.mark.parametrize("packed", [False, True])
@pytest.mark.parametrize("step", ["after-copy", "after-rename", "after-index", "after-delete"])
def test_crash_during_sync_is_recoverable(e, step, packed):
    data = os.urandom(100000) if packed else b"data\n"
    e.write("m/a", data)
    rc = e.run("sync", "m", overrides={"ICLOUD_ARCHIVE_FAULT": step})
    assert rc.returncode == 99
    e.ok("verify", "--fix")
    e.ok("sync", "m")
    assert "m/a" in e.records()
    e.ok("restore", "m")
    assert (e.repo / "m/a").read_bytes() == data


@pytest.mark.parametrize("step", ["restore-after-rename", "restore-after-index"])
def test_crash_during_restore_is_recoverable(e, step):
    e.write("m/a", "recover me")
    e.ok("sync", "m")
    result = e.run("restore", "m/a", overrides={"ICLOUD_ARCHIVE_FAULT": step})
    assert result.returncode == 99
    e.ok("verify", "--fix")
    if "m/a" in e.records():
        e.ok("restore", "m/a")
    assert (e.repo / "m/a").read_text() == "recover me"


def test_rerun_sync_adopts_identical_copy_left_by_a_crash(e):
    e.write("a", "keep")
    assert e.run("sync", "a", overrides={"ICLOUD_ARCHIVE_FAULT": "after-rename"}).returncode == 99
    assert "adopted a" in e.ok("sync", "a")
    assert not (e.repo / "a").exists() and "a" in e.records()


def test_torn_manifest_line_is_tolerated_and_fixed(e):
    e.write("a", "keep")
    e.ok("sync", "a")
    manifest = e.repo / "ICLOUD.manifest.jsonl"
    with manifest.open("a") as stream:
        stream.write('{"op":')
    assert e.run("verify").returncode == 2
    e.ok("verify", "--fix")
    assert all(isinstance(json.loads(line), dict) for line in manifest.read_text().splitlines())


def test_deleted_index_is_rebuilt_from_manifest(e):
    e.write("a", "keep")
    e.ok("sync", "a")
    (e.repo / "ICLOUD.md").unlink()
    e.ok("verify", "--fix")
    assert (e.repo / "ICLOUD.md").exists()


def test_verify_never_touches_a_changed_file(e):
    e.write("a", "old")
    e.ok("sync", "a")
    e.write("a", "edited")
    assert e.run("verify", "--fix").returncode == 2
    assert (e.repo / "a").read_text() == "edited"
    assert (e.root / "files/a").read_text() == "old"


def test_unknown_orphan_left_alone(e):
    e.write("a", "old")
    e.ok("sync", "a")
    path = e.root / "files/unknown"
    path.write_text("unknown bytes")
    assert e.run("verify", "--fix").returncode == 2
    assert path.read_text() == "unknown bytes"


def test_parallel_syncs_of_different_folders_lose_nothing(e):
    for name in ("a/x", "b/x"):
        e.write(name, name)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda name: e.run("sync", name), ("a", "b")))
    assert all(r.returncode == 0 for r in results), [(r.stdout, r.stderr) for r in results]
    assert set(e.records()) == {"a/x", "b/x"}
    e.ok("verify")


def test_parallel_syncs_of_same_folder_end_consistent(e):
    for i in range(8):
        e.write(f"m/{i}", str(i))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: e.run("sync", "m"), range(2)))
    assert len(e.records()) == 8
    assert not (e.repo / "m").exists()
    e.ok("verify")


def test_summary_counts_and_space_note(e):
    e.write("a", "data")
    output = e.ok("sync", "a")
    assert "archived: 1 (4 B)   refused: 0   skipped: 0" in output
    assert "checked on disk: all files are where they should be" in output
    assert "space: not returned (archive root is on this disk)" in output


def test_upload_status_and_evict_do_not_apply_outside_icloud(e):
    e.write("a", "data")
    e.ok("sync", "a")
    for command in ("upload-status", "evict"):
        assert "not in iCloud Drive" in e.ok(command)


def test_list_filters_by_path(e):
    e.write("m/a", "a")
    e.write("n/a", "n")
    e.ok("sync", "m", "n")
    output = e.ok("list", "m")
    assert "m/a\tformat 2\tfile\tby 3.6.0\t" in output
    assert "n/a\t" not in output


def test_records_and_manifest_carry_versions(e):
    e.write("a", "data")
    e.ok("sync", "a")
    record = e.records()["a"]
    assert record["format"] == 2 and record["by"] == "3.6.0"
    header = json.loads((e.repo / "ICLOUD.manifest.jsonl").read_text().splitlines()[0])
    assert list(header) == ["icloud_archive_manifest", "root", "id", "gen", "by", "parked"]
    assert header["by"] == "3.6.0"


def test_skill_md_version_matches_script(e):
    import re
    script_version = re.search(r'^SKILL_VERSION = "([^"]+)"', SCRIPT.read_text(), re.M)[1]
    for skill in (SKILL,):
        assert f"version: {script_version}\n" in (skill / "SKILL.md").read_text()


def test_new_archive_is_nested_under_repos(e):
    e.write("a", "data")
    e.ok("sync", "a")
    assert str(e.root).startswith(str(e.base / "repos") + "/")
    entries = list((e.base / "registry").glob("*.json"))
    assert len(entries) == 1
    value = json.loads(entries[0].read_text())
    assert value["root"] == e.root.relative_to(e.base).as_posix()
    assert value["formats"] == {"2": 1} and value["written_by"] == {"3.6.0": 1}


def test_repo_outside_home_nests_under_abs(e):
    e.write("a", "data")
    e.ok("sync", "a")
    assert e.root == e.base / "repos/_abs" / str(e.repo).lstrip("/")


def test_full_restore_removes_registry_entry(e):
    e.write("a", "data")
    e.ok("sync", "a")
    e.ok("restore", "a")
    assert not (e.base / "REGISTRY.md").exists()
    assert not list((e.base / "registry").glob("*.json"))
    assert not (e.repo / "ICLOUD.md").exists()


def test_same_path_different_repo_refused(e):
    e.write("a", "old")
    e.ok("sync", "a")
    (e.tmp / "backup").mkdir()
    for name in ("ICLOUD.md", "ICLOUD.manifest.jsonl"):
        (e.repo / name).rename(e.tmp / "backup" / name)
    subprocess.run(["git", "-C", str(e.repo), "config", "remote.origin.url", "https://example.invalid/different.git"], check=True)
    e.write("b", "new")
    before = e.snapshot()
    assert "another repo" in e.refused("sync", "b")
    assert e.snapshot() == before


def test_fresh_clone_finds_its_archive_through_the_registry(e):
    remote = "https://example.invalid/shared.git"
    subprocess.run(["git", "-C", str(e.repo), "config", "remote.origin.url", remote], check=True)
    e.write("data/a", "shared")
    e.ok("sync", "data")
    clone = e.tmp / "clone/repo"
    clone.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "config", "remote.origin.url", remote], check=True)
    original_root = e.root
    e.repo = clone
    assert "archived" in e.ok("status")
    assert not (clone / "ICLOUD.md").exists()
    e.ok("verify", "--fix")
    assert e.root == original_root and "data/a" in e.records()


def test_format_from_the_future_is_refused(e):
    e.write("a", "old")
    e.ok("sync", "a")
    record = dict(e.records()["a"], format=99, op="add")
    with (e.repo / "ICLOUD.manifest.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    before = e.snapshot()
    assert "update the skill" in e.refused("read", "a")
    e.refused("restore", "a")
    e.write("a", "new")
    e.refused("sync", "a")
    assert (e.root / "files/a").read_text() == "old"


def test_tampered_history_is_not_run(e):
    tool, release = own_history_copy(e)
    e.write("a", "old")
    e.ok("sync", "a")
    with (release / "archive.py").open("a") as stream:
        stream.write("\nraise RuntimeError('tampered')\n")
    output = e.refused("read", "--via-history", "a", script=tool / "icloud_archive.py")
    assert "not running it" in output
    assert "Traceback" not in output


def test_history_hashes_match(e):
    index = json.loads((SKILL / ".history/INDEX.json").read_text()) if (SKILL / ".history/INDEX.json").exists() else {}
    folders = {p.name for p in (SKILL / ".history").glob("*") if p.is_dir()}
    assert folders == set(index)
    for version in folders:
        release = SKILL / ".history" / version
        for line in (release / "SHA256SUMS").read_text().splitlines():
            sha, name = line.split(None, 1)
            assert hashlib.sha256((release / name.strip()).read_bytes()).hexdigest() == sha


def test_import_mirror_with_manifest(e):
    import csv
    folder, manifest, rows = mirror(e)
    before = manifest.read_bytes()
    e.ok("import", folder, "--kind", "mirror", "--manifest", manifest, "--plan")
    assert manifest.read_bytes() == before and (folder / "data/a.csv").exists()
    e.ok("import", folder, "--kind", "mirror", "--manifest", manifest)
    assert set(e.records()) == {"data/a.csv", "data/b.csv"}
    assert not folder.exists()
    with manifest.open(newline="") as stream:
        after = list(csv.DictReader(stream))
    assert len(after) == len(rows)
    for old, new in zip(rows, after):
        assert all(new[k] == v for k, v in old.items())
        assert new["imported_to"].endswith("/files/" + old["path"])
    origin = e.records()["data/a.csv"]["imported_from"]
    assert origin["row"] == 1 and origin["path"] == str(folder / "data/a.csv")


def test_import_mirror_md5_mismatch_moves_nothing_for_that_file(e):
    folder, manifest, _ = mirror(e, mismatch=True)
    output = e.refused("import", folder, "--kind", "mirror", "--manifest", manifest)
    assert "md5 mismatch" in output
    assert set(e.records()) == {"data/a.csv"}
    assert (folder / "data/b.csv").read_bytes() == b"b\n"


def test_import_mirror_refuses_unlisted_file_and_collisions(e):
    folder, manifest, _ = mirror(e)
    (folder / "unlisted").write_text("unlisted")
    e.write("data/a.csv", "local must survive")
    e.refused("import", folder, "--kind", "mirror", "--manifest", manifest)
    assert set(e.records()) == {"data/b.csv"}
    assert (folder / "unlisted").read_text() == "unlisted"
    assert (e.repo / "data/a.csv").read_text() == "local must survive"


def test_import_mirror_without_manifest(e):
    folder, _, _ = mirror(e, manifest=False)
    e.ok("import", folder, "--kind", "mirror")
    assert set(e.records()) == {"data/a.csv", "data/b.csv"}


def test_import_mirror_crash_resumes(e):
    folder, manifest, _ = mirror(e)
    args = ("import", folder, "--kind", "mirror", "--manifest", manifest)
    assert e.run(*args, overrides={"ICLOUD_ARCHIVE_FAULT": "import-after-move"}).returncode == 99
    e.ok(*args)
    assert set(e.records()) == {"data/a.csv", "data/b.csv"}
    assert not (e.root / ".import-journal.jsonl").exists()
    e.ok("verify")


def test_read_through_the_old_hand_made_path(e):
    folder, manifest, _ = mirror(e)
    old = folder / "data/a.csv"
    e.ok("import", folder, "--kind", "mirror", "--manifest", manifest)
    assert str(e.root / "files/data/a.csv") in e.ok("read", old)


def test_import_split_round_trip(e):
    folder, data = split(e)
    e.ok("import", folder, "--kind", "split", "--plan")
    assert (folder / "MANIFEST.txt").exists()
    e.ok("import", folder, "--kind", "split")
    assert (e.root / ".big/data/trace.db/imported/restore.sh").is_file()
    assert not folder.exists()
    e.ok("restore", "data/trace.db")
    assert (e.repo / "data/trace.db").read_bytes() == data


@pytest.mark.parametrize("bad", ["part", "stream"])
def test_import_split_refuses_bad_hashes_and_moves_nothing(e, bad):
    folder, _ = split(e, bad_part=bad == "part", bad_stream=bad == "stream")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    e.refused("import", folder, "--kind", "split")
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert not e.records()


def test_import_split_crash_resumes(e):
    folder, data = split(e)
    args = ("import", folder, "--kind", "split")
    assert e.run(*args, overrides={"ICLOUD_ARCHIVE_FAULT": "import-after-move"}).returncode == 99
    e.ok(*args)
    e.ok("restore", "data/trace.db")
    assert (e.repo / "data/trace.db").read_bytes() == data


def test_import_refuses_a_folder_inside_claude_archive(e):
    folder = e.base / "foreign"
    folder.mkdir(parents=True)
    (folder / "a").write_text("not an import")
    assert "use upgrade" in e.refused("import", folder, "--kind", "mirror")
    assert (folder / "a").exists()


def test_remove_empty_tree_never_removes_a_real_file(e):
    import importlib.util
    spec = importlib.util.spec_from_file_location("archive_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = e.tmp / "foreign"
    (folder / "empty").mkdir(parents=True)
    (folder / "real").write_text("keep")
    assert not module.remove_empty_tree(folder)
    assert (folder / "real").read_text() == "keep"


def test_import_accept_mismatch_only_for_the_named_file(e):
    import csv
    folder, manifest, rows = mirror(e, mismatch=True)
    rows[0]["md5"] = "0" * 32
    with manifest.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    e.refused("import", folder, "--kind", "mirror", "--manifest", manifest, "--accept-mismatch", "data/a.csv")
    assert set(e.records()) == {"data/a.csv"}
    assert (folder / "data/b.csv").exists()
    mismatch = e.records()["data/a.csv"]["imported_from"]["md5_mismatch"]
    assert mismatch["manifest_md5"] == "0" * 32
    assert mismatch["actual_md5"] == hashlib.md5(b"a\n").hexdigest()


def test_import_never_follows_a_symlink(e):
    folder, _, _ = mirror(e, manifest=False)
    outside = e.tmp / "outside"
    outside.write_text("precious")
    (folder / "link").symlink_to(outside)
    e.refused("import", folder, "--kind", "mirror")
    assert (folder / "link").is_symlink()
    assert outside.read_text() == "precious"
    assert "link" not in e.records()


def test_plain_read_of_a_huge_compressed_file_needs_full(e):
    e.write("a", b"x\n" * 50000)
    e.ok("sync", "a")
    assert "--full" in e.refused("read", "a", overrides={"ICLOUD_ARCHIVE_READ_FULL_LIMIT": "100"})
    assert "x\nx\n" in e.ok("read", "--head", "2", "a")
    output = e.ok("read", "--full", "a", overrides={"ICLOUD_ARCHIVE_READ_FULL_LIMIT": "100"})
    assert Path(output.splitlines()[0]).read_bytes() == b"x\n" * 50000


def test_old_path_inside_a_split_import_never_reassembles_the_original(e):
    folder, _ = split(e)
    old = folder / "MANIFEST.txt"
    e.ok("import", folder, "--kind", "split")
    out = e.ok("read", old)
    assert str(e.root / ".big/data/trace.db/imported/MANIFEST.txt") in out
    assert "icloud-archive-read" not in out


# The original suite makes these fixtures by executing real frozen releases.
# A6 explicitly requires skips when the original release files did not survive.
_HISTORY_CASES = [
    "test_v1_and_v2_coexist", "test_old_v1_script_still_reads_a_v2_index",
    "test_v2_restores_every_v1_form", "test_sync_skips_files_inside_a_v1_entry",
    "test_restore_of_file_inside_v1_dir_names_the_dir", "test_v1_entry_in_v2_area_blocks_sync",
    "test_upgrade_plan_changes_nothing", "test_upgrade_repo_relocates_and_converts_every_v1_row",
    "test_upgrade_unpacks_small_pack_raw", "test_registry_scan_registers_v1_archive_without_changing_icloud_md",
    "test_upgrade_one_folder_only", "test_upgrade_all_reaches_a_repo_that_is_not_here",
    "test_read_through_an_old_icloud_path_after_relocate", "test_broken_v1_reader_names_the_history_fallback",
    "test_upgrade_waits_for_icloud_upload", "test_verify_reports_ghosts_left_at_an_old_root",
]


def _history_test(name, version="1.0.0"):
    def test(e):
        historical_case(e, name, version)
    test.__name__ = name
    return test


for _name in _HISTORY_CASES:
    globals()[_name] = _history_test(_name)
test_v200_archive_read_and_restored_through_its_own_history = _history_test("test_v200_archive_read_and_restored_through_its_own_history", "2.0.0")


@pytest.mark.parametrize("step", ["relocate-after-rename", "relocate-after-index", "upgrade-after-move"])
def test_crash_during_upgrade_is_recoverable(e, step):
    frozen = require_history("1.0.0")
    e.write("old/sub/a", "data")
    e.ok("archive", "old", script=frozen)
    assert e.run("upgrade", overrides={"ICLOUD_ARCHIVE_FAULT": step}).returncode == 99
    e.ok("upgrade")
    e.ok("verify", "--fix")
    e.ok("restore", "old")
    assert (e.repo / "old/sub/a").read_text() == "data"


def historical_case(e, name, version):
    frozen = require_history(version)
    e.env["ICLOUD_ARCHIVE_PACK_THRESHOLD"] = "65536"
    if name == "test_v200_archive_read_and_restored_through_its_own_history":
        e.write("a", "older v2")
        e.ok("archive", "a", script=frozen)
        assert "via history" in e.ok("read", "--via-history", "a")
        e.ok("restore", "--via-history", "a")
        assert (e.repo / "a").read_text() == "older v2"
        return
    if name in ("test_v2_restores_every_v1_form", "test_upgrade_unpacks_small_pack_raw"):
        e.write("raw", "raw")
        e.write("old/sub/a", "old")
        data = b"packed\n" * 15000
        e.write("big", data)
        e.ok("archive", "raw", "old", "big", script=frozen)
        if name == "test_upgrade_unpacks_small_pack_raw":
            e.ok("upgrade", overrides={"ICLOUD_ARCHIVE_FILE_LIMIT": "1000000"})
            assert e.records()["big"]["form"] == "file"
        e.ok("restore", "raw", "old", "big")
        assert (e.repo / "raw").read_text() == "raw"
        assert (e.repo / "old/sub/a").read_text() == "old"
        assert (e.repo / "big").read_bytes() == data
        return
    rel = "files" if name == "test_v1_entry_in_v2_area_blocks_sync" else "old"
    if name == "test_broken_v1_reader_names_the_history_fallback":
        e.write("old", "old")
    else:
        e.write(rel + "/sub/a", "old")
    e.ok("archive", rel, script=frozen)
    if name == "test_broken_v1_reader_names_the_history_fallback":
        assert "--via-history" in e.refused("read", "old", overrides={"ICLOUD_ARCHIVE_BREAK": "fmt1-read"})
        assert "via history" in e.ok("read", "--via-history", "old", overrides={"ICLOUD_ARCHIVE_BREAK": "fmt1-read"})
    elif name == "test_v1_entry_in_v2_area_blocks_sync":
        e.write("new", "new")
        before = e.snapshot()
        e.refused("sync", "new")
        assert e.snapshot() == before
    elif name == "test_sync_skips_files_inside_a_v1_entry":
        e.write("old/new", "still live")
        e.ok("sync", "old")
        assert (e.repo / "old/new").read_text() == "still live"
        assert not e.records()
    elif name == "test_restore_of_file_inside_v1_dir_names_the_dir":
        assert "restore that folder" in e.refused("restore", "old/sub/a")
    elif name in ("test_v1_and_v2_coexist", "test_old_v1_script_still_reads_a_v2_index"):
        e.write("new", "new")
        e.ok("sync", "new")
        index = (e.repo / "ICLOUD.md").read_text()
        assert index.index("`old/`") < index.index("<!-- archive-icloud v2:")
        e.ok("read", "old", script=frozen)
        e.ok("verify")
        assert not e.records().get("old/sub/a")
    elif name == "test_registry_scan_registers_v1_archive_without_changing_icloud_md":
        before = (e.repo / "ICLOUD.md").read_bytes()
        e.ok("registry", "--scan", e.repo)
        assert (e.repo / "ICLOUD.md").read_bytes() == before
        assert (e.repo / "ICLOUD.manifest.jsonl").exists()
    elif name == "test_upgrade_plan_changes_nothing":
        before = e.snapshot()
        out = e.ok("upgrade", "--plan")
        assert "fmt1to2" in out and "relocate" in out
        assert e.snapshot() == before
    elif name == "test_upgrade_one_folder_only":
        e.write("keep/a", "keep")
        e.ok("archive", "keep", script=frozen)
        root = e.root
        e.ok("upgrade", "old")
        assert e.root == root and set(e.records()) == {"old/sub/a"}
        assert "`keep/`" in (e.repo / "ICLOUD.md").read_text()
    elif name == "test_upgrade_waits_for_icloud_upload":
        before = e.snapshot()
        e.refused("upgrade", "--wait", "0", overrides={"ICLOUD_ARCHIVE_FAKE_PENDING": "1"})
        assert e.snapshot() == before
    elif name == "test_upgrade_all_reaches_a_repo_that_is_not_here":
        e.ok("registry", "--scan", e.repo)
        before = e.root
        moved = e.tmp / "moved-repo"
        e.repo.rename(moved)
        e.ok("upgrade", "--all", cwd=e.tmp)
        e.repo = moved
        e.ok("verify", "--fix")
        assert e.root != before and "old/sub/a" in e.records()
    else:
        old_root = e.root
        old_path = old_root / "old/sub/a"
        e.ok("upgrade")
        assert set(e.records()) == {"old/sub/a"}
        if name == "test_read_through_an_old_icloud_path_after_relocate":
            assert str(e.root / "files/old/sub/a") in e.ok("read", old_path)
        elif name == "test_verify_reports_ghosts_left_at_an_old_root":
            old_root.mkdir(parents=True, exist_ok=True)
            (old_root / "ghost").write_text("unknown")
            result = e.run("verify", "--fix")
            assert result.returncode == 2 and "[ghost]" in result.stdout
            assert (old_root / "ghost").read_text() == "unknown"
        else:
            e.ok("verify")
            e.ok("restore", "old")
            assert (e.repo / "old/sub/a").read_text() == "old"
