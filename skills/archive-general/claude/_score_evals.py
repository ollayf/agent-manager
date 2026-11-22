#!/usr/bin/env python3
"""Score only sandbox disk, command logs, and the agent's own saved answer."""
import argparse
import json
from pathlib import Path
import shlex
from _setup_evals import invoke, scenarios


def records(repo):
    result = {}
    path = repo / 'ICLOUD.manifest.jsonl'
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get('op') == 'add':
                result[row['path']] = row
            elif row.get('op') == 'del':
                result.pop(row['path'], None)
    return result


def v1(repo):
    import re
    path = repo / 'ICLOUD.md'
    return set(re.findall(r'^\| `([^`]+)` \| (?:file|dir|zst×\d+) \|', path.read_text(), re.M)) if path.exists() else set()


def score(sandbox):
    sandbox = Path(sandbox).resolve()
    spec = json.loads((sandbox / 'spec.json').read_text())
    if spec.get('skipped'):
        return None, [spec['skipped']]
    repo = sandbox / 'repo'
    rec, old = records(repo), v1(repo)
    answer = (sandbox / 'answer.txt').read_text().lower() if (sandbox / 'answer.txt').is_file() else ''
    failures = [] if answer.strip() else ['missing/empty answer.txt']
    log = sandbox / 'log.jsonl'
    commands = []
    if log.exists():
        for line in log.read_text().splitlines():
            row = json.loads(line)
            argv = row['argv']
            if '--help' in argv:
                continue
            if argv[:1] == ['--repo']:
                argv = argv[2:]
            commands.append(argv)
    def matching(want, command):
        want = shlex.split(want) if isinstance(want, str) else want
        if not command or command[0] != want[0]:
            return False
        if len(want) == 1 and ('--plan' in command or '--fix' in command):
            return False
        return all(item in command for item in want[1:])
    def check(ok, label):
        if not ok:
            failures.append(label)
    for kind, value in spec['checks'].items():
        values = value if isinstance(value, list) else [value]
        if kind in ('archived', 'still_archived', 'untouched', 'local_kept', 'not_archived', 'archived_v1', 'v2_records', 'v1_rows', 'no_file', 'restored', 'parked', 'not_parked', 'source_kept'):
            for p in values:
                local = repo / p
                ok = {'archived': p in rec and not local.exists(), 'still_archived': p in rec and not local.exists(), 'untouched': local.exists() and p not in rec, 'local_kept': local.exists(), 'not_archived': p not in rec, 'archived_v1': p in old and not local.exists(), 'v2_records': rec.get(p, {}).get('format') == 2, 'v1_rows': p in old, 'no_file': not local.exists(), 'restored': local.is_file() and p not in rec, 'parked': (repo / '_archive' / p).is_dir() and not local.exists(), 'not_parked': local.is_dir() and not (repo / '_archive' / p).exists(), 'source_kept': Path(p).exists()}[kind]
                check(ok, kind + ': ' + p)
        elif kind == 'archived_prefix':
            names = [p for p in rec if p.startswith(value)]
            check(len(names) >= 3 and all(not (repo / p).exists() for p in names), kind)
        elif kind == 'nothing_archived_v2':
            check(not rec, kind)
        elif kind == 'nothing_archived':
            check(not rec and not old and not list((sandbox / 'root').rglob('*.csv')), kind)
        elif kind == 'v1_rows_all':
            check(not rec and bool(old), kind)
        elif kind == 'no_flag':
            check(all(value not in command for command in commands), kind + ': ' + value)
        elif kind == 'must_run':
            for want in value:
                check(any(matching(want, c) for c in commands), kind + ': ' + str(want))
        elif kind == 'no_cmd':
            check(all(c[0] not in value for c in commands if c), kind)
        elif kind == 'no_cmd_exact':
            for want in value:
                # A planned run is allowed, a real run (with or without --fix) is not.
                check(not any(matching(want, c) and '--plan' not in c for c in commands), kind + ': ' + str(want))
        elif kind == 'order':
            a, b = value
            check(any(matching(a, x) and any(matching(b, y) for y in commands[i + 1:]) for i, x in enumerate(commands)), kind)
        elif kind == 'verify_clean':
            check(invoke(sandbox, ['verify'], cwd=repo, overrides={'ICLOUD_ARCHIVE_LOG': ''}).returncode == 0, kind)
        elif kind == 'content':
            for name, expected in value.items():
                local = repo / name
                if local.is_file():
                    data = local.read_bytes()
                else:
                    result = invoke(sandbox, ['read', name], cwd=repo, overrides={'ICLOUD_ARCHIVE_LOG': ''})
                    location = Path(result.stdout.strip())
                    data = location.read_bytes() if result.returncode == 0 and location.is_file() else b''
                check(data == expected.encode(), kind + ': ' + name)
        elif kind == 'answer_any':
            for group in value:
                check(any(word.lower() in answer for word in group), kind + ': ' + str(group))
        elif kind == 'asks':
            check(any(word in answer for word in ['?', 'should i', 'do you want', 'would you like', 'which ', 'confirm', 'let me know', 'go ahead', 'your decision', 'need you to decide', 'your call']), kind)
        else:
            raise ValueError('unknown check: ' + kind)
    return not failures, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('runs', nargs='*')
    args = parser.parse_args()
    failed = 0
    for run in args.runs or [p.name for p in sorted(args.directory.iterdir()) if (p / 'spec.json').exists()]:
        passed, failures = score(args.directory / run)
        print(run, 'SKIPPED' if passed is None else 'PASS' if passed else 'FAIL', '; '.join(failures))
        failed += passed is False
    return bool(failed)


if __name__ == '__main__':
    raise SystemExit(main())
