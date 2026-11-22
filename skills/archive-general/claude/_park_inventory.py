#!/usr/bin/env python3
"""Read-only stat inventory around a folder-layout migration; never download content."""
import argparse
import collections
import json
import os
from pathlib import Path
import re


def snap(repo):
    repo = repo.expanduser().resolve()
    files, records = {}, {}
    generic = any((repo / name).is_file() for name in ('ARCHIVE.md', 'ARCHIVE.manifest.jsonl'))
    index = repo / ('ARCHIVE.md' if generic else 'ICLOUD.md')
    manifest = repo / ('ARCHIVE.manifest.jsonl' if generic else 'ICLOUD.manifest.jsonl')
    root = None
    if manifest.is_file():
        for line in manifest.read_text().splitlines():
            item = json.loads(line)
            if 'icloud_archive_manifest' in item:
                root = item['root']
            elif item.get('op') == 'add':
                records[item['path']] = item
            elif item.get('op') == 'del':
                records.pop(item['path'], None)
    old_rows = []
    if index.is_file():
        text = index.read_text()
        match = re.search(r'^Root:\s*`([^`]+)`', text, re.M)
        if match:
            root = match[1]
        old_rows = re.findall(r'^\| `([^`]+)` \| (file|dir|zst×\d+) \| ([^|]+) \|$', text, re.M)
    for parent, dirs, names in os.walk(repo, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.git' and not (Path(parent) / d).is_symlink()]
        for name in names:
            p = Path(parent) / name
            if name in ('ARCHIVE.md', 'ARCHIVE.manifest.jsonl', 'ICLOUD.md', 'ICLOUD.manifest.jsonl') and p.parent == repo:
                continue
            info = p.lstat()
            files[p.relative_to(repo).as_posix()] = dict(size=info.st_size, mtime_ns=info.st_mtime_ns, link=os.readlink(p) if p.is_symlink() else None)
    count = size = 0
    if root:
        for parent, dirs, names in os.walk(Path(root).expanduser(), followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
            for name in names:
                if name in ('.DS_Store', '.manifest.jsonl'):
                    continue
                info = (Path(parent) / name).lstat()
                count += 1
                size += info.st_size
    return dict(files=files, records=records, v1_rows=old_rows, cloud=dict(count=count, bytes=size))


def compare(before, after):
    problems = []
    if before.keys() != after.keys():
        problems.append('repo set differs')
    for repo in before.keys() & after.keys():
        a, b = before[repo], after[repo]
        for field in ('records', 'v1_rows', 'cloud'):
            if a[field] != b[field]:
                problems.append(repo + ': ' + field + ' differs')
        normal = lambda v: {p: x for p, x in v.items() if Path(p).name != '.DS_Store'}
        finder = lambda v: collections.Counter(json.dumps(x, sort_keys=True) for p, x in v.items() if Path(p).name == '.DS_Store')
        if normal(a['files']) != normal(b['files']) or finder(a['files']) != finder(b['files']):
            problems.append(repo + ': file stats differ')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('snap')
    p.add_argument('output', type=Path)
    p.add_argument('repos', nargs='+', type=Path)
    p = sub.add_parser('diff')
    p.add_argument('before', type=Path)
    p.add_argument('after', type=Path)
    args = parser.parse_args()
    if args.command == 'snap':
        args.output.write_text(json.dumps({str(p.expanduser().resolve()): snap(p) for p in args.repos}, indent=2, sort_keys=True) + '\n')
        print(args.output)
        return 0
    problems = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    print('\n'.join(problems) if problems else 'identical files, records, and archive totals')
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
