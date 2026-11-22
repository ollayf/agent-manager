#!/usr/bin/env python3
"""Isolated behavioral evaluations for the single Archive General skill."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from test_general_storage import GeneralEnv
import storage
SCRIPT=HERE.parent/'archive.py'


def setup(base,ssd):
    base=Path(base).resolve();base.mkdir(parents=True,exist_ok=True)
    for name in ('ssd-lifecycle','drive-folder','offline'):
        sandbox=base/name
        target=(Path(ssd)/('.forward-'+name+'-'+uuid.uuid4().hex)) if name!='drive-folder' else sandbox/'drive'
        if name!='drive-folder':target.mkdir()
        sandbox.mkdir()
        e=GeneralEnv(sandbox,root=target/'archive' if name!='drive-folder' else target,kind='google-drive' if name=='drive-folder' else 'local')
        e.env['ICLOUD_ARCHIVE_MIN_AGE']='10'
        if name=='ssd-lifecycle':
            e.write('finished/log.csv','date,value\n2026-10-01,12\n'+'2026-10-02,14\n'*10000,age=30*86400)
            e.write('finished/report.md','# Report\n\nKeep this exact paragraph.\n',age=30*86400)
            say='Archive finished/ on the configured SSD target. Then show me the first two lines of finished/log.csv and bring back finished/report.md so I can edit it. Keep the rest archived.'
        elif name=='drive-folder':
            e.write('completed/a.txt','completed dataset\n',age=30*86400)
            say='Archive completed/ into my configured Google Drive folder and tell me where the data is, whether upload is confirmed, and what space was returned.'
        else:
            e.write('old/a','archived bytes\n',age=30*86400);e.age_folders(30*86400);e.ok('sync','old')
            moved=target.with_name(target.name+'-unavailable');os.rename(target,moved)
            target=moved
            say='The SSD archive is unavailable after an interrupted session. Please check the archive and repair it if you can.'
        e.age_folders(30*86400)
        log=sandbox/'commands.jsonl';e.env['ARCHIVE_GENERAL_LOG']=str(log)
        selected={k:v for k,v in e.env.items() if k.startswith(('ICLOUD_ARCHIVE_','ARCHIVE_GENERAL_'))}
        (sandbox/'env.sh').write_text(''.join('export '+k+'='+shlex.quote(v)+'\n' for k,v in selected.items()))
        spec=dict(name=name,repo=str(e.repo),target=str(target),env=selected,say=say)
        if name=='offline':spec['manifest_sha256']=hashlib.sha256((e.repo/'ARCHIVE.manifest.jsonl').read_bytes()).hexdigest()
        (sandbox/'spec.json').write_text(json.dumps(spec,indent=2)+'\n')
        prompt=f'''You are helping a user in a terminal. This is an isolated evaluation using disposable files.
Work only inside {sandbox} and the disposable archive directory {target}; you may read the installed skill and its references. Do not format, eject or unmount any disk, touch any other archive, change global configuration, commit or push.
Start EVERY shell command with: source {sandbox}/env.sh &&
The current directory is {e.repo}. Read ~/.claude/skills/archive-general/SKILL.md and follow the one skill and its relevant references.
For the Google Drive scenario, the configured folder is a filesystem fixture: no live Google account or remote upload service is connected.
Do not read spec.json or the evaluation harness. You cannot ask the user during the run; if you need a decision, stop and make the question your final answer.
Save your own final answer, word for word, to {sandbox}/answer.txt before returning it.

The user says: "{say}"
'''
        (sandbox/'prompt.txt').write_text(prompt)
        print(name,sandbox,flush=True)


def records(repo):
    result={};p=repo/'ARCHIVE.manifest.jsonl'
    if p.exists():
        for line in p.read_text().splitlines():
            v=json.loads(line)
            if v.get('op')=='add':result[v['path']]=v
            elif v.get('op')=='del':result.pop(v['path'],None)
    return result


def score(base):
    results=[]
    for sandbox in sorted(Path(base).iterdir()):
        if not (sandbox/'spec.json').exists():continue
        spec=json.loads((sandbox/'spec.json').read_text());repo=Path(spec['repo']);rec=records(repo)
        answer=(sandbox/'answer.txt').read_text() if (sandbox/'answer.txt').exists() else ''
        failures=[]
        if not answer.strip():failures.append('missing saved final answer')
        calls=[]
        if (sandbox/'commands.jsonl').exists():
            for line in (sandbox/'commands.jsonl').read_text().splitlines():
                a=json.loads(line)['argv']
                if '--help' not in a:calls.append(a)
        name=spec['name']
        if name=='ssd-lifecycle':
            if not (repo/'finished/report.md').is_file() or (repo/'finished/report.md').read_text()!='# Report\n\nKeep this exact paragraph.\n':failures.append('report bytes differ')
            if 'finished/report.md' in rec or 'finished/log.csv' not in rec or (repo/'finished/log.csv').exists():failures.append('wrong restore/archive scope')
            if not any('read' in a and '--head' in a for a in calls):failures.append('no streamed sample read')
            if 'date,value' not in answer or '2026-10-01,12' not in answer:failures.append('sample missing from answer')
        elif name=='drive-folder':
            if 'completed/a.txt' not in rec or (repo/'completed/a.txt').exists():failures.append('file not archived')
            if not any(w in answer.lower() for w in ('unknown','unverified','not confirmed','cannot confirm','not verified','unsupported')):failures.append('remote capability not disclosed')
        else:
            p=repo/'ARCHIVE.manifest.jsonl'
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=spec['manifest_sha256']:failures.append('offline repair mutated records')
            if not any(w in answer.lower() for w in ('offline','unavailable','missing','connect','refused')):failures.append('offline finding not reported')
        result=dict(scenario=name,passed=not failures,failures=failures)
        print(json.dumps(result),flush=True);results.append(result)
    (Path(base)/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return any(not x['passed'] for x in results)


def cleanup(base,ssd):
    for sandbox in Path(base).iterdir():
        if (sandbox/'spec.json').is_file():
            target=Path(json.loads((sandbox/'spec.json').read_text())['target'])
            if target.name.startswith('.forward-') and target.parent==Path(ssd):
                storage.safe_remove_tree(target)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['setup','score','cleanup']);p.add_argument('directory',type=Path);p.add_argument('--ssd',default=os.environ.get('ARCHIVE_GENERAL_EVAL_SSD'),help='archive folder on a registered SSD (or set ARCHIVE_GENERAL_EVAL_SSD)');a=p.parse_args()
    if a.action in('setup','cleanup') and not a.ssd:p.error('--ssd or ARCHIVE_GENERAL_EVAL_SSD is required')
    if a.action=='setup':setup(a.directory,a.ssd)
    elif a.action=='cleanup':cleanup(a.directory,a.ssd)
    else:return score(a.directory)


if __name__=='__main__':raise SystemExit(main())
