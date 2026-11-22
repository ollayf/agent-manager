#!/usr/bin/env python3
"""Verified archives across registered filesystem targets. Based on the recovered iCloud engine.

All filesystem mutations go through the store's advisory lock. A durable record is
written before removing the source, and folder housekeeping never moves user files.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import datetime as dt
import errno
import fcntl
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata

SKILL_VERSION = "3.1.1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import storage
# New names take precedence; the old environment is a compatibility adapter.
for _key, _value in list(os.environ.items()):
    if _key.startswith("ARCHIVE_GENERAL_") and _key not in ("ARCHIVE_GENERAL_CONFIG",):
        os.environ["ICLOUD_ARCHIVE_" + _key[len("ARCHIVE_GENERAL_"):]] = _value
TARGET = None
LEGACY_PREFIX = None
HOME = Path.home()
DRIVE = HOME / "Library/Mobile Documents/com~apple~CloudDocs"
BASE = Path(os.environ.get("ICLOUD_ARCHIVE_ROOT", str(DRIVE / "claude-archive"))).expanduser().absolute()
LOCK_DIR = Path(os.environ.get("ICLOUD_ARCHIVE_LOCK_DIR", str(HOME / ".claude/locks"))).expanduser()
FILE_LIMIT = int(os.environ.get("ICLOUD_ARCHIVE_FILE_LIMIT", 49_000_000_000))
PART_SIZE = int(os.environ.get("ICLOUD_ARCHIVE_PART_SIZE", 2 * 1024**3))
MIN_AGE = float(os.environ.get("ICLOUD_ARCHIVE_MIN_AGE", 10))
READ_FULL_LIMIT = int(os.environ.get("ICLOUD_ARCHIVE_READ_FULL_LIMIT", 10_000_000_000))
IMPORT_BATCH = int(os.environ.get("ICLOUD_ARCHIVE_IMPORT_BATCH", 10_000_000_000))
MARGIN = int(os.environ.get("ICLOUD_ARCHIVE_MARGIN", 1024**3))
LOCK_TIMEOUT = float(os.environ.get("ICLOUD_ARCHIVE_LOCK_TIMEOUT", 120))
LSOF = os.environ.get("ICLOUD_ARCHIVE_LSOF", "lsof")
LSOF_TIMEOUT = float(os.environ.get("ICLOUD_ARCHIVE_LSOF_TIMEOUT", 600))
SF_DATALESS = 0x40000000
CHUNK = 8 * 1024**2
INDEX = "ICLOUD.md"
MANIFEST = "ICLOUD.manifest.jsonl"
BEGIN = "<!-- archive-icloud v2: generated from ICLOUD.manifest.jsonl, do not edit -->"
END = "<!-- /archive-icloud v2 -->"
DEFAULT_PREFIX = [
    "# iCloud archive", "",
    "Files moved out of this repo into iCloud Drive by the archive-icloud skill. Do not edit the tables by hand.",
    "Location of an entry = Root + Path. `file`/`dir`: read in place. `zst×N`: compressed parts, use the skill's `read`.",
    "", "Root: `{root}/`", "",
]
NO_DELETE = re.compile(r"\b(never|do not|don't|must not)\b[^.\n]{0,40}\b(delete|remove|rm)\b", re.I)
BUSY = re.compile(r"\.cursor$|\.partial-|\.tmp-|\.restoring-")
CONFLICT = re.compile(r" \d+$")


class Refused(Exception):
    """A refusal whose user-facing message explains what remains on disk."""


def nfc(s):
    return unicodedata.normalize("NFC", str(s))


def compact_path(path):
    s = str(path)
    return "~" + s[len(str(HOME)):] if s == str(HOME) or s.startswith(str(HOME) + "/") else s


def expand(path):
    return Path(path).expanduser().absolute()


def root_name(path):
    try:
        return path.relative_to(BASE).as_posix()
    except ValueError:
        return compact_path(path)


def registry_root(value):
    return expand(value) if value.startswith(("/", "~")) else BASE / value


def today():
    return dt.date.today().isoformat()


def size_text(value):
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{int(number)} B" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024


def fault(step):
    if os.environ.get("ICLOUD_ARCHIVE_FAULT") == step:
        os._exit(99)


def dataless(path):
    return bool(getattr(Path(path).lstat(), "st_flags", 0) & SF_DATALESS)


def exists(path):
    return os.path.lexists(path)


def inside(path, parent):
    try:
        Path(path).relative_to(parent)
        return True
    except ValueError:
        return False


def hash_file(path, md5=False):
    guard_archive_path(path)
    sha = hashlib.sha256()
    other = hashlib.md5() if md5 else None
    with open(path, "rb") as stream:
        while chunk := stream.read(CHUNK):
            sha.update(chunk)
            if other is not None:
                other.update(chunk)
    return (sha.hexdigest(), other.hexdigest()) if other is not None else sha.hexdigest()


def litter(name):
    return name == ".DS_Store" or (name.startswith(".") and name.endswith(".icloud"))


def digest(path):
    path = Path(path)
    if path.is_file():
        return hash_file(path)
    lines = []
    for parent, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not litter(d))
        for d in dirs:
            lines.append("D " + nfc((Path(parent) / d).relative_to(path).as_posix()))
        for name in sorted(files):
            if litter(name):
                continue
            p = Path(parent) / name
            if p.is_symlink():
                raise Refused(f"symlink in archived folder: {p}")
            lines.append("F " + nfc(p.relative_to(path).as_posix()) + " " + hash_file(p))
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def ensure_free(path, need):
    parent = Path(path)
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < need + MARGIN:
        raise Refused(f"not enough free space: needs {size_text(need + MARGIN)} free on {parent}")


def atomic_write(path, text):
    path = Path(path)
    guard_archive_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        storage.fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def guard_archive_path(path):
    path = Path(path)
    if TARGET:
        TARGET.available()
    if inside(path, BASE):
        cursor = path
        while cursor != BASE:
            if cursor.is_symlink():
                raise Refused(f"symlink in archive storage: {cursor}")
            cursor = cursor.parent


def publish(source, destination):
    guard_archive_path(destination)
    storage.publish(source, destination, BASE / ".publications")


def remove_output(path):
    guard_archive_path(path)
    if path.is_dir() and not path.is_symlink():
        storage.safe_remove_tree(path)
    else:
        path.unlink(missing_ok=True)


def prune(path, stop):
    while inside(path, stop) and path != stop:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


@contextlib.contextmanager
def lock(repo_id):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK_DIR / f"icloud-archive-{repo_id}.lock", "a") as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Refused(f"another agent holds the archive lock for {repo_id}; try again later")
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def git_output(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def repo_id(repo):
    key = git_output(repo, "config", "--get", "remote.origin.url") or str(repo)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", repo.name)
    return name + "-" + hashlib.sha256(key.encode()).hexdigest()[:8]


def find_repo(explicit=None):
    start = expand(explicit).resolve() if explicit else Path.cwd()
    if not start.is_dir():
        raise Refused(f"not a folder: {start}")
    git = git_output(start, "rev-parse", "--show-toplevel")
    if explicit:
        result = expand(git) if git else start
    else:
        candidates = []
        for path in [start, *start.parents]:
            if path in (HOME, Path("/")):
                break
            candidates.append(path)
        indexed = [p for p in candidates if any((p / name).is_file() for name in (INDEX, MANIFEST, "ARCHIVE.md", "ARCHIVE.manifest.jsonl", "ICLOUD.md", "ICLOUD.manifest.jsonl"))]
        claude = [p for p in candidates if (p / "CLAUDE.md").is_file()]
        result = indexed[-1] if indexed else expand(git) if git else claude[-1] if claude else None
        if result is None:
            raise Refused(f"no project root found above {start}: no git repo, CLAUDE.md or ICLOUD.md; pass --repo DIR")
    print(f"repo: {result}", file=sys.stderr)
    return result


def checked_rel(repo, value, allow_root=False):
    if "`" in str(value) or any(ord(x) < 32 or ord(x) == 127 for x in str(value)):
        raise Refused(f"backtick or control character in path: {value!r}")
    path = Path(os.path.abspath(os.path.expanduser(value)))
    if not inside(path, repo):
        path = path.parent.resolve() / path.name
    if not inside(path, repo):
        raise Refused(f"outside repo: {value}")
    rel = path.relative_to(repo)
    if not rel.parts and not allow_root:
        raise Refused("the repo root itself cannot be archived")
    if ".git" in rel.parts or rel.as_posix() in (INDEX, MANIFEST, "ICLOUD.md", "ICLOUD.manifest.jsonl", "ARCHIVE.md", "ARCHIVE.manifest.jsonl"):
        raise Refused(f"protected archive or git path: {value}")
    parent = path.parent
    while parent != repo and inside(parent, repo):
        if parent.is_symlink():
            raise Refused(f"parent path goes through a symlink: {value}")
        parent = parent.parent
    return nfc(rel.as_posix()) if rel.parts else ""


def stored_rel(value):
    value = nfc(value)
    p = Path(value.rstrip("/"))
    if p.is_absolute() or not p.parts or p.as_posix() in (INDEX, MANIFEST, "ICLOUD.md", "ICLOUD.manifest.jsonl", "ARCHIVE.md", "ARCHIVE.manifest.jsonl") or any(x in ("..", ".git") for x in p.parts):
        raise Refused(f"unsafe path in archive record: {value}")
    if "`" in value or any(ord(x) < 32 for x in value):
        raise Refused(f"unsafe name in archive record: {value!r}")
    return value


def match_path(path, patterns):
    return any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") or fnmatch.fnmatchcase(path, p) for p in patterns)


def under(path, scopes):
    return not scopes or match_path(path.rstrip("/"), scopes)


def folder_key(path):
    parts = Path(path).parent.parts[:2]
    return "/".join(parts) + "/" if parts else "./"


def read_index(path):
    if not path.is_file():
        return None, [], None, [], []
    lines = path.read_text().splitlines()
    table = next((i for i, line in enumerate(lines) if line.startswith("| Path |")), None)
    root = next((m[1] for line in lines if (m := re.fullmatch(r"Root:\s*`([^`]+)`\s*", line))), None)
    if root is None or table is None or table + 1 >= len(lines):
        raise Refused(f"{path} malformed (no Root line or no table)")
    prefix = lines[:table]
    parked = next((m[1] for line in prefix if (m := re.match(r"^Parked folders:\s*`([^`/]+)/`", line))), None)
    rows = []
    i = table + 2
    while i < len(lines) and lines[i].startswith("|"):
        m = re.fullmatch(r"\|\s*`(.+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*", lines[i])
        if not m:
            raise Refused(f"{path} malformed table row: {lines[i]}")
        rows.append(dict(path=stored_rel(m[1].replace("\\|", "|")), form=m[2], date=m[3], format=1, by="1.x"))
        i += 1
    suffix = []
    in_block = False
    for line in lines[i:]:
        if line == BEGIN:
            in_block = True
        elif line == END:
            in_block = False
        elif not in_block:
            suffix.append(line)
    while suffix and not suffix[-1]:
        suffix.pop()
    return expand(root.rstrip("/")), prefix, parked, rows, suffix


def read_manifest(path):
    guard_archive_path(path)
    header, records, rows, torn = {}, {}, [], False
    if not path.is_file():
        return header, records, rows, torn
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                torn = True
                continue
            raise Refused(f"malformed manifest line {i + 1}: {path}")
        if not isinstance(value, dict):
            raise Refused(f"invalid manifest object: {path}:{i + 1}")
        if "icloud_archive_manifest" in value:
            header = value
            continue
        op = value.pop("op", None)
        if op not in ("add", "del", "v1"):
            raise Refused(f"unknown manifest op {op!r}: {path}:{i + 1}")
        rel = stored_rel(value.get("path", ""))
        if op == "del":
            records.pop(rel, None)
        elif op == "v1":
            rows.append(value)
        else:
            value.setdefault("format", 2)
            value.setdefault("by", "2.0.0")
            records[rel] = value
    return header, records, rows, torn


def registry_entries():
    result = []
    for path in sorted((BASE / "registry").glob("*.json")):
        if CONFLICT.search(path.stem):
            continue
        try:
            item = json.loads(path.read_text())
            if isinstance(item, dict) and "root" in item and "id" in item:
                result.append(item)
        except (OSError, ValueError):
            continue
    return result


class Store:
    def __init__(self, repo, remote=None):
        if TARGET:
            TARGET.available()
            if repo:
                TARGET.check_repo(repo)
        self.repo = repo
        self.remote = remote
        self.dirty = False
        self.notes = []
        self.park_note = None
        self.index_exists = bool(repo and (repo / INDEX).is_file())
        self.manifest_exists = bool(repo and (repo / MANIFEST).is_file())
        ix_root, self.prefix, ix_park, self.v1, self.suffix = read_index(repo / INDEX) if repo else (None, [], None, [], [])
        self.header, self.records, manifest_v1, self.torn = read_manifest(repo / MANIFEST) if repo else ({}, {}, [], False)
        self.id = remote["id"] if remote else self.header.get("id") or repo_id(repo)
        self.registry_path = BASE / "registry" / (self.id + ".json")
        try:
            self.registry = json.loads(self.registry_path.read_text())
        except FileNotFoundError:
            self.registry = {}
        except ValueError as error:
            raise Refused(f"malformed registry: {self.registry_path}: {error}")
        if ix_root and self.header.get("root") and ix_root != expand(self.header["root"]):
            raise Refused("ICLOUD.md and the manifest name different roots; fix by hand")
        fallback = BASE / self.id
        self.root = registry_root(remote["root"]) if remote else ix_root or (expand(self.header["root"]) if self.header.get("root") else None) or (registry_root(self.registry["root"]) if self.registry.get("root") else None) or (fallback if fallback.exists() else self.nested_root())
        current = registry_root(self.registry["root"]) if self.registry.get("root") else None
        old = [registry_root(x) for x in self.registry.get("old_roots", [])]
        target = registry_root(self.registry["target"]) if self.registry.get("target") else None
        if self.root in old and current and current.exists():
            self.root = current
            self.note("archive moved; repo index updated from the registry")
        elif target and target.exists() and (not self.root.exists() or storage.publication_complete(BASE / ".publications", self.root, target)):
            self.registry.setdefault("old_roots", []).append(root_name(self.root))
            self.root = target
            self.note("finishing interrupted relocate from the registry")
        if TARGET and TARGET.managed and not inside(self.root, BASE):
            raise Refused("recorded archive root is outside the selected target; refusing to redirect it")
        guard_archive_path(self.root)
        mirror, mirrored, mirror_v1, self.mirror_torn = read_manifest(self.root / ".manifest.jsonl")
        if mirror.get("id") and mirror["id"] != self.id:
            raise Refused(f"{self.root} holds the archive of another repo ({mirror['id']}); not overwriting")
        self.mirror_header = mirror
        if mirror and (remote or (not self.index_exists and not self.manifest_exists) or ("gen" in mirror and "gen" in self.header and mirror["gen"] > self.header["gen"])):
            before = self.header.get("gen", 0)
            self.records, self.v1 = mirrored, mirror_v1
            self.gen = mirror.get("gen", 0)
            if repo:
                self.note(f"repo index updated from the iCloud copy (gen {before} → {self.gen})")
        else:
            self.gen = self.header.get("gen", 0)
            if not self.index_exists:
                self.v1 = manifest_v1
        self.parked = None
        header_park = self.header.get("parked")
        if repo:
            if ix_park and header_park and ix_park != header_park:
                self.park_note = "park settings disagree; no folder moves until `upgrade --park-dir NAME` settles it"
            elif ix_park or header_park:
                self.parked = ix_park or header_park
            else:
                reason = self.taken("_archive")
                if reason:
                    self.park_note = f"folders stay in place: {reason}. `upgrade --park-dir NAME --plan` picks another folder"
                elif not self.index_exists and not self.manifest_exists:
                    self.parked = "_archive"
                elif (repo / "_archive").is_dir():
                    self.park_note = "unclaimed _archive/; `upgrade --plan` takes it over"
        self.park_missing = bool(repo and self.parked and (self.records or self.v1 or self.index_exists or self.manifest_exists) and (ix_park != self.parked or header_park != self.parked))
        if self.parked:
            stored_rel(self.parked)

    def note(self, text):
        self.notes.append(text)
        self.dirty = True

    def nested_root(self):
        if self.repo is None:
            return self.root
        try:
            rel = self.repo.relative_to(HOME)
        except ValueError:
            rel = Path("_abs") / str(self.repo).lstrip("/")
        return BASE / "repos" / rel

    @property
    def scheme(self):
        return "nested" if inside(self.root, BASE / "repos") else "flat"

    def taken(self, name):
        if self.repo is None:
            return None
        for item in self.repo.iterdir():
            if item.name.casefold() == name.casefold() and item.name != name:
                return f"{item.name}/ takes the name {name}/"
        p = self.repo / name
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            return f"{name}/ is a link or is not a folder"
        if p.is_dir():
            for parent, dirs, files in os.walk(p, followlinks=False):
                if any((Path(parent) / d).is_symlink() for d in dirs) or any(f != ".DS_Store" for f in files):
                    return f"{name}/ is this repo's own folder and holds files"
        if any(Path(r.rstrip("/")).parts[0].casefold() == name.casefold() for r in [*self.records, *(x["path"] for x in self.v1)]):
            return f"archived paths sit under {name}/"
        return None

    def rel(self, value, command, allow_root=False):
        rel = checked_rel(self.repo, value, allow_root)
        if self.parked and (rel == self.parked or rel.startswith(self.parked + "/")):
            if command == "sync":
                return rel, True
            if rel == self.parked:
                if command in ("read", "restore"):
                    raise Refused(f"name a path inside {self.parked}/")
                return "", False
            mapped = rel[len(self.parked) + 1:]
            print(f"note: {rel} means {mapped}", file=sys.stderr)
            rel = mapped
        return rel, False

    def location(self, record):
        return self.root / ("files" if record["form"] == "file" else ".big") / record["path"]

    def v1_location(self, row):
        return self.root / (row["path"].rstrip("/") + (".packed" if row["form"].startswith("zst") else ""))

    def check_v1_overlap(self):
        if any(Path(x["path"]).parts[0] in ("files", ".big", ".versions", ".manifest.jsonl", ".import-journal.jsonl") for x in self.v1):
            raise Refused("a v1 entry sits in the v2 archive area; restore it before sync")

    def header_value(self, gen=None):
        value = dict(icloud_archive_manifest=2, root=compact_path(self.root), id=self.id, gen=self.gen if gen is None else gen, by=SKILL_VERSION)
        parked = self.parked if self.repo else self.mirror_header.get("parked")
        if parked:
            value["parked"] = parked
        if TARGET and TARGET.managed:
            value["archive_target"] = TARGET.value
        return value

    def manifest_text(self, gen):
        lines = [json.dumps(self.header_value(gen), ensure_ascii=False)]
        lines += [json.dumps(dict(row, op="v1"), ensure_ascii=False, sort_keys=True) for row in sorted(self.v1, key=lambda x: x["path"])]
        lines += [json.dumps(dict(self.records[path], op="add"), ensure_ascii=False, sort_keys=True) for path in sorted(self.records)]
        return "\n".join(lines) + "\n"

    def render(self):
        if not self.records and not self.v1:
            return ""
        prefix = list(self.prefix or [x.replace("{root}", compact_path(self.root)) for x in DEFAULT_PREFIX])
        found = False
        for i, line in enumerate(prefix):
            if line.startswith("Root:"):
                prefix[i] = f"Root: `{compact_path(self.root)}/`"
                found = True
        if not found:
            raise Refused("malformed index: no Root line")
        if self.parked:
            parkline = f"Parked folders: `{self.parked}/` — folders stay in this repo, but one whose files are all in iCloud is kept at `{self.parked}/<its path>`."
            if INDEX == "ARCHIVE.md":
                parkline = parkline.replace("iCloud", "the archive target")
            previous = next((i for i, x in enumerate(prefix) if x.startswith("Parked folders:")), None)
            if previous is not None:
                prefix[previous] = parkline
            else:
                prefix.insert(next(i for i, x in enumerate(prefix) if x.startswith("Root:")) + 1, parkline)
        lines = prefix + ["| Path | Form | Archived |", "|---|---|---|"]
        esc = lambda s: s.replace("|", "\\|")
        lines += [f"| `{esc(x['path'])}` | {x['form']} | {x['date']} |" for x in sorted(self.v1, key=lambda x: x["path"])]
        lines += self.suffix
        if self.records:
            lines += ["", BEGIN, "## Archived files (v2)", "", "Each file is at Root + `files/` + its repo path, stored as is; read it in place (iCloud downloads it on open).", f"Files over {size_text(FILE_LIMIT)} are compressed under Root + `.big/` + path; use the skill's `read`.", "Folders stay in the repo. Every file is listed, with the skill version that wrote it, in `ICLOUD.manifest.jsonl`.", "The table above lists format-1 entries (skill 1.x).", "", "| Folder | Files | Size | Last archived | Written by |", "|---|---|---|---|---|"]
            groups = collections.defaultdict(list)
            for record in self.records.values():
                groups[folder_key(record["path"])].append(record)
            for key, values in sorted(groups.items()):
                writers = ", ".join(sorted({x.get("by", "2.0.0") for x in values}))
                lines.append(f"| `{esc(key)}` | {len(values)} | {size_text(sum(x['size'] for x in values))} | {max(x['date'] for x in values)} | {writers} |")
            big = [x for x in self.records.values() if x["form"] != "file"]
            if big:
                lines += ["", "| Big file | Form | Size | Archived |", "|---|---|---|---|"]
                lines += [f"| `{esc(x['path'])}` | {x['form']} | {size_text(x['size'])} | {x['date']} |" for x in sorted(big, key=lambda x: x["path"])]
            lines.append(END)
        if INDEX == "ARCHIVE.md" and BEGIN in lines:
            start, end = lines.index(BEGIN), lines.index(END)
            for i in range(start + 1, end):
                lines[i] = lines[i].replace("ICLOUD.manifest.jsonl", MANIFEST).replace("iCloud", "the archive target")
                if lines[i].startswith("Each file is at Root"):
                    lines[i] = "Each file is at Root + `files/` + its repo path, stored as is; read it in place. Cloud-provider folders may download bytes on access."
                if not FILE_LIMIT and lines[i].startswith("Files over "):
                    lines[i] = "Explicitly packed files are under Root + `.big/` + path; use the skill's `read`."
        return "\n".join(lines) + "\n"

    def settle(self):
        if self.dirty:
            for receipt, publication in storage.publication_problems(BASE / ".publications", self.root):
                if publication.get("phase") == "copied" and Path(publication["destination"]) == self.root:
                    storage.repair_publication(receipt, publication)
            self.save()

    def append(self, op, value):
        guard_archive_path(self.root)
        target = self.repo / MANIFEST if self.repo else self.root / ".manifest.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.torn:
            text = target.read_text()
            atomic_write(target, "\n".join(text.splitlines()[:-1]) + "\n")
            self.torn = False
        if not target.exists():
            atomic_write(target, json.dumps(self.header_value(), ensure_ascii=False) + "\n")
        with open(target, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(value, op=op), ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if op == "add":
            self.records[value["path"]] = value
        elif op == "del":
            self.records.pop(value["path"], None)

    def save(self):
        guard_archive_path(self.root)
        self.gen = max(self.gen, self.mirror_header.get("gen", 0)) + 1
        if self.records or self.v1:
            text = self.manifest_text(self.gen)
            if self.repo:
                atomic_write(self.repo / MANIFEST, text)
                atomic_write(self.repo / INDEX, self.render())
            atomic_write(self.root / ".manifest.jsonl", text)
            self.header = self.header_value()
            self.mirror_header = self.header.copy()
        else:
            if self.repo:
                (self.repo / MANIFEST).unlink(missing_ok=True)
                (self.repo / INDEX).unlink(missing_ok=True)
            (self.root / ".manifest.jsonl").unlink(missing_ok=True)
            prune(self.root, BASE)
        self.write_registry()
        self.dirty = self.torn = self.park_missing = False

    def write_registry(self, state=None, target=None):
        with lock("_registry"):
            try:
                value = json.loads(self.registry_path.read_text())
            except FileNotFoundError:
                value = dict(self.registry)
            for key in ("old_roots", "imports"):
                value[key] = list(self.registry.get(key, value.get(key, [])))
            count = len(self.records) + len(self.v1)
            if not count and not value["old_roots"] and not value["imports"] and state != "upgrading":
                self.registry_path.unlink(missing_ok=True)
                self.registry = {}
                try:
                    self.registry_path.parent.rmdir()
                except OSError:
                    pass
            else:
                formats = collections.Counter(str(x.get("format", 2)) for x in self.records.values())
                writers = collections.Counter(x.get("by", "2.0.0") for x in self.records.values())
                if self.v1:
                    formats["1"] += len(self.v1)
                    writers["1.x"] += len(self.v1)
                value.update(id=self.id, repo=compact_path(self.repo) if self.repo else self.remote["repo"], host=socket.gethostname().split(".")[0], root=root_name(self.root), scheme=self.scheme, formats=dict(formats), written_by=dict(writers), last_skill=SKILL_VERSION, files=count, bytes=sum(x["size"] for x in self.records.values()), created=value.get("created", today()), updated=dt.datetime.now().isoformat(timespec="seconds"), state=state or ("ok" if count else "empty"))
                if target is not None:
                    value["target"] = root_name(target)
                else:
                    value.pop("target", None)
                if TARGET and TARGET.managed:
                    value["archive_target"] = TARGET.value
                atomic_write(self.registry_path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
                self.registry = value
            render_registry()


def render_registry():
    entries = registry_entries()
    path = BASE / "REGISTRY.md"
    if not entries:
        path.unlink(missing_ok=True)
        return
    lines = ["# Archive General registry", "", "Every archive on this target, one row per project. Generated from `registry/*.json`; do not edit.", "Root is relative to this folder. `nested` roots sit under `repos/<repo path under ~>/`; `flat` roots are", "older (`<name>-<hash>/`) and `upgrade` moves them. Formats: 1 = whole file/folder or zst×N pack (skill 1.x),", "2 = per-file mirror under `files/` + `.big/` (skill 2.x).", "", "| Repo | Mac | Root | Scheme | Formats | Written by | Files | Size | Updated | State |", "|---|---|---|---|---|---|---|---|---|---|"]
    for value in sorted(entries, key=lambda x: x.get("repo", "")):
        formats = ", ".join(f"{k}: {v}" for k, v in sorted(value.get("formats", {}).items()))
        writers = ", ".join(f"{k} ×{v}" for k, v in sorted(value.get("written_by", {}).items()))
        fields = [f"`{value.get('repo', '')}`", value.get("host", ""), f"`{value['root']}`", value.get("scheme", ""), formats, writers, str(value.get("files", 0)), size_text(value.get("bytes", 0)), value.get("updated", ""), value.get("state", "ok")]
        lines.append("| " + " | ".join(s.replace("|", "\\|") for s in fields) + " |")
    atomic_write(path, "\n".join(lines) + "\n")


def record_for(rel, path, sha=None, **extra):
    info = path.stat()
    value = dict(path=rel, size=info.st_size, sha256=sha or hash_file(path), mtime_ns=info.st_mtime_ns, mode=stat.S_IMODE(info.st_mode), form="file", date=today(), format=2, by=SKILL_VERSION)
    value.update(extra)
    return value


def supported(record):
    if record.get("format", 2) != 2:
        raise Refused(f"skill {SKILL_VERSION} does not know that format ({record.get('format')}): {record['path']}; update the skill")


def read_pack(path, check=True):
    try:
        value = json.loads((path / "MANIFEST.json").read_text())
        sums = {}
        for line in (path / "SHA256SUMS").read_text().splitlines():
            sha, name = line.split(None, 1)
            sums[name.strip().lstrip("*")] = sha
        if not isinstance(value.get("parts"), list) or not value["parts"]:
            raise ValueError("no parts")
        for part in value["parts"]:
            if Path(part["name"]).name != part["name"] or part["name"] in (".", ".."):
                raise ValueError("unsafe part name")
            item = path / part["name"]
            if item.is_symlink() or not item.is_file():
                raise ValueError(f"missing part {part['name']}")
            if sums.get(part["name"]) != part["sha256"] or item.stat().st_size != part["size"]:
                raise ValueError(f"part metadata mismatch: {part['name']}")
            if check and hash_file(item) != part["sha256"]:
                raise ValueError(f"SHA-256 mismatch: {part['name']}")
        return value
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Refused(f"invalid compressed archive {path}: {error}")


def decompress_parts(paths, output=None, head=None, expected=None):
    """Pump parts concurrently with draining stdout; never buffer an entire file."""
    errors = []
    try:
        proc = subprocess.Popen(["zstd", "-q", "-d", "--long=31", "-c"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as error:
        raise Refused(f"zstd unavailable: {error}")

    def feed():
        try:
            for path in paths:
                with open(path, "rb") as stream:
                    shutil.copyfileobj(stream, proc.stdin, CHUNK)
        except BrokenPipeError:
            pass
        except BaseException as error:
            errors.append(error)
        finally:
            with contextlib.suppress(BrokenPipeError):
                proc.stdin.close()

    worker = threading.Thread(target=feed, daemon=True)
    worker.start()
    sha, count = hashlib.sha256(), 0
    try:
        if head is not None:
            # Read in chunks too: a "line" can itself be a multi-gigabyte field.
            remaining = head
            while remaining > 0:
                chunk = proc.stdout.read1(CHUNK)
                if not chunk:
                    break
                offset = 0
                for _ in range(min(remaining, chunk.count(b"\n"))):
                    offset = chunk.index(b"\n", offset) + 1
                    remaining -= 1
                    if remaining == 0:
                        chunk = chunk[:offset]
                        break
                sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            proc.terminate()
        else:
            while chunk := proc.stdout.read(CHUNK):
                sha.update(chunk)
                count += len(chunk)
                if output is not None:
                    output.write(chunk)
        message = proc.stderr.read().decode(errors="replace").strip()
        rc = proc.wait()
        worker.join()
        if head is None:
            if errors or rc:
                raise Refused(f"zstd decompress failed: {message or str(errors)}")
            if expected and (count != expected[0] or sha.hexdigest() != expected[1]):
                raise Refused("decompressed size or SHA-256 mismatch")
        return count, sha.hexdigest()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()
        worker.join(timeout=2)


def unpack(path, output=None, head=None):
    meta = read_pack(path)
    return decompress_parts([path / p["name"] for p in meta["parts"]], output, head, (meta["original_size"], meta["original_sha256"]))


def pack_file(source, destination, fast=False):
    guard_archive_path(source)
    guard_archive_path(destination)
    part_limit = FILE_LIMIT or PART_SIZE
    if part_limit <= 0:
        raise Refused("archive part size must be positive")
    destination.mkdir(parents=True)
    flags = ["-10"] if fast else ["-19", "--long=30"]
    parts = []
    try:
        with open(source, "rb") as incoming, tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen(["zstd", "-q", *flags, "-T0", "-c"], stdin=incoming, stdout=subprocess.PIPE, stderr=errors)
            try:
                while True:
                    sha, written = hashlib.sha256(), 0
                    name = f"part-{len(parts):03d}.zst"
                    outpath = destination / name
                    with open(outpath, "wb") as out:
                        while written < part_limit:
                            chunk = proc.stdout.read(min(CHUNK, part_limit - written))
                            if not chunk:
                                break
                            out.write(chunk)
                            sha.update(chunk)
                            written += len(chunk)
                        out.flush()
                        os.fsync(out.fileno())
                    if not written:
                        outpath.unlink()
                        break
                    parts.append(dict(name=name, size=written, sha256=sha.hexdigest()))
                if proc.wait():
                    errors.seek(0)
                    raise Refused("zstd compression failed: " + errors.read().decode(errors="replace"))
            finally:
                proc.stdout.close()
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        meta = dict(format=1, original_name=source.name, original_size=source.stat().st_size, original_sha256=hash_file(source), zstd_args=flags, part_size=part_limit, parts=parts)
        atomic_write(destination / "MANIFEST.json", json.dumps(meta, indent=2) + "\n")
        atomic_write(destination / "SHA256SUMS", "".join(f"{p['sha256']}  {p['name']}\n" for p in parts))
        unpack(destination)
        return meta
    except BaseException:
        remove_output(destination)
        raise


def copy_verified(source, destination, expected):
    guard_archive_path(source)
    guard_archive_path(destination)
    shutil.copy2(source, destination)
    with open(destination, "rb") as handle:
        os.fsync(handle.fileno())
    if hash_file(destination) != expected:
        raise Refused("copy SHA-256 mismatch")


def estimate_packed(source):
    length = source.stat().st_size
    if length <= 256 * 1024**2:
        return length
    samples, compressed = 0, 0
    with open(source, "rb") as stream:
        for i in range(25):
            stream.seek(int((length - 4 * 1024**2) * i / 24))
            chunk = stream.read(4 * 1024**2)
            result = subprocess.run(["zstd", "-q", "-3", "-c"], input=chunk, capture_output=True)
            if result.returncode:
                raise Refused("zstd sampling failed")
            samples += len(chunk)
            compressed += len(result.stdout)
    return int(length * compressed / samples * 1.15)


def lsof_paths(path, folder=True):
    args = [LSOF, "-Fn", "+D", str(path)] if folder else [LSOF, "-Fn", "--", str(path)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=LSOF_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        return set(), f"lsof cannot answer: {error}"
    if result.returncode not in (0, 1):
        return set(), f"lsof cannot answer (exit {result.returncode}): {result.stderr.strip()}"
    return {Path(x[1:]).resolve() for x in result.stdout.splitlines() if x.startswith("n")}, None


def live_reason(path, opened, min_age):
    if path.resolve() in opened:
        return "live: a process has it open"
    names = {p.name for p in path.parent.iterdir()}
    if any(BUSY.search(name) for name in names):
        return "live: busy-folder marker (.cursor, .partial-, .tmp- or .restoring-)"
    if any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")) or any(path.name.endswith(suffix) for suffix in ("-wal", "-shm", "-journal")):
        return "live: database sidecar"
    if time.time() - path.stat().st_mtime < min_age * 60:
        return "live: changed recently"
    return None


class Ledger:
    def __init__(self):
        self.entries = {}

    def before(self, path):
        path = Path(path)
        now = path.stat().st_mtime_ns if path.exists() else None
        entry = self.entries.setdefault(path, dict(before=now, after=now, external=False))
        if now != entry["after"]:
            entry["external"] = True

    def after(self, path):
        path = Path(path)
        self.entries[path]["after"] = path.stat().st_mtime_ns if path.exists() else None

    def mkdir(self, path):
        path = Path(path)
        if path.exists():
            return
        self.mkdir(path.parent)
        self.before(path.parent)
        self.before(path)
        path.mkdir()
        self.after(path)
        self.after(path.parent)

    def unlink(self, path):
        guard_archive_path(path)
        self.before(path.parent)
        path.unlink()
        self.after(path.parent)

    def young(self, path, min_age):
        current = path.stat().st_mtime_ns
        entry = self.entries.get(path)
        if entry:
            if entry["external"] or current != entry["after"]:
                return "changed by another program during this run"
            before = entry["before"]
            if before is None:
                return None
        else:
            before = current
        if time.time_ns() - before < min_age * 60 * 1e9:
            return "changed recently (age guard)"
        return None


def all_folders(root):
    result = []
    if root.is_dir() and not root.is_symlink():
        for parent, dirs, _ in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d != ".git" and not (Path(parent) / d).is_symlink()]
            result.extend(Path(parent) / d for d in dirs)
    return result


class FolderPlan:
    def __init__(self, store, scopes=None, excludes=None, min_age=MIN_AGE, ledger=None, opened=None):
        self.store, self.repo, self.name = store, store.repo, store.parked
        self.scopes = scopes or []
        self.excludes = excludes or []
        self.ledger = ledger or Ledger()
        self.min_age = min_age
        self.opened = opened or set()
        self.into, self.back, self.containers = [], [], []
        self.kept, self.bad_files = {}, []
        self.failed, self.blocked, self.moves = [], None, []
        self.places = {}
        if not self.repo or not self.name:
            return
        self.park = self.repo / self.name
        if self.park.is_symlink() or (self.park.exists() and not self.park.is_dir()):
            self.blocked = f"{self.name}/ is a link or is not a folder"
            return
        self.archived = set()
        for path in [*store.records, *(x["path"] for x in store.v1)]:
            for parent in Path(path.rstrip("/")).parents:
                if parent.parts:
                    self.archived.add(parent.as_posix())
            if path.endswith("/"):
                self.archived.add(path.rstrip("/"))
        self.linked = set()
        for parent, dirs, files in os.walk(self.repo, followlinks=False):
            dirs[:] = [d for d in dirs if d != ".git"]
            for name in dirs + files:
                path = Path(parent) / name
                if path.is_symlink():
                    target = path.resolve()
                    if inside(target, self.repo):
                        self.mark_ancestors(target, self.linked)
        self.in_use = set()
        for path in self.opened | {Path.cwd()}:
            if inside(path, self.repo):
                self.mark_ancestors(path, self.in_use)
        folders = [p for p in all_folders(self.repo) if not inside(p, self.park)]
        for path in sorted(folders, key=lambda p: len(p.parts), reverse=True):
            rel = nfc(path.relative_to(self.repo).as_posix())
            children = list(path.iterdir())
            content = any(p.name != ".DS_Store" and (p.is_symlink() or not p.is_dir() or p.name == ".git") for p in children)
            live_children = [self.places.get(nfc(p.relative_to(self.repo).as_posix())) == "live" for p in children if p.is_dir() and not p.is_symlink()]
            reason = self.guard(path, rel)
            if content or any(live_children):
                place = "live"
            elif reason:
                place = "live"
                self.kept[rel] = reason
            elif rel in self.archived:
                place = "park"
            else:
                place = "follow"
            self.places[rel] = place
        for path in sorted(folders, key=lambda p: len(p.parts)):
            rel = nfc(path.relative_to(self.repo).as_posix())
            if self.places[rel] == "follow":
                parent_rel = nfc(path.parent.relative_to(self.repo).as_posix())
                self.places[rel] = self.places.get(parent_rel, "live")
        wanted = set()
        if not self.scopes:
            wanted = {r for r, place in self.places.items() if place == "park"}
        else:
            for scope in self.scopes:
                if scope == self.name or scope.startswith(self.name + "/"):
                    continue
                path = self.repo / scope
                while path != self.repo and not path.is_dir():
                    path = path.parent
                rel = nfc(path.relative_to(self.repo).as_posix())
                selected = [r for r, place in self.places.items() if place == "park" and (r == rel or r.startswith(rel + "/"))]
                current = path
                while current != self.repo:
                    r = nfc(current.relative_to(self.repo).as_posix())
                    if self.places.get(r) == "park":
                        selected.extend(q for q, place in self.places.items() if place == "park" and (q == r or q.startswith(r + "/")))
                    current = current.parent
                wanted.update(selected)
        self.into = sorted(wanted)
        self.kept = {r: reason for r, reason in self.kept.items() if r in self.archived and (not self.scopes or any(r == s or r.startswith(s + "/") or s.startswith(r + "/") for s in self.scopes))}
        parked_folders = all_folders(self.park)
        clean = {}
        for path in sorted(parked_folders, key=lambda p: len(p.parts), reverse=True):
            rel = nfc(path.relative_to(self.park).as_posix())
            entries = list(path.iterdir())
            direct_bad = [p for p in entries if p.name != ".DS_Store" and not storage.apple_double(p) and (p.is_symlink() or not p.is_dir())]
            self.bad_files.extend(nfc(p.relative_to(self.repo).as_posix()) for p in direct_bad)
            clean[rel] = not direct_bad and all(clean.get(nfc(p.relative_to(self.park).as_posix()), False) for p in entries if p.is_dir() and not p.is_symlink())
        if self.park.exists():
            self.bad_files.extend(nfc(p.relative_to(self.repo).as_posix()) for p in self.park.iterdir() if p.name != ".DS_Store" and not storage.apple_double(p) and (p.is_symlink() or not p.is_dir()))
        back_place = {}
        for path in sorted(parked_folders, key=lambda p: len(p.parts)):
            rel = nfc(path.relative_to(self.park).as_posix())
            twin = self.repo / rel
            parent_rel = Path(rel).parent.as_posix()
            parent_live = parent_rel == "." or back_place.get(parent_rel) == "repo" or ((self.repo / parent_rel).is_dir() and self.places.get(parent_rel) != "park")
            # The park-side pass follows each scope's root tree. In particular,
            # a restored file's empty sibling folders follow its live parent.
            scoped = not self.scopes or Path(rel).parts[0] in {Path(s).parts[0] for s in self.scopes if Path(s).parts}
            reason = self.guard(twin, rel, age=False)
            if not exists(twin) and rel not in self.archived and parent_live and clean[rel] and not reason and scoped:
                back_place[rel] = "repo"
                self.back.append(rel)
            elif twin.is_dir() and not twin.is_symlink() and self.places.get(rel) != "park":
                back_place[rel] = "repo"
                if clean[rel]:
                    self.containers.append(rel)
            else:
                back_place[rel] = "park"

    def mark_ancestors(self, path, target):
        current = path
        while current != self.repo and inside(current, self.repo):
            target.add(nfc(current.relative_to(self.repo).as_posix()))
            current = current.parent

    def guard(self, path, rel, age=True):
        if match_path(rel, self.excludes) or match_path(rel + "/", self.excludes):
            return "excluded"
        if rel in self.linked:
            return "a symlink points into it"
        if rel in self.in_use:
            return "a process has it open or works in it"
        return self.ledger.young(path, self.min_age) if age and path.exists() else None

    def apply(self):
        if self.blocked:
            return
        race = os.environ.get("ICLOUD_ARCHIVE_RACE_FILE")
        if race:
            rel = stored_rel(race)
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("written by a racing process\n")
        jobs = [(self.repo / r, self.park / r, r, "in") for r in self.into]
        jobs += [(self.park / r, self.repo / r, r, "back") for r in self.back]
        saved_times, received = {}, set()
        for source, dest, rel, direction in sorted(jobs, key=lambda x: len(x[0].parts), reverse=True):
            if not source.is_dir() or source.is_symlink():
                self.failed.append((rel, "source is no longer a folder"))
                continue
            info = saved_times.get(source, source.stat())
            for parent in (source.parent, dest.parent):
                if parent.exists() and parent not in saved_times:
                    saved_times[parent] = parent.stat()
            made = not exists(dest)
            try:
                if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
                    raise OSError("destination is not a plain folder")
                dest.mkdir(parents=True, exist_ok=True)
                fault("tidy-after-mkdir")
                finder = source / ".DS_Store"
                if finder.is_file() and not finder.is_symlink():
                    if (dest / ".DS_Store").exists():
                        finder.unlink()
                    else:
                        publish(finder, dest / ".DS_Store")
                source.rmdir()
                fault("tidy-after-rmdir")
                os.chmod(dest, stat.S_IMODE(info.st_mode))
                os.utime(dest, ns=(info.st_atime_ns, info.st_mtime_ns))
                if hasattr(os, "chflags"):
                    os.chflags(dest, getattr(info, "st_flags", 0))
                self.moves.append((rel, direction))
                received.add(dest)
            except OSError as error:
                self.failed.append((rel, str(error)))
                if made:
                    with contextlib.suppress(OSError):
                        dest.rmdir()
        for rel in sorted(self.containers, key=lambda r: len(Path(r).parts), reverse=True):
            path = self.park / rel
            if path not in received:
                with contextlib.suppress(OSError):
                    if (path / ".DS_Store").is_file():
                        (path / ".DS_Store").unlink()
                    path.rmdir()
        with contextlib.suppress(OSError):
            if (self.park / ".DS_Store").is_file():
                (self.park / ".DS_Store").unlink()
            self.park.rmdir()
        for parent, info in saved_times.items():
            if parent.exists():
                os.utime(parent, ns=(info.st_atime_ns, info.st_mtime_ns))

    def problems(self):
        result = []
        for rel, direction in self.moves:
            new, old = (self.park / rel, self.repo / rel) if direction == "in" else (self.repo / rel, self.park / rel)
            if not new.is_dir() or exists(old):
                result.append(f"folder {rel} is not at its reported place")
        return result

    def report(self, plan=False):
        if self.blocked:
            print(f"  folders: none moved — {self.blocked}")
            return
        ins = self.into if plan else [r for r, d in self.moves if d == "in"]
        backs = self.back if plan else [r for r, d in self.moves if d == "back"]
        top = lambda paths: [r for r in paths if not any(r.startswith(p + "/") for p in paths if p != r)]
        ins, backs = top(ins), top(backs)
        if not (ins or backs or self.kept or self.failed or self.bad_files):
            print("  folders: nothing to move")
            return
        verb = "would move" if plan else "moved"
        tail = f", {len(self.failed)} not moved" if self.failed else ""
        print(f"  folders: {len(ins)} {verb} into {self.name}/, {len(backs)} {verb} back into the repo, {len(self.kept)} kept in place{tail}")
        for rel in ins[:20]:
            print(f"    → {self.name}/{rel}/")
        for rel in backs[:20]:
            print(f"    ← {rel}/")
        for rel, why in list(sorted(self.kept.items()))[:20]:
            print(f"    kept {rel}/: {why}")
        for rel, why in self.failed[:20]:
            print(f"    not moved {rel}/: {why}")
        for rel in self.bad_files[:10]:
            print(f"    [parked-file] {rel}: a file in {self.name}/ (the skill never puts one there); left alone")


def tidy_plan(store, scopes=None, excludes=None, min_age=MIN_AGE, ledger=None, check_open=True):
    plan = FolderPlan(store, scopes, excludes, min_age, ledger)
    if check_open and not plan.blocked and (plan.into or plan.back):
        opened, error = lsof_paths(store.repo)
        if error:
            plan.blocked = error
        else:
            plan = FolderPlan(store, scopes, excludes, min_age, ledger, opened)
    return plan


def check_protection(repo, allowed):
    if allowed:
        return
    hits = []
    for name in ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md"):
        path = repo / name
        if path.is_file():
            hits += [f"{name}:{i}: {line}" for i, line in enumerate(path.read_text().splitlines(), 1) if NO_DELETE.search(line)]
    if hits:
        raise Refused("no-delete rule:\n" + "\n".join(hits) + "\nShow these lines to the user; --allow-protected requires their explicit override.")


def check_remote(record, path, deep=False):
    supported(record)
    if not path.exists():
        raise Refused(f"archive copy missing: {path} — Nothing changed. Run verify")
    if record["form"] != "file":
        meta = read_pack(path)
        if meta["original_sha256"] != record["sha256"] or meta["original_size"] != record["size"]:
            raise Refused(f"compressed record does not match its manifest: {path}")
        if deep:
            unpack(path)
    elif path.stat().st_size != record["size"]:
        raise Refused(f"wrong size in archive: {path}")
    elif deep or not dataless(path):
        if hash_file(path) != record["sha256"]:
            raise Refused(f"SHA-256 mismatch in archive: {path}")


class RunReport:
    def __init__(self, repo, restoring=False):
        self.repo, self.restoring = repo, restoring
        self.items, self.skipped, self.changed, self.refusals = [], [], [], []
        self.bytes = 0
        self.before = shutil.disk_usage(repo).free

    def refuse(self, text):
        self.refusals.append(str(text))
        print(f"REFUSED: {text}", file=sys.stderr)

    def summary(self, store, folder=None):
        problems = []
        for rel in self.items:
            local = self.repo / rel
            if self.restoring:
                if not exists(local) or rel in store.records or any(x["path"].rstrip("/") == rel.rstrip("/") for x in store.v1):
                    problems.append(f"{rel}: restore result is not consistent on disk")
            else:
                record = store.records.get(rel)
                if exists(local) or not record or not store.location(record).exists():
                    problems.append(f"{rel}: archive result is not consistent on disk")
        if folder:
            problems += folder.problems()
        print("SUMMARY")
        verb = "restored" if self.restoring else "archived"
        detail = "" if self.restoring else f"   changed, not updated: {len(self.changed)}"
        print(f"  {verb}: {len(self.items)} ({size_text(self.bytes)})   refused: {len(self.refusals)}   skipped: {len(self.skipped)}{detail}")
        print("  checked on disk: " + ("PROBLEMS FOUND" if problems else "all files are where they should be"))
        for problem in problems:
            print("    ✗ " + problem)
        for rel, reason in self.skipped:
            print(f"    skipped {rel}: {reason}")
        for rel, detail in self.changed:
            print(f"    changed {rel}: {detail}")
        if folder:
            folder.report()
        elif store.park_note:
            print("  note: " + store.park_note)
        elif not store.parked:
            hypothetical = Store(self.repo)
            hypothetical.parked = "_archive"
            p = tidy_plan(hypothetical, check_open=False, min_age=0)
            if p.into:
                print(f"  note: {len(p.into)} folder(s) here hold only archived files. This repo keeps folders in place (it was archived before 2.3): `upgrade --plan` shows moving them into _archive/")
        after = shutil.disk_usage(self.repo).free
        delta = after - self.before
        print(f"  disk free (repo volume): {size_text(self.before)} → {size_text(after)} ({'+' if delta >= 0 else '-'}{size_text(abs(delta))}; includes other activity on this Mac)")
        if self.restoring:
            print(f"  space: restored files now use {size_text(self.bytes)} in the repo; their active archive copies are deleted")
        elif TARGET and TARGET.kind == "google-drive":
            print("  Google Drive: verified mounted-folder copy; remote upload is UNKNOWN. Check the Drive app. Automatic eviction is unsupported.")
            print("  space: no claim about remote durability or reclaimed cloud-cache space")
        elif inside(store.root, DRIVE) and (not TARGET or TARGET.kind == "icloud"):
            states = cloud_states(archive_files(store), "status")
            done = sum(state in ("uploaded", "evicted") for state in states.values())
            print(f"  iCloud upload: {done}/{len(states)} files uploaded")
            print("  space: NOT returned yet — iCloud Drive is on this disk. The bytes come back only after upload completes and `evict` runs.")
            if done < len(states):
                print("  Until upload completes, this Mac holds the only copy")
        else:
            if TARGET and TARGET.managed:
                print(f"  target: {TARGET.name} ({TARGET.kind}) at {TARGET.root}; identity checked")
            parent = store.root
            while not parent.exists():
                parent = parent.parent
            if parent.stat().st_dev != self.repo.stat().st_dev:
                print(f"  space: moved {size_text(self.bytes)} off the repo volume; actual disk-free change is reported above")
            else:
                print("  space: not returned (archive root is on this disk)")
        return 1 if problems or self.refusals else 0


def sync_one(repo, rel, args, ledger):
    initial = Store(repo)
    with lock(initial.id):
        store = Store(repo)
        store.check_v1_overlap()
        path = repo / rel
        if not path.is_file() or path.is_symlink():
            raise Refused(f"vanished or no longer a regular file: {rel}")
        if time.time() - path.stat().st_mtime < args.min_age * 60:
            return "skipped", "changed during this run", 0
        if any(rel == r["path"].rstrip("/") or rel.startswith(r["path"].rstrip("/") + "/") for r in store.v1):
            return "skipped", "inside a v1 entry", 0
        sha = hash_file(path)
        old = store.records.get(rel)
        if old:
            supported(old)
            if sha == old["sha256"]:
                check_remote(old, store.location(old))
                store.settle()
                ledger.unlink(path)
                return "finished", "", old["size"]
            if not args.update:
                return "changed", "differs from its iCloud copy; rerun sync with --update to replace it (the old copy is kept)", 0
        clash = next((p for p in store.records if p.casefold() == rel.casefold() and p != rel), None)
        if clash:
            raise Refused(f"case-only clash: {rel} and {clash}")
        raw, packed = store.root / "files" / rel, store.root / ".big" / rel
        # Detect case variants on case-sensitive test disks too.
        for area, dest in ((store.root / "files", raw), (store.root / ".big", packed)):
            cursor = area
            for part in Path(rel).parts:
                if cursor.is_dir():
                    different = next((x.name for x in cursor.iterdir() if x.name.casefold() == part.casefold() and x.name != part), None)
                    if different:
                        raise Refused(f"case-only clash in archive: {different} and {part}")
                cursor /= part
        if old is None and (exists(raw) or exists(packed)):
            if raw.is_file() and not raw.is_symlink() and not exists(packed) and hash_file(raw) == sha:
                record = record_for(rel, path, sha)
                store.settle()
                os.chmod(raw, 0o444)
                store.append("add", record)
                ledger.unlink(path)
                return "adopted", "", record["size"]
            raise Refused(f"archive already has {rel} with no record of it; not overwriting (run verify)")
        store.settle()
        if old:
            check_remote(old, store.location(old))
            kept = store.root / ".versions" / rel / (old["date"] + "-" + old["sha256"][:8] + (".big" if old["form"] != "file" else ""))
            stem, serial = kept, 0
            while exists(kept):
                serial += 1
                kept = stem.with_name(stem.name + f"-{serial}")
            kept.parent.mkdir(parents=True, exist_ok=True)
            publish(store.location(old), kept)
            store.append("del", {"path": rel})
        info = path.stat()
        record = record_for(rel, path, sha)
        packing = args.pack or (FILE_LIMIT > 0 and info.st_size > FILE_LIMIT)
        destination = packed if packing else raw
        ensure_free(store.root, estimate_packed(path) if packing else info.st_size)
        guard_archive_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".partial-{os.getpid()}")
        try:
            if exists(temporary):
                raise Refused(f"partial output already exists: {temporary}; run verify")
            if packing:
                meta = pack_file(path, temporary, args.fast)
                record["form"] = f"zst×{len(meta['parts'])}"
            else:
                copy_verified(path, temporary, sha)
                os.chmod(temporary, 0o444)
            fault("after-copy")
            if exists(destination):
                raise Refused(f"destination appeared meanwhile: {destination}; not overwriting")
            publish(temporary, destination)
        except BaseException as error:
            if exists(temporary):
                remove_output(temporary)
            full = isinstance(error, OSError) and error.errno == errno.ENOSPC
            raise Refused(("disk full while archiving; " if full else str(error) + "; ") + "partial output removed, original untouched")
        fault("after-rename")
        store.append("add", record)
        fault("after-index")
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
            raise Refused(f"{rel} changed while copying; archive copy kept, local NOT deleted")
        guard_archive_path(destination)
        check_remote(record, destination, deep=True)
        ledger.unlink(path)
        fault("after-delete")
        return "archived", "", record["size"]


def sync_command(repo, args):
    store = Store(repo)
    store.check_v1_overlap()
    check_protection(repo, args.allow_protected)
    report, ledger, seen, scopes = RunReport(repo), Ledger(), {}, []
    changed_store = False
    manifest_path = repo / MANIFEST
    before_manifest = (manifest_path.stat().st_size, manifest_path.stat().st_mtime_ns) if manifest_path.exists() else None
    for value in args.paths:
        try:
            rel, parked = store.rel(value, "sync")
            scopes.append(rel)
            if parked:
                report.skipped.append((rel, "the park folder holds only folders; skipped"))
                continue
            path = repo / rel
            if path.is_symlink():
                raise Refused(f"symlink named directly: {rel}")
            if not exists(path):
                if any(under(p, [rel]) for p in [*store.records, *(r["path"] for r in store.v1)]):
                    print(f"{rel}: already archived, nothing new")
                    continue
                raise Refused(f"path does not exist: {rel}")
            if storage.reserved_collision(path):
                raise Refused(f"reserved ._ filename or ordinary metadata-name sibling; kept local: {rel}")
            if path.is_file() and (path.name == ".keep" or litter(path.name)):
                raise Refused(f"never archive this name directly: {rel}")
            files = []
            if path.is_dir():
                for parent, dirs, names in os.walk(path, followlinks=False):
                    retained = []
                    for name in sorted(dirs):
                        p = Path(parent) / name
                        r = nfc(p.relative_to(repo).as_posix())
                        if storage.apple_double(p):
                            continue
                        if p.is_symlink():
                            report.skipped.append((r, "symlink"))
                        elif name != ".git" and not match_path(r, args.exclude):
                            retained.append(name)
                    dirs[:] = retained
                    for name in sorted(names):
                        p = Path(parent) / name
                        r = nfc(p.relative_to(repo).as_posix())
                        if storage.apple_double(p):
                            continue
                        if p.is_symlink():
                            report.skipped.append((r, "symlink"))
                        elif storage.reserved_collision(p):
                            report.skipped.append((r, "reserved ._ filename or ordinary metadata-name sibling; kept local"))
                        elif name not in (".git", ".keep") and not litter(name) and r not in (INDEX, MANIFEST, "ICLOUD.md", "ICLOUD.manifest.jsonl", "ARCHIVE.md", "ARCHIVE.manifest.jsonl") and not match_path(r, args.exclude):
                            files.append((r, p))
            elif path.is_file():
                if not match_path(rel, args.exclude):
                    files = [(rel, path)]
            else:
                raise Refused(f"not a regular file or folder: {rel}")
            opened, open_error = lsof_paths(path, path.is_dir())
            if open_error and TARGET and TARGET.managed:
                raise Refused("cannot confirm whether files are open; target operation refused: " + open_error)
            for rel_file, file in files:
                key = rel_file.casefold()
                if key in seen:
                    if seen[key] != rel_file:
                        report.refuse(f"case-only clash: {rel_file} and {seen[key]}")
                    continue
                seen[key] = rel_file
                if any(rel_file == r["path"].rstrip("/") or rel_file.startswith(r["path"].rstrip("/") + "/") for r in store.v1):
                    report.skipped.append((rel_file, "inside a v1 entry"))
                    continue
                try:
                    reason = live_reason(file, opened, args.min_age)
                    if reason:
                        report.skipped.append((rel_file, reason))
                        print(f"skipped (live) {rel_file}: {reason}")
                        continue
                    state, detail, count = sync_one(repo, rel_file, args, ledger)
                    if state in ("skipped", "changed"):
                        getattr(report, state).append((rel_file, detail))
                    else:
                        changed_store = True
                        report.items.append(rel_file)
                        report.bytes += count
                        print(f"{state} {rel_file}")
                except (Refused, OSError) as error:
                    report.refuse(f"{rel_file}: {error}")
        except (Refused, OSError) as error:
            report.refuse(error)
    with lock(store.id):
        store = Store(repo)
        after_manifest = (manifest_path.stat().st_size, manifest_path.stat().st_mtime_ns) if manifest_path.exists() else None
        if changed_store or before_manifest != after_manifest:
            store.save()
        folder = None
        if store.parked and (changed_store or not report.refusals):
            folder = tidy_plan(store, scopes, args.exclude, args.min_age, ledger)
            folder.apply()
    return report.summary(Store(repo), folder)


def fallback_hint(store, rel, command, error, record=None):
    writer = record.get("by", "2.0.0") if record else "1.x"
    return Refused(f"built-in reader for {rel} failed: {error}; skill {writer} wrote this. Try: python3 {shlex.quote(str(HERE / 'archive.py'))} --repo {shlex.quote(str(store.repo))} {command} --via-history {shlex.quote(str(store.repo / rel))}")


def restore_one(repo, rel, ledger, v1=False):
    initial = Store(repo)
    with lock(initial.id):
        store = Store(repo)
        row = next((x for x in store.v1 if x["path"] == rel), None) if v1 else store.records.get(rel)
        if row is None:
            raise Refused(f"not archived: {rel}")
        if not v1:
            supported(row)
        path = repo / rel.rstrip("/")
        if exists(path):
            raise Refused(f"{rel} exists locally; not overwriting")
        source = store.v1_location(row) if v1 else store.location(row)
        if storage.reserved_collision(source) or storage.reserved_collision(path):
            raise Refused("reserved ._ filename collision; copies retained for inspection")
        if not source.exists():
            raise Refused(f"archive copy missing — Nothing changed. Run verify: {source}")
        if dataless(source):
            print("note: iCloud will fetch it on read", file=sys.stderr)
        packing = row["form"].startswith("zst")
        if packing:
            meta = read_pack(source)
            need, expected = meta["original_size"], meta["original_sha256"]
        else:
            need = sum(p.stat().st_size for p in source.rglob("*") if p.is_file()) if source.is_dir() else source.stat().st_size
            expected = digest(source) if v1 else row["sha256"]
        ensure_free(repo, need)
        store.settle()
        ledger.mkdir(path.parent)
        temporary = path.with_name(path.name + f".restoring-{os.getpid()}")
        try:
            if packing:
                with open(temporary, "xb") as out:
                    unpack(source, out)
                    out.flush()
                    os.fsync(out.fileno())
            elif source.is_dir():
                shutil.copytree(source, temporary, copy_function=shutil.copy2)
                if digest(temporary) != expected:
                    raise Refused("restored folder hash mismatch")
            else:
                copy_verified(source, temporary, expected)
            if not v1:
                if temporary.stat().st_size != row["size"] or hash_file(temporary) != expected:
                    raise Refused("restored size or SHA-256 mismatch")
                os.chmod(temporary, row["mode"])
                os.utime(temporary, ns=(row["mtime_ns"], row["mtime_ns"]))
            if exists(path):
                raise Refused(f"{rel} appeared meanwhile; not overwriting")
            ledger.before(path.parent)
            publish(temporary, path)
            ledger.after(path.parent)
        except BaseException:
            if exists(temporary):
                remove_output(temporary)
            raise
        fault("restore-after-rename")
        if v1:
            store.v1 = [x for x in store.v1 if x["path"] != rel]
            store.save()
        else:
            store.append("del", {"path": rel})
        fault("restore-after-index")
        remove_output(source)
        prune(source.parent, store.root)
        return need


def restore_command(repo, args):
    store = Store(repo)
    if args.via_history:
        if len(args.paths) != 1:
            raise Refused("restore --via-history takes exactly one path")
        rel, _ = store.rel(args.paths[0], "restore")
        return via_history(store, rel, "restore")
    report, ledger, scopes = RunReport(repo, restoring=True), Ledger(), []
    work_v1, work_v2 = [], []
    for value in args.paths:
        try:
            rel, _ = store.rel(value, "restore")
            scopes.append(rel)
            containing = next((x for x in store.v1 if x["form"] == "dir" and rel.startswith(x["path"].rstrip("/") + "/")), None)
            if containing:
                raise Refused(f"{rel} is inside v1 folder {containing['path']}; restore that folder")
            old = [x["path"] for x in store.v1 if under(x["path"], [rel])]
            records = [p for p in store.records if under(p, [rel])]
            if not old and not records:
                raise Refused(f"not archived: {rel}")
            work_v1.extend(old)
            work_v2.extend(records)
        except Refused as error:
            report.refuse(error)
    remembered_park = store.parked
    for v1, paths in [(True, work_v1), (False, work_v2)]:
        for rel in dict.fromkeys(paths):
            try:
                tag = "fmt1-restore" if v1 else "fmt2-restore"
                if os.environ.get("ICLOUD_ARCHIVE_BREAK") == tag:
                    raise fallback_hint(store, rel, "restore", "injected reader failure", None if v1 else store.records.get(rel))
                count = restore_one(repo, rel, ledger, v1)
                report.items.append(rel)
                report.bytes += count
                print(f"restored {rel}")
            except (Refused, OSError) as error:
                report.refuse(error)
    with lock(store.id):
        store = Store(repo)
        if report.items:
            store.save()
        store.parked = remembered_park
        folder = tidy_plan(store, scopes, min_age=MIN_AGE, ledger=ledger) if remembered_park and report.items else None
        if folder:
            folder.apply()
    return report.summary(Store(repo), folder)


def resolve_cloud_read(path):
    entries = registry_entries()
    for entry in entries:
        for origin in entry.get("imports", []):
            foreign = expand(origin["from"])
            if inside(path, foreign):
                rel = path.relative_to(foreign)
                if origin["kind"] == "split":
                    folder = registry_root(entry["root"]) / ".big" / origin["maps_to"]
                    kept = folder / "imported" / rel
                    result = kept if kept.exists() else folder / rel if (folder / rel).exists() else folder
                    return entry, None, result
                return entry, nfc(rel.as_posix()), None
    if inside(path, BASE):
        for entry in entries:
            for root in [entry["root"], *entry.get("old_roots", [])]:
                root = registry_root(root)
                if inside(path, root):
                    rel = path.relative_to(root).as_posix()
                    for prefix in ("files/", ".big/"):
                        if rel.startswith(prefix):
                            rel = rel[len(prefix):]
                            break
                    if rel.endswith(".packed"):
                        rel = rel[:-7]
                    return entry, nfc(rel), None
    return None


def read_command(store, rel, args):
    if args.via_history:
        return via_history(store, rel, "read", args)
    record = store.records.get(rel)
    row = next((x for x in store.v1 if x["path"].rstrip("/") == rel.rstrip("/")), None)
    if row is None:
        row = next((x for x in store.v1 if x["form"] == "dir" and rel.startswith(x["path"].rstrip("/") + "/")), None)
        if row:
            print(store.root / rel)
            return 0
    try:
        if record:
            supported(record)
            path = store.location(record)
            schema = "fmt2-read"
        elif row:
            path = store.v1_location(row)
            schema = "fmt1-read"
        else:
            children = [x for x in store.records.values() if under(x["path"], [rel])]
            if children:
                if any(x["form"] != "file" for x in children):
                    print("note: compressed files under this folder: use read --head N on each file", file=sys.stderr)
                print(store.root / "files" / rel)
                return 0
            raise Refused(f"not archived: {rel}")
        if os.environ.get("ICLOUD_ARCHIVE_BREAK") == schema:
            raise RuntimeError("injected reader failure")
        form = (record or row)["form"]
        if form.startswith("zst"):
            meta = read_pack(path)
            if args.head is not None:
                unpack(path, head=args.head)
                return 0
            if meta["original_size"] > READ_FULL_LIMIT and not args.full:
                raise Refused(f"plain read needs --full for a compressed file over {size_text(READ_FULL_LIMIT)}; use read --head N {shlex.quote(rel)} for a sample")
            destination = Path(tempfile.gettempdir()) / "icloud-archive-read" / store.id / rel
            if not destination.is_file() or destination.stat().st_size != meta["original_size"]:
                ensure_free(destination, meta["original_size"])
                guard_archive_path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                tmp = destination.with_name(destination.name + f".tmp-{os.getpid()}")
                try:
                    with open(tmp, "wb") as out:
                        unpack(path, out)
                        out.flush()
                        os.fsync(out.fileno())
                    os.chmod(tmp, 0o444)
                    os.replace(tmp, destination)
                finally:
                    tmp.unlink(missing_ok=True)
            path = destination
        elif dataless(path):
            print("note: dataless; iCloud downloads it on open", file=sys.stderr)
        print(path)
        return 0
    except Refused:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        raise fallback_hint(store, rel, "read", error, record)


def list_command(store, scopes):
    for row in sorted(store.v1, key=lambda x: x["path"]):
        if under(row["path"], scopes):
            print(f"{row['path']}\tformat 1\t{row['form']}\tby 1.x\t{row['date']}\t{store.v1_location(row)}")
    for rel, row in sorted(store.records.items()):
        if under(rel, scopes):
            print(f"{rel}\tformat {row.get('format', 2)}\t{row['form']}\tby {row.get('by', '2.0.0')}\t{row['date']}\t{store.location(row)}")
    return 0


def walk_files(path):
    if path.is_file() or path.is_symlink():
        return [path]
    result = []
    if path.is_dir():
        for parent, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if d != ".git" and not (Path(parent) / d).is_symlink()]
            result += [Path(parent) / f for f in files if not litter(f) and not storage.apple_double(Path(parent) / f)]
    return result


def orphan_items(store):
    result = []
    if not store.root.is_dir():
        return result
    reserved = {"files", ".big", ".versions", ".manifest.jsonl", ".import-journal.jsonl"}
    v1_locations = [store.v1_location(r) for r in store.v1]
    for parent, dirs, files in os.walk(store.root, followlinks=False):
        base = Path(parent)
        retained = []
        for d in sorted(dirs):
            item = base / d
            if storage.apple_double(item):
                continue
            if base == store.root and d in reserved:
                continue
            if any(item == v or inside(item, v) for v in v1_locations):
                continue
            if any(inside(v, item) for v in v1_locations):
                retained.append(d)
            else:
                result.append((item, nfc(item.relative_to(store.root).as_posix())))
        dirs[:] = retained
        for name in sorted(files):
            item = base / name
            if storage.apple_double(item) or litter(name) or (base == store.root and name in reserved) or any(item == v or inside(item, v) for v in v1_locations) or re.search(r"\.partial-\d+$", name):
                continue
            result.append((item, nfc(item.relative_to(store.root).as_posix())))
    for path in walk_files(store.root / "files"):
        rel = nfc(path.relative_to(store.root / "files").as_posix())
        if rel not in store.records and not re.search(r"\.partial-\d+$", rel):
            result.append((path, rel))
    big = store.root / ".big"
    if big.is_dir():
        for parent, dirs, files in os.walk(big):
            p = Path(parent)
            if "MANIFEST.json" in files or "IMPORT-PLAN.json" in files:
                rel = nfc(p.relative_to(big).as_posix())
                if rel not in store.records:
                    result.append((p, rel))
                dirs[:] = []
    return result


def record_states(store, scopes=None, deep=False):
    counts = collections.Counter()
    details, archived_bytes = [], 0
    for row in store.v1:
        if not under(row["path"], scopes):
            continue
        rel = row["path"].rstrip("/")
        local, cloud = store.repo / rel, store.v1_location(row)
        if not cloud.exists():
            state = "missing-remote" if exists(local) else "lost"
        elif exists(local):
            state = "interrupted"
        else:
            state = "archived (v1)"
        counts[state] += 1
        if state != "archived (v1)":
            details.append((state, rel))
    for rel, record in sorted(store.records.items()):
        if not under(rel, scopes):
            continue
        local, cloud = store.repo / rel, store.location(record)
        if record.get("format", 2) != 2:
            state = "unknown-format"
        elif not cloud.exists():
            state = "missing-remote" if exists(local) else "lost"
        else:
            try:
                check_remote(record, cloud, deep)
                if exists(local):
                    same = local.is_file() and (hash_file(local) == record["sha256"] if deep else (local.stat().st_size, local.stat().st_mtime_ns) == (record["size"], record["mtime_ns"]))
                    state = "interrupted" if same else "changed"
                else:
                    state = "archived"
                    archived_bytes += record["size"]
            except (Refused, OSError):
                state = "corrupt"
        counts[state] += 1
        if state != "archived":
            details.append((state, rel))
    for cloud, rel in orphan_items(store):
        if under(rel, scopes):
            counts["orphan"] += 1
            details.append(("orphan", f"{cloud}; left alone"))
    return counts, details, archived_bytes


def status_folders(store, scopes):
    if store.parked:
        p = tidy_plan(store, scopes, check_open=False)
        root = store.repo / store.parked
        folders = all_folders(root)
        top = [x for x in folders if x.parent == root]
        print(f"parked: {len(top)} folder tree(s), {len(folders)} folder(s), in {store.parked}/ (their files are all in iCloud)")
        for rel in p.into:
            if Path(rel).parent.as_posix() not in p.into:
                print(f"[unparked] {rel}/: holds only archived files; `tidy` moves it into {store.parked}/")
        for rel in p.back:
            if Path(rel).parent.as_posix() not in p.back:
                print(f"[unparked] {store.parked}/{rel}/: no archived file under it; `tidy` moves it back into the repo")
        for rel in p.bad_files:
            print(f"[parked-file] {rel}: a file in {store.parked}/ (the skill never puts one there); move it out by hand")
    elif store.park_note:
        print("note: " + store.park_note)
    else:
        store.parked = "_archive"
        plan = tidy_plan(store, scopes, min_age=0, check_open=False)
        store.parked = None
        if plan.into:
            print(f"note: {len(plan.into)} folder(s) hold only archived files. This repo keeps folders in place (it was archived before 2.3): `upgrade --plan` shows moving them into _archive/")


def status_command(store, scopes, deep=False):
    scheme = "nested" if store.scheme == "nested" else "flat; `upgrade` moves it under repos/"
    print(f"root: {store.root}/  ({scheme})")
    for note in store.notes:
        print(f"note: {note} (the next change, or `verify --fix`, writes it to the repo)")
    writers = collections.Counter((x.get("format", 2), x.get("by", "2.0.0")) for x in store.records.values() if under(x["path"], scopes))
    if store.v1:
        writers[(1, "1.x")] += len([x for x in store.v1 if under(x["path"], scopes)])
    if writers:
        print("written: " + ", ".join(f"format {fmt} by {writer} ×{n}" for (fmt, writer), n in sorted(writers.items())))
    counts, details, byte_count = record_states(store, scopes, deep)
    new = collections.defaultdict(list)
    for path in walk_files(store.repo):
        rel = nfc(path.relative_to(store.repo).as_posix())
        if rel in (INDEX, MANIFEST) or path.name == ".keep" or not under(rel, scopes):
            continue
        if rel in store.records or any(rel == x["path"].rstrip("/") or rel.startswith(x["path"].rstrip("/") + "/") for x in store.v1):
            continue
        if store.parked and rel.startswith(store.parked + "/"):
            continue
        new[folder_key(rel)].append(path)
    counts["new"] = sum(map(len, new.values()))
    for state in ("archived", "archived (v1)", "new", "changed", "interrupted", "missing-remote", "lost", "corrupt", "orphan", "unknown-format"):
        tail = f"  ({size_text(byte_count)})" if state == "archived" and counts[state] else ""
        print(f"  {state:<15} {counts[state]}{tail}")
    order = {s: i for i, s in enumerate(("changed", "interrupted", "missing-remote", "lost", "corrupt", "orphan", "unknown-format"))}
    for state, detail in sorted(details, key=lambda x: (order.get(x[0], 99), x[1])):
        print(f"[{state}] {detail}")
    for key, paths in sorted(new.items()):
        print(f"[new] {key}\t{len(paths)} file(s), {size_text(sum(p.stat().st_size for p in paths))}")
    status_folders(store, scopes)
    return 2 if any(counts[k] for k in ("interrupted", "missing-remote", "lost", "corrupt", "orphan", "unknown-format")) else 0


def verify_command(repo, args):
    initial = Store(repo)
    with lock(initial.id):
        store = Store(repo)
        problems = fixed = 0
        write = False

        def issue(check, detail, repair=None):
            nonlocal problems, fixed, write
            problems += 1
            print(f"[{check}] {detail}")
            if args.fix and repair:
                try:
                    guard_archive_path(store.root)
                    repair()
                    fixed += 1
                    write = True
                    print(f"  fixed: {detail}")
                except (Refused, OSError, ValueError) as error:
                    print(f"  not fixed: {error}")

        for receipt, publication in storage.publication_problems(BASE / ".publications", store.root) + storage.publication_problems(BASE / ".publications", repo):
            issue("publication", publication["destination"] + "; exclusive-copy publication was interrupted", lambda r=receipt, v=publication: storage.repair_publication(r, v))
        protected_publication_sources = {Path(p[1]["source"]) for p in storage.publication_problems(BASE / ".publications", store.root) + storage.publication_problems(BASE / ".publications", repo)}
        if store.torn:
            issue("manifest", "torn last manifest line", lambda: None)
        for note in store.notes:
            issue("index", note + "; the repo index is behind", lambda: None)
        if store.park_missing:
            issue("park-setting", "a copy of the park setting is missing", lambda: None)
        plan = tidy_plan(store, check_open=False)
        for rel in plan.bad_files:
            issue("parked-file", rel + "; move it out by hand")
        for rel in plan.into:
            if Path(rel).parent.as_posix() not in plan.into:
                print(f"note: [unparked] {rel}/: tidy moves it into {store.parked}/")
        for rel in plan.back:
            if Path(rel).parent.as_posix() not in plan.back:
                print(f"note: [unparked] {store.parked}/{rel}/: tidy moves it back into the repo")
        for area in (store.root, BASE / "registry", repo):
            if area.exists():
                for path in walk_files(area):
                    if CONFLICT.search(path.stem) and (area != repo or path.name.startswith("ICLOUD")):
                        issue("conflict-copy", f"{path}; compare by hand, never delete unread")
        if store.registry and registry_root(store.registry["root"]) != store.root:
            issue("registry", "root differs from the repo index", lambda: None)
        for old in store.registry.get("old_roots", []):
            path = registry_root(old)
            if any(not litter(p.name) for p in walk_files(path)):
                issue("ghost", f"{path}: leftover old root; check by hand")
        if (store.records or store.v1) and not store.registry:
            print("note: this archive is not in the registry yet; registry --scan registers it")
        for row in list(store.v1):
            rel = row["path"].rstrip("/")
            cloud, local = store.v1_location(row), repo / rel
            moved = store.root / "files" / rel
            big = store.root / ".big" / rel
            if moved.exists() or big.exists():
                issue("half-upgraded", rel, lambda row=row: upgrade_v1(store, row, Ledger()))
                continue
            if cloud.exists() and exists(local):
                try:
                    if row["form"].startswith("zst"):
                        meta = read_pack(cloud)
                        equal = local.is_file() and hash_file(local) == meta["original_sha256"]
                    else:
                        equal = digest(cloud) == digest(local)
                except (OSError, Refused):
                    equal = False
                issue("complete-archive" if equal else "conflict", rel, (lambda p=local: remove_output(p)) if equal else None)
            elif not cloud.exists():
                issue("missing-remote" if exists(local) else "lost", rel, (lambda row=row: store.v1.remove(row)) if exists(local) else None)
        for rel, record in list(sorted(store.records.items())):
            local, cloud = repo / rel, store.location(record)
            if record.get("format", 2) != 2:
                issue("unknown-format", f"{rel}: update the skill")
            elif not cloud.exists():
                issue("missing-remote" if exists(local) else "lost", rel, (lambda rel=rel: store.records.pop(rel, None)) if exists(local) else None)
            else:
                try:
                    check_remote(record, cloud)
                except (Refused, OSError) as error:
                    issue("corrupt", f"{rel}: {error}")
                    continue
                if exists(local):
                    same = local.is_file() and not local.is_symlink() and hash_file(local) == record["sha256"]
                    issue("interrupted" if same else "changed", rel, (lambda p=local: p.unlink()) if same else None)
        if store.root.exists():
            for parent, dirs, files in os.walk(store.root, topdown=True, followlinks=False):
                for name in list(dirs) + files:
                    if re.search(r"\.partial-\d+$", name):
                        path = Path(parent) / name
                        if not exists(path) or storage.apple_double(path) or any(path == protected or inside(path, protected) for protected in protected_publication_sources):
                            continue
                        issue("leftover", str(path), lambda p=path: remove_output(p))
                        if name in dirs:
                            dirs.remove(name)
        for cloud, rel in orphan_items(store):
            local = repo / rel
            equal = False
            try:
                if exists(local) and not local.is_symlink():
                    if cloud.is_dir() and (cloud / "MANIFEST.json").is_file():
                        equal = local.is_file() and hash_file(local) == read_pack(cloud)["original_sha256"]
                    elif cloud.is_dir() == local.is_dir():
                        equal = digest(cloud) == digest(local)
            except (Refused, OSError):
                pass
            issue("orphan", str(cloud) + ("; identical to local" if equal else "; left alone"), (lambda p=cloud: remove_output(p)) if equal else None)
        for path in walk_files(repo):
            if any(path == protected or inside(path, protected) for protected in protected_publication_sources):
                continue
            if re.search(r"\.restoring-\d+$", path.name) or re.fullmatch(r"\.(ICLOUD\.md|ICLOUD\.manifest\.jsonl)\.tmp-\d+", path.name):
                issue("leftover", str(path), lambda p=path: remove_output(p))
        if store.records:
            if not (repo / INDEX).is_file() or (repo / INDEX).read_text() != store.render():
                issue("index", f"{INDEX} is out of date with {MANIFEST}", lambda: None)
            local_text = (repo / MANIFEST).read_text() if (repo / MANIFEST).is_file() else ""
            mirror_text = (store.root / ".manifest.jsonl").read_text() if (store.root / ".manifest.jsonl").is_file() else ""
            if local_text != mirror_text:
                issue("mirror", f"{store.root / '.manifest.jsonl'} is out of date", lambda: None)
        if args.fix and write:
            store.save()
        if problems:
            print(f"{problems} problem(s), {fixed} fixed, {problems - fixed} need a human")
        else:
            print("clean")
        return 2 if problems > fixed else 0


def archive_files(store):
    result = []
    for row in store.v1:
        result += walk_files(store.v1_location(row))
    for row in store.records.values():
        result += walk_files(store.location(row))
    return list(dict.fromkeys(result))


def cloud_states(paths, action="status"):
    states = {}
    for i in range(0, len(paths), 400):
        batch = paths[i:i + 400]
        result = subprocess.run(["swift", str(HERE / "icloud_status.swift"), action, *map(str, batch)], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "\t" in line:
                state, path = line.split("\t", 1)
                states[Path(path)] = state
        for path in batch:
            states.setdefault(path, "error:" + (result.stderr.strip() or "no helper response"))
    return states


def pending_upload(root):
    if os.environ.get("ICLOUD_ARCHIVE_FAKE_PENDING") == "1":
        return True
    if TARGET and TARGET.kind != "icloud":
        return False
    if not inside(root, DRIVE):
        return False
    return any(x not in ("uploaded", "evicted") for x in cloud_states(walk_files(root)).values())


def wait_uploaded(root, minutes):
    deadline = time.monotonic() + max(0, minutes) * 60
    while pending_upload(root):
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(10, max(0, deadline - time.monotonic())))
    return True


def cloud_command(store, action):
    if not store.records and not store.v1:
        print("nothing archived")
        return 0
    if TARGET and TARGET.kind == "google-drive":
        print("Google Drive filesystem copy is available; remote upload confirmation and eviction are unsupported. Confirm sync in Google Drive; no cloud durability or freed space is claimed.")
        return 2
    if not inside(store.root, DRIVE) or (TARGET and TARGET.kind != "icloud"):
        print(f"archive root {store.root} is not in iCloud Drive; upload and evict do not apply")
        return 0
    groups = collections.OrderedDict()
    for row in sorted(store.v1, key=lambda x: x["path"]):
        groups[row["path"] + " (v1)"] = walk_files(store.v1_location(row))
    for row in sorted(store.records.values(), key=lambda x: x["path"]):
        groups.setdefault(folder_key(row["path"]), []).extend(walk_files(store.location(row)))
    paths = [p for files in groups.values() for p in files]
    before = shutil.disk_usage(store.root).free
    states = cloud_states(paths, "status" if action == "upload-status" else "evict")
    if action == "upload-status":
        for label, files in groups.items():
            done = sum(states[p] in ("uploaded", "evicted") for p in files)
            print(f"{label}\t{done}/{len(files)} uploaded")
        pending = any(s not in ("uploaded", "evicted") for s in states.values())
        if pending:
            print("WARNING: not everything is uploaded; the only copy is still on this Mac")
        return 2 if pending else 0
    for label, files in groups.items():
        counts = collections.Counter(states[p] for p in files)
        print(f"{label}\t" + ", ".join(f"{n} {state}" for state, n in sorted(counts.items())))
    deadline = time.monotonic() + 30
    remaining = list(paths)
    while remaining:
        remaining = [p for p in remaining if p.exists() and not dataless(p)]
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    evicted = [p for p in paths if p not in remaining]
    after = shutil.disk_usage(store.root).free
    print("SUMMARY")
    print(f"  checked on disk: {len(evicted)}/{len(paths)} files are dataless (bytes only in iCloud)")
    print(f"  space returned: {size_text(sum(p.stat().st_size for p in evicted if p.exists()))} (sum of evicted file sizes)")
    print(f"  disk free: {size_text(before)} → {size_text(after)} (includes other activity on this Mac)")
    for path in remaining[:10]:
        print(f"    ✗ still local: {path}")
    if remaining:
        print("  rerun evict after the upload finishes")
    return 2 if remaining else 0


def tidy_command(repo, args):
    initial = Store(repo)
    with lock(initial.id):
        store = Store(repo)
        if not store.parked:
            raise Refused(store.park_note or "this repo keeps folders in place (it was archived before 2.3): `upgrade --plan` shows moving them into _archive/")
        scopes = [store.rel(p, "tidy")[0] for p in args.paths]
        plan = tidy_plan(store, scopes, args.exclude, args.min_age)
        if plan.blocked:
            print(f"REFUSED: {plan.blocked}", file=sys.stderr)
        if not args.plan:
            plan.apply()
        print("SUMMARY")
        if args.plan:
            print("  plan only: nothing changed")
        plan.report(args.plan)
        problems = plan.problems()
        if not args.plan:
            print("  checked on disk: " + ("PROBLEMS FOUND" if problems else "every folder is where it should be"))
            for problem in problems:
                print("    ✗ " + problem)
        return 1 if plan.blocked or problems else 0


def validate_park_name(name):
    if not name or "/" in name or name.startswith(".") or name in (INDEX, MANIFEST, ".git") or "`" in name or any(ord(c) < 32 for c in name):
        raise Refused("--park-dir must be one plain, non-hidden folder name")


def upgrade_v1(store, row, ledger):
    """Keep the v1 row until every file and every original directory is settled."""
    rel = row["path"].rstrip("/")
    origin = store.v1_location(row)
    provenance = dict(format=1, by=row.get("by", "1.x"), form=row["form"])
    if row["form"].startswith("zst"):
        big = store.root / ".big" / rel
        raw = store.root / "files" / rel
        source = origin if origin.exists() else big
        if not source.exists() and not raw.is_file():
            raise Refused(f"v1 pack is missing: {origin}")
        meta = read_pack(source) if source.exists() else None
        if meta and FILE_LIMIT > 0 and meta["original_size"] > FILE_LIMIT:
            if source != big:
                if exists(big):
                    raise Refused(f"not overwriting {big}")
                big.parent.mkdir(parents=True, exist_ok=True)
                publish(source, big)
                fault("upgrade-after-move")
            record = record_for(rel, big / "MANIFEST.json", meta["original_sha256"], form=f"zst×{len(meta['parts'])}", size=meta["original_size"], mode=0o644, upgraded_from=provenance)
        else:
            if not raw.exists():
                ensure_free(store.root, meta["original_size"])
                raw.parent.mkdir(parents=True, exist_ok=True)
                tmp = raw.with_name(raw.name + f".partial-{os.getpid()}")
                try:
                    with open(tmp, "xb") as out:
                        unpack(source, out)
                        out.flush()
                        os.fsync(out.fileno())
                    os.chmod(tmp, 0o444)
                    publish(tmp, raw)
                finally:
                    tmp.unlink(missing_ok=True)
                fault("upgrade-after-move")
            if meta and (raw.stat().st_size != meta["original_size"] or hash_file(raw) != meta["original_sha256"]):
                raise Refused(f"unpacked v1 pack does not match: {raw}")
            record = record_for(rel, raw, mode=0o644, upgraded_from=provenance)
            os.chmod(raw, 0o444)
            if source.exists():
                remove_output(source)
        if rel not in store.records:
            store.append("add", record)
        if store.repo:
            ledger.mkdir(store.repo / Path(rel).parent)
    else:
        target = store.root / "files" / rel
        if row["form"] == "file":
            pairs = [(origin, target, rel)]
            directories = []
        elif row["form"] == "dir":
            source_dirs = all_folders(origin) if origin.exists() else []
            moved_dirs = all_folders(target) if target.exists() else []
            directories = {rel}
            directories.update(nfc((Path(rel) / p.relative_to(origin)).as_posix()) for p in source_dirs)
            directories.update(nfc((Path(rel) / p.relative_to(target)).as_posix()) for p in moved_dirs)
            pairs = []
            for base, destination in ((origin, target), (target, target)):
                for item in walk_files(base):
                    if item.is_symlink():
                        raise Refused(f"symlink in v1 entry: {item}")
                    suffix = item.relative_to(base)
                    pairs.append((item, destination / suffix, nfc((Path(rel) / suffix).as_posix())))
        else:
            raise Refused(f"unknown v1 form: {row['form']}")
        for source, destination, path in pairs:
            if path in store.records:
                continue
            if source != destination and source.exists():
                if destination.exists():
                    raise Refused(f"not overwriting {destination}")
                guard_archive_path(destination)
                destination.parent.mkdir(parents=True, exist_ok=True)
                publish(source, destination)
                fault("upgrade-after-move")
            if not destination.is_file() or destination.is_symlink():
                raise Refused(f"v1 copy missing: {destination}")
            record = record_for(path, destination, upgraded_from=provenance)
            os.chmod(destination, 0o444)
            store.append("add", record)
        if store.repo:
            for folder in sorted(directories, key=lambda x: len(Path(x).parts)):
                ledger.mkdir(store.repo / folder)
        if origin.is_dir():
            remove_empty_tree(origin)
    store.v1 = [r for r in store.v1 if r["path"] != row["path"]]
    prune(origin.parent, store.root)
    store.save()
    return rel


def upgrade_plan(store, scopes, args):
    steps, skips = [], []
    for row in store.v1:
        if not under(row["path"], scopes):
            if any(s.startswith(row["path"].rstrip("/") + "/") for s in scopes):
                steps.append(dict(kind="fmt1to2", path=row["path"], detail="name the v1 folder itself", refuse=True, row=row))
            continue
        download, free = 0, 0
        source = store.v1_location(row)
        error = None
        try:
            if row["form"].startswith("zst"):
                # A plan reads only metadata and stat; hashing is part of the run.
                meta = read_pack(source if source.exists() else store.root / ".big" / row["path"], check=False)
                raw = not FILE_LIMIT or meta["original_size"] <= FILE_LIMIT
                detail = "unpack raw into files/" if raw else "keep compressed parts under .big/"
                free = meta["original_size"] + MARGIN if raw else 0
            else:
                detail = f"format 1 {row['form']} → format 2 files under files/"
            download = sum(p.stat().st_size for p in walk_files(source) if dataless(p))
        except (Refused, OSError) as exc:
            error, detail = str(exc), str(exc)
        steps.append(dict(kind="fmt1to2", path=row["path"], detail=detail, download=download, free=free, refuse=bool(error), row=row))
    for record in store.records.values():
        if record.get("format", 2) != 2 and under(record["path"], scopes):
            skips.append(record["path"])
    if not scopes and store.repo:
        name = args.park_dir or store.parked or "_archive"
        refused = None
        try:
            validate_park_name(name)
            if store.parked and name != store.parked:
                raise Refused(f"this repo keeps parked folders in {store.parked}/ already; renaming the park folder is not supported")
            if not store.parked:
                taken = store.taken(name)
                if taken:
                    raise Refused(taken)
        except Refused as exc:
            refused = str(exc)
        if not store.parked or refused:
            remembered = store.parked
            store.parked = name
            p = tidy_plan(store, min_age=0, check_open=False)
            store.parked = remembered
            top = [r for r in p.into if Path(r).parent.as_posix() not in p.into]
            detail = refused or f"move {len(top)} folder tree(s) into {name}/; records and iCloud unchanged"
            if store.v1 and not refused:
                detail += "; the folders the format steps put back move there at the end"
            steps.append(dict(kind="park", path=name + "/", detail=detail, refuse=bool(refused), name=name))
    if not scopes and store.scheme == "flat":
        target = store.nested_root() if store.repo else nested_for_path(expand(store.remote["repo"]))
        refused = False
        if target.exists() and target != store.root:
            header = read_manifest(target / ".manifest.jsonl")[0]
            refused = header.get("id") != store.id or any(target.iterdir())
        steps.append(dict(kind="relocate", path=str(target), detail="target already holds another repo's archive" if refused else f"{store.root} → {target}", refuse=refused, target=target))
    if TARGET and TARGET.kind == "google-drive":
        for step in steps:
            if step["kind"] != "park":
                step["refuse"] = True
                step["detail"] = "Google Drive remote upload cannot be confirmed; automatic archive-data migration/relocation is unsupported"
    return steps, skips


def nested_for_path(repo):
    try:
        rel = repo.relative_to(HOME)
    except ValueError:
        rel = Path("_abs") / str(repo).lstrip("/")
    return BASE / "repos" / rel


def upgrade_archive(repo, remote, args):
    initial = Store(repo, remote)
    with lock(initial.id):
        store = Store(repo, remote)
        scopes = [store.rel(p, "upgrade")[0] for p in args.paths] if repo else []
        steps, skips = upgrade_plan(store, scopes, args)
        print(f"archive {store.id}  repo {store.repo or store.remote['repo']}" + ("" if repo else " (not on this Mac: via the iCloud copy)"))
        print(f"  root {store.root}  ({store.scheme})   already format 2: {len(store.records)} file(s)")
        for step in steps:
            prefix = "  REFUSE  " if step["refuse"] else "  step    "
            cost = f"  [downloads {size_text(step.get('download', 0))} first; needs {size_text(step.get('free', 0))} free on this Mac until uploaded and evicted]"
            print(f"{prefix}{step['kind']} {step['path']}: {step['detail']}{cost}")
        for rel in skips:
            print(f"  SKIP    {rel}: format unknown to skill {SKILL_VERSION}")
        pending = any(s["kind"] != "park" for s in steps) and pending_upload(store.root)
        if pending:
            print(f"  WAIT    iCloud uploads pending. Renaming inside iCloud before the upload finishes leaves ghost folders, so upgrade waits up to --wait {args.wait:g} min for it.")
        refused = sum(s["refuse"] for s in steps)
        if args.plan:
            print(f"plan only: nothing changed. Steps refused: {refused}. Ask the user, then rerun without --plan.")
            return 1 if refused else 0
        if pending and not wait_uploaded(store.root, args.wait):
            raise Refused("iCloud uploads still pending; whole upgrade refused, nothing changed")
        done = deferred = 0
        ledger = Ledger()
        if store.dirty or any(not x["refuse"] for x in steps):
            store.settle()
        upgraded_paths = []
        for step in steps:
            if step["refuse"]:
                print("REFUSED: " + step["detail"], file=sys.stderr)
                continue
            try:
                if step["kind"] == "fmt1to2":
                    upgraded_paths.append(upgrade_v1(store, step["row"], ledger))
                elif step["kind"] == "park":
                    store.parked = step["name"]
                    store.save()
                    fault("park-after-setting")
                else:
                    if done and not wait_uploaded(store.root, args.wait):
                        print("DEFERRED relocate: iCloud upload is still pending; rerun upgrade after upload")
                        deferred += 1
                        continue
                    old, target = store.root, step["target"]
                    store.write_registry(state="upgrading", target=target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise Refused(f"not overwriting relocate target {target}")
                    publish(old, target)
                    fault("relocate-after-rename")
                    store.root = target
                    store.registry.setdefault("old_roots", []).append(root_name(old))
                    store.save()
                    fault("relocate-after-index")
                done += 1
            except (Refused, OSError) as error:
                refused += 1
                print(f"REFUSED: {step['kind']} {step['path']}: {error}", file=sys.stderr)
        plan = None
        if repo and store.parked:
            plan = tidy_plan(store, [] if any(s["kind"] == "park" and not s["refuse"] for s in steps) else upgraded_paths, min_age=MIN_AGE, ledger=ledger)
            plan.apply()
        print("SUMMARY")
        print(f"  upgraded: {done} step(s)   refused: {refused}   deferred: {deferred}")
        if plan:
            plan.report()
            for problem in plan.problems():
                print("    ✗ " + problem)
                refused += 1
        print("  run verify in each upgraded repo; then upload-status and evict")
        return 1 if refused else 2 if deferred else 0


def upgrade_command(repo, args):
    if not args.all:
        return upgrade_archive(repo, None, args)
    if args.paths:
        raise Refused("upgrade --all takes no paths")
    result = 0
    for entry in registry_entries():
        local = expand(entry["repo"])
        on_mac = any((local / name).is_file() for name in ("ARCHIVE.md", "ARCHIVE.manifest.jsonl", "ICLOUD.md", "ICLOUD.manifest.jsonl"))
        if on_mac:
            try:
                scoped = argparse.Namespace(**vars(args))
                scoped.target = TARGET.name if TARGET and TARGET.managed else getattr(args, "target", None)
                configure_session(scoped, local)
                on_mac = Store(local).id == entry["id"]
            except Refused:
                on_mac = False
        if not on_mac and not (registry_root(entry["root"]) / ".manifest.jsonl").exists():
            print(f"{entry['repo']}: repo not on this Mac and no iCloud manifest; run `registry --scan` where the repo is")
            continue
        try:
            rc = upgrade_archive(local if on_mac else None, None if on_mac else entry, args)
            result = 1 if rc == 1 or result == 1 else max(result, rc)
        except (Refused, OSError) as error:
            print(f"REFUSED: {entry['repo']}: {error}", file=sys.stderr)
            result = 1
    return result


def registry_command(args):
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "Library"}
    if args.scan is not None:
        for directory in args.scan or [str(HOME / "develop")]:
            directory = expand(directory)
            for parent, dirs, files in os.walk(directory, followlinks=False):
                path = Path(parent)
                depth = len(path.relative_to(directory).parts)
                dirs[:] = sorted(d for d in dirs if d not in skip and not (path / d).is_symlink()) if depth < 5 else []
                if any(name in files for name in ("ARCHIVE.md", "ARCHIVE.manifest.jsonl", "ICLOUD.md", "ICLOUD.manifest.jsonl")):
                    dirs[:] = []
                    try:
                        scoped = argparse.Namespace(**vars(args))
                        scoped.target = TARGET.name if TARGET and TARGET.managed else getattr(args, "target", None)
                        configure_session(scoped, path)
                        store = Store(path)
                        with lock(store.id):
                            store = Store(path)
                            if store.records or store.v1:
                                store.save()
                                print(f"registered {path} → {store.root}")
                    except (Refused, OSError) as error:
                        print(f"REFUSED: {path}: {error}", file=sys.stderr)
    entries = registry_entries()
    for entry in sorted(entries, key=lambda x: x["repo"]):
        formats = ", ".join(f"format {k}: {v}" for k, v in sorted(entry.get("formats", {}).items()))
        print(f"{entry['repo']}\t{entry['root']}\t{entry.get('scheme', '')}\t{formats}\tby {', '.join(sorted(entry.get('written_by', {})))}\t{entry.get('state', 'ok')}")
    named = {str(x).split("/")[0] for e in entries for x in [e["root"], *e.get("old_roots", [])]}
    if BASE.is_dir():
        for path in sorted(BASE.iterdir()):
            if path.is_dir() and path.name not in named | {"registry", "repos", ".publications"} and not litter(path.name):
                print(f"[unregistered] {path.name}: an archive no registry file names; run `registry --scan <folder holding its repo>`")
    return 0


def history_index():
    path = history_root() / "INDEX.json"
    try:
        value = json.loads(path.read_text())
        return value
    except FileNotFoundError:
        return {}


def version_key(text):
    return (1, 99, 99) if text == "1.x" else tuple(int(p) for p in text.split("."))


def via_history(store, rel, command, args=None):
    record = store.records.get(rel)
    row = next((r for r in store.v1 if r["path"].rstrip("/") == rel.rstrip("/") or rel.startswith(r["path"])), None)
    if record is None and row is None:
        raise Refused(f"not archived: {rel}")
    fmt, writer = (record.get("format", 2), record.get("by", "2.0.0")) if record else (1, "1.x")
    versions = history_index()
    choices = [v for v, meta in versions.items() if fmt in meta.get("writes", []) and version_key(v) <= version_key(writer)]
    version = writer if writer in versions else max(choices, key=version_key) if choices else None
    if not version:
        raise Refused(f"no frozen history release can read format {fmt} by {writer}; original history/ was unavailable for this rebuild")
    folder = history_root() / version
    sums = folder / "SHA256SUMS"
    if not sums.is_file():
        raise Refused(f"{sums} is missing; not running it")
    names = set()
    for line in sums.read_text().splitlines():
        sha, filename = line.split(None, 1)
        filename = filename.strip().lstrip("*")
        if Path(filename).name != filename or filename in (".", ".."):
            raise Refused("unsafe history checksum path; not running it")
        path = folder / filename
        if path.is_symlink() or not path.is_file() or hash_file(path) != sha:
            raise Refused(f"history SHA-256 mismatch: {path}; not running it")
        names.add(filename)
    engine = "archive.py" if "archive.py" in names else "icloud_archive.py"
    if not {engine, "SKILL.md"} <= names:
        raise Refused("history SHA256SUMS does not cover the script and SKILL.md; not running it")
    script = folder / engine
    print(f"via history: skill {version} wrote this (format {fmt}); running {script}", file=sys.stderr)
    argv = [sys.executable, str(script), "--repo", str(store.repo), command, str(store.repo / rel)]
    if args and args.head is not None:
        argv += ["--head", str(args.head)]
    if args and args.full:
        argv.append("--full")
    child_env = dict(os.environ)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"  # frozen runtimes must not write caches into a release
    child_env["ICLOUD_ARCHIVE_ROOT"] = str(BASE)
    child_env["ICLOUD_ARCHIVE_LOCK_DIR"] = str(LOCK_DIR)
    result = subprocess.run(argv, env=child_env)
    if result.returncode == 0 and command == "restore" and store.parked:
        with lock(store.id):
            fresh = Store(store.repo)
            fresh.parked = store.parked
            fresh.save()
            plan = tidy_plan(fresh, [rel])
            plan.apply()
            plan.report()
    return result.returncode


def remove_empty_tree(path):
    """Only directories and Finder's own metadata may be removed by this helper."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        return False
    for child in list(path.iterdir()):
        if child.is_dir() and not child.is_symlink():
            remove_empty_tree(child)
        elif (child.name == ".DS_Store" or storage.apple_double(child)) and child.is_file() and not child.is_symlink():
            child.unlink()
    try:
        path.rmdir()
        return True
    except OSError:
        return False


def foreign_items(folder):
    result = []
    for parent, dirs, files in os.walk(folder, followlinks=False):
        for name in list(dirs):
            path = Path(parent) / name
            if path.is_symlink():
                result.append(path)
                dirs.remove(name)
        result += [Path(parent) / name for name in files if name != ".DS_Store" and not storage.apple_double(Path(parent) / name)]
    return sorted(result)


def evict_batch(paths):
    if paths and (not TARGET or TARGET.kind == "icloud") and inside(paths[0], DRIVE):
        cloud_states(paths, "evict")


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"path", "archive_path"} <= set(reader.fieldnames or []):
            raise Refused("CSV manifest needs path and archive_path columns")
        return list(reader.fieldnames), list(reader)


def import_origin(folder, csv_path, old_path, row):
    return dict(folder=compact_path(folder), kind="mirror", manifest=compact_path(csv_path) if csv_path else None, path=compact_path(old_path), row=row)


def resume_import(store, journal, ledger):
    if not journal.exists():
        return []
    lines = journal.read_text().splitlines()
    resumed = []
    for i, line in enumerate(lines):
        try:
            item = json.loads(line)
        except ValueError:
            if i == len(lines) - 1:
                atomic_write(journal, "\n".join(lines[:-1]) + ("\n" if len(lines) > 1 else ""))
                break
            raise Refused("malformed import journal")
        rel = stored_rel(item["rel"])
        path = store.root / "files" / rel
        if rel in store.records or not path.is_file():
            continue
        if path.is_symlink():
            raise Refused(f"symlink in import journal destination: {path}")
        sha, md5 = hash_file(path, md5=True)
        if item.get("md5") and item["md5"] != md5:
            raise Refused(f"md5 mismatch resuming import: {rel}; left alone")
        record = item.get("record") or record_for(rel, path, sha, imported_from=item["origin"])
        if record.get("sha256") != sha or record.get("size") != path.stat().st_size:
            raise Refused("import journal SHA-256 or size mismatch; source retained")
        store.append("add", record)
        os.chmod(path, 0o444)
        ledger.mkdir(store.repo / Path(rel).parent)
        resumed.append(rel)
        store.save()
        original = expand(item["origin"].get("path", ""))
        folder = expand(item["origin"].get("folder", ""))
        if original.exists() and original != path and inside(original, folder):
            if original.is_symlink() or hash_file(original) != sha:
                raise Refused("foreign source changed after interruption; retained: " + str(original))
            guard_archive_path(path)
            original.unlink()
    return resumed


def mirror_plan(store, folder, csv_path):
    fields, rows = load_csv(csv_path) if csv_path else ([], [])
    mapped, refused, notes, seen = [], [], [], {}
    for path in foreign_items(folder):
        item = dict(source=path, rel=None, row=None, csv_row=None)
        matching = None
        if csv_path:
            for number, row in enumerate(rows, 1):
                archive = row.get("archive_path", "")
                if not archive.startswith("/"):
                    continue
                original = Path(archive)
                if path == original:
                    matching = (number, row, "")
                    break
                if inside(path, original) and (archive.endswith("/") or original.is_dir() or row.get("path", "").endswith("/")):
                    matching = (number, row, path.relative_to(original).as_posix())
                    break
            if matching is None:
                refused.append((str(path), "in the folder but in no manifest row"))
                continue
            number, row, suffix = matching
            if row.get("status", "").lower().startswith("deleted"):
                notes.append(f"{path}: skipped: deleted before import")
                continue
            rel = row["path"].rstrip("/") + ("/" + suffix if suffix else "")
            item.update(row=number, csv_row=row)
        else:
            rel = path.relative_to(folder).as_posix()
        try:
            rel = stored_rel(rel)
            if path.name.startswith(".") and path.name.endswith(".icloud"):
                raise Refused("evicted iCloud placeholder; download it first")
            if path.is_symlink():
                raise Refused("symlink; never followed")
            if not path.is_file():
                raise Refused("not a regular file")
            if exists(store.repo / rel):
                raise Refused("exists locally; not overwriting")
            if rel in store.records or any(rel == x["path"].rstrip("/") or rel.startswith(x["path"].rstrip("/") + "/") for x in store.v1):
                raise Refused("already archived")
            if exists(store.root / "files" / rel) or exists(store.root / ".big" / rel):
                raise Refused("archive already has the path with no record of it; not overwriting")
            if rel.casefold() in seen or any(x.casefold() == rel.casefold() for x in store.records):
                raise Refused("case-only clash or duplicate destination")
            seen[rel.casefold()] = rel
            item["rel"] = rel
            mapped.append(item)
        except Refused as error:
            refused.append((rel, str(error)))
    if csv_path:
        for row in rows:
            if row.get("archive_path") and not Path(row["archive_path"]).exists() and not row.get("imported_to"):
                notes.append(f"CSV row points at nothing: {row['archive_path']}")
    return mapped, refused, notes, fields, rows


def write_import_csv(store, path, fields, rows):
    if "imported_to" not in fields:
        fields.append("imported_to")
    for row in rows:
        rel = row["path"].rstrip("/")
        if rel in store.records:
            value = root_name(store.root) + "/files/" + rel
        elif any(p.startswith(rel + "/") for p in store.records):
            value = root_name(store.root) + "/files/" + rel + "/ (folder)"
        else:
            value = "skipped: deleted before import" if row.get("status", "").lower().startswith("deleted") else "NOT imported: see the import output"
            if row.get("imported_to"):
                value = row["imported_to"]
        row["imported_to"] = value
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
        storage.fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def mirror_import(store, folder, args, ledger):
    csv_path = expand(args.manifest) if args.manifest else None
    journal = store.root / ".import-journal.jsonl"
    imported = [] if args.plan else resume_import(store, journal, ledger)
    mapped, refused, notes, fields, rows = mirror_plan(store, folder, csv_path)
    total = sum(x["source"].stat().st_size for x in mapped)
    download = sum(x["source"].stat().st_size for x in mapped if not x["source"].is_symlink() and dataless(x["source"]))
    print(f"import (mirror) {folder} → {store.root}/files/")
    print(f"  files: {len(mapped)}, {size_text(total)}; downloads {size_text(download)} to hash")
    for note in notes:
        print("  note: " + note)
    for path, why in refused[:30]:
        print(f"  REFUSE  {path}: {why}")
    pending = pending_upload(folder)
    if pending:
        print("  WAIT    foreign archive still has uploads pending")
    if args.plan:
        print(f"plan only: nothing changed. Refused: {len(refused)}. Ask the user, then rerun without --plan.")
        return [], len(refused)
    for path, why in refused:
        print(f"REFUSED: {path}: {why}", file=sys.stderr)
    if pending and not wait_uploaded(folder, args.wait):
        raise Refused("foreign archive uploads still pending; import changed nothing")
    accepted = {checked_rel(store.repo, x) for x in args.accept_mismatch}
    batch, batch_bytes = [], 0
    for item in mapped:
        rel, source, row = item["rel"], item["source"], item["csv_row"]
        try:
            if source.is_symlink() or not source.is_file():
                raise Refused("no longer a regular file")
            if row and row.get("bytes") and not row["path"].endswith("/"):
                if source.stat().st_size != int(row["bytes"]):
                    raise Refused("size differs from CSV manifest")
            before = source.stat()
            sha, md5 = hash_file(source, md5=True)
            origin = import_origin(folder, csv_path, source, item["row"])
            if row and row.get("md5") and row["md5"].lower() != md5:
                if rel not in accepted:
                    raise Refused(f"md5 mismatch: manifest {row['md5']}, actual {md5}; file stays where it is")
                origin["md5_mismatch"] = dict(manifest_md5=row["md5"], actual_md5=md5, accepted_by_user=today())
            record = record_for(rel, source, sha, imported_from=origin)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise Refused("source changed while hashing; left alone")
            destination = store.root / "files" / rel
            if exists(destination) or exists(store.repo / rel):
                raise Refused("destination appeared meanwhile; not overwriting")
            journal.parent.mkdir(parents=True, exist_ok=True)
            with open(journal, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(kind="mirror", rel=rel, md5=md5, origin=origin, record=record), ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            guard_archive_path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            publish(source, destination)
            fault("import-after-move")
            store.append("add", record)
            os.chmod(destination, 0o444)
            ledger.mkdir(store.repo / Path(rel).parent)
            imported.append(rel)
            batch.append(destination)
            batch_bytes += record["size"]
            print(f"imported {rel}")
            if batch_bytes >= IMPORT_BATCH:
                store.save()
                evict_batch(batch)
                batch, batch_bytes = [], 0
        except (Refused, OSError, ValueError) as error:
            refused.append((rel, str(error)))
            print(f"REFUSED: {rel}: {error}", file=sys.stderr)
    if imported:
        store.save()
    evict_batch(batch)
    journal.unlink(missing_ok=True)
    if csv_path:
        write_import_csv(store, csv_path, fields, rows)
    remove_empty_tree(folder)
    with contextlib.suppress(OSError):
        folder.parent.rmdir()
    return imported, len(refused)


def split_metadata(folder):
    meta = {}
    try:
        for line in (folder / "MANIFEST.txt").read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                meta[key.strip()] = value.strip()
        for key in ("original_path", "original_bytes", "original_sha256", "part_prefix"):
            if key not in meta:
                raise ValueError(f"missing {key}")
        meta["original_path"] = stored_rel(meta["original_path"])
        meta["original_bytes"] = int(meta["original_bytes"])
        parts = sorted(p for p in folder.iterdir() if p.name.startswith(meta["part_prefix"]))
        if not parts or any(p.is_symlink() or not p.is_file() for p in parts):
            raise ValueError("parts missing or not regular files")
        if "parts" in meta and len(parts) != int(meta["parts"]):
            raise ValueError("part count disagrees")
        sums = {}
        for line in (folder / "SHA256SUMS").read_text().splitlines():
            sha, name = line.split(None, 1)
            sums[name.strip().lstrip("*")] = sha
        values = []
        for i, path in enumerate(parts):
            if path.name not in sums:
                raise ValueError(f"SHA256SUMS misses {path.name}")
            values.append(dict(src=path.name, dest=f"part-{i:03d}.zst", size=path.stat().st_size, sha256=sums[path.name]))
        extras = [p.name for p in folder.iterdir() if p not in parts and p.name != ".DS_Store"]
        if any((folder / p).is_symlink() or (folder / p).is_dir() for p in extras):
            raise ValueError("split archive has a symlink or unexpected folder")
        return meta, values, extras
    except (OSError, ValueError, KeyError) as error:
        raise Refused(f"invalid split import: {error}")


def split_import(store, folder, args, ledger):
    plans = [p for p in (store.root / ".big").glob("**/IMPORT-PLAN.json") if json.loads(p.read_text()).get("folder") == compact_path(folder)]
    if plans:
        planfile = plans[0]
        plan = json.loads(planfile.read_text())
        meta, parts, extras = plan["meta"], plan["parts"], plan["extras"]
        rel = stored_rel(meta["original_path"])
        destination = planfile.parent
    else:
        meta, parts, extras = split_metadata(folder)
        rel = meta["original_path"]
        destination = store.root / ".big" / rel
        planfile = destination / "IMPORT-PLAN.json"
        plan = dict(folder=compact_path(folder), meta=meta, parts=parts, extras=extras)
        if exists(destination):
            raise Refused(f".big/{rel} already exists without a plan file; not overwriting")
    if rel in store.records or exists(store.repo / rel):
        raise Refused(f"already archived or exists locally: {rel}")
    if any(p.casefold() == rel.casefold() for p in store.records):
        raise Refused(f"case-only clash: {rel}")
    print(f"import (split) {folder} → {destination}")
    print(f"  {rel}: {size_text(meta['original_bytes'])}, {len(parts)} parts; check every part and the whole stream before and after the move; keep imported_from")
    if args.plan:
        print("plan only: nothing changed. Ask the user, then rerun without --plan.")
        return [], 0
    if not wait_uploaded(folder, args.wait):
        raise Refused("foreign split archive uploads still pending; nothing moved")
    paths = []
    for part in parts:
        source = folder / part["src"]
        if not source.exists():
            source = destination / part["dest"]
        if source.is_symlink() or not source.is_file() or source.stat().st_size != part["size"] or hash_file(source) != part["sha256"]:
            raise Refused(f"part SHA-256 mismatch: {source}; nothing further moved")
        paths.append(source)
    decompress_parts(paths, expected=(meta["original_bytes"], meta["original_sha256"]))
    atomic_write(planfile, json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    for part in parts:
        source, dest = folder / part["src"], destination / part["dest"]
        if source.exists():
            if exists(dest):
                raise Refused(f"not overwriting split part: {dest}")
            publish(source, dest)
            fault("import-after-move")
    for name in extras:
        source, dest = folder / name, destination / "imported" / name
        if source.exists():
            if dest.exists():
                raise Refused(f"not overwriting kept import file: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            publish(source, dest)
    flags = ["-" + str(meta["zstd_level"])] if meta.get("zstd_level") else []
    if flags and meta.get("zstd_long"):
        flags.append("--long=" + str(meta["zstd_long"]))
    manifest = dict(format=1, original_name=Path(rel).name, original_size=meta["original_bytes"], original_sha256=meta["original_sha256"], zstd_args=flags, part_size=max(p["size"] for p in parts), parts=[dict(name=p["dest"], size=p["size"], sha256=p["sha256"]) for p in parts], imported_from=dict(folder=compact_path(folder), kind="split"))
    atomic_write(destination / "MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    atomic_write(destination / "SHA256SUMS", "".join(f"{p['sha256']}  {p['dest']}\n" for p in parts))
    try:
        unpack(destination)
    except Refused as error:
        raise Refused(f"{error}; parts moved but unrecorded; run verify")
    mtime = time.time_ns()
    with contextlib.suppress(ValueError, KeyError):
        mtime = int(dt.datetime.strptime(meta["original_mtime"], "%Y-%m-%dT%H:%M:%S%z").timestamp() * 1e9)
    record = dict(path=rel, size=meta["original_bytes"], sha256=meta["original_sha256"], mtime_ns=mtime, mode=0o644, form=f"zst×{len(parts)}", date=today(), format=2, by=SKILL_VERSION, imported_from=dict(folder=compact_path(folder), kind="split", manifest="MANIFEST.txt"))
    store.append("add", record)
    planfile.unlink()
    store.save()
    ledger.mkdir(store.repo / Path(rel).parent)
    remove_empty_tree(folder)
    return [rel], 0


def import_command(repo, args):
    folder = expand(args.folder)
    if folder.is_symlink() or not folder.is_dir():
        raise Refused(f"import source is not a plain folder: {folder}")
    if inside(folder.resolve(), BASE.resolve()):
        raise Refused("folder is inside claude-archive; use upgrade, not import")
    initial = Store(repo)
    with lock(initial.id):
        store = Store(repo)
        store.check_v1_overlap()
        if not args.plan:
            store.settle()
        ledger = Ledger()
        if args.kind == "mirror":
            imported, refused = mirror_import(store, folder, args, ledger)
        else:
            imported, refused = split_import(store, folder, args, ledger)
        plan = None
        if not args.plan:
            origin = dict(**{"from": compact_path(folder)}, kind=args.kind, manifest=compact_path(expand(args.manifest)) if args.manifest else None, date=today())
            if args.kind == "split" and imported:
                origin["maps_to"] = imported[0]
            imports = store.registry.setdefault("imports", [])
            if not any(x["from"] == origin["from"] for x in imports):
                imports.append(origin)
            store.save()
            if store.parked and imported:
                plan = tidy_plan(store, [str(Path(rel).parent) for rel in imported], ledger=ledger)
                plan.apply()
        print("SUMMARY")
        print(f"  imported: {len(imported)} file(s)   refused: {refused}")
        if plan:
            plan.report()
        return 1 if refused or (plan and plan.problems()) else 0


def history_root():
    return HERE / ".history" if (HERE / ".history").exists() else HERE / "history"


def configure_session(args, repo=None, optional=False):
    global TARGET, BASE, INDEX, MANIFEST, FILE_LIMIT, DEFAULT_PREFIX, LEGACY_PREFIX
    if LEGACY_PREFIX is None:
        LEGACY_PREFIX = list(DEFAULT_PREFIX)
    old_root = None
    recorded = None
    generic = False
    if repo:
        generic = any((repo / name).is_file() for name in ("ARCHIVE.md", "ARCHIVE.manifest.jsonl"))
        legacy = any((repo / name).is_file() for name in ("ICLOUD.md", "ICLOUD.manifest.jsonl"))
        if generic and legacy:
            raise Refused("both ARCHIVE and ICLOUD indexes exist; refusing an ambiguous project")
        INDEX, MANIFEST = ("ARCHIVE.md", "ARCHIVE.manifest.jsonl") if generic else ("ICLOUD.md", "ICLOUD.manifest.jsonl")
        manifest = repo / MANIFEST
        if manifest.is_file():
            try:
                header = json.loads(manifest.read_text().splitlines()[0])
            except (ValueError, IndexError):
                raise Refused("malformed archive manifest header")
            recorded = header.get("archive_target")
            old_root = expand(header["root"]) if header.get("root") and not (recorded and recorded.get("kind") == "google-drive-api") else None
        elif (repo / INDEX).is_file():
            index_text = (repo / INDEX).read_text()
            cloud_root = re.search(r'^Root: `gdrive://([^/]+)/', index_text, re.M)
            if cloud_root:
                matches = [v for v in storage.load_config()['targets'].values() if v.get('kind') == 'google-drive-api' and v.get('drive_folder_id') == cloud_root[1]]
                if len(matches) != 1:
                    raise Refused('Drive index has no unique registered target; ask before reconciling it')
                recorded = matches[0]
            else:
                old_root = read_index(repo / INDEX)[0]
    explicit = os.environ.get("ICLOUD_ARCHIVE_ROOT")
    if old_root and not recorded and not explicit:
        candidates = storage.load_config()["targets"].values()
        match = next((x for x in candidates if inside(old_root, Path(x["root"]))), None)
        if match:
            recorded = match
        elif inside(old_root, DRIVE / "claude-archive"):
            explicit = str(DRIVE / "claude-archive")
        else:
            raise Refused("older archive root has no registered target; register its existing base before accessing it")
    try:
        TARGET = storage.select_target(args.target, recorded, explicit)
    except storage.TargetError:
        if optional and not args.target and not explicit and not recorded:
            return
        raise
    BASE = TARGET.root
    if TARGET.kind == 'google-drive-api':
        if old_root:
            raise Refused('filesystem archives cannot be redirected to Drive API; an explicit planned migration is required')
        INDEX, MANIFEST = 'ARCHIVE.md', 'ARCHIVE.manifest.jsonl'
        if repo: TARGET.check_repo(repo)
        return
    if old_root and TARGET.managed and not inside(old_root, BASE):
        raise Refused("existing archive belongs to a different target; changing the default does not migrate it")
    if repo and not old_root:
        legacy_env = bool(os.environ.get("ICLOUD_ARCHIVE_ROOT")) and not os.environ.get("ARCHIVE_GENERAL_ROOT")
        INDEX, MANIFEST = ("ICLOUD.md", "ICLOUD.manifest.jsonl") if legacy_env and not TARGET.managed else ("ARCHIVE.md", "ARCHIVE.manifest.jsonl")
    DEFAULT_PREFIX = list(LEGACY_PREFIX)
    if INDEX == "ARCHIVE.md":
        DEFAULT_PREFIX = [x.replace("iCloud Drive", "the selected storage target").replace("iCloud archive", "Archive General").replace("archive-icloud", "archive-general") for x in DEFAULT_PREFIX]
    if not os.environ.get("ICLOUD_ARCHIVE_FILE_LIMIT"):
        FILE_LIMIT = TARGET.value.get("file_limit", 49_000_000_000 if TARGET.kind == "icloud" else 0)
    if repo:
        TARGET.check_repo(repo)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Archive General: verified storage targets; target setup, sync, restore, read, list, status, verify, tidy, upload-status, evict, registry, upgrade, import, version")
    parser.add_argument("--target", help="registered storage target; existing projects remain bound to their recorded target")
    parser.add_argument("--repo", help="project root (git toplevel when inside a git repo)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sync", "archive"):
        p = sub.add_parser(name)
        p.add_argument("paths", nargs="+")
        p.add_argument("--exclude", action="append", default=[])
        p.add_argument("--min-age", type=float, default=MIN_AGE)
        p.add_argument("--pack", action="store_true")
        p.add_argument("--fast", action="store_true")
        p.add_argument("--allow-protected", action="store_true")
        if name == "sync":
            p.add_argument("--update", action="store_true")
        else:
            p.set_defaults(update=False)
    p = sub.add_parser("restore")
    p.add_argument("paths", nargs="+")
    p.add_argument("--via-history", action="store_true")
    p = sub.add_parser("read")
    p.add_argument("path")
    p.add_argument("--head", type=int)
    p.add_argument("--full", action="store_true")
    p.add_argument("--via-history", action="store_true")
    for name in ("list", "status"):
        p = sub.add_parser(name)
        p.add_argument("paths", nargs="*")
        if name == "status":
            p.add_argument("--deep", action="store_true")
    p = sub.add_parser("verify")
    p.add_argument("--fix", action="store_true")
    p = sub.add_parser("tidy")
    p.add_argument("paths", nargs="*")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--min-age", type=float, default=MIN_AGE)
    p.add_argument("--exclude", action="append", default=[])
    sub.add_parser("upload-status")
    sub.add_parser("evict")
    p = sub.add_parser("registry")
    p.add_argument("--scan", nargs="*")
    p = sub.add_parser("upgrade")
    p.add_argument("paths", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--wait", type=float, default=10)
    p.add_argument("--park-dir")
    p = sub.add_parser("import")
    p.add_argument("folder")
    p.add_argument("--kind", choices=["mirror", "split"], required=True)
    p.add_argument("--manifest")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--wait", type=float, default=10)
    p.add_argument("--accept-mismatch", action="append", default=[])
    p = sub.add_parser("target", help="register, select or inspect a storage target")
    targets = p.add_subparsers(dest="target_action", required=True)
    q = targets.add_parser("add")
    q.add_argument("name")
    q.add_argument("--root")
    q.add_argument("--kind", choices=storage.KINDS, default="local")
    q.add_argument("--drive-folder-id")
    q.add_argument("--credential-remote", help="existing rclone Drive authorization profile; tokens stay private")
    q.add_argument("--credential-config")
    q.add_argument("--oauth-file", help="private authorized-user OAuth credential file")
    q.add_argument("--default", action="store_true")
    q.add_argument("--removable", action="store_true")
    q.add_argument("--adopt-existing", action="store_true", help="bind a recognizable old archive base without moving its data")
    q.add_argument("--plan", action="store_true")
    targets.add_parser("list")
    q = targets.add_parser("use")
    q.add_argument("name")
    q = targets.add_parser("doctor")
    q.add_argument("name", nargs="?")
    sub.add_parser("version")
    return parser.parse_args(argv)


def dispatch(args):
    if "drive_api" in sys.modules:
        sys.modules["drive_api"].clear_validation_cache()
    command = args.command
    if command == "target":
        return storage.target_command(args)
    if command == "version":
        versions = ", ".join(sorted(history_index(), key=version_key)) or "none (original history unavailable)"
        print(f"archive-general {SKILL_VERSION}: writes formats 2 (filesystem), 3 (direct Drive); reads formats [1, 2, 3]; repo layouts: folders in place (before 2.3), parked folders in _archive/ (2.3+); history: {versions}")
        return 0
    if command == "registry":
        configure_session(args)
        if TARGET.kind == 'google-drive-api':
            import drive_archive
            return drive_archive.dispatch(sys.modules[__name__], None, args)
        return registry_command(args)
    if command == "upgrade" and args.all:
        if args.repo:
            raise Refused("--repo and upgrade --all are mutually exclusive")
        configure_session(args)
        if TARGET.kind == 'google-drive-api':
            import drive_archive
            return drive_archive.dispatch(sys.modules[__name__], None, args)
        return upgrade_command(None, args)
    if command == "read" and not args.repo and Path(args.path).is_absolute():
        if not args.target:
            absolute = expand(args.path)
            match = next((name for name, value in storage.load_config()["targets"].items() if inside(absolute, Path(value["root"]))), None)
            if match:
                args.target = match
        configure_session(args, optional=True)
        resolved = resolve_cloud_read(expand(args.path))
        if resolved:
            entry, rel, direct = resolved
            if direct:
                print(direct)
                return 0
            repo = expand(entry["repo"])
            if repo.is_dir():
                print(f"repo: {repo} (from the registry)", file=sys.stderr)
                configure_session(args, repo)
                return read_command(Store(repo), rel, args)
            store = Store(None, entry)
            row = store.records.get(rel)
            if row:
                supported(row)
                print(store.location(row))
                return 0
            old = next((x for x in store.v1 if x["path"].rstrip("/") == rel.rstrip("/")), None)
            if old:
                print(store.v1_location(old))
                return 0
            raise Refused(f"not archived: {rel}")
    repo = find_repo(args.repo)
    configure_session(args, repo)
    if TARGET.kind == 'google-drive-api':
        import drive_archive
        return drive_archive.dispatch(sys.modules[__name__], repo, args)
    if command in ("sync", "archive"):
        return sync_command(repo, args)
    if command == "restore":
        return restore_command(repo, args)
    if command == "upgrade":
        return upgrade_command(repo, args)
    if command == "import":
        return import_command(repo, args)
    if command == "verify":
        return verify_command(repo, args)
    if command == "tidy":
        return tidy_command(repo, args)
    store = Store(repo)
    if command == "read":
        if args.head is not None and args.head < 0:
            raise Refused("--head must be non-negative")
        rel, _ = store.rel(args.path, "read")
        return read_command(store, rel, args)
    if command in ("list", "status"):
        scopes = [store.rel(p, command)[0] for p in args.paths]
        scopes = [p for p in scopes if p]
        return list_command(store, scopes) if command == "list" else status_command(store, scopes, args.deep)
    return cloud_command(store, command)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    rc = 1
    try:
        args = parse_args(argv)
        rc = dispatch(args)
    except SystemExit as error:
        rc = error.code
    except (Refused, OSError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        rc = 1
    finally:
        logfile = os.environ.get("ICLOUD_ARCHIVE_LOG")
        if logfile:
            with open(logfile, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(t=time.time(), cwd=str(Path.cwd()), argv=argv, rc=rc), ensure_ascii=False) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
