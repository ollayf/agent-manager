"""Batched-lock sync/restore (3.2.0): same results as the frozen 3.1.4 engine, fair lock, safe failures."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from test_support import SKILL
from test_general_storage import GeneralEnv

sys.path.insert(0, str(SKILL))
import storage

FROZEN = SKILL / ".history" / "3.1.4" / "archive.py"


def tree(e, count=120):
    files = {}
    for i in range(count):
        rel = f"data/d{i % 7}/sub{i % 3}/f{i:03d}.bin"
        data = hashlib.sha256(str(i).encode()).digest() * (1 + i % 5)
        e.write(rel, data)
        files[rel] = data
    e.write("data/top.txt", b"top\n")
    files["data/top.txt"] = b"top\n"
    for rel in files:  # identical, old timestamps so two trees compare exactly
        os.utime(e.repo / rel, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    e.age_folders()
    return files


def comparable(records):
    return {path: {k: v for k, v in r.items() if k not in ("date", "by")} for path, r in records.items()}


def archived_bytes(e):
    root = e.root / "files"
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file() and not p.name.startswith("._")}


def local_tree(e):
    return sorted(str(p.relative_to(e.repo)) for p in e.repo.rglob("*") if ".git" not in p.parts and p.name not in ("ARCHIVE.md", "ARCHIVE.manifest.jsonl"))


@pytest.mark.parametrize("seconds", ["0.05", "600"])
def test_batched_sync_matches_frozen_engine(tmp_path, seconds):
    if not FROZEN.is_file():
        pytest.skip("frozen 3.1.4 release unavailable")
    (tmp_path / "new").mkdir()
    (tmp_path / "old").mkdir()
    new, old = GeneralEnv(tmp_path / "new"), GeneralEnv(tmp_path / "old")
    files = tree(new)
    assert tree(old) == files
    new.ok("sync", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS=seconds))
    old.ok("sync", "data", script=FROZEN)
    assert comparable(new.records()) == comparable(old.records())
    assert set(new.records()) == set(files)
    assert archived_bytes(new) == archived_bytes(old) == files
    assert local_tree(new) == local_tree(old)
    assert new.run("verify").returncode == 0


def test_batched_restore_round_trip_restores_bytes_mode_and_time(tmp_path):
    e = GeneralEnv(tmp_path)
    files = tree(e, 90)
    os.chmod(e.repo / "data/top.txt", 0o640)
    before = {rel: ((e.repo / rel).stat().st_mode, (e.repo / rel).stat().st_mtime_ns) for rel in files}
    e.ok("sync", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS="0.02"))
    assert not any((e.repo / rel).exists() for rel in files)
    e.ok("restore", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS="0.02"))
    for rel, data in files.items():
        p = e.repo / rel
        assert p.read_bytes() == data
        assert (p.stat().st_mode, p.stat().st_mtime_ns) == before[rel]
    assert e.records() == {}


def test_lock_is_released_between_batches_and_other_writers_get_in(tmp_path):
    e = GeneralEnv(tmp_path)
    files = tree(e, 2500)
    env = dict(e.env, ICLOUD_ARCHIVE_BATCH_SECONDS="0.1")
    proc = subprocess.Popen([sys.executable, str(SKILL / "archive.py"), "sync", "data"], cwd=e.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    manifest = e.repo / "ARCHIVE.manifest.jsonl"
    count = lambda: sum('"op": "add"' in line for line in manifest.read_text().splitlines()) if manifest.exists() else 0
    observations = []  # (seconds waited, records already written when we got in)
    deadline = time.monotonic() + 120
    while proc.poll() is None and time.monotonic() < deadline and len(observations) < 5:
        found = [p for p in e.locks.glob("icloud-archive-*.lock") if "_registry" not in p.name] if e.locks.exists() else []
        if found and count() > 0:  # the run is now archiving files
            with open(found[0], "a") as handle:
                start = time.monotonic()
                while True:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        time.sleep(0.005)
                observations.append((time.monotonic() - start, count()))
                time.sleep(0.15)  # hold it like another writer would
                fcntl.flock(handle, fcntl.LOCK_UN)
        time.sleep(0.05)
    out, err = proc.communicate(timeout=300)
    assert proc.returncode == 0, out + err
    assert len(observations) >= 3, f"too few observations while the run was busy: {observations}"
    # Every time we got in, the run was still mid-way (more files followed), and we waited about one batch.
    assert all(written < len(files) for _, written in observations), observations
    assert max(wait for wait, _ in observations) < 2, observations
    assert set(e.records()) == set(files)
    assert not any((e.repo / rel).exists() for rel in files)


def test_refusal_mid_batch_keeps_that_file_and_archives_the_rest(tmp_path):
    e = GeneralEnv(tmp_path)
    files = tree(e, 60)
    victim = "data/d3/sub1/f031.bin"
    assert victim in files
    planted = e.root / "files" / victim
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_bytes(b"someone else's bytes")
    result = e.run("sync", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS="600"))
    assert result.returncode == 1 and "no record of it" in result.stderr
    assert (e.repo / victim).read_bytes() == files[victim]
    assert planted.read_bytes() == b"someone else's bytes"
    records = e.records()
    assert set(records) == set(files) - {victim}
    for rel in records:
        assert not (e.repo / rel).exists()
        assert (e.root / "files" / rel).read_bytes() == files[rel]


def test_target_identity_lost_mid_run_refuses_the_remaining_files(tmp_path):
    e = GeneralEnv(tmp_path)
    for i in range(30):
        e.write(f"first/f{i}.txt", f"one {i}\n")
        e.write(f"second/f{i}.txt", f"two {i}\n")
    e.age_folders()
    marker = e.base / storage.MARKER
    counter = e.tmp / "lsof-calls"
    fake = e.tmp / "marker-thief-lsof"
    fake.write_text(f"#!/bin/sh\nn=$(cat {counter} 2>/dev/null || echo 0); n=$((n+1)); echo $n > {counter}\nif [ $n -eq 2 ]; then mv {marker} {marker}.away; fi\nexit 1\n")
    fake.chmod(0o755)
    result = e.run("sync", "first", "second", overrides=dict(ICLOUD_ARCHIVE_LSOF=str(fake), ICLOUD_ARCHIVE_BATCH_SECONDS="600"))
    os.rename(f"{marker}.away", marker)
    assert result.returncode == 1 and "identity marker" in result.stdout + result.stderr
    assert all((e.repo / f"second/f{i}.txt").read_text() == f"two {i}\n" for i in range(30))
    assert not any(r.startswith("second/") for r in e.records())
    assert {r for r in e.records() if r.startswith("first/")} == {f"first/f{i}.txt" for i in range(30)}
    assert not any((e.repo / f"first/f{i}.txt").exists() for i in range(30))


from test_general_storage import ssd  # noqa: E402,F401  (opt-in disposable SSD fixture)


def test_ssd_batched_sync_and_restore_round_trip(ssd):
    e = ssd
    files = tree(e, 300)
    before = {rel: (e.repo / rel).stat().st_mtime_ns for rel in files}
    e.ok("sync", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS="2"))  # several batch boundaries on the SSD
    assert set(e.records()) == set(files)
    assert archived_bytes(e) == files
    assert e.run("verify").returncode == 0
    e.ok("restore", "data", overrides=dict(ICLOUD_ARCHIVE_BATCH_SECONDS="2"))
    for rel, data in files.items():
        assert (e.repo / rel).read_bytes() == data
        assert (e.repo / rel).stat().st_mtime_ns == before[rel]
    assert e.records() == {}


def test_a_second_real_archive_run_gets_in_while_a_big_run_is_busy(tmp_path):
    e = GeneralEnv(tmp_path)
    files = tree(e, 2500)
    e.write("other/late.txt", b"late\n")
    e.age_folders()
    env = dict(e.env, ICLOUD_ARCHIVE_BATCH_SECONDS="0.5")
    big = subprocess.Popen([sys.executable, str(SKILL / "archive.py"), "sync", "data"], cwd=e.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    manifest = e.repo / "ARCHIVE.manifest.jsonl"
    count = lambda: sum('"op": "add"' in line for line in manifest.read_text().splitlines()) if manifest.exists() else 0
    deadline = time.monotonic() + 60
    while count() < 50 and time.monotonic() < deadline:
        time.sleep(0.02)
    small = e.run("sync", "other/late.txt")  # real lock() waiter; the test env gives it a 2 s lock timeout
    written_when_done = count()
    out, err = big.communicate(timeout=300)
    assert big.returncode == 0, out + err
    assert small.returncode == 0, small.stdout + small.stderr
    assert written_when_done < len(files) + 1, "the second run only got in after the big run finished"
    assert set(e.records()) == set(files) | {"other/late.txt"}
