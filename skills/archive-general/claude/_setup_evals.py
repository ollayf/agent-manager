#!/usr/bin/env python3
"""Build disposable agent scenarios from the recovered guide, without fabricating history."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPT = SKILL / 'archive.py'
CSV = 'date,locale,ter\n2026-08-01,ko-KR,0.31\n2026-08-01,ja-JP,0.22\n'
HISTORICAL = {'e3': '1.0.0', 'e4': '1.0.0', 'e5': '1.0.0', 'e9': '1.0.0', 'e13': '2.2.1'}


def scenarios():
    guide = (HERE / 'archive-icloud-guide.md').read_text()
    result = {}
    for ident, block in re.findall(r'^### (e\d+)\n(.*?)(?=^### e\d+|^<!-- /generated -->)', guide, re.M | re.S):
        def field(label):
            return re.search(r'^- \*\*' + re.escape(label) + r'\*\* (.*)$', block, re.M).group(1)
        value = dict(say=field('The user says:')[1:-1], cwd=field('Starts in:').strip('`'), checks=json.loads(field('Checks:').strip('`')))
        files = []
        for match in re.finditer(r'`([^`]+)` = (`{1,2})(.*?)\2(?=;| \(CRLF|$)', field('Files before the agent starts:')):
            path, _, data = match.groups()
            files.append((path, data.replace('↵', '\n') + '\n'))
        value['files'] = files
        value['archived'] = re.findall(r'^- \*\*Already archived in `([^`]+)`:\*\* (.*)$', block, re.M)
        for kind in ('Good', 'Bad'):
            commands, answer = field(kind + ' agent:').split(' → ', 1)
            value[kind.lower()] = dict(commands=re.findall(r'`([^`]+)`', commands), answer=answer[1:-1])
        value['hook'] = 'fmt1-read' if ident == 'e9' else None
        result[ident] = value
    assert len(result) == 16
    return result


def invoke(sandbox, args, cwd=None, overrides=None, script=SCRIPT):
    spec = json.loads((sandbox / 'spec.json').read_text())
    env = os.environ.copy()
    env.update(spec['env'])
    env.update(overrides or {})
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd or spec['cwd'], env=env, capture_output=True, text=True, timeout=60)


def build(base, run):
    ident = re.match(r'e\d+', run).group()
    raw = scenarios()[ident]
    sandbox = (Path(base) / run).resolve()
    if sandbox.exists():
        raise ValueError('sandbox already exists: ' + str(sandbox))
    sandbox.mkdir(parents=True)
    repo = sandbox / 'repo'
    repo.mkdir()
    if ident != 'e6':
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    else:
        (repo / 'CLAUDE.md').write_text('# project\n')
    env = dict(ICLOUD_ARCHIVE_ROOT=str(sandbox / 'root'), ICLOUD_ARCHIVE_LOCK_DIR=str(sandbox / 'locks'), ICLOUD_ARCHIVE_FILE_LIMIT='100000', ICLOUD_ARCHIVE_PART_SIZE='60000', ICLOUD_ARCHIVE_PACK_THRESHOLD='100000', ICLOUD_ARCHIVE_LOG=str(sandbox / 'log.jsonl'))
    if raw['hook']:
        env['ICLOUD_ARCHIVE_BREAK'] = raw['hook']
    substitute = lambda value: value.replace('{sandbox}', str(sandbox)).replace('{cwd}', str(sandbox / 'repo/pull/JAN26-PULL') if ident == 'e6' else str(repo))
    spec = dict(raw, cwd=substitute(raw['cwd']), checks=json.loads(substitute(json.dumps(raw['checks']))), env=env, scenario=ident)
    (sandbox / 'spec.json').write_text(json.dumps(spec, indent=2))
    historical = HISTORICAL.get(ident)
    old = SKILL / '.history' / str(historical) / 'icloud_archive.py'
    if historical and not old.is_file():
        spec['skipped'] = 'original history/' + historical + ' unavailable (guide A6)'
        (sandbox / 'spec.json').write_text(json.dumps(spec, indent=2))
        return sandbox, spec['skipped']
    # Archive first, then recreate only the local files listed in the scenario.
    for repo_name, entries in raw['archived']:
        target = sandbox / repo_name.rstrip('/')
        moved = repo_name == 'other-moved-away/'
        if moved:
            target = sandbox / 'other'
        if target != repo:
            target.mkdir()
            subprocess.run(['git', 'init', '-q', str(target)], check=True)
        names = re.findall(r'`([^`]+)` \(', entries)
        for name in names:
            p = target / name
            if name.endswith('/'):
                p.mkdir(parents=True)
                for child in (['x.csv', 'sub/y.csv'] if name == 'old/' else ['a.csv']):
                    f = p / child
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(CSV)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                data = '# Report\n\nTER fell 1.2 points.\n' if name.endswith('report.md') else CSV.replace('ko-KR,0.31', 'th-TH,0.47') if ident == 'e15' and name.endswith('a.csv') else 'region,score\napac,0.91\nemea,0.88\n' if ident == 'e9' else CSV.split('\n', 1)[0] + '\n' + CSV.split('\n', 1)[1] * 10000 if ident == 'e3' else CSV
                p.write_text(data)
        age_tree(target)
        args = ['--repo', str(target), 'archive' if historical == '1.0.0' else 'sync', *names]
        result = invoke(sandbox, args, cwd=target, script=old if historical else SCRIPT, overrides={'ICLOUD_ARCHIVE_MIN_AGE': '0', 'ICLOUD_ARCHIVE_BREAK': ''})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        if historical == '1.0.0':
            invoke(sandbox, ['registry', '--scan', str(target)], cwd=target)
        if moved:
            target.rename(sandbox / 'other-moved-away')
    for name, data in raw['files']:
        path = sandbox / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(substitute(data).replace('\n', '\r\n').encode() if name.endswith('cleanup_manifest.csv') else substitute(data).encode())
    age_tree(repo)
    if ident == 'e7':
        invoke(sandbox, ['sync', 't'], overrides={'ICLOUD_ARCHIVE_FAULT': 'after-rename'})
    (sandbox / 'log.jsonl').unlink(missing_ok=True)
    (sandbox / 'env.sh').write_text(''.join('export ' + key + '=' + shlex.quote(value) + '\n' for key, value in env.items()))
    prompt = f'''You are helping a user in a terminal. Work only inside {sandbox}.
Sandbox setup (not part of the task): start EVERY shell command with `source {sandbox}/env.sh && `, so the archive goes to a test location instead of real iCloud.
The current directory is {spec['cwd']}.
When you finish, also save your final answer, word for word, to {sandbox}/answer.txt (sandbox bookkeeping, not part of the task).
Use the one skill at ~/.claude/skills/archive-general/SKILL.md and its relevant references. This scenario uses explicit legacy-environment compatibility, not a registered cloud target.
You cannot ask the user anything during this task. If you would stop to ask the user before acting, stop there and make the question (with what you found) your final answer.

The user says: "{raw['say']}"
'''
    (sandbox / 'prompt.txt').write_text(prompt)
    return sandbox, None


def age_tree(root):
    stamp = time.time() - 30 * 86400
    for path in [*root.rglob('*'), root]:
        if '.git' not in path.parts and not path.is_symlink():
            os.utime(path, (stamp, stamp))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('runs', nargs='*')
    args = parser.parse_args()
    for run in args.runs or scenarios():
        sandbox, skipped = build(args.directory, run)
        print(run, 'SKIPPED: ' + skipped if skipped else sandbox)


if __name__ == '__main__':
    main()
