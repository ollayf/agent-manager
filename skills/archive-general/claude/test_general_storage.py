"""General-target regressions, with explicit opt-in disposable SSD integration."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import pytest
from test_support import Env, SCRIPT, SKILL, mirror, split, literal_v1

sys.path.insert(0, str(SKILL))
import storage


class GeneralEnv(Env):
    def __init__(self, tmp_path, root=None, kind='local'):
        super().__init__(tmp_path)
        self.env.pop('ICLOUD_ARCHIVE_ROOT')
        self.base = root or self.tmp / 'target'
        self.env['ARCHIVE_GENERAL_CONFIG'] = str(self.tmp / 'targets.json')
        self.ok('target', 'add', 'test', '--root', self.base, '--kind', kind, '--default')

    def records(self):
        path = self.repo / 'ARCHIVE.manifest.jsonl'
        if not path.exists():
            return super().records()
        result = {}
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get('op') == 'add':result[row['path']] = row
            elif row.get('op') == 'del':result.pop(row['path'],None)
        return result

    @property
    def root(self):
        path = self.repo / 'ARCHIVE.manifest.jsonl'
        if path.exists():return Path(json.loads(path.read_text().splitlines()[0])['root']).expanduser()
        return super().root


@pytest.fixture(params=['local', 'google-drive'])
def g(tmp_path, request):
    return GeneralEnv(tmp_path, kind=request.param)


@pytest.fixture
def ssd(tmp_path):
    value = os.environ.get('ARCHIVE_GENERAL_TEST_SSD')
    if not value:pytest.skip('set ARCHIVE_GENERAL_TEST_SSD for explicitly authorized disposable external-drive integration')
    parent = Path(value).resolve()
    if not parent.is_dir() or not os.path.ismount(parent.parents[0]):
        pytest.skip('requested SSD archive root is offline/unavailable; no fallback directory created')
    owned = Path(tempfile.mkdtemp(prefix='.archive-general-test-', dir=parent))
    env = GeneralEnv(tmp_path, root=owned / 'archive')
    try:yield env
    finally:storage.safe_remove_tree(owned)


def assert_clean_roundtrip(e, paths):
    expected={p:(e.repo/p).read_bytes() for p in paths}
    metadata={p:((e.repo/p).stat().st_mtime_ns,(e.repo/p).stat().st_mode & 0o777) for p in paths}
    e.age_folders()
    e.ok('sync', *paths)
    assert set(e.records()) == set(paths)
    for p,data in expected.items():
        assert not (e.repo/p).exists()
        assert (e.root/'files'/p).read_bytes() == data
        assert str(e.root/'files'/p) in e.ok('read', p)
    e.ok('status', '--deep'); e.ok('verify')
    e.ok('restore', *paths)
    assert not e.records()
    for p,data in expected.items():
        assert (e.repo/p).read_bytes()==data
        assert ((e.repo/p).stat().st_mtime_ns,(e.repo/p).stat().st_mode & 0o777)==metadata[p]


def test_generic_raw_lifecycle(g):
    for p,data in [('data/a',b'zero\0one'),('data/empty',b''),('nested/café/space | file.txt','text')]:g.write(p,data).chmod(0o640)
    assert_clean_roundtrip(g,['data/a','data/empty','nested/café/space | file.txt'])
    assert not (g.repo/'ICLOUD.md').exists()


def test_generic_target_descriptor_and_index(g):
    g.write('a','a');g.ok('sync','a')
    header=json.loads((g.repo/'ARCHIVE.manifest.jsonl').read_text().splitlines()[0])
    assert header['archive_target']['kind'] in ('local','google-drive')
    assert header['archive_target']['id']==json.loads((g.base/storage.MARKER).read_text())['id']
    visible='\n'.join(line for line in (g.repo/'ARCHIVE.md').read_text().splitlines() if not line.startswith('<!--'))
    assert 'ICLOUD.manifest.jsonl' not in visible
    assert g.ok('target','doctor','test')
    config=json.loads(Path(g.env['ARCHIVE_GENERAL_CONFIG']).read_text())
    marker=json.loads((g.base/storage.MARKER).read_text())
    assert config['by']==marker['by']==header['by']==storage.SKILL_VERSION


def test_default_target_change_does_not_redirect_bound_project(g):
    g.write('a','a');g.ok('sync','a');original=g.root
    other=g.tmp/'other'
    g.ok('target','add','other','--root',other,'--kind','local','--default')
    g.write('b','b');g.ok('sync','b')
    assert g.root==original and (original/'files/b').read_text()=='b'
    assert not list(other.glob('repos/**/*'))
    g.write('c','c')
    assert 'different archive target' in g.refused('--target','other','sync','c')
    assert (g.repo/'c').read_text()=='c'


@pytest.mark.parametrize('command',[['sync','new'],['restore','a'],['verify','--fix'],['status','--deep'],['read','a'],['upgrade']])
def test_offline_target_refuses_without_record_changes(g,command):
    g.write('a','a');g.ok('sync','a');g.write('new','new')
    manifest=(g.repo/'ARCHIVE.manifest.jsonl').read_bytes()
    offline=g.base.with_name('offline-root')
    os.rename(g.base,offline)
    try:
        assert 'offline' in g.refused(*command)
        assert (g.repo/'ARCHIVE.manifest.jsonl').read_bytes()==manifest
        assert (g.repo/'new').read_text()=='new'
        assert not g.base.exists()
    finally:os.rename(offline,g.base)


@pytest.mark.parametrize('change',['missing','wrong-id','symlink'])
def test_wrong_marker_refuses_verification_and_preserves_data(g,change):
    g.write('a','a');g.ok('sync','a');manifest=(g.repo/'ARCHIVE.manifest.jsonl').read_bytes()
    marker=g.base/storage.MARKER; original=marker.read_bytes(); marker.unlink()
    if change=='wrong-id':marker.write_text(json.dumps(dict(format=1,id='different',kind='local')))
    if change=='symlink':marker.symlink_to(g.tmp/'not-a-marker')
    try:
        g.refused('verify','--fix')
        assert (g.repo/'ARCHIVE.manifest.jsonl').read_bytes()==manifest
    finally:
        marker.unlink(missing_ok=True);marker.write_bytes(original)
    g.ok('restore','a');assert (g.repo/'a').read_text()=='a'


def test_nested_target_and_project_refuse(g):
    nested=g.base/'nested-project';nested.mkdir();(nested/'CLAUDE.md').write_text('project')
    (nested/'a').write_text('keep')
    assert 'contain one another' in g.refused('--repo',nested,'sync','a',cwd=nested)
    assert (nested/'a').read_text()=='keep'


def test_google_capabilities_do_not_claim_upload_or_eviction(tmp_path):
    e=GeneralEnv(tmp_path,kind='google-drive');e.write('a','a')
    summary=e.ok('sync','a')
    assert 'UNKNOWN' in summary and 'unsupported' in summary
    for command in ('upload-status','evict'):
        result=e.run(command)
        assert result.returncode==2 and 'unsupported' in result.stdout
    e.ok('restore','a')


def test_native_icloud_path_is_required(tmp_path):
    e=Env(tmp_path);e.env['ARCHIVE_GENERAL_CONFIG']=str(e.tmp/'cfg')
    assert 'actual iCloud Drive' in e.refused('target','add','fake','--root',e.tmp/'fake','--kind','icloud')
    assert not (e.tmp/'fake').exists()


def test_unmarked_nonempty_target_is_not_taken_over(tmp_path):
    e=Env(tmp_path);e.env['ARCHIVE_GENERAL_CONFIG']=str(e.tmp/'cfg')
    root=e.tmp/'archive-with-user-files';root.mkdir();(root/'keep').write_text('user bytes')
    e.refused('target','add','bad','--root',root,'--kind','local')
    assert (root/'keep').read_text()=='user bytes' and not (root/storage.MARKER).exists()


def test_atomic_publication_never_overwrites(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.write_bytes(b'one');b.write_bytes(b'two')
    with pytest.raises(FileExistsError):storage.publish(a,b)
    assert a.read_bytes()==b'one' and b.read_bytes()==b'two'


def unsupported(*args,**kwargs):
    import errno
    raise OSError(errno.EOPNOTSUPP,'test filesystem lacks atomic publication')


@pytest.mark.parametrize('directory',[False,True])
def test_fallback_publication_hashes_and_removes_only_verified_source(tmp_path,monkeypatch,directory):
    monkeypatch.setattr(storage,'_native_publish',unsupported)
    a=tmp_path/'source';b=tmp_path/'dest'
    if directory:(a/'empty').mkdir(parents=True);(a/'data').write_bytes(os.urandom(100000))
    else:a.write_bytes(os.urandom(100000))
    expected=storage.fingerprint(a)
    storage.publish(a,b)
    assert not a.exists() and storage.fingerprint(b)==expected
    assert not list((tmp_path/'.publications').glob('*.json'))


def test_fallback_collision_never_erases_preexisting_file(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'_native_publish',unsupported)
    a=tmp_path/'source';b=tmp_path/'dest';a.write_text('one');b.write_text('two')
    with pytest.raises(FileExistsError):storage.publish(a,b)
    assert a.read_text()=='one' and b.read_text()=='two'


def test_publication_repair_does_not_remove_a_replacement_inode(tmp_path):
    source=tmp_path/'source';dest=tmp_path/'dest';source.write_text('source');dest.write_text('someone else')
    home=tmp_path/'.publications';home.mkdir();receipt=home/'r.json'
    value=dict(format=1,source=str(source),destination=str(dest),expected=storage.fingerprint(source),inode=0,device=0,phase='created')
    receipt.write_text(json.dumps(value))
    with pytest.raises(storage.TargetError):storage.repair_publication(receipt,value)
    assert dest.read_text()=='someone else' and source.read_text()=='source'


def test_fake_appledouble_user_file_is_preserved(g):
    g.write('data/a','a');g.write('data/._a','ordinary user file, not AppleDouble')
    summary=g.ok('sync','data')
    assert 'reserved ._' in summary
    assert not g.records()
    assert (g.repo/'data/a').read_text()=='a'
    assert (g.repo/'data/._a').read_text()=='ordinary user file, not AppleDouble'


def test_true_appledouble_is_metadata_only(tmp_path):
    (tmp_path/'a').write_bytes(b'file');(tmp_path/'._a').write_bytes(b'\0\x05\x16\x07metadata')
    assert storage.apple_double(tmp_path/'._a')
    (tmp_path/'a').unlink()
    assert not storage.apple_double(tmp_path/'._a')


def test_wrong_external_uuid_is_refused_without_any_write(tmp_path,monkeypatch):
    root=tmp_path/'target';root.mkdir();value=dict(name='external',id='test-id',kind='local',root=str(root),mount_point=str(tmp_path),volume_uuid='expected')
    (root/storage.MARKER).write_text(json.dumps(dict(format=1,id='test-id',kind='local')))
    monkeypatch.setattr(storage.os.path,'ismount',lambda p:True)
    monkeypatch.setattr(storage,'volume_uuid',lambda p:'different')
    before=(root/storage.MARKER).read_bytes()
    with pytest.raises(storage.TargetError,match='wrong volume UUID'):storage.Target(value).available()
    assert (root/storage.MARKER).read_bytes()==before


def test_archive_storage_symlink_is_refused(g):
    g.write('a','a');g.ok('sync','a');g.write('new','new')
    outside=g.tmp/'outside';outside.mkdir();(outside/'note').write_text('outside')
    (g.root/'files/unsafe').symlink_to(outside,target_is_directory=True)
    g.write('unsafe/b','b')
    g.refused('sync','unsafe')
    assert (g.repo/'unsafe/b').read_text()=='b' and (outside/'note').read_text()=='outside'


def test_ssd_raw_metadata_unicode_empty_and_large_roundtrip(ssd):
    e=ssd
    for p,data in [('data/zero',b''),('data/café | name',b'utf8 bytes\0'),('large/random.bin',os.urandom(2*1024**2))]:e.write(p,data).chmod(0o640)
    e.env['ICLOUD_ARCHIVE_FILE_LIMIT']='0'
    assert_clean_roundtrip(e,['data/zero','data/café | name','large/random.bin'])


def test_ssd_packed_read_update_versions_and_scoped_restore(ssd):
    e=ssd;data=(b'header,value\n'+b'data,123\n'*20000)
    e.write('m/a.csv',data);e.write('m/b','b');e.ok('sync','m','--pack','--fast')
    assert e.records()['m/a.csv']['form'].startswith('zst')
    assert 'header,value' in e.ok('read','--head','2','m/a.csv')
    e.write('m/a.csv',b'updated\n');e.ok('sync','m/a.csv')
    assert (e.repo/'m/a.csv').read_bytes()==b'updated\n'
    e.ok('sync','m/a.csv','--update')
    assert list((e.root/'.versions/m/a.csv').iterdir())
    e.ok('verify');e.ok('restore','m/a.csv')
    assert (e.repo/'m/a.csv').read_bytes()==b'updated\n' and 'm/b' in e.records()
    e.ok('restore','m/b');e.ok('verify')


def test_ssd_mirror_import_across_filesystems_and_original_metadata(ssd):
    e=ssd;folder,csv,rows=mirror(e)
    p=folder/'data/a.csv';p.chmod(0o751);stamp=time.time_ns()-2*3600*10**9;os.utime(p,ns=(stamp,stamp))
    e.ok('import',folder,'--kind','mirror','--manifest',csv,'--plan')
    assert p.exists()
    e.ok('import',folder,'--kind','mirror','--manifest',csv)
    e.ok('verify');e.ok('restore','data')
    assert (e.repo/'data/a.csv').read_bytes()==b'a\n'
    assert (e.repo/'data/a.csv').stat().st_mtime_ns==stamp
    assert (e.repo/'data/a.csv').stat().st_mode & 0o777==0o751


def test_ssd_split_import_across_filesystems(ssd):
    e=ssd;folder,data=split(e)
    e.ok('import',folder,'--kind','split','--plan')
    e.ok('import',folder,'--kind','split')
    e.ok('status','--deep');e.ok('verify');e.ok('restore','data/trace.db')
    assert (e.repo/'data/trace.db').read_bytes()==data


@pytest.mark.parametrize('point',['after-copy','after-rename','after-index','after-delete'])
def test_ssd_archive_crashes_preserve_data_and_converge(ssd,point):
    e=ssd;data=os.urandom(10000);e.write('m/a',data)
    assert e.run('sync','m',overrides={'ICLOUD_ARCHIVE_FAULT':point}).returncode==99
    e.ok('verify','--fix')
    e.ok('sync','m')
    e.ok('verify');e.ok('restore','m/a')
    assert (e.repo/'m/a').read_bytes()==data


@pytest.mark.parametrize('point',['publish-after-create','publish-after-copy'])
def test_ssd_publication_crash_preserves_source_and_repairs(ssd,point):
    e=ssd;data=os.urandom(10000);e.write('m/a',data)
    result=e.run('sync','m',overrides={'ARCHIVE_GENERAL_FAULT':point})
    assert result.returncode==99,result.stdout+result.stderr
    assert (e.repo/'m/a').read_bytes()==data
    assert list((e.base/'.publications').glob('*.json'))
    e.ok('verify','--fix')
    e.ok('sync','m');e.ok('verify');e.ok('restore','m/a')
    assert (e.repo/'m/a').read_bytes()==data


def test_ssd_corrupt_copy_refuses_restore_and_preserves_local_work(ssd):
    e=ssd;data=b'exact original bytes';e.write('a',data);e.ok('sync','a')
    cloud=e.root/'files/a';cloud.write_bytes(b'corrupt payload')
    e.refused('restore','a');assert not (e.repo/'a').exists()
    e.write('a','new local work');e.refused('restore','a');assert (e.repo/'a').read_text()=='new local work'
    (e.repo/'a').unlink();cloud.write_bytes(data);e.ok('restore','a');assert (e.repo/'a').read_bytes()==data


def test_ssd_legacy_upgrade_on_exfat(ssd):
    e=ssd;origin,data=literal_v1(e,'dir','old')
    (e.repo/'ICLOUD.md').replace(e.repo/'ARCHIVE.md')
    # An old root on this registered target is adopted without changing providers.
    e.ok('upgrade','--plan');e.ok('upgrade');e.ok('verify')
    e.ok('restore','old');assert (e.repo/'old/sub/a').read_bytes()==data


def test_ssd_parallel_archives_do_not_lose_records(ssd):
    from concurrent.futures import ThreadPoolExecutor
    e=ssd
    for n in range(8):e.write('batch/'+str(n),('data-'+str(n)).encode())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda n:e.run('sync','batch/'+str(n)),range(8)))
    assert all(r.returncode==0 for r in results),[(r.stdout,r.stderr) for r in results if r.returncode]
    assert len(e.records())==8
    e.ok('verify');e.ok('restore','batch')
    for n in range(8):assert (e.repo/'batch'/str(n)).read_text()=='data-'+str(n)


def test_registered_file_operation_fails_closed_when_lsof_is_missing(g):
    g.write('data/a','keep this')
    result=g.refused('sync','data',overrides={'ICLOUD_ARCHIVE_LSOF':str(g.tmp/'not-an-lsof')})
    assert 'cannot confirm whether files are open' in result
    assert (g.repo/'data/a').read_text()=='keep this' and not g.records()


def test_registry_scan_and_upgrade_all_find_generic_indexes(g):
    g.write('a','a');g.ok('sync','a')
    assert 'registered' in g.ok('registry','--scan',g.repo)
    plan=g.ok('upgrade','--all','--plan')
    assert 'not on this Mac' not in plan
    g.ok('upgrade','--all');g.ok('verify')
    assert '[unregistered] .publications' not in g.ok('registry')


def test_absolute_read_selects_nondefault_registered_target(g):
    g.write('a','a');g.ok('sync','a');archive=g.root/'files/a'
    g.ok('target','add','other','--root',g.tmp/'another','--kind','local','--default')
    assert str(archive) in g.ok('read',archive)


def test_publication_nonce_rejects_reused_inode(tmp_path):
    source=tmp_path/'source';dest=tmp_path/'dest';source.write_text('original');dest.write_text('replacement')
    info=dest.stat();home=tmp_path/'.publications';home.mkdir();receipt=home/'r.json'
    value=dict(format=1,source=str(source),destination=str(dest),expected=storage.fingerprint(source),inode=info.st_ino,device=info.st_dev,identity='not-on-this-object',phase='created')
    receipt.write_text(json.dumps(value))
    with pytest.raises(storage.TargetError):storage.repair_publication(receipt,value)
    assert dest.read_text()=='replacement' and source.read_text()=='original'


def test_authentic_frozen_231_adopt_read_upgrade_and_restore(tmp_path):
    e=Env(tmp_path);frozen=SKILL/'.history/2.3.1/icloud_archive.py'
    assert frozen.is_file()
    e.write('old/a','authentic older writer');e.ok('sync','old',script=frozen)
    expected_root=e.root;expected_data=(expected_root/'files/old/a').read_bytes()
    e.env.pop('ICLOUD_ARCHIVE_ROOT')
    e.env['ARCHIVE_GENERAL_CONFIG']=str(e.tmp/'targets.json')
    result=e.ok('target','add','old','--root',e.base,'--kind','local','--adopt-existing','--plan')
    assert 'PLAN' in result and not (e.base/storage.MARKER).exists()
    e.ok('target','add','old','--root',e.base,'--kind','local','--adopt-existing','--default')
    assert str(expected_root/'files/old/a') in e.ok('read','old/a')
    assert 'via history' in e.ok('read','--via-history','old/a')
    e.ok('upgrade','--plan');e.ok('upgrade');e.ok('verify')
    e.ok('restore','old/a')
    assert (e.repo/'old/a').read_bytes()==expected_data


def test_unknown_folder_cannot_be_adopted(tmp_path):
    e=Env(tmp_path);e.env['ARCHIVE_GENERAL_CONFIG']=str(e.tmp/'cfg')
    root=e.tmp/'unrelated';root.mkdir();(root/'precious').write_text('keep')
    e.refused('target','add','bad','--root',root,'--kind','local','--adopt-existing')
    assert (root/'precious').read_text()=='keep' and not (root/storage.MARKER).exists()


def test_google_legacy_data_migration_is_refused_without_upload_confirmation(tmp_path):
    e=GeneralEnv(tmp_path,kind='google-drive');origin,data=literal_v1(e)
    (e.repo/'ICLOUD.md').rename(e.repo/'ARCHIVE.md')
    result=e.run('upgrade','--plan')
    assert result.returncode==1 and 'unsupported' in result.stdout
    assert origin.read_bytes()==data


def test_fallback_copy_refuses_bad_bytes_and_keeps_source(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'_native_publish',unsupported)
    source=tmp_path/'source';dest=tmp_path/'dest';source.write_bytes(b'original bytes')
    monkeypatch.setattr(storage.shutil,'copyfileobj',lambda incoming,out,length:out.write(b'X'*len(b'original bytes')))
    with pytest.raises(storage.TargetError):storage.publish(source,dest)
    assert source.read_bytes()==b'original bytes'


def test_nonempty_partial_directory_is_never_recursively_deleted(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'a').write_text('complete source')
    dest=tmp_path/'dest';dest.mkdir();(dest/'unknown').write_text('keep unknown data')
    fd=os.open(dest,os.O_RDONLY)
    try:identity=storage.publication_identity(fd,'known-publication')
    finally:os.close(fd)
    assert identity=='known-publication'
    info=dest.stat();home=tmp_path/'.publications';home.mkdir();receipt=home/'r.json'
    value=dict(format=1,source=str(source),destination=str(dest),expected=storage.fingerprint(source),inode=info.st_ino,device=info.st_dev,identity=identity,phase='created')
    receipt.write_text(json.dumps(value))
    with pytest.raises(OSError):storage.repair_publication(receipt,value)
    assert (dest/'unknown').read_text()=='keep unknown data' and (source/'a').read_text()=='complete source'


def test_registered_target_roots_cannot_overlap(g):
    g.refused('target','add','nested','--root',g.base/'nested','--kind','local')
    assert not (g.base/'nested').exists()


def test_valid_publication_identity_survives_inode_remapping(tmp_path):
    source=tmp_path/'source';dest=tmp_path/'dest';source.write_text('complete');dest.write_text('partial')
    fd=os.open(dest,os.O_RDONLY)
    try:identity=storage.publication_identity(fd,'object-token')
    finally:os.close(fd)
    assert identity=='object-token'
    home=tmp_path/'.publications';home.mkdir();receipt=home/'r.json'
    value=dict(format=1,source=str(source),destination=str(dest),expected=storage.fingerprint(source),inode=0,device=dest.stat().st_dev,identity=identity,phase='created')
    receipt.write_text(json.dumps(value))
    storage.repair_publication(receipt,value)
    assert source.read_text()=='complete' and not dest.exists() and not receipt.exists()


def subject_for(e, monkeypatch):
    for key,value in e.env.items():
        if key.startswith(('ARCHIVE_GENERAL_', 'ICLOUD_ARCHIVE_')):monkeypatch.setenv(key,value)
    spec=importlib.util.spec_from_file_location('archive_general_offline_subject',SCRIPT)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    from types import SimpleNamespace
    result.configure_session(SimpleNamespace(target=None),e.repo)
    return result


@pytest.mark.parametrize('action',['append','save','unlink','remove-output'])
def test_target_disappears_before_mutation_preserves_maps_and_both_copies(g,monkeypatch,action):
    g.write('a','original');g.ok('sync','a');g.write('a','original')
    m=subject_for(g,monkeypatch);store=m.Store(g.repo)
    before=(g.repo/'ARCHIVE.manifest.jsonl').read_bytes()
    offline=g.base.with_name('removed-target');os.rename(g.base,offline)
    try:
        with pytest.raises(storage.TargetError):
            if action=='append':store.append('del',{'path':'a'})
            elif action=='save':store.records.clear();store.save()
            elif action=='unlink':m.Ledger().unlink(g.repo/'a')
            else:m.remove_output(g.repo/'a')
        assert (g.repo/'a').read_text()=='original'
        assert (g.repo/'ARCHIVE.manifest.jsonl').read_bytes()==before
        assert not g.base.exists()
    finally:os.rename(offline,g.base)


def test_verify_rechecks_target_before_repair_if_it_disappears_during_hash(g,monkeypatch):
    g.write('a','original');g.ok('sync','a');g.write('a','original')
    m=subject_for(g,monkeypatch);before=(g.repo/'ARCHIVE.manifest.jsonl').read_bytes()
    offline=g.base.with_name('removed-during-verify');original=m.hash_file
    def disappear(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        if path==g.repo/'a':os.rename(g.base,offline)
        return value
    monkeypatch.setattr(m,'hash_file',disappear)
    from types import SimpleNamespace
    try:
        assert m.verify_command(g.repo,SimpleNamespace(fix=True))==2
        assert (g.repo/'a').read_text()=='original'
        assert (g.repo/'ARCHIVE.manifest.jsonl').read_bytes()==before
        assert not g.base.exists()
    finally:
        if offline.exists():os.rename(offline,g.base)
