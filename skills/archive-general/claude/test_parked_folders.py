import json
import os
from pathlib import Path
import time
import unicodedata

import pytest

from test_icloud_archive import Env
from test_support import SCRIPT, require_history, mirror, own_history_copy


@pytest.fixture
def e(tmp_path):
    return Env(tmp_path)


def month(e):
    e.write("m/AUG/a.csv", "a")
    e.write("m/AUG/sub/b.csv", "b")
    e.write("mixed/old.csv", "old")
    e.write("mixed/new.csv", "new")
    (e.repo / "m/AUG/empty/deeper").mkdir(parents=True)
    e.age_folders()


def parked(e, rel):
    assert (e.repo / "_archive" / rel).is_dir()
    assert not (e.repo / rel).exists()


def test_sync_parks_folders_that_hold_only_archived_files(e):
    month(e)
    e.ok("sync", "m")
    parked(e, "m/AUG/sub")
    parked(e, "m/AUG/empty/deeper")
    assert (e.repo / "mixed/old.csv").exists()


def test_partly_archived_folder_stays(e):
    month(e)
    e.ok("sync", "mixed", "--exclude", "mixed/new.csv")
    assert (e.repo / "mixed/new.csv").is_file()
    assert not (e.repo / "_archive/mixed").exists()
    assert "→ _archive/mixed/" not in e.ok("tidy", "--plan")


def test_next_month_merges_into_the_parked_tree(e):
    month(e)
    e.ok("sync", "m")
    e.write("m/SEP/c.csv", "c")
    e.ok("sync", "m")
    parked(e, "m/SEP")
    parked(e, "m/AUG")


def test_folders_without_records_follow_their_parent_both_ways(e):
    month(e)
    e.ok("sync", "m")
    parked(e, "m/AUG/empty/deeper")
    e.ok("restore", "m/AUG/a.csv")
    assert (e.repo / "m/AUG/empty/deeper").is_dir()
    assert (e.repo / "_archive/m/AUG/sub").is_dir()


def test_sync_of_single_files_parks_their_folder(e):
    e.write("a/b/c", "c")
    e.ok("sync", "a/b/c")
    parked(e, "a/b")


def test_empty_folder_without_archived_files_never_moves(e):
    (e.repo / "empty/sub").mkdir(parents=True)
    e.write("m/a", "a")
    e.ok("sync", "m")
    e.ok("tidy")
    assert (e.repo / "empty/sub").is_dir()
    assert not (e.repo / "_archive/empty").exists()


def test_ds_store_is_carried_and_the_run_converges(e):
    e.write("m/a", "a")
    e.write("m/.DS_Store", b"finder")
    e.ok("sync", "m")
    parked(e, "m")
    assert (e.repo / "_archive/m/.DS_Store").read_bytes() == b"finder"
    assert "nothing to move" in e.ok("tidy", "--plan")


def test_nfd_folder_names_park_and_restore(e):
    name = unicodedata.normalize("NFD", "café")
    e.write(name + "/a", "unicode")
    e.ok("sync", name)
    assert "café/a" in e.records()
    e.ok("restore", "café/a")
    assert (e.repo / name / "a").read_text() == "unicode"


def test_sync_of_the_park_folder_is_skipped_not_refused(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    before = e.snapshot()
    assert "skipped" in e.ok("sync", "_archive")
    assert e.snapshot() == before


def test_keep_file_pins_its_folder(e):
    e.write("m/a", "a")
    e.write("m/.keep", b"")
    e.ok("sync", "m")
    assert (e.repo / "m/.keep").exists()
    assert set(e.records()) == {"m/a"}
    assert not (e.repo / "_archive/m").exists()


def test_restore_one_file_brings_back_its_folder_only(e):
    month(e)
    e.ok("sync", "m")
    e.ok("restore", "m/AUG/a.csv")
    assert (e.repo / "m/AUG/a.csv").read_text() == "a"
    parked(e, "m/AUG/sub")
    assert "m/AUG/sub/b.csv" in e.records()


def test_full_restore_removes_the_park_folder(e):
    month(e)
    e.ok("sync", "m")
    e.ok("restore", "m")
    assert (e.repo / "m/AUG/sub/b.csv").read_text() == "b"
    assert not (e.repo / "_archive").exists()


def test_restore_works_when_the_park_folder_was_deleted(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    (e.repo / "_archive/m").rmdir()
    (e.repo / "_archive").rmdir()
    e.ok("restore", "m/a")
    assert (e.repo / "m/a").read_text() == "a"


def test_paths_under_the_park_folder_mean_the_same_path(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    assert str(e.root / "files/m/a") in e.ok("read", "_archive/m/a")
    assert "m/a\tformat 2" in e.ok("list", "_archive/m")
    e.ok("restore", "_archive/m/a")
    assert (e.repo / "m/a").read_text() == "a"


def test_via_history_runs_from_a_subfolder(e):
    tool, _ = own_history_copy(e)
    e.write("m/a", "a")
    e.ok("sync", "m")
    folder = e.repo / "working"
    folder.mkdir()
    e.ok("restore", "--via-history", "../_archive/m/a", script=tool / "icloud_archive.py", cwd=folder)
    assert (e.repo / "m/a").read_text() == "a"


def test_age_guard_keeps_a_folder_changed_by_someone_else(e):
    e.write("m/a", "a")
    e.age_folders()
    os.utime(e.repo / "m", None)
    text = e.ok("sync", "m", "--min-age", "10")
    assert "kept m/" in text
    assert (e.repo / "m").is_dir()
    e.age_folders()
    e.ok("tidy", "--min-age", "10")
    parked(e, "m")
    e.write("outer/held", "held")
    e.write("outer/old/a", "archived")
    e.age_folders()
    stamp = (e.repo / "outer").stat().st_mtime_ns
    e.ok("sync", "outer/old", "--min-age", "10")
    assert (e.repo / "outer").stat().st_mtime_ns == stamp


def test_a_folder_changed_just_before_the_run_stays(e):
    e.write("m/a", "a")
    e.ok("sync", "m", "--min-age", "10")
    assert (e.repo / "m").is_dir()
    assert "m/a" in e.records()


def test_ledger_spots_another_program_between_this_runs_changes(e):
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_subject", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = e.repo / "m"
    folder.mkdir()
    old = time.time() - 3600
    os.utime(folder, (old, old))
    ledger = module.Ledger()
    ledger.before(folder)
    (folder / "a").write_text("own change")
    ledger.after(folder)
    (folder / "external").write_text("another process")
    ledger.before(folder)
    (folder / "a").unlink()
    ledger.after(folder)
    assert ledger.young(folder, 0) == "changed by another program during this run"


def test_folder_in_use_is_kept(e):
    e.write("m/a", "a")
    opened = e.tmp / "open-lsof"
    opened.write_text(f"#!/bin/sh\nprintf '%s\\n' 'n{e.repo}/m'\n")
    opened.chmod(0o755)
    e.ok("sync", "m", overrides={"ICLOUD_ARCHIVE_LSOF": str(opened)})
    assert (e.repo / "m").is_dir()
    assert "m/a" in e.records()


def test_the_scripts_own_working_folder_is_kept(e):
    e.write("m/a", "a")
    text = e.ok("sync", "a", cwd=e.repo / "m")
    assert "kept m/" in text
    assert (e.repo / "m").is_dir()


@pytest.mark.parametrize("failure", ["missing", "fails", "hangs"])
def test_no_folder_moves_when_lsof_cannot_answer(e, failure):
    e.write("m/a", "a")
    fake = e.tmp / "broken-lsof"
    if failure != "missing":
        fake.write_text("#!/bin/sh\n" + ("sleep 5\n" if failure == "hangs" else "exit 2\n"))
        fake.chmod(0o755)
    e.ok("sync", "m", overrides={"ICLOUD_ARCHIVE_LSOF": str(fake), "ICLOUD_ARCHIVE_LSOF_TIMEOUT": "0.1"})
    assert (e.repo / "m").is_dir()
    before = e.snapshot()
    e.refused("tidy", overrides={"ICLOUD_ARCHIVE_LSOF": str(fake), "ICLOUD_ARCHIVE_LSOF_TIMEOUT": "0.1"})
    assert e.snapshot() == before


def test_symlink_into_a_folder_keeps_it(e):
    e.write("m/a", "a")
    (e.repo / "link").symlink_to(e.repo / "m", target_is_directory=True)
    e.ok("sync", "m")
    assert (e.repo / "m").is_dir()
    assert (e.repo / "link").is_symlink()


def test_excluded_folder_stays(e):
    e.write("m/a", "a")
    (e.repo / "m/empty").mkdir()
    e.ok("sync", "m", "--exclude", "m/empty")
    assert (e.repo / "m/empty").is_dir()
    assert not (e.repo / "_archive/m").exists()


def test_nested_repo_and_submodule_link_keep_their_folders(e):
    e.write("m/a", "a")
    e.write("m/submodule/.git", "gitdir: elsewhere")
    e.write("m/submodule/data", "data")
    e.ok("sync", "m")
    assert (e.repo / "m/submodule/.git").read_text() == "gitdir: elsewhere"
    assert "m/submodule/.git" not in e.records()
    assert not (e.repo / "_archive/m").exists()


def test_a_file_written_during_the_move_keeps_its_folder(e):
    e.write("m/a", "a")
    e.ok("sync", "m", overrides={"ICLOUD_ARCHIVE_RACE_FILE": "m/raced"})
    assert (e.repo / "m/raced").is_file()
    assert not (e.repo / "_archive/m").exists()


@pytest.mark.parametrize("kind", ["symlink", "file", "dangling"])
def test_park_folder_must_be_a_plain_folder(e, kind):
    e.write("a", "a")
    e.ok("sync", "a")
    park = e.repo / "_archive"
    if kind == "file":
        park.write_text("own file")
    else:
        park.symlink_to(e.tmp if kind == "symlink" else e.tmp / "does-not-exist", target_is_directory=True)
    before = e.snapshot()
    e.refused("tidy")
    assert e.snapshot() == before


def test_files_in_the_park_folder_are_never_touched(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    e.write("_archive/m/own", "do not touch")
    output = e.ok("tidy")
    assert "[parked-file]" in output
    assert (e.repo / "_archive/m/own").read_text() == "do not touch"
    assert e.run("verify", "--fix").returncode == 2
    assert (e.repo / "_archive/m/own").read_text() == "do not touch"


@pytest.mark.parametrize("name", ["_ARCHIVE/", "_archive/notes.txt"])
def test_a_taken_name_keeps_folders_in_place(e, name):
    if name.endswith("/"):
        (e.repo / name).mkdir()
    else:
        e.write(name, "own file")
    e.write("m/a", "a")
    assert "folders stay in place" in e.ok("sync", "m")
    assert (e.repo / "m").is_dir()
    assert "park-dir" in e.ok("status")


def test_deleted_index_is_rebuilt_with_the_line(e):
    e.write("m/a", "a")
    e.ok("sync", "m")
    (e.repo / "ICLOUD.md").unlink()
    e.ok("verify", "--fix")
    assert "Parked folders: `_archive/`" in (e.repo / "ICLOUD.md").read_text()


def test_sync_while_the_icloud_index_is_newer_keeps_every_record(e):
    e.write("a", "a")
    e.ok("sync", "a")
    manifest = e.repo / "ICLOUD.manifest.jsonl"
    old = manifest.read_bytes()
    e.write("b", "b")
    e.ok("sync", "b")
    manifest.write_bytes(old)
    e.write("c", "c")
    e.ok("sync", "c")
    assert set(e.records()) == {"a", "b", "c"}
    e.ok("verify")


@pytest.mark.parametrize("step", ["tidy-after-mkdir", "tidy-after-rmdir"])
def test_crash_during_a_move_converges(e, step):
    e.write("m/sub/a", "a")
    assert e.run("sync", "m", overrides={"ICLOUD_ARCHIVE_FAULT": step}).returncode == 99
    e.ok("tidy")
    parked(e, "m/sub")
    assert "nothing to move" in e.ok("tidy", "--plan")


def test_crash_while_moving_back_converges(e):
    month(e)
    e.ok("sync", "m")
    # Restoring a sibling brings back empty record-less directories at the end.
    assert e.run("restore", "m/AUG/a.csv", overrides={"ICLOUD_ARCHIVE_FAULT": "tidy-after-mkdir"}).returncode == 99
    e.ok("tidy")
    e.ok("verify")
    assert (e.repo / "m/AUG/a.csv").read_text() == "a"


def test_import_into_a_parked_repo_parks_the_structure(e):
    folder, _, _ = mirror(e, manifest=False)
    e.ok("import", folder, "--kind", "mirror")
    parked(e, "data")


def test_remove_empty_tree_keeps_an_icloud_placeholder(e):
    import importlib.util
    spec = importlib.util.spec_from_file_location("empty_subject", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    folder = e.tmp / "foreign"
    folder.mkdir()
    (folder / ".evicted.icloud").write_bytes(b"")
    assert not module.remove_empty_tree(folder)
    assert (folder / ".evicted.icloud").exists()


def test_import_keeps_icloud_placeholders(e):
    folder, _, _ = mirror(e, manifest=False)
    (folder / ".evicted.icloud").write_bytes(b"")
    e.refused("import", folder, "--kind", "mirror")
    assert (folder / ".evicted.icloud").exists()
    assert ".evicted.icloud" not in e.records()


_OLD_CASES = [
    "test_tidy_plan_is_read_only_and_tidy_refuses_an_old_repo",
    "test_old_release_restore_then_23_matches_a_23_restore",
    "test_repo_archived_by_221_keeps_folders_until_upgraded",
    "test_park_step_neither_waits_nor_refuses_while_an_upload_is_pending",
    "test_park_step_changes_nothing_in_icloud", "test_the_mirror_never_turns_on_parking",
    "test_upgrade_all_parks_each_repo_or_says_why_not", "test_records_under_the_name_refuse_it",
    "test_crash_after_the_setting_is_saved_converges",
]


def _old_test(name, version="2.2.1"):
    def test(e):
        historical_park_case(e, name, version)
    test.__name__ = name
    return test


for _name in _OLD_CASES:
    globals()[_name] = _old_test(_name)
test_setting_survives_v1_deleting_icloud_md = _old_test("test_setting_survives_v1_deleting_icloud_md", "1.0.0")
test_release_200_on_a_parked_pure_v2_repo = _old_test("test_release_200_on_a_parked_pure_v2_repo", "2.0.0")


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0", "2.2.1"])
def test_old_releases_work_on_a_parked_repo(e, version):
    frozen = require_history(version)
    month(e)
    e.ok("sync", "m")
    for command in (("read", "m/AUG/a.csv"), ("list",), ("status",), ("verify",)):
        e.ok(*command, script=frozen)
    parked(e, "m/AUG")


@pytest.mark.parametrize("seed", [1, 2])
def test_random_operations_stay_consistent(e, seed):
    import random
    frozen = require_history("2.2.1")
    rng, written = random.Random(seed), {}
    for step in range(24):
        records = e.records()
        action = rng.choice(["write", "sync", "restore", "tidy", "old", "empty"])
        if action == "write":
            rel = f"m{rng.randrange(6)}/f{step}"
            written[rel] = f"{seed}:{step}"
            e.write(rel, written[rel])
        elif action == "sync":
            for i in range(6):
                if (e.repo / f"m{i}").exists():
                    e.ok("sync", f"m{i}")
        elif action in ("restore", "old") and records:
            rel = rng.choice(sorted(records))
            e.ok("restore", rel, **({"script": frozen} if action == "old" else {}))
        elif action == "empty":
            (e.repo / f"empty{step}").mkdir()
        elif action == "tidy":
            e.ok("tidy")
            assert "nothing to move" in e.ok("tidy", "--plan")
        result = e.run("verify")
        if result.returncode:
            findings = [line for line in result.stdout.splitlines() if line.startswith("[")]
            assert all(line.startswith(("[park-setting]", "[index]")) for line in findings)
            e.ok("verify", "--fix")
        e.ok("verify", script=frozen)
        records = e.records()
        for rel, data in written.items():
            assert (e.repo / rel).exists() != (rel in records)
            if (e.repo / rel).exists():
                assert (e.repo / rel).read_text() == data
        assert not [p for p in (e.repo / "_archive").glob("**/*") if p.is_file()]
    for rel in list(e.records()):
        e.ok("restore", rel)
    assert all((e.repo / rel).read_text() == data for rel, data in written.items())


def historical_park_case(e, name, version):
    frozen = require_history(version)
    if name == "test_setting_survives_v1_deleting_icloud_md":
        e.write("old", "old")
        e.ok("archive", "old", script=frozen)
        e.write("m/a", "a")
        e.ok("sync", "m")
        e.ok("upgrade")
        e.ok("restore", "old", script=frozen)
        assert not (e.repo / "ICLOUD.md").exists()
        e.ok("verify", "--fix")
        assert "Parked folders: `_archive/`" in (e.repo / "ICLOUD.md").read_text()
        assert (e.repo / "old").read_text() == "old"
        return
    if name in ("test_old_release_restore_then_23_matches_a_23_restore", "test_release_200_on_a_parked_pure_v2_repo"):
        month(e)
        e.ok("sync", "m")
        if version == "2.0.0":
            e.ok("read", "m/AUG/a.csv", script=frozen)
            assert e.run("verify", script=frozen).returncode == 2
        else:
            e.ok("restore", "m/AUG/a.csv", script=frozen)
            e.ok("tidy")
            e.ok("verify", "--fix")
            assert (e.repo / "m/AUG/empty/deeper").is_dir()
            parked(e, "m/AUG/sub")
        return
    month(e)
    if name == "test_records_under_the_name_refuse_it":
        e.write("_archive/old", "old")
        e.ok("sync", "_archive", script=frozen)
    e.ok("sync", "m", script=frozen)
    if name == "test_tidy_plan_is_read_only_and_tidy_refuses_an_old_repo":
        before = e.snapshot()
        e.refused("tidy", "--plan")
        e.refused("tidy")
        assert e.snapshot() == before
    elif name == "test_repo_archived_by_221_keeps_folders_until_upgraded":
        e.write("m/SEP/c", "c")
        e.ok("sync", "m")
        assert (e.repo / "m/AUG").is_dir()
        e.ok("upgrade")
        parked(e, "m/AUG")
    elif name == "test_park_step_neither_waits_nor_refuses_while_an_upload_is_pending":
        e.ok("upgrade", "--wait", "0", overrides={"ICLOUD_ARCHIVE_FAKE_PENDING": "1"})
        parked(e, "m/AUG")
    elif name == "test_park_step_changes_nothing_in_icloud":
        import hashlib
        before = {str(p.relative_to(e.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (e.root / "files").glob("**/*") if p.is_file()}
        records = e.records()
        e.ok("upgrade")
        assert e.records() == records
        after = {str(p.relative_to(e.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (e.root / "files").glob("**/*") if p.is_file()}
        assert after == before
    elif name == "test_the_mirror_never_turns_on_parking":
        path = e.root / ".manifest.jsonl"
        lines = path.read_text().splitlines()
        header = json.loads(lines[0])
        header["parked"], header["gen"] = "_archive", header.get("gen", 0) + 1
        lines[0] = json.dumps(header)
        path.write_text("\n".join(lines) + "\n")
        e.write("m/new", "new")
        e.ok("sync", "m/new")
        assert (e.repo / "m/AUG").is_dir()
        assert "Parked folders:" not in (e.repo / "ICLOUD.md").read_text()
    elif name == "test_upgrade_all_parks_each_repo_or_says_why_not":
        e.ok("upgrade", "--all")
        parked(e, "m/AUG")
    elif name == "test_records_under_the_name_refuse_it":
        e.refused("upgrade")
        e.ok("upgrade", "--park-dir", "_old_folders")
        e.ok("restore", "_archive/old")
        assert (e.repo / "_archive/old").read_text() == "old"
    elif name == "test_crash_after_the_setting_is_saved_converges":
        assert e.run("upgrade", overrides={"ICLOUD_ARCHIVE_FAULT": "park-after-setting"}).returncode == 99
        e.ok("upgrade")
        parked(e, "m/AUG")
