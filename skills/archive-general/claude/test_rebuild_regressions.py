"""Additional contract tests; literal fixtures do not replace frozen-release tests."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess

import pytest

from test_support import Env, SCRIPT, SKILL, literal_v1, mirror, own_history_copy


@pytest.fixture
def e(tmp_path):
    return Env(tmp_path)


@pytest.mark.parametrize("form", ["file", "dir", "pack"])
def test_builtin_v1_restore_literal_format(e, form):
    source, data = literal_v1(e, form)
    metadata = source.stat()
    e.ok("read", "legacy/a")
    e.ok("restore", "legacy/a")
    target = e.repo / "legacy/a" / "sub/a" if form == "dir" else e.repo / "legacy/a"
    assert target.read_bytes() == data
    if form == "file":
        assert target.stat().st_mode & 0o777 == 0o640
        assert target.stat().st_mtime_ns == metadata.st_mtime_ns
    if form == "dir":
        assert (e.repo / "legacy/a/empty/deeper").is_dir()
    assert not (e.repo / "ICLOUD.md").exists()
    assert not source.exists()


@pytest.mark.parametrize("form", ["file", "dir", "pack"])
def test_builtin_v1_upgrade_literal_format(e, form):
    source, data = literal_v1(e, form)
    before = e.snapshot()
    e.ok("upgrade", "--plan")
    assert e.snapshot() == before
    e.ok("upgrade")
    assert e.root != source.parent
    e.ok("verify")
    path = "legacy/a/sub/a" if form == "dir" else "legacy/a"
    assert e.records()[path]["upgraded_from"]["format"] == 1
    assert e.records()[path]["by"] == "3.6.0"
    e.ok("restore", "legacy/a")
    assert (e.repo / path).read_bytes() == data


def test_builtin_v1_big_pack_stays_packed(e):
    data = os.urandom(90000)
    literal_v1(e, "pack", data=data)
    e.ok("upgrade")
    assert e.records()["legacy/a"]["form"].startswith("zst×")
    e.ok("restore", "legacy/a")
    assert (e.repo / "legacy/a").read_bytes() == data


@pytest.mark.parametrize("step", ["upgrade-after-move", "park-after-setting", "relocate-after-rename", "relocate-after-index"])
def test_builtin_upgrade_crash_recovery(e, step):
    literal_v1(e, "dir")
    assert e.run("upgrade", overrides={"ICLOUD_ARCHIVE_FAULT": step}).returncode == 99
    e.ok("upgrade")
    e.ok("verify", "--fix")
    e.ok("restore", "legacy/a")
    assert (e.repo / "legacy/a/sub/a").read_bytes() == b"legacy bytes\n"


def test_scoped_upgrade_keeps_other_rows_and_layout(e):
    literal_v1(e, "file", "old/a")
    literal_v1(e, "file", "keep/a")
    root = e.root
    e.ok("upgrade", "old")
    assert e.root == root
    assert set(e.records()) == {"old/a"}
    assert "`keep/a` | file" in (e.repo / "ICLOUD.md").read_text()
    assert "Parked folders:" not in (e.repo / "ICLOUD.md").read_text()


def test_v1_overlap_is_refused_and_inside_dir_restore_names_folder(e):
    literal_v1(e, "dir", "files")
    e.write("new", "new")
    before = e.snapshot()
    e.refused("sync", "new")
    assert e.snapshot() == before
    assert "restore that folder" in e.refused("restore", "files/sub/a")


def test_v1_registry_scan_preserves_prose_and_table(e):
    literal_v1(e)
    text = (e.repo / "ICLOUD.md").read_bytes()
    e.ok("registry", "--scan", e.repo)
    assert (e.repo / "ICLOUD.md").read_bytes() == text
    assert (e.repo / "ICLOUD.manifest.jsonl").exists()
    assert (e.root / ".manifest.jsonl").exists()


def test_v1_table_remains_above_v2_block(e):
    literal_v1(e)
    e.write("new", "new")
    e.ok("sync", "new")
    text = (e.repo / "ICLOUD.md").read_text()
    assert text.index("| `legacy/a` |") < text.index("<!-- archive-icloud v2:")
    assert "User prose to preserve." in text
    e.ok("verify")


def test_upgrade_waits_before_any_nonpark_step(e):
    literal_v1(e)
    before = e.snapshot()
    e.refused("upgrade", "--wait", "0", overrides={"ICLOUD_ARCHIVE_FAKE_PENDING": "1"})
    assert e.snapshot() == before


def test_upgrade_all_uses_remote_mirror_and_old_path_reads_follow(e):
    literal_v1(e)
    e.ok("registry", "--scan", e.repo)
    old = e.root / "legacy/a"
    moved = e.tmp / "moved"
    e.repo.rename(moved)
    e.ok("upgrade", "--all", cwd=e.tmp)
    # Registry's old local path is absent: the read must use the cloud mirror.
    output = e.ok("read", old, cwd=e.tmp)
    assert "/files/legacy/a" in output
    e.repo = moved
    e.ok("verify", "--fix")
    assert "legacy/a" in e.records()


@pytest.mark.parametrize("name", [".keep", ".DS_Store", ".x.icloud"])
def test_named_junk_is_refused_without_side_effects(e, name):
    e.write("m/" + name, "preserve")
    before = e.snapshot()
    e.refused("sync", "m/" + name)
    assert e.snapshot() == before


def test_import_batch_saves_and_evicts_between_batches(e, monkeypatch):
    spec = importlib.util.spec_from_file_location("batch_subject", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE, module.LOCK_DIR, module.IMPORT_BATCH = e.base, e.locks, 1
    module.LSOF = str(e.fake_lsof)
    folder, manifest, _ = mirror(e)
    calls = []
    monkeypatch.setattr(module, "evict_batch", lambda paths: calls.append((list(paths), set(e.records()))))
    args = module.parse_args(["import", str(folder), "--kind", "mirror", "--manifest", str(manifest)])
    assert module.import_command(e.repo, args) == 0
    batches = [x for x in calls if x[0]]
    assert len(batches) == 2
    assert batches[0][1] == {"data/a.csv"}
    assert batches[1][1] == {"data/a.csv", "data/b.csv"}


def test_read_only_commands_do_not_settle_newer_mirror(e):
    e.write("a", "a")
    e.ok("sync", "a")
    path = e.repo / "ICLOUD.manifest.jsonl"
    old = path.read_bytes()
    e.write("b", "b")
    e.ok("sync", "b")
    path.write_bytes(old)
    before = e.snapshot()
    for command in [("status",), ("list",), ("read", "b"), ("upload-status",), ("tidy", "--plan")]:
        e.ok(*command)
        assert e.snapshot() == before


@pytest.mark.parametrize("case", ["unknown-op", "bad-middle-line", "unsafe-path", "root-mismatch"])
def test_store_refuses_ambiguous_or_unsafe_records(e, case):
    e.write("a", "a")
    e.ok("sync", "a")
    path = e.repo / "ICLOUD.manifest.jsonl"
    if case == "root-mismatch":
        index = e.repo / "ICLOUD.md"
        index.write_text(index.read_text().replace(str(e.root), str(e.tmp / "elsewhere")))
    else:
        line = '{"op":"oops", "path":"a"}' if case == "unknown-op" else '{"op":"add", "path":"../outside"}' if case == "unsafe-path" else "{bad"
        path.write_text(path.read_text() + line + "\n" + '{"op":"del","path":"not-present"}\n')
    before = e.snapshot()
    e.refused("status")
    assert e.snapshot() == before


def test_registry_unknown_fields_survive_updates(e):
    e.write("a", "a")
    e.ok("sync", "a")
    path = next((e.base / "registry").glob("*.json"))
    value = json.loads(path.read_text())
    value["future_field"] = {"keep": [1, 2, 3]}
    path.write_text(json.dumps(value))
    e.write("b", "b")
    e.ok("sync", "b")
    assert json.loads(path.read_text())["future_field"] == {"keep": [1, 2, 3]}


def test_run_log_records_help_and_usage_exits(e):
    log = e.tmp / "log.jsonl"
    e.ok("--help", overrides={"ICLOUD_ARCHIVE_LOG": str(log)})
    assert e.run("archive", "a", "--update", overrides={"ICLOUD_ARCHIVE_LOG": str(log)}).returncode == 2
    lines = [json.loads(s) for s in log.read_text().splitlines()]
    assert [v["rc"] for v in lines] == [0, 2]
    assert lines[0]["argv"] == ["--help"]


@pytest.mark.parametrize("seed", [1, 2])
def test_rebuild_random_round_trips(e, seed):
    rng, written = random.Random(seed), {}
    tool, _ = own_history_copy(e)
    for step in range(24):
        records = e.records()
        action = rng.choice(["write", "sync", "restore", "tidy", "history", "empty"])
        if action == "write":
            rel = f"m{rng.randrange(6)}/file{step}"
            data = f"{seed}:{step}\n".encode()
            e.write(rel, data)
            written[rel] = data
        elif action == "sync":
            for i in range(6):
                rel = f"m{i}"
                if (e.repo / rel).exists() or any(p.startswith(rel + "/") for p in records):
                    e.ok("sync", rel)
        elif action in ("restore", "history") and records:
            rel = rng.choice(sorted(records))
            extra = dict(script=tool / "icloud_archive.py") if action == "history" else {}
            e.ok("restore", *( ["--via-history"] if action == "history" else []), rel, **extra)
        elif action == "empty":
            (e.repo / f"empty{step}").mkdir()
        elif action == "tidy":
            e.ok("tidy")
            assert "nothing to move" in e.ok("tidy", "--plan")
        e.ok("verify", "--fix")
        records = e.records()
        for rel, data in written.items():
            local = e.repo / rel
            assert local.exists() != (rel in records)
            if local.exists():
                assert local.read_bytes() == data
        assert not [p for p in (e.repo / "_archive").glob("**/*") if p.is_file()]
    for rel in list(e.records()):
        e.ok("restore", rel)
    assert all((e.repo / rel).read_bytes() == data for rel, data in written.items())


def test_verify_finishes_a_partly_moved_v1_directory(e):
    origin, data = literal_v1(e, 'dir', 'legacy/tree')
    (origin / 'z').write_bytes(b'another file')
    assert e.run('upgrade', overrides={'ICLOUD_ARCHIVE_FAULT': 'upgrade-after-move'}).returncode == 99
    assert origin.is_dir() and any(origin.rglob('*'))
    result = e.run('verify')
    assert result.returncode == 2 and '[half-upgraded]' in result.stdout
    e.ok('verify', '--fix')
    e.ok('verify')
    assert set(e.records()) == {'legacy/tree/sub/a', 'legacy/tree/z'}
    e.ok('restore', 'legacy/tree')
    assert (e.repo / 'legacy/tree/sub/a').read_bytes() == data
    assert (e.repo / 'legacy/tree/z').read_bytes() == b'another file'


def test_upgrade_alone_settles_an_interrupted_relocation(e):
    literal_v1(e)
    assert e.run('upgrade', overrides={'ICLOUD_ARCHIVE_FAULT': 'relocate-after-rename'}).returncode == 99
    e.ok('upgrade')
    e.ok('verify')
    registries = list((e.base / 'registry').glob('*.json'))
    assert len(registries) == 1
    assert json.loads(registries[0].read_text())['state'] == 'ok'


def test_failed_sync_with_durable_changes_compacts_both_indexes(e, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('failed_sync_subject', SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, 'BASE', e.base)
    monkeypatch.setattr(m, 'LOCK_DIR', e.locks)
    monkeypatch.setattr(m, 'LSOF', str(e.fake_lsof))
    monkeypatch.setattr(m, 'MARGIN', 0)
    e.write('a', 'durably copied')
    def fail_unlink(self, path):
        raise OSError('injected error after the durable add')
    monkeypatch.setattr(m.Ledger, 'unlink', fail_unlink)
    args = m.parse_args(['sync', str(e.repo / 'a'), '--min-age', '0'])
    assert m.sync_command(e.repo, args) == 1
    assert (e.repo / 'a').read_text() == 'durably copied'
    assert 'a' in e.records()
    assert (e.root / '.manifest.jsonl').is_file(), 'durable changes were not compacted to the iCloud mirror'
    assert (e.repo / 'ICLOUD.manifest.jsonl').read_bytes() == (e.root / '.manifest.jsonl').read_bytes()
    assert (e.repo / 'ICLOUD.md').is_file()
    e.ok('verify', '--fix')
    e.ok('verify')


def test_upgrade_and_main_versions_always_match():
    import re
    from test_support import SKILL
    version = re.search(r'^SKILL_VERSION = "([^"]+)"', SCRIPT.read_text(), re.M).group(1)
    for path in (SKILL / 'SKILL.md',):
        assert re.search(r'^\s*version: (.+)$', path.read_text(), re.M).group(1) == version


@pytest.mark.parametrize('name', ['ICLOUD.md', 'ICLOUD.manifest.jsonl'])
@pytest.mark.parametrize('kind', ['mirror', 'split'])
def test_import_cannot_create_records_for_the_indexes(e, name, kind):
    if kind == 'mirror':
        folder = e.tmp / 'foreign-index'
        folder.mkdir()
        (folder / name).write_bytes(b'user data masquerading as an index')
    else:
        from test_support import split
        folder, _ = split(e)
        meta = folder / 'MANIFEST.txt'
        meta.write_text(meta.read_text().replace('original_path=data/trace.db', 'original_path=' + name))
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    e.refused('import', folder, '--kind', kind)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert not e.records()
    assert not (e.repo / 'ICLOUD.md').exists()
    assert not (e.repo / 'ICLOUD.manifest.jsonl').exists()


def test_inventory_allows_only_folder_and_finder_moves(e):
    from _park_inventory import snap, compare
    e.write('m/a', 'archived')
    e.write('m/.DS_Store', b'finder metadata')
    e.ok('sync', 'm', '--min-age', '10')
    before = {str(e.repo): snap(e.repo)}
    e.ok('tidy', '--min-age', '0')
    assert not (e.repo / 'm').exists()
    after = {str(e.repo): snap(e.repo)}
    assert not compare(before, after)
    e.write('new-file', 'a real difference')
    assert compare(before, {str(e.repo): snap(e.repo)})


def test_release_is_immutable_and_checks_its_own_sums(e):
    import shutil, subprocess, sys
    from test_support import SKILL
    skill=e.tmp/'release-test/archive-general';(skill/'claude').mkdir(parents=True)
    for name in ('archive.py','storage.py','drive_api.py','drive_archive.py','icloud_status.swift','SKILL.md'):
        shutil.copy2(SKILL/name,skill/name)
    script=skill/'claude/_release.py';shutil.copy2(SKILL/'claude/_release.py',script)
    def run(*args):return subprocess.run([sys.executable,str(script),*args],capture_output=True,text=True)
    assert run().returncode==0
    assert run('--check').returncode==0
    import re;ver=re.search(r'^SKILL_VERSION = "([^"]+)"',(SKILL/'archive.py').read_text(),re.M).group(1)
    frozen=skill/'history'/ver/'archive.py';original=frozen.read_bytes()
    (skill/'archive.py').write_bytes(original+b'\n# changed\n')
    assert run().returncode!=0 and frozen.read_bytes()==original
    helper=skill/'history'/ver/'storage.py';helper.write_text(helper.read_text()+'\n# tampered\n')
    assert run('--check').returncode!=0
