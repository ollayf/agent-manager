#!/usr/bin/env python3
"""Good scripts must pass; each deliberately bad script must fail before any agent runs."""
import argparse
import json
from pathlib import Path
import shlex
import tempfile
from _setup_evals import build, invoke, scenarios
from _score_evals import score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    base = args.directory or Path(tempfile.mkdtemp(prefix='archive-eval-selftest-'))
    problems = 0
    summary = []
    for ident in scenarios():
        for kind in ('good', 'bad'):
            sandbox, skipped = build(base / kind, ident)
            if skipped:
                print(ident, kind, 'SKIPPED', skipped)
                continue
            spec = json.loads((sandbox / 'spec.json').read_text())
            agent = spec[kind]
            for command in agent['commands']:
                command = command.replace('{sandbox}', str(sandbox)).replace('{cwd}', spec['cwd'])
                invoke(sandbox, shlex.split(command))
            (sandbox / 'answer.txt').write_text(agent['answer'] + '\n')
            passed, failures = score(sandbox)
            expected = kind == 'good'
            ok = passed == expected
            problems += not ok
            print(ident, kind, 'OK' if ok else 'FAILED', '; '.join(failures))
            summary.append(dict(scenario=ident, kind=kind, correct=ok, failures=failures))
    (base / 'selftest-results.json').write_text(json.dumps(summary, indent=2))
    print('Evidence:', base)
    # Unlike the historical harness, both good and bad failures affect the exit code.
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
