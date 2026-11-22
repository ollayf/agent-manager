"""APFS-compressed sources (3.2.1): ExFAT refuses the UF_COMPRESSED flag; archives must still copy and restore."""
import errno
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest
from test_support import SKILL
from test_general_storage import GeneralEnv, ssd  # noqa: F401  (ssd is a fixture)

sys.path.insert(0, str(SKILL))
import storage

FROZEN = SKILL / ".history" / "3.2.0" / "archive.py"

# Runs an engine with chflags behaving like ExFAT: any flags that include UF_COMPRESSED fail with EINVAL.
EXFAT = '''
import errno, os, runpy, stat, sys
real = os.chflags
def chflags(path, flags, *args, **kwargs):
    if flags & stat.UF_COMPRESSED:
        raise OSError(errno.EINVAL, "Invalid argument", str(path))
    return real(path, flags, *args, **kwargs)
os.chflags = chflags
os.supports_follow_symlinks.add(chflags)
engine = os.environ["EXFAT_SIM_ENGINE"]
sys.argv[0] = engine
sys.path.insert(0, os.path.dirname(engine))
runpy.run_path(engine, run_name="__main__")
'''


def compressed(path, data):
    """Write data as an APFS transparently compressed file (what macOS does to many system files)."""
    if not shutil.which("ditto"):
        pytest.skip("ditto unavailable")
    plain = path.with_name(path.name + ".plain")
    path.parent.mkdir(parents=True, exist_ok=True)
    plain.write_bytes(data)
    subprocess.run(["ditto", "--hfsCompression", str(plain), str(path)], check=True)
    plain.unlink()
    if not os.stat(path).st_flags & stat.UF_COMPRESSED:
        pytest.skip("temporary volume does not support APFS compression")
    return path


def fake_exfat(monkeypatch, reject=lambda flags: flags & stat.UF_COMPRESSED, code=errno.EINVAL):
    real, calls = os.chflags, []
    def chflags(path, flags, *args, **kwargs):
        calls.append(flags)
        if reject(flags):
            raise OSError(code, os.strerror(code), str(path))
        return real(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "chflags", chflags)
    monkeypatch.setattr(os, "supports_follow_symlinks", set(os.supports_follow_symlinks) | {chflags})
    return calls


DATA = b"thumbnail bytes " * 2000  # below the test FILE_LIMIT, so files take the plain copy path, not packing


@pytest.mark.parametrize("follow", [True, False])
def test_copy_stat_drops_only_the_compression_flag_and_keeps_other_metadata(tmp_path, monkeypatch, follow):
    source = compressed(tmp_path / "a.ithmb", DATA)
    os.chflags(source, os.stat(source).st_flags | stat.UF_HIDDEN)
    os.chmod(source, 0o640)
    os.utime(source, ns=(1_600_000_000_000_000_000, 1_600_000_000_123_456_789))
    destination = tmp_path / "b.ithmb"
    shutil.copyfile(source, destination)
    calls = fake_exfat(monkeypatch)
    storage.copy_stat(source, destination, follow_symlinks=follow)
    assert calls[0] & stat.UF_COMPRESSED, "the fake must have refused the real flags first"
    after = os.stat(destination)
    assert destination.read_bytes() == DATA
    assert not after.st_flags & stat.UF_COMPRESSED
    assert after.st_flags & stat.UF_HIDDEN
    assert stat.S_IMODE(after.st_mode) == 0o640
    assert after.st_mtime_ns == 1_600_000_000_123_456_789


def test_copy_stat_still_raises_einval_for_an_uncompressed_source(tmp_path, monkeypatch):
    source, destination = tmp_path / "a", tmp_path / "b"
    source.write_bytes(b"x")
    destination.write_bytes(b"x")
    fake_exfat(monkeypatch, reject=lambda flags: True)
    with pytest.raises(OSError) as error:
        storage.copy_stat(source, destination)
    assert error.value.errno == errno.EINVAL


def test_copy_stat_still_raises_other_errors_for_a_compressed_source(tmp_path, monkeypatch):
    source = compressed(tmp_path / "a", DATA)
    destination = tmp_path / "b"
    shutil.copyfile(source, destination)
    fake_exfat(monkeypatch, code=errno.EPERM)
    with pytest.raises(OSError) as error:
        storage.copy_stat(source, destination)
    assert error.value.errno == errno.EPERM


def test_copy_stat_is_plain_copystat_when_the_destination_accepts_the_flags(tmp_path):
    source, destination = tmp_path / "a", tmp_path / "b"
    source.write_bytes(b"x")
    os.chmod(source, 0o600)
    os.utime(source, ns=(1_500_000_000_000_000_000, 1_500_000_000_000_000_000))
    destination.write_bytes(b"x")
    storage.copy_stat(source, destination)
    assert (stat.S_IMODE(destination.stat().st_mode), destination.stat().st_mtime_ns) == (0o600, 1_500_000_000_000_000_000)


def files(e):
    paths = {}
    for i in range(6):
        rel = f"Media/PhotoData/Thumbnails/{3300 + i}.ithmb"
        paths[rel] = compressed(e.repo / rel, DATA + bytes([i]) * (i + 1))
    plain = e.write("Media/PhotoData/plain.txt", b"not compressed\n")
    paths["Media/PhotoData/plain.txt"] = plain
    for i, p in enumerate(paths.values()):
        os.chmod(p, 0o644 if i % 2 else 0o664)
        os.utime(p, ns=(1_615_000_000_000_000_000 + i, 1_615_000_000_000_000_000 + i))
    return {rel: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode), p.stat().st_mtime_ns) for rel, p in paths.items()}


def exfat_sim(tmp_path, engine):
    wrapper = tmp_path / "exfat_sim.py"
    wrapper.write_text(EXFAT)
    return dict(script=wrapper, overrides=dict(EXFAT_SIM_ENGINE=str(engine)))


def assert_round_trip(e, before, **run):
    e.age_folders()
    out = e.ok("sync", "Media", **run)
    assert "refused: 0" in out, out
    assert set(e.records()) == set(before)
    for rel, (data, mode, mtime) in before.items():
        assert not (e.repo / rel).exists()
        assert (e.root / "files" / rel).read_bytes() == data
        assert e.records()[rel]["mode"] & 0o777 == mode and e.records()[rel]["mtime_ns"] == mtime
    assert e.run("verify", **run).returncode == 0
    e.ok("restore", "Media", **run)
    assert e.records() == {}
    for rel, (data, mode, mtime) in before.items():
        p = e.repo / rel
        assert (p.read_bytes(), stat.S_IMODE(p.stat().st_mode), p.stat().st_mtime_ns) == (data, mode, mtime)


def test_compressed_files_archive_and_restore_on_a_target_that_refuses_the_flag(tmp_path):
    (tmp_path / "w").mkdir()
    e = GeneralEnv(tmp_path / "w")
    assert_round_trip(e, files(e), **exfat_sim(tmp_path, SKILL / "archive.py"))


def test_frozen_320_engine_refuses_compressed_files_under_the_same_simulation(tmp_path):
    """Proves the simulation reproduces the 3.2.0 bug, so the round trip above tests the fix."""
    if not FROZEN.is_file():
        pytest.skip("frozen 3.2.0 release unavailable")
    (tmp_path / "w").mkdir()
    e = GeneralEnv(tmp_path / "w")
    before = files(e)
    e.age_folders()
    result = e.run("sync", "Media", **exfat_sim(tmp_path, FROZEN))
    assert result.returncode == 1 and "Invalid argument" in result.stderr, result.stdout + result.stderr
    assert set(e.records()) == {"Media/PhotoData/plain.txt"}
    for rel, (data, mode, mtime) in before.items():
        if rel.endswith(".ithmb"):
            assert (e.repo / rel).read_bytes() == data and os.stat(e.repo / rel).st_flags & stat.UF_COMPRESSED
    assert not [p for p in e.root.rglob("*.partial-*")]


def test_real_ssd_compressed_files_round_trip(ssd):
    assert_round_trip(ssd, files(ssd))


def test_real_ssd_frozen_320_engine_refuses_compressed_files(ssd):
    if not FROZEN.is_file():
        pytest.skip("frozen 3.2.0 release unavailable")
    before = files(ssd)
    ssd.age_folders()
    result = ssd.run("sync", "Media", script=FROZEN)
    assert result.returncode == 1 and "Invalid argument" in result.stderr, result.stdout + result.stderr
    for rel, (data, mode, mtime) in before.items():
        if rel.endswith(".ithmb"):
            assert (ssd.repo / rel).read_bytes() == data
