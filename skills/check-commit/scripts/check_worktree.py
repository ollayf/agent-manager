#!/usr/bin/env python3
"""Read-only, local review of pending Git content; never a full readiness verdict."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata
from file_types import classify, HEADER_BYTES, TOTAL_ADDED_BYTES

MAX_BYTES = 1024 * 1024
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    "api-token": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b"),
    "authenticated-url": re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@", re.I),
    "credential-assignment": re.compile(
        r'''["']?\b(?:[A-Za-z0-9_]*(?:api[_-]?key|secret|password|passwd|access[_-]?token|auth[_-]?token)|token)["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']''', re.I),
    "unquoted-credential-assignment": re.compile(
        r"^\s*(?:export\s+)?(?:[A-Za-z0-9_]*(?:api[_-]?key|secret|password|passwd|access[_-]?token|auth[_-]?token)|token)\s*[:=]\s*([A-Za-z0-9_+/-]{12,})\s*(?:#.*)?$", re.I | re.M),
}
PLACEHOLDER = re.compile(
    r"^(?:example|placeholder|dummy|fake|test|changeme|replace[_ -]?me|your[_ -]|<|\$\{|\{\{)", re.I)
CONFLICT = re.compile(r"^(?:<{7} |={7}$|>{7} |\|{7} )", re.M)


class CheckError(Exception):
    pass


def git_environment():
    env = dict(os.environ)
    # Ambient Git overrides must not redirect the caller's --repo or its index.
    for key in tuple(env):
        if key.startswith("GIT_"):
            del env[key]
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    return env


def git_command(repo, *args):
    return ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-C", str(repo), *args]


def git(repo, *args, ok=(0,)):
    try:
        result = subprocess.run(
            git_command(repo, *args), env=git_environment(), capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CheckError("Git unavailable or timed out") from exc
    if result.returncode not in ok:
        # stderr can contain sensitive data from a repository; don't echo it.
        raise CheckError("Git command failed: " + args[0])
    return result


def blob_header(repo, oid):
    """Read a bounded prefix even for multi-gigabyte staged blobs."""
    with subprocess.Popen(git_command(repo, "cat-file", "blob", oid),
                          env=git_environment(), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        try:
            data = process.stdout.read(HEADER_BYTES)
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return data


def names(repo, *args):
    return [os.fsdecode(p) for p in git(repo, *args).stdout.split(b"\0") if p]


def inventory(repo):
    common = ("--no-ext-diff", "--no-textconv", "--name-only", "-z")
    return {
        "staged": names(repo, "diff", "--cached", *common),
        "unstaged": names(repo, "diff", *common),
        "untracked": names(repo, "ls-files", "--others", "--exclude-standard", "-z"),
    }


def index_entries(repo):
    entries = {}
    for item in git(repo, "ls-files", "--stage", "-z").stdout.split(b"\0"):
        if item:
            metadata, path = item.split(b"\t", 1)
            mode, oid, stage = metadata.split()
            entries[os.fsdecode(path)] = (mode.decode(), oid.decode(), stage.decode())
    return entries


def sensitive_path(path):
    p = PurePosixPath(path)
    name = p.name.lower()
    template = name.endswith((".example", ".sample", ".template", ".dist"))
    return (
        (name == ".env" or name.startswith(".env.")) and not template
        or name in {"id_rsa", "id_ed25519", "id_ecdsa", ".netrc", ".pypirc"}
        or name.endswith((".p12", ".pfx", ".key", ".keystore"))
        or any(part.lower() in {".aws", ".ssh"} for part in p.parts)
    )


def suspicious_artifact(path):
    p = PurePosixPath(path)
    return (any(part in {"node_modules", "__pycache__", ".venv", "venv", "dist", "build"} for part in p.parts)
            or p.suffix.lower() in {".log", ".sqlite", ".sqlite3", ".db", ".zip", ".tar", ".gz", ".pyc"})


def check(repo):
    repo = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel").stdout).rstrip("\n"))
    before = inventory(repo)
    entries = index_entries(repo)
    added_paths = set(names(repo, "diff", "--cached", "--no-ext-diff", "--no-textconv",
                            "--no-renames", "--name-only", "--diff-filter=A", "-z"))
    added_paths.update(before["untracked"])
    findings, scanned, snapshots, file_reports = [], [], [], {}

    def record_file(source, path, head, size, mode, coverage):
        file_reports[source, path] = classify(path, source, head, size, mode,
                                             path in added_paths, coverage)

    def add(severity, code, path=None, source=None, line=None):
        finding = {"severity": severity, "code": code}
        if path is not None:
            finding["path"] = path
        if source is not None:
            finding["source"] = source
        if line is not None:
            finding["line"] = line
        if finding not in findings:
            findings.append(finding)

    def read(source, path):
        if source == "index":
            entry = entries.get(path)
            if entry is None:  # staged deletion
                return None
            mode, oid, stage = entry
            if stage != "0":
                record_file(source, path, None, None, mode, "unmerged")
                add("blocker", "unmerged-index", path, source)
                return None
            if mode == "160000":
                record_file(source, path, None, None, mode, "submodule-not-read")
                add("review", "submodule-not-scanned", path, source)
                return None
            size = int(git(repo, "cat-file", "-s", oid).stdout)
            if size > MAX_BYTES:
                record_file(source, path, blob_header(repo, oid), size, mode, "header-only")
                add("review", "oversized-not-scanned", path, source)
                return None
            data = git(repo, "cat-file", "blob", oid).stdout
            record_file(source, path, data[:HEADER_BYTES], size, mode,
                        "symlink-target-only" if mode == "120000" else "full-file-read")
            if mode == "120000":
                add("review", "symlink-review", path, source)
            return data
        file = repo / path
        # Don't follow parent directory links or a changed file's symlink.
        for parent in file.parents:
            if parent == repo:
                break
            if parent.is_symlink():
                record_file(source, path, None, None, "unknown", "symlink-parent-not-read")
                add("review", "symlink-parent-not-scanned", path, source)
                return None
        try:
            info = file.lstat()
            if stat.S_ISLNK(info.st_mode):
                add("review", "symlink-review", path, source)
                data = os.fsencode(os.readlink(file))
                record_file(source, path, data, len(data), "120000", "symlink-target-only")
                return data
            if not stat.S_ISREG(info.st_mode):
                record_file(source, path, None, None, "special", "special-not-read")
                add("review", "nonregular-not-scanned", path, source)
                return None
            # O_NOFOLLOW also closes the final-component lstat/open race.
            fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    record_file(source, path, None, None, "special", "special-not-read")
                    add("review", "nonregular-not-scanned", path, source)
                    return None
                opened_info = os.fstat(stream.fileno())
                data = stream.read(HEADER_BYTES if opened_info.st_size > MAX_BYTES else MAX_BYTES + 1)
            mode = "100755" if opened_info.st_mode & 0o111 else "100644"
            record_file(source, path, data[:HEADER_BYTES], opened_info.st_size, mode,
                        "header-only" if opened_info.st_size > MAX_BYTES else "full-file-read")
            if opened_info.st_size > MAX_BYTES:
                add("review", "oversized-not-scanned", path, source)
                return None
            if len(data) > MAX_BYTES:
                add("review", "oversized-not-scanned", path, source)
                return None
            return data
        except FileNotFoundError:
            if path in before["untracked"]:
                record_file(source, path, None, None, "unknown", "missing-during-check")
                add("review", "worktree-changed-during-check", path, source)
            return None  # unstaged deletion
        except OSError:
            record_file(source, path, None, None, "unknown", "unreadable")
            add("review", "unreadable-not-scanned", path, source)
            return None

    if git(repo, "ls-files", "--unmerged", "-z").stdout:
        add("blocker", "unmerged-index")
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "BISECT_LOG"):
        location = os.fsdecode(git(repo, "rev-parse", "--git-path", marker).stdout).rstrip("\n")
        if (repo / location).exists():
            add("blocker", "unfinished-git-operation")
    for cached in (True, False):
        args = ["diff", "--no-ext-diff", "--no-textconv", "--check"]
        if cached:
            args.append("--cached")
        result = git(repo, *args, ok=(0, 2))
        if result.returncode:
            add("blocker", "diff-check-failed", source="index" if cached else "worktree")

    candidates = [("index", p) for p in before["staged"]]
    deleted = set(names(repo, "diff", "--no-ext-diff", "--no-textconv",
                        "--name-only", "--diff-filter=D", "-z"))
    candidates += [("worktree", p) for p in sorted(
        (set(before["unstaged"]) - deleted) | set(before["untracked"]))]
    for source, path in candidates:
        if sensitive_path(path) and (source == "index" and path in entries
                                     or source == "worktree" and os.path.lexists(repo / path)):
            add("blocker", "sensitive-file", path, source)
        data = read(source, path)
        snapshots.append((source, path, None if data is None else hashlib.sha256(data).hexdigest()))
        if data is None:
            continue
        if sensitive_path(path):
            add("blocker", "sensitive-file", path, source)
        if suspicious_artifact(path):
            add("review", "generated-or-private-artifact", path, source)
        if b"\0" in data:
            add("review", "binary-not-scanned", path, source)
            continue
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            add("review", "encoding-not-scanned", path, source)
            continue
        scanned.append({"path": path, "source": source})
        for code, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                if code.endswith("credential-assignment") and PLACEHOLDER.match(match.group(1)):
                    continue
                add("blocker", code, path, source, content.count("\n", 0, match.start()) + 1)
        for match in CONFLICT.finditer(content):
            add("blocker", "conflict-marker", path, source, content.count("\n", 0, match.start()) + 1)
        if path in before["untracked"]:
            for i, line in enumerate(content.splitlines(), 1):
                if line.rstrip(" \t") != line:
                    add("blocker", "trailing-whitespace", path, source, i)
    # Check both Git inventory and bytes again. Index hashes catch staging races.
    if before != inventory(repo) or entries != index_entries(repo):
        add("review", "worktree-changed-during-check")
    for source, path, digest in snapshots:
        if source == "worktree":
            data = read(source, path)
            if digest != (None if data is None else hashlib.sha256(data).hexdigest()):
                add("review", "worktree-changed-during-check", path, source)
    if not any(before.values()):
        add("review", "nothing-to-commit")
    if set(before["staged"]) & set(before["unstaged"]):
        add("review", "staged-worktree-versions-differ")
    for record in file_reports.values():
        for warning in record["warnings"]:
            finding = {**warning, "path": record["path"], "source": record["source"],
                       "category": record["category"], "size_bytes": record["size_bytes"]}
            if finding not in findings:
                findings.append(finding)
    added_reports = [r for r in file_reports.values() if r["added"]]
    # Count each added path once, retaining the larger of staged/working sizes.
    sizes = {}
    for record in added_reports:
        sizes[record["path"]] = max(sizes.get(record["path"], 0), record["size_bytes"] or 0)
    if sum(sizes.values()) > TOTAL_ADDED_BYTES:
        findings.append({"severity": "review", "code": "added-files-total-size-review",
                         "size_bytes": sum(sizes.values()),
                         "reason": "Added files exceed the 20 MiB aggregate review threshold.",
                         "action": "Review whether the full asset set belongs in Git or external storage."})
    folded = {}
    for path in sorted(set(entries) | added_paths):
        folded.setdefault(unicodedata.normalize("NFC", path).casefold(), []).append(path)
    for paths in folded.values():
        if len(paths) > 1:
            for path in paths:
                if path not in added_paths:
                    continue
                findings.append({"severity": "review", "code": "case-collision-review",
                                 "path": path, "reason": "Path collides under case folding or Unicode normalization.",
                                 "action": "Use names that stay distinct on case-insensitive filesystems."})
    for path in added_paths:
        if path not in {r["path"] for r in added_reports}:
            add("review", "added-file-not-inspected", path)
    status = ("BLOCKED" if any(f["severity"] == "blocker" for f in findings)
              else "NEEDS_REVIEW" if findings else "AUTOMATED_PASS")
    return {
        "status": status, "repository": str(repo), "scope": before,
        "scanned": scanned, "findings": findings,
        "file_checks": sorted(file_reports.values(), key=lambda r: (r["path"], r["source"])),
        "added_file_summary": {"paths": len(added_paths), "reported_paths": len(sizes),
                               "content_inspected_paths": len({r["path"] for r in added_reports
                                   if r["inspection"]["coverage"] in {"full-file-read", "header-only"}}),
                               "unknown_size_paths": sorted({r["path"] for r in added_reports if r["size_bytes"] is None}),
                               "total_size_complete": not any(r["size_bytes"] is None for r in added_reports),
                               "total_bytes": sum(sizes.values())},
        "limitations": ["Heuristic secret detection; unknown formats can be missed.",
                        "Ignored untracked files and existing history are outside scope.",
                        "Tests and human code/checklist review are still required.",
                        "File types use bounded headers and extensions; embedded asset contents are not inspected.",
                        "Rerun after any edit or staging operation."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = check(args.repo)
    except (CheckError, ValueError, OSError):
        report = {"status": "NEEDS_REVIEW", "findings": [
            {"severity": "review", "code": "operational-error"}],
            "limitations": ["Unable to complete checks; verify Git and repository access."]}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(report["status"])
        for group, paths in report.get("scope", {}).items():
            print(f"{group}: {len(paths)}")
        for finding in report["findings"]:
            # JSON quoting prevents control characters in filenames forging output.
            print(json.dumps(finding, ensure_ascii=True))
        for limitation in report["limitations"]:
            print(limitation)
    return (1 if report["status"] == "BLOCKED" else
            2 if report["status"] == "NEEDS_REVIEW" else 0)


if __name__ == "__main__":
    sys.exit(main())
