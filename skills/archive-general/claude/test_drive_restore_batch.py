"""A batch never retires cloud bytes before checked staging copies and durable maps."""
import copy
import os
from pathlib import Path
import tempfile

import pytest
from test_drive_api import d


def seed(d, count=7):
    expected={}
    for i in range(count):
        path='media/sub/file-'+str(i)+'.bin';data=bytes([i])*int(10000+i)
        d.write(path,data);expected[path]=data
    assert d.run('sync','media')==0
    return expected,copy.deepcopy(d.store().records)


def test_parallel_staging_restore_checks_every_file_and_consumes_only_its_archive(d):
    expected,records=seed(d)
    out=d.env.tmp/'staging'
    assert d.run('restore','media','--into',out,'--batch-size','3','--jobs','2')==0
    assert d.core.TARGET is not None and d.core.TARGET.kind=='google-drive-api'
    assert not d.store().records and not d.store().pending()
    for rel,data in expected.items():
        assert (out/rel).read_bytes()==data and not (d.repo/rel).exists()
        assert d.wire.files[records[rel]['drive']['objects'][0]['id']]['trashed']


def test_bad_download_keeps_the_entire_uncommitted_batch_in_drive(d):
    expected,records=seed(d,3);out=d.env.tmp/'staging'
    bad=next(iter(records.values()))['drive']['objects'][0]['id']
    d.wire.download_override=lambda ident,data:b'corrupt' if ident==bad else data
    assert d.run('restore','media','--into',out,'--batch-size','3','--jobs','2')==1
    assert set(d.store().records)==set(records)
    assert all(not d.wire.files[r['drive']['objects'][0]['id']]['trashed'] for r in records.values())
    d.wire.download_override=None
    assert d.run('restore','media','--into',out,'--batch-size','3','--jobs','2')==0
    assert all((out/rel).read_bytes()==data for rel,data in expected.items())


def test_batch_interruption_after_cloud_map_commit_resumes_every_journal(d,monkeypatch):
    expected,records=seed(d,3);out=d.env.tmp/'staging'
    def crash(step):
        if step=='drive-restore-batch-after-record':raise RuntimeError('power loss')
    monkeypatch.setattr(d.core,'fault',crash)
    with pytest.raises(RuntimeError):d.run('restore','media','--into',out,'--batch-size','3','--jobs','2')
    assert not d.store().records and len(d.store().pending())==3
    assert all(not d.wire.files[r['drive']['objects'][0]['id']]['trashed'] for r in records.values())
    monkeypatch.setattr(d.core,'fault',lambda step:None)
    assert d.run('restore',*records,'--into',out,'--batch-size','3','--jobs','2')==0
    assert not d.store().pending()
    assert all((out/rel).read_bytes()==data for rel,data in expected.items())


def test_local_change_after_preparation_keeps_cloud_maps_and_objects(d,monkeypatch):
    _,records=seed(d,3);out=d.env.tmp/'staging';original=d.core.fault
    import drive_archive
    restore=drive_archive.restore_one;calls={}
    def changed(store,rel,into=None,defer=False):
        value=restore(store,rel,into,defer)
        if defer:
            calls[rel]=calls.get(rel,0)+1
            if calls[rel]==1:(out/rel).write_bytes(b'external edit')
        return value
    monkeypatch.setattr(drive_archive,'restore_one',changed)
    assert d.run('restore','media','--into',out,'--batch-size','3','--jobs','2')==1
    assert set(d.store().records)==set(records)
    assert all(not d.wire.files[r['drive']['objects'][0]['id']]['trashed'] for r in records.values())


@pytest.mark.parametrize('args',[['--batch-size','0'],['--batch-size','33'],['--batch-size','2','--jobs','3'],['--batch-size','2']])
def test_unsafe_parallel_restore_options_never_change_cloud_records(d,args):
    _,records=seed(d,2)
    assert d.run('restore','media',*args)==1
    assert set(d.store().records)==set(records)


def test_batched_restore_to_real_ssd_uses_owned_disposable_staging(d):
    parent=os.environ.get('ARCHIVE_GENERAL_TEST_SSD')
    if not parent:pytest.skip('set ARCHIVE_GENERAL_TEST_SSD for disposable SSD rehearsal')
    parent=Path(parent).resolve()
    if not parent.is_dir() or not os.path.ismount(parent.parent):pytest.skip('SSD is offline')
    expected,records=seed(d,7)
    with tempfile.TemporaryDirectory(prefix='.batch-restore-test-',dir=parent) as owned:
        stage=Path(owned)/'staging'
        assert d.run('restore','media','--into',stage,'--batch-size','4','--jobs','3')==0
        assert all((stage/rel).read_bytes()==data for rel,data in expected.items())
        assert all(d.wire.files[r['drive']['objects'][0]['id']]['trashed'] for r in records.values())
        assert not d.store().pending()
