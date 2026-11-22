#!/usr/bin/env python3
"""Maintain rebuild appendices separately, preserving the recovered source verbatim."""
import argparse
import collections
import json
from pathlib import Path
import subprocess
import sys
from _mutate import mutants
from _mutate_drive import CASES
from _setup_evals import scenarios

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / 'general-appendices.md'


def render():
    files = ['test_icloud_archive.py', 'test_parked_folders.py', 'test_legacy_compat.py', 'test_rebuild_regressions.py', 'test_general_storage.py', 'test_drive_api.py', 'test_batching.py', 'test_compressed.py']
    process = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', *[str(HERE / f) for f in files]], capture_output=True, text=True, check=True)
    nodes = [line[line.index('test_'):] for line in process.stdout.splitlines() if 'test_' in line and '::' in line and not line.startswith(' ')]
    counts = collections.Counter(node.split('::')[0] for node in nodes)
    assert sum(counts[f] for f in files[:3]) == 219, counts
    result = ['# Archive General validation appendices', '', 'Generated from the current Archive General source. The recovered guide and historical rebuild results remain unchanged.', '', '## E — collected tests', '']
    for f in files:
        result += ['### ' + f + ' (' + str(counts[f]) + ' cases)', '']
        result += ['- `' + node.split('::', 1)[1] + '`' for node in nodes if node.startswith(f + '::')]
        result.append('')
    result += ['## F — mutation pairings', '', '| # | Guard | Test |', '|---|---|---|']
    for value in mutants():
        result.append('| ' + str(value['id']) + ' | ' + value['guard'] + ' | `' + value['test'] + '` |')
    result += ['', '### Direct Drive mutation pairings', '', '| # | Guard | Test |', '|---|---|---|']
    for number,guard,file,changes,test in CASES:
        result.append('| D'+str(number)+' | '+guard+' | `test_drive_api.py::'+test+'` |')
    result += ['', '## G — original scenario definitions (legacy environment)', '', 'These original scenarios exercise legacy environment overrides. Five require unavailable original frozen releases and are explicitly skipped. The current target/SSD/Google/offline forward scenarios are defined in _forward_general.py; actual outcomes are in general-evidence/.', '']
    for ident, value in scenarios().items():
        result += ['### ' + ident, '', '```json', json.dumps(value, indent=2, ensure_ascii=False), '```', '']
    return '\n'.join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--write', action='store_true')
    action.add_argument('--check', action='store_true')
    args = parser.parse_args()
    generated = render()
    if args.write:
        OUTPUT.write_text(generated)
        print('wrote', OUTPUT)
        return 0
    current = OUTPUT.exists() and OUTPUT.read_text() == generated
    print('current' if current else 'stale: run --write (recovered source is never overwritten)')
    return not current


if __name__ == '__main__':
    raise SystemExit(main())
