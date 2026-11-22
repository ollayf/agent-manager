#!/usr/bin/env python3
"""Recheck documented findings in disposable local repositories."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from test_support import Env, SCRIPT, SKILL


def module():
    spec = importlib.util.spec_from_file_location('archive_probe_subject', SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def run(name):
    folder = Path(tempfile.mkdtemp(prefix='archive-probe-' + name + '-'))
    if name not in ('resurrect', 'clone', 'keep', 'scan', 'v1verify', 'unknown', 'drift'):
        raise ValueError('unknown probe: ' + name)
    e = Env(folder)
    print('Sandbox:', folder)
    if name in ('resurrect', 'scan', 'v1verify'):
        old = SKILL / '.history/1.0.0/icloud_archive.py'
        if not old.is_file():
            print('SKIPPED: original history/1.0.0 unavailable (A6)')
            return None
        e.write('old/a', 'old bytes')
        e.ok('archive', 'old/a', script=old)
        if name == 'scan':
            before = (e.repo / 'ICLOUD.md').read_bytes()
            print(e.ok('registry', '--scan', e.repo))
            assert (e.repo / 'ICLOUD.md').read_bytes() == before
            print('manifest created:', (e.repo / 'ICLOUD.manifest.jsonl').exists())
        elif name == 'v1verify':
            e.write('new/a', 'new bytes')
            e.ok('sync', 'new')
            result = e.run('verify', script=old)
            print('frozen verify exit:', result.returncode, result.stdout)
            assert result.returncode == 2
        else:
            e.ok('registry', '--scan', e.repo)
            e.ok('restore', 'old/a', script=old)
            print(e.ok('status'))
            print(e.run('verify', '--fix').stdout)
            assert (e.repo / 'old/a').read_text() == 'old bytes'
    elif name == 'keep':
        e.write('data/.keep', '')
        before = e.snapshot()
        print(e.refused('sync', 'data/.keep'))
        assert e.snapshot() == before
        print('FIXED in rebuild: direct .keep is refused')
    elif name == 'clone':
        remote = 'https://example.invalid/archive-probe/repo.git'
        subprocess.run(['git', '-C', str(e.repo), 'remote', 'add', 'origin', remote], check=True)
        e.write('data/a', 'clone bytes')
        e.ok('sync', 'data')
        clone = folder / 'clone/repo'
        clone.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(clone)], check=True)
        subprocess.run(['git', '-C', str(clone), 'remote', 'add', 'origin', remote], check=True)
        print(e.ok('status', cwd=clone))
        m = module()
        m.BASE = e.base
        store = m.Store(clone)
        print('fresh clone park setting:', store.parked)
        assert store.parked == '_archive'
    elif name == 'unknown':
        e.write('data/a', 'bytes')
        e.ok('sync', 'data')
        p = e.repo / 'ICLOUD.manifest.jsonl'
        p.write_text(p.read_text().replace('"format": 2', '"format": 999'))
        print(e.refused('read', 'data/a'))
        assert (e.root / 'files/data/a').read_text() == 'bytes'
    elif name == 'drift':
        m = module()
        versions = [m.SKILL_VERSION]
        for p in (SKILL / 'SKILL.md',):
            import re
            versions.append(re.search(r'^\s*version: (.+)$', p.read_text(), re.M).group(1))
        assert len(set(versions)) == 1
        print('versions agree:', versions[0])
        print('Recovered guide remains the historical 2.3.0 specification; rebuild results are separate.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='*')
    args = parser.parse_args()
    for name in args.names or ['resurrect', 'clone', 'keep', 'scan', 'v1verify', 'unknown', 'drift']:
        print('\nPROBE', name)
        run(name)


if __name__ == '__main__':
    main()
