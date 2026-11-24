#!/usr/bin/env python3
"""List tracked symlinks that would break in a fresh clone on another machine.

    tracked_links.py <repo> [pathspec ...]

A tracked link survives a clone only when it is relative, stays inside the repository and
points at content Git also tracks. Absolute links, links that climb out of the checkout and
links to ignored or untracked files (secrets.env, caches) are printed, one per line.
Targets are read from the index, so the answer matches what a commit would carry.
"""
import os
import subprocess
import sys


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True).stdout


def broken_links(repo, pathspecs=()):
    entries = git(repo, "ls-files", "-s", "-z", "--", *pathspecs).split(b"\0")
    bad = []
    for entry in filter(None, entries):
        meta, path = entry.split(b"\t", 1)
        mode, sha = meta.split()[:2]
        if mode != b"120000":
            continue
        path = path.decode()
        target = git(repo, "cat-file", "blob", sha.decode()).decode()
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if (os.path.isabs(target) or resolved == ".." or resolved.startswith("../")
                or not git(repo, "ls-files", "-z", "--", resolved)):
            bad.append(path)
    return bad


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    for path in broken_links(sys.argv[1], sys.argv[2:]):
        print(path)


if __name__ == "__main__":
    main()
