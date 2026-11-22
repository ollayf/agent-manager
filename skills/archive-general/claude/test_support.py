"""Test fixtures use only disposable local directories; never the real archive."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "archive.py"


class Env:
    def __init__(self, tmp_path):
        self.tmp = tmp_path.resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.base = self.tmp / "archive"
        self.locks = self.tmp / "locks"
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith(("ICLOUD_ARCHIVE_", "ARCHIVE_GENERAL_")):
                del self.env[key]
        self.fake_lsof = self.tmp / "empty-lsof"
        self.fake_lsof.write_text("#!/bin/sh\nexit 1\n")
        self.fake_lsof.chmod(0o755)
        self.env.update(ICLOUD_ARCHIVE_ROOT=str(self.base), ICLOUD_ARCHIVE_LOCK_DIR=str(self.locks), ICLOUD_ARCHIVE_MIN_AGE="0", ICLOUD_ARCHIVE_FILE_LIMIT="65536", ICLOUD_ARCHIVE_PART_SIZE="32768", ICLOUD_ARCHIVE_MARGIN="0", ICLOUD_ARCHIVE_LOCK_TIMEOUT="2", ICLOUD_ARCHIVE_LSOF=str(self.fake_lsof), ICLOUD_ARCHIVE_LSOF_TIMEOUT="1")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def run(self, *args, script=SCRIPT, cwd=None, overrides=None):
        env = dict(self.env)
        env.update(overrides or {})
        timeout = float(os.environ.get("ARCHIVE_GENERAL_TEST_TIMEOUT", "30"))
        return subprocess.run([sys.executable, str(script), *map(str, args)], cwd=cwd or self.repo, env=env, capture_output=True, text=True, timeout=timeout)

    def ok(self, *args, **kwargs):
        result = self.run(*args, **kwargs)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout + result.stderr

    def refused(self, *args, **kwargs):
        result = self.run(*args, **kwargs)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "REFUSED" in result.stderr
        return result.stdout + result.stderr

    def write(self, path, data=b"hello\n", age=3600):
        import time
        path = self.repo / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        timestamp = time.time() - age
        os.utime(path, (timestamp, timestamp))
        return path

    def records(self):
        result = {}
        path = self.repo / "ICLOUD.manifest.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("op") == "add":
                    result[record["path"]] = record
                elif record.get("op") == "del":
                    result.pop(record["path"], None)
        return result

    @property
    def root(self):
        path = self.repo / "ICLOUD.manifest.jsonl"
        if path.exists():
            return Path(json.loads(path.read_text().splitlines()[0])["root"]).expanduser()
        index = self.repo / "ICLOUD.md"
        if index.exists():
            import re
            match = re.search(r"^Root:\s*`([^`]+)`", index.read_text(), re.M)
            if match:
                return Path(match[1]).expanduser()
        registries = list((self.base / "registry").glob("*.json"))
        if registries:
            value = json.loads(registries[0].read_text())["root"]
            return self.base / value
        return self.base / "repos/_abs" / str(self.repo).lstrip("/")

    def snapshot(self):
        result = {}
        for root in (self.repo, self.base):
            if root.exists():
                for path in root.rglob("*"):
                    if ".git" in path.relative_to(root).parts:
                        continue
                    key = str(path.relative_to(self.tmp))
                    result[key] = ("link", os.readlink(path)) if path.is_symlink() else ("dir",) if path.is_dir() else ("file", hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode)
        return result

    def age_folders(self, age=3600):
        import time
        stamp = time.time() - age
        for path in [self.repo, *self.repo.rglob("*")]:
            if path.is_dir() and ".git" not in path.parts:
                os.utime(path, (stamp, stamp))


def require_history(version):
    import pytest
    folder = SKILL / "history" / version
    if not (folder / "icloud_archive.py").is_file():
        pytest.skip(f"original frozen history/{version}/ unavailable; no stand-in release was fabricated (guide A6)")
    return folder / "icloud_archive.py"


def mirror(e, manifest=True, mismatch=False):
    import csv
    folder = e.tmp / "foreign"
    (folder / "data").mkdir(parents=True)
    rows = []
    for name, data in [("a.csv", b"a\n"), ("b.csv", b"b\n")]:
        path = folder / "data" / name
        path.write_bytes(data)
        rows.append(dict(path="data/" + name, archive_path=str(path), bytes=str(len(data)), md5="0" * 32 if mismatch and name == "b.csv" else hashlib.md5(data).hexdigest(), status="archived"))
    csv_path = e.repo / "foreign.csv"
    if manifest:
        with csv_path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return folder, csv_path, rows


def split(e, bad_part=False, bad_stream=False):
    folder = e.tmp / "split-foreign"
    folder.mkdir()
    data = os.urandom(90000)
    packed = subprocess.run(["zstd", "-q", "-c"], input=data, capture_output=True, check=True).stdout
    names = []
    for i, offset in enumerate(range(0, len(packed), 30000)):
        name = f"db.zst.part-{i:03d}"
        (folder / name).write_bytes(packed[offset:offset + 30000])
        names.append(name)
    meta = dict(original_path="data/trace.db", original_bytes=len(data), original_sha256="0" * 64 if bad_stream else hashlib.sha256(data).hexdigest(), part_prefix="db.zst.part-", parts=len(names), original_mtime="2026-01-01T00:00:00+0000", zstd_level="3")
    (folder / "MANIFEST.txt").write_text("".join(f"{k}={v}\n" for k, v in meta.items()))
    (folder / "SHA256SUMS").write_text("".join(f"{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}\n" for name in names))
    (folder / "restore.sh").write_text("# kept original instructions\n")
    if bad_part:
        sums = folder / "SHA256SUMS"
        text = sums.read_text()
        sums.write_text("0" * 64 + text[64:])
    return folder, data


def own_history_copy(e):
    """Snapshot of this actual new engine for an isolated fallback test."""
    import shutil
    tool = e.tmp / "rebuild-copy"
    tool.mkdir()
    names = ("archive.py", "storage.py", "drive_api.py", "drive_archive.py", "SKILL.md", "icloud_status.swift")
    for name in names:
        shutil.copy2(SKILL / name, tool / name)
    release = tool / "history/3.2.1"
    release.mkdir(parents=True)
    for name in names:
        shutil.copy2(tool / name, release / name)
    # The old CLI filename is an adapter only; tests keep using it for compatibility.
    shutil.copy2(SKILL / "icloud_archive.py", tool / "icloud_archive.py")
    (release / "SHA256SUMS").write_text("".join(f"{hashlib.sha256((release / name).read_bytes()).hexdigest()}  {name}\n" for name in names))
    (tool / "history/INDEX.json").write_text(json.dumps({"3.2.1": dict(date="2026-10-25", writes=[2], reads=[1, 2], summary="isolated test snapshot")}))
    return tool, release


def literal_v1(e, form="file", rel="legacy/a", data=b"legacy bytes\n"):
    """A literal published-format fixture, not an imitation of old release code."""
    import time
    root = e.base / "literal-v1"
    location = root / (rel + (".packed" if form == "pack" else ""))
    if form == "dir":
        (location / "sub").mkdir(parents=True)
        (location / "empty/deeper").mkdir(parents=True)
        (location / "sub/a").write_bytes(data)
        form_text, row_path = "dir", rel + "/"
    elif form == "pack":
        location.mkdir(parents=True)
        compressed = subprocess.run(["zstd", "-q", "-c"], input=data, capture_output=True, check=True).stdout
        parts = []
        for i, offset in enumerate(range(0, len(compressed), 20000)):
            name = f"part-{i:03d}.zst"
            part = compressed[offset:offset + 20000]
            (location / name).write_bytes(part)
            parts.append(dict(name=name, size=len(part), sha256=hashlib.sha256(part).hexdigest()))
        value = dict(format=1, original_name=Path(rel).name, original_size=len(data), original_sha256=hashlib.sha256(data).hexdigest(), zstd_args=["-3"], part_size=20000, parts=parts)
        (location / "MANIFEST.json").write_text(json.dumps(value, indent=2) + "\n")
        (location / "SHA256SUMS").write_text("".join(f"{p['sha256']}  {p['name']}\n" for p in parts))
        form_text, row_path = f"zst×{len(parts)}", rel
    else:
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes(data)
        location.chmod(0o640)
        stamp = time.time() - 3600
        os.utime(location, (stamp, stamp))
        form_text, row_path = "file", rel
    root_text = str(root)
    path = e.repo / "ICLOUD.md"
    prefix = f"# iCloud archive\n\nUser prose to preserve.\n\nRoot: `{root_text}/`\n\n| Path | Form | Archived |\n|---|---|---|\n"
    row = f"| `{row_path.replace('|', chr(92) + '|')}` | {form_text} | 2026-01-01 |\n"
    if path.exists():
        path.write_text(path.read_text().rstrip() + "\n" + row)
    else:
        path.write_text(prefix + row)
    return location, data
