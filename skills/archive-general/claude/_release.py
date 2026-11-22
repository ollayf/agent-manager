#!/usr/bin/env python3
"""Freeze the complete runtime; existing release bytes are immutable."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import sys

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL))
import storage
NAMES = ('archive.py','storage.py','drive_api.py','drive_archive.py','icloud_status.swift','SKILL.md')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def history():
    return SKILL/'.history' if (SKILL/'.history').exists() else SKILL/'history'


def validate(folder):
    index=json.loads((folder/'INDEX.json').read_text())
    dirs={p.name for p in folder.iterdir() if p.is_dir() and re.fullmatch(r'\d+\.\d+\.\d+',p.name)}
    if dirs != set(index):raise ValueError('INDEX keys differ from frozen folders')
    for version,meta in index.items():
        release=folder/version
        sums={name.strip():digest for digest,name in (line.split(None,1) for line in (release/'SHA256SUMS').read_text().splitlines())}
        expected=set(meta.get('runtime_files',('icloud_archive.py','SKILL.md')))
        if set(sums)!=expected:raise ValueError('SHA256SUMS does not cover the complete runtime: '+version)
        for name,expected_sha in sums.items():
            if Path(name).name!=name or (release/name).is_symlink() or sha(release/name)!=expected_sha:
                raise ValueError('SHA-256 mismatch: '+str(release/name))
    return index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--summary',default='Archive General: registered filesystem targets, pinned SSD identity, generic indexes, checked ExFAT/cross-device publication and one consolidated skill.')
    args=parser.parse_args()
    folder=history()
    if args.check:
        print('verified '+str(len(validate(folder)))+' immutable releases');return
    version=re.search(r'^SKILL_VERSION = "([^"]+)"',(SKILL/'archive.py').read_text(),re.M).group(1)
    if not re.search(r'^\s*version: '+re.escape(version)+r'$',(SKILL/'SKILL.md').read_text(),re.M):raise ValueError('skill/engine versions disagree')
    folder.mkdir(parents=True,exist_ok=True)
    index=json.loads((folder/'INDEX.json').read_text()) if (folder/'INDEX.json').exists() else {}
    target=folder/version
    if target.exists():
        if any(sha(target/name)!=sha(SKILL/name) for name in NAMES):raise ValueError('refusing to rewrite an existing immutable release')
    else:
        stage=Path(tempfile.mkdtemp(prefix='.release-',dir=folder))
        for name in NAMES:shutil.copy2(SKILL/name,stage/name)
        (stage/'SHA256SUMS').write_text(''.join(sha(stage/name)+'  '+name+'\n' for name in NAMES))
        for p in stage.iterdir():
            with p.open('rb') as stream:
                import os
                os.fsync(stream.fileno())
        storage.fsync_dir(stage)
        stage.rename(target);storage.fsync_dir(folder)
    index.setdefault(version,dict(date=datetime.date.today().isoformat(),writes=[2,3],reads=[1,2,3],layouts=['in-place','parked'],runtime_files=list(NAMES),summary=args.summary))
    storage.atomic_json(folder/'INDEX.json',index)
    validate(folder);print('frozen '+version+' with complete runtime')


if __name__=='__main__':main()
