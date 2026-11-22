"""restore --into, scope remove and copy-fallback identity (3.5).

restore --into lets an archive move to a new place or target without passing through the
project: restore into a staging folder on the destination drive, then `import` it into the
new location. These tests use disposable local targets and the fake Drive wire only."""
import errno
import json
import os
from pathlib import Path

import pytest
from test_support import SKILL
from test_general_storage import GeneralEnv
from test_drive_api import Fixture, api
import storage


@pytest.fixture
def two(tmp_path):
    e = GeneralEnv(tmp_path)
    e.second = tmp_path / 'ssd'
    e.ok('target', 'add', 'ssd', '--root', e.second, '--kind', 'local')
    return e


def rows(path):
    out = {}
    if path.exists():
        for line in path.read_text().splitlines()[1:]:
            r = json.loads(line)
            if r.get('op') == 'add': out[r['path']] = r
            elif r.get('op') == 'del': out.pop(r['path'], None)
    return out


def files_under(path):
    return sorted(str(p.relative_to(path)) for p in path.rglob('*') if p.is_file() and p.name != '.DS_Store') if path.exists() else []


def test_restore_into_writes_outside_the_project_and_consumes_the_archive_copy(two):
    e = two
    p = e.write('m/sub/a.bin', b'A' * 4000); p.chmod(0o640); info = p.stat()
    e.write('m/b.txt', 'b')
    e.ok('sync', 'm')
    root = e.root
    out = e.tmp / 'staging'
    e.ok('restore', 'm', '--into', out)
    assert (out / 'm/sub/a.bin').read_bytes() == b'A' * 4000
    assert (out / 'm/sub/a.bin').stat().st_mtime_ns == info.st_mtime_ns
    assert (out / 'm/sub/a.bin').stat().st_mode & 0o777 == 0o640
    assert (out / 'm/b.txt').read_text() == 'b'
    assert not e.records() and not files_under(e.repo / 'm') and not files_under(root / 'files')
    assert '[unparked]' not in e.ok('status')
    e.ok('verify')


def test_restore_into_refuses_unsafe_destinations_without_changes(two):
    e = two
    e.write('a.txt', 'a'); e.ok('sync', 'a.txt')
    (e.tmp / 'afile').write_text('x')
    (e.tmp / 'real').mkdir(); (e.tmp / 'link').symlink_to(e.tmp / 'real')
    for bad in (e.repo / 'inside', e.base / 'x', e.second / 'x', e.tmp / 'afile', e.tmp / 'link', e.tmp / 'no/such/parent'):
        e.refused('restore', 'a.txt', '--into', bad)
    assert set(e.records()) == {'a.txt'} and not (e.repo / 'a.txt').exists()
    assert not (e.repo / 'inside').exists() and not (e.second / 'x').exists()


def test_restore_into_never_overwrites_an_existing_destination(two):
    e = two
    e.write('a.txt', 'archived'); e.ok('sync', 'a.txt')
    out = e.tmp / 'staging'; out.mkdir(); (out / 'a.txt').write_text('mine')
    e.run('restore', 'a.txt', '--into', out)
    assert (out / 'a.txt').read_text() == 'mine' and set(e.records()) == {'a.txt'}


def test_via_history_does_not_take_into(two):
    e = two
    e.write('a.txt', 'a'); e.ok('sync', 'a.txt')
    e.refused('restore', 'a.txt', '--via-history', '--into', e.tmp / 'staging')
    assert set(e.records()) == {'a.txt'}


def test_move_between_targets_and_places_through_a_staging_folder(two):
    """The full migration: parent archive (target test) and an old scope (ssd) move to a new
    scope on ssd at a new path; the old scope is retired; everything stays restorable."""
    e = two
    e.write('storage/Camera01/v1.mp4', b'1' * 3000); e.write('notes/keep.txt', 'keep')
    e.ok('sync', 'storage', 'notes/keep.txt')                      # parent on "test"
    e.write('p3/edit/trip.json', '{}'); e.write('p3/exports/final.mp4', 'final')
    e.ok('scope', 'add', 'p3', '--to', 'ssd'); e.ok('sync', 'p3/edit')
    stage = e.tmp / 'stage'; stage.mkdir()
    e.ok('restore', 'storage', '--into', stage / 'parent')
    e.ok('restore', 'p3/edit', '--into', stage / 'p3')
    assert set(e.records()) == {'notes/keep.txt'}
    assert not rows(e.repo / 'p3/ARCHIVE.manifest.jsonl')
    # lay the staged files out in the new structure, then file them into the new scope
    new = stage / 'trip-01'
    (new / 'raw').mkdir(parents=True)
    (stage / 'parent/storage/Camera01/v1.mp4').rename(new / 'raw/v1.mp4')
    (stage / 'p3/edit').rename(new / 'edit')
    (e.repo / 'japan/01').mkdir(parents=True)
    e.ok('scope', 'add', 'japan/01', '--to', 'ssd')
    e.ok('import', new, '--kind', 'mirror', cwd=e.repo / 'japan/01')
    moved = rows(e.repo / 'japan/01/ARCHIVE.manifest.jsonl')
    assert set(moved) == {'raw/v1.mp4', 'edit/trip.json'}
    assert Path(json.loads((e.repo / 'japan/01/ARCHIVE.manifest.jsonl').read_text().splitlines()[0])['root']).is_relative_to(e.second)
    assert (e.repo / '_archive/japan/01/raw').is_dir() and not (e.repo / 'japan/01/raw').exists()
    # the emptied old scope retires cleanly; its parked structure goes with it
    e.ok('scope', 'remove', 'p3')
    assert not (e.repo / 'p3/ARCHIVE.scope.json').exists() and not (e.repo / '_archive/p3').exists()
    assert (e.repo / 'p3/exports/final.mp4').read_text() == 'final'
    for where in (e.repo, e.repo / 'japan/01'):
        assert '[unparked]' not in e.ok('status', cwd=where)
        e.ok('verify', cwd=where)
    e.ok('restore', 'japan/01/raw/v1.mp4')
    assert (e.repo / 'japan/01/raw/v1.mp4').read_bytes() == b'1' * 3000


def test_scope_remove_refuses_while_anything_is_archived_or_parked(two):
    e = two
    e.write('trip/a.txt', 'a'); e.ok('scope', 'add', 'trip', '--to', 'ssd'); e.ok('sync', 'trip/a.txt')
    e.refused('scope', 'remove', 'trip')                            # index still present
    assert (e.repo / 'trip/ARCHIVE.scope.json').is_file()
    e.ok('restore', 'trip/a.txt')
    (e.repo / '_archive/trip/x').mkdir(parents=True); (e.repo / '_archive/trip/x/stray.txt').write_text('s')
    e.refused('scope', 'remove', 'trip')                            # something real in its park
    (e.repo / '_archive/trip/x/stray.txt').unlink()
    assert 'PLAN' in e.ok('scope', 'remove', 'trip', '--plan')
    assert (e.repo / 'trip/ARCHIVE.scope.json').is_file()
    e.ok('scope', 'remove', 'trip')
    assert not (e.repo / 'trip/ARCHIVE.scope.json').exists() and (e.repo / 'trip/a.txt').read_text() == 'a'
    e.refused('scope', 'remove', 'trip')                            # no longer a scope


def test_copy_fallback_publication_keeps_the_source_identity(tmp_path, monkeypatch):
    def unsupported(source, destination):
        raise OSError(errno.ENOTSUP, 'no atomic exclusive rename here')
    monkeypatch.setattr(storage, '_native_publish', unsupported)
    src = tmp_path / 'src.bin'; src.write_bytes(b'payload')
    fd = os.open(src, os.O_RDONLY)
    try:
        assert storage.publication_identity(fd, 'owner-token') == 'owner-token'
    finally:
        os.close(fd)
    dst = tmp_path / 'dst.bin'
    storage.publish(src, dst, tmp_path / 'receipts')
    assert dst.read_bytes() == b'payload' and not src.exists()
    fd = os.open(dst, os.O_RDONLY)
    try:
        assert storage.publication_identity(fd) == 'owner-token'
    finally:
        os.close(fd)


@pytest.fixture
def d(tmp_path, monkeypatch):
    return Fixture(tmp_path, monkeypatch)


def test_drive_restore_into_a_staging_folder(d):
    d.write('storage/v.mp4', 'cloud bytes'); assert d.run('sync', 'storage') == 0
    ident = d.store().records['storage/v.mp4']['drive']['objects'][0]['id']
    out = d.env.tmp / 'stage'
    assert d.run('restore', 'storage', '--into', str(out)) == 0
    assert (out / 'storage/v.mp4').read_text() == 'cloud bytes'
    assert not (d.repo / 'storage/v.mp4').exists() and not d.store().records
    assert d.wire.files[ident]['trashed']


@pytest.mark.parametrize('point', ['drive-restore-after-create', 'drive-restore-after-local-rename', 'drive-restore-after-publish', 'drive-restore-after-record'])
def test_drive_restore_into_resumes_into_the_same_folder(d, monkeypatch, point):
    d.write('a', 'original exact bytes'); assert d.run('sync', 'a') == 0
    out = d.env.tmp / 'stage'
    monkeypatch.setattr(api.os, '_exit', lambda code: (_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ARCHIVE_GENERAL_FAULT', point); monkeypatch.setenv('ICLOUD_ARCHIVE_FAULT', point)
    assert d.run('restore', 'a', '--into', str(out)) == 99
    monkeypatch.delenv('ARCHIVE_GENERAL_FAULT'); monkeypatch.delenv('ICLOUD_ARCHIVE_FAULT')
    assert d.run('verify', '--fix') == 0
    assert (out / 'a').read_text() == 'original exact bytes'
    assert not (d.repo / 'a').exists() and not d.store().records


def test_drive_restore_onto_a_filesystem_without_exclusive_rename(d, monkeypatch):
    """ExFAT (the SSD) cannot rename exclusively; the copy fallback must keep the restore's
    ownership mark or the restore refuses its own file."""
    def unsupported(source, destination):
        raise OSError(errno.ENOTSUP, 'no atomic exclusive rename here')
    monkeypatch.setattr(storage, '_native_publish', unsupported)
    d.write('x/a', 'bytes A'); d.write('b', 'bytes B'); assert d.run('sync', 'x', 'b') == 0
    out = d.env.tmp / 'stage'
    assert d.run('restore', 'x', '--into', str(out)) == 0 and (out / 'x/a').read_text() == 'bytes A'
    assert d.run('restore', 'b') == 0 and (d.repo / 'b').read_text() == 'bytes B'
    assert not d.store().records


def test_restore_into_keeps_parked_structure_that_still_has_archived_files(two):
    e = two
    e.write('m/a.txt', 'a'); e.write('m/sub/b.txt', 'b'); e.ok('sync', 'm')
    assert (e.repo / '_archive/m/sub').is_dir()
    e.ok('restore', 'm/a.txt', '--into', e.tmp / 'staging')
    assert set(e.records()) == {'m/sub/b.txt'}
    assert (e.repo / '_archive/m/sub').is_dir()
    assert '[unparked]' not in e.ok('status')
    e.ok('restore', 'm/sub/b.txt')
    assert (e.repo / 'm/sub/b.txt').read_text() == 'b'


from test_general_storage import ssd  # noqa: E402,F401  (real external drive, opt-in)


def write_csv(path, rows_):
    import csv
    with open(path, 'w', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=['path', 'archive_path', 'bytes', 'sha256', 'mode', 'mtime_ns'])
        w.writeheader(); w.writerows(rows_)


def test_import_csv_restores_original_identity_and_metadata(two, tmp_path):
    e = two
    src = tmp_path / 'stage'; src.mkdir(); f = src / 'v.mp4'; f.write_bytes(b'V' * 500); f.chmod(0o700)
    import hashlib
    good = hashlib.sha256(b'V' * 500).hexdigest()
    (e.repo / 'seg').mkdir()
    e.ok('scope', 'add', 'seg', '--to', 'ssd')
    write_csv(tmp_path / 'bad.csv', [dict(path='raw/v.mp4', archive_path=str(f), bytes=500, sha256='0' * 64, mode='640', mtime_ns=1700000000123456789)])
    e.run('import', src, '--kind', 'mirror', '--manifest', tmp_path / 'bad.csv', cwd=e.repo / 'seg')
    assert f.exists() and not rows(e.repo / 'seg/ARCHIVE.manifest.jsonl')
    write_csv(tmp_path / 'good.csv', [dict(path='raw/v.mp4', archive_path=str(f), bytes=500, sha256=good, mode='640', mtime_ns=1700000000123456789)])
    e.ok('import', src, '--kind', 'mirror', '--manifest', tmp_path / 'good.csv', cwd=e.repo / 'seg')
    r = rows(e.repo / 'seg/ARCHIVE.manifest.jsonl')['raw/v.mp4']
    assert (r['mode'], r['mtime_ns'], r['sha256']) == (0o640, 1700000000123456789, good)
    e.ok('restore', 'seg/raw/v.mp4')
    q = e.repo / 'seg/raw/v.mp4'
    assert q.stat().st_mode & 0o777 == 0o640 and q.stat().st_mtime_ns == 1700000000123456789


def test_ssd_move_through_staging_on_exfat(ssd):
    """Real-drive rehearsal of the migration: restore --into a staging folder on the SSD, then
    import it into a new scope on the same SSD with a CSV built from the old index (the new
    paths plus each file's original SHA-256, mode and mtime). ExFAT has no exclusive rename and
    no Unix modes, so this takes the verified-copy path and needs the CSV metadata."""
    e = ssd
    stage = e.base.parent / 'stage'; stage.mkdir()
    data = os.urandom(300000)
    p = e.write('storage/Camera01/v.mp4', data); p.chmod(0o640)
    e.write('edit/trip.json', '{"a": 1}')
    e.age_folders()
    e.ok('sync', 'storage', 'edit')
    old = e.records()
    e.ok('restore', 'storage', 'edit', '--into', stage / 'old')
    assert not e.records()
    mapping = {'storage/Camera01/v.mp4': 'raw/v.mp4', 'edit/trip.json': 'edit/trip.json'}
    write_csv(stage / 'move.csv', [dict(path=new, archive_path=str(stage / 'old' / rel), bytes=old[rel]['size'], sha256=old[rel]['sha256'],
                                        mode=format(old[rel]['mode'], 'o'), mtime_ns=old[rel]['mtime_ns']) for rel, new in mapping.items()])
    e.write('notes.txt', 'n'); e.ok('sync', 'notes.txt')
    (e.repo / 'japan/01').mkdir(parents=True)
    e.ok('target', 'add', 'ssd2', '--root', e.base.parent / 'archive2', '--kind', 'local')
    e.ok('scope', 'add', 'japan/01', '--to', 'ssd2')
    e.ok('import', stage / 'old', '--kind', 'mirror', '--manifest', stage / 'move.csv', cwd=e.repo / 'japan/01')
    moved = rows(e.repo / 'japan/01/ARCHIVE.manifest.jsonl')
    assert set(moved) == {'raw/v.mp4', 'edit/trip.json'}
    assert all((moved[new]['sha256'], moved[new]['mode'], moved[new]['mtime_ns']) == (old[rel]['sha256'], old[rel]['mode'], old[rel]['mtime_ns']) for rel, new in mapping.items())
    e.ok('verify', cwd=e.repo / 'japan/01')
    e.ok('restore', 'japan/01/raw/v.mp4')
    q = e.repo / 'japan/01/raw/v.mp4'
    assert q.read_bytes() == data and q.stat().st_mode & 0o777 == 0o640 and q.stat().st_mtime_ns == old['storage/Camera01/v.mp4']['mtime_ns']
