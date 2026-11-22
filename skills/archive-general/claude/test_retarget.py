"""Whole-project Drive -> SSD moves, without changing any project-relative path."""
import copy
import csv
import json
import os
from pathlib import Path
import tempfile

import pytest

from test_drive_api import d, archive
import storage


def prepare(d, root=None):
    root = root or d.env.tmp / 'ssd'
    assert d.run('target', 'add', 'ssd', '--root', root, '--kind', 'local') == 0
    p = d.write('media/sub/original.bin', b'original bytes' * 2000)
    p.chmod(0o640)
    assert d.run('sync', 'media') == 0
    source = copy.deepcopy(d.store().records['media/sub/original.bin'])
    stage = root.parent / 'staging'
    assert d.run('restore', 'media', '--into', stage) == 0
    return root, stage, source


def test_retarget_plan_and_whole_project_move_preserve_paths_and_metadata(d):
    root, stage, record = prepare(d)
    old = d.manifest()
    old_index = (d.repo / 'ARCHIVE.md').read_bytes()
    config = storage.load_config()
    assert d.run('retarget', 'ssd', '--plan') == 0
    assert d.manifest() == old and (d.repo / 'ARCHIVE.md').read_bytes() == old_index
    assert not (d.repo / 'ARCHIVE.retarget.json').exists()
    assert d.run('retarget', 'ssd') == 0
    header = json.loads(d.manifest().splitlines()[0])
    assert header['archive_target']['name'] == 'ssd'
    assert header['icloud_archive_manifest'] == 2
    assert storage.load_config() == config  # especially the machine's default
    move = stage.parent / 'move.csv'
    with move.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'archive_path', 'bytes', 'sha256', 'mode', 'mtime_ns'])
        writer.writeheader()
        writer.writerow(dict(path=record['path'], archive_path=str(stage / record['path']),
                             bytes=record['size'], sha256=record['sha256'], mode=format(record['mode'], 'o'),
                             mtime_ns=record['mtime_ns']))
    assert d.run('import', stage, '--kind', 'mirror', '--manifest', move, '--plan') == 0
    assert d.run('import', stage, '--kind', 'mirror', '--manifest', move) == 0
    a = d.core.parse_args(['--repo', str(d.repo), 'verify'])
    d.core.configure_session(a, d.repo)
    store = d.core.Store(d.repo)
    assert set(store.records) == {record['path']}
    moved = store.records[record['path']]
    assert all(moved[k] == record[k] for k in ('path', 'size', 'sha256', 'mode', 'mtime_ns'))
    assert store.root.is_relative_to(root)
    assert store.location(moved).read_bytes() == b'original bytes' * 2000
    assert not (d.repo / record['path']).exists()
    assert d.run('verify') == 0
    assert d.run('restore', record['path']) == 0
    assert (d.repo / record['path']).read_bytes() == b'original bytes' * 2000


def test_retarget_refuses_nonempty_cloud_project(d):
    d.write('a', 'original')
    assert d.run('sync', 'a') == 0
    assert d.run('target', 'add', 'ssd', '--root', d.env.tmp / 'ssd') == 0
    before = d.manifest()
    assert d.run('retarget', 'ssd') == 1
    assert d.manifest() == before and set(d.store().records) == {'a'}


@pytest.mark.parametrize('unsafe', ['allocated', 'container', 'restore', 'missing-original', 'old-version', 'wrong-target'])
def test_retarget_never_discards_started_or_unsafe_operations(d, unsafe):
    prepare(d)
    local = d.write('pending', b'pending')
    store = d.store()
    op = dict(target=store.target.value['id'], action='archive', phase='prepared', objects=[], old=None, record={'path': 'pending'})
    if unsafe == 'allocated': op['objects'] = [{'id': 'already-allocated'}]
    if unsafe == 'container': op['container'] = {'id': 'already-allocated-folder'}
    if unsafe == 'restore': op['action'] = 'restore'
    if unsafe == 'missing-original': local.unlink()
    if unsafe == 'old-version': op['old'] = {'path': 'previous'}
    if unsafe == 'wrong-target': op['target'] = 'another-target'
    path = store.journal_path('pending')
    archive.op_save(path, op)
    before = d.manifest()
    assert d.run('retarget', 'ssd', '--cancel-unstarted') == 1
    assert d.manifest() == before and path.exists()


def test_retarget_can_cancel_only_an_explicitly_selected_unstarted_intent(d):
    prepare(d)
    local = d.write('pending', b'pending original')
    store = d.store()
    path = store.journal_path('pending')
    archive.op_save(path, dict(target=store.target.value['id'], action='archive', phase='prepared', objects=[], old=None, record={'path': 'pending'}))
    assert d.run('retarget', 'ssd') == 1 and path.exists()
    assert d.run('retarget', 'ssd', '--plan', '--cancel-unstarted') == 0 and path.exists()
    assert d.run('retarget', 'ssd', '--cancel-unstarted') == 0
    assert not path.exists() and local.read_bytes() == b'pending original'


@pytest.mark.parametrize('point', ['retarget-after-journal', 'retarget-after-ARCHIVE.manifest.jsonl', 'retarget-after-ARCHIVE.md'])
def test_retarget_interruption_recovers_before_using_either_index(d, monkeypatch, point):
    prepare(d)
    def crash(step):
        if step == point: raise RuntimeError('simulated power loss')
    monkeypatch.setattr(d.core, 'fault', crash)
    with pytest.raises(RuntimeError): d.run('retarget', 'ssd')
    assert (d.repo / 'ARCHIVE.retarget.json').exists()
    before = d.manifest()
    assert d.run('retarget', 'ssd', '--plan') == 1 and d.manifest() == before
    monkeypatch.setattr(d.core, 'fault', lambda step: None)
    assert d.run('status') == 0
    assert not (d.repo / 'ARCHIVE.retarget.json').exists()
    assert json.loads(d.manifest().splitlines()[0])['archive_target']['name'] == 'ssd'


def test_retarget_refuses_occupied_destination_and_wrong_ssd_marker(d):
    root, _, _ = prepare(d)
    before = d.manifest()
    rel = Path('_abs') / str(d.repo).lstrip('/')
    destination = root / 'repos' / rel
    destination.mkdir(parents=True)
    (destination / 'unknown').write_text('keep')
    assert d.run('retarget', 'ssd') == 1 and d.manifest() == before
    (destination / 'unknown').unlink()
    (root / '.archive-general-target.json').write_text('{}')
    assert d.run('retarget', 'ssd') == 1 and d.manifest() == before


def test_retarget_recovery_refuses_changed_cloud_or_local_indexes(d, monkeypatch):
    prepare(d)
    def crash(step):
        if step == 'retarget-after-journal': raise RuntimeError('power loss')
    monkeypatch.setattr(d.core, 'fault', crash)
    with pytest.raises(RuntimeError): d.run('retarget', 'ssd')
    monkeypatch.setattr(d.core, 'fault', lambda step: None)
    p = d.repo / 'ARCHIVE.md'
    p.write_text(p.read_text() + '\nexternal edit\n')
    before = d.manifest()
    assert d.run('status') == 1 and d.manifest() == before
    assert (d.repo / 'ARCHIVE.retarget.json').exists()


def test_retarget_recovery_refuses_changed_cloud_manifest(d, monkeypatch):
    prepare(d)
    store = d.store()
    def crash(step):
        if step == 'retarget-after-journal': raise RuntimeError('power loss')
    monkeypatch.setattr(d.core, 'fault', crash)
    with pytest.raises(RuntimeError): d.run('retarget', 'ssd')
    monkeypatch.setattr(d.core, 'fault', lambda step: None)
    d.wire.files[store.mirror_id]['data'] += b'\n'
    before = d.manifest()
    assert d.run('status') == 1 and d.manifest() == before
    assert (d.repo / 'ARCHIVE.retarget.json').exists()


def test_retarget_on_real_ssd_uses_only_an_owned_disposable_folder(d):
    parent = os.environ.get('ARCHIVE_GENERAL_TEST_SSD')
    if not parent: pytest.skip('set ARCHIVE_GENERAL_TEST_SSD for disposable SSD rehearsal')
    parent = Path(parent).resolve()
    if not parent.is_dir() or not os.path.ismount(parent.parent): pytest.skip('SSD is offline')
    with tempfile.TemporaryDirectory(prefix='.retarget-test-', dir=parent) as owned:
        root, stage, record = prepare(d, Path(owned) / 'archive')
        assert d.run('retarget', 'ssd', '--plan') == 0
        assert d.run('retarget', 'ssd') == 0
        assert d.run('import', stage, '--kind', 'mirror') == 0
        assert d.run('verify') == 0
        assert d.run('restore', record['path']) == 0
        assert (d.repo / record['path']).read_bytes() == b'original bytes' * 2000
