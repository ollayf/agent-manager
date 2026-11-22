"""Drive protocol/transaction tests; this fake never contacts a real account."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
from types import SimpleNamespace

import pytest
from test_support import Env, SKILL
sys.path.insert(0,str(SKILL))
import storage
import drive_api as api
import drive_archive as archive


def sha(data):return hashlib.sha256(data).hexdigest()


class Wire:
    def __init__(self):
        self.files={};self.sessions={};self.next=0;self.calls=[];self.inject=None;self.download_override=None
        self.make('root-id','My Drive',api.FOLDER,[],b'')
        self.make('archive-folder','Test archives',api.FOLDER,['root-id'],b'')

    def make(self,ident,name,mime,parents,data,props=None):
        self.files[ident]=dict(id=ident,name=name,mimeType=mime,parents=parents,data=data,size=str(len(data)),sha256Checksum=sha(data),md5Checksum=hashlib.md5(data).hexdigest(),version='1',trashed=False,appProperties=props or {},capabilities={'canAddChildren':True,'canDownload':True,'canTrash':True})
        return self.meta(ident)

    def meta(self,ident):return {k:copy.deepcopy(v) for k,v in self.files[ident].items() if k!='data'}
    def new_id(self):self.next+=1;return 'id-'+str(self.next)
    def answer(self,status=200,body=None,headers=None):return status,headers or {},json.dumps(body).encode() if body is not None else b''

    def __call__(self,method,url,data,headers):
        p=urllib.parse.urlsplit(url);q={k:v[0] for k,v in urllib.parse.parse_qs(p.query).items()};path=p.path
        self.calls.append((method,path,q))
        if self.inject:
            answer=self.inject(method,path,q,data,headers)
            if answer is not None:return answer
        if path=='/batch/drive/v3' and method=='POST':
            from email.parser import BytesParser
            from email.policy import default
            content_type=headers['Content-Type']
            message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\n\r\n').encode()+data)
            boundary='wire_batch';parts=[]
            for part in message.iter_parts():
                payload=part.get_payload(decode=True)
                request=payload.splitlines()[0].decode().split()
                assert request[0]=='GET' and request[1].startswith('/drive/v3/files/')
                status,_,body=self('GET','https://www.googleapis.com'+request[1],None,{})
                ident=part['Content-ID'].strip('<>')
                parts.append(('--'+boundary+'\r\nContent-Type: application/http\r\nContent-ID: <response-'+ident+'>\r\n\r\nHTTP/1.1 '+str(status)+' OK\r\nContent-Type: application/json\r\n\r\n').encode()+body+b'\r\n')
            return 200,{'Content-Type':'multipart/mixed; boundary='+boundary},b''.join(parts)+('--'+boundary+'--\r\n').encode()
        if path=='/drive/v3/about':return self.answer(body={'user':{'permissionId':'account-A','emailAddress':'fixture@example.invalid'},'storageQuota':{'limit':'999999999999'}})
        if path=='/drive/v3/files/generateIds':return self.answer(body={'ids':[self.new_id()]})
        if path=='/drive/v3/files' and method=='GET':
            parent=re.search(r"'([^']+)' in parents",q['q'])[1]
            return self.answer(body={'files':[self.meta(k) for k,v in self.files.items() if parent in v['parents'] and not v['trashed']]})
        if path=='/drive/v3/files' and method=='POST':
            v=json.loads(data);ident=v.get('id') or self.new_id()
            if ident in self.files:return self.answer(409)
            return self.answer(body=self.make(ident,v['name'],v['mimeType'],v['parents'],b'',v.get('appProperties')))
        if path.startswith('/drive/v3/files/'):
            ident=path.rsplit('/',1)[1]
            if ident=='root':ident='root-id'
            if ident not in self.files:return self.answer(404)
            f=self.files[ident]
            if method=='GET':
                if q.get('alt')=='media':return 200,{},self.download_override(ident,f['data']) if self.download_override else f['data']
                return self.answer(body=self.meta(ident))
            if method=='PATCH':
                v=json.loads(data)
                if 'addParents' in q:f['parents']=[q['addParents']]
                f.update(v);f['version']=str(int(f['version'])+1);return self.answer(body=self.meta(ident))
        if path=='/upload/drive/v3/files' and q.get('uploadType')=='resumable':
            v=json.loads(data)
            if v['id'] in self.files:return self.answer(409)
            token=self.new_id();self.sessions[token]=dict(metadata=v,data=b'',total=int(headers['X-Upload-Content-Length']))
            return self.answer(headers={'Location':'https://www.googleapis.com/session/'+token})
        if path.startswith('/session/'):
            token=path.rsplit('/',1)[1]
            if token not in self.sessions:return self.answer(404)
            session=self.sessions[token];value=headers['Content-Range'];received=len(session['data']);total=session['total']
            if value.startswith('bytes */'):
                if received==total:
                    if session['metadata']['id'] not in self.files:self.complete(session)
                    return self.answer(body=self.meta(session['metadata']['id']))
                return self.answer(308,headers={'Range':'bytes=0-'+str(received-1)} if received else {})
            m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',value)
            assert m and int(m[1])==received and len(data)==int(m[2])-int(m[1])+1
            session['data']+=data;received=len(session['data'])
            if received==total:self.complete(session);return self.answer(body=self.meta(session['metadata']['id']))
            return self.answer(308,headers={'Range':'bytes=0-'+str(received-1)})
        if path=='/upload/drive/v3/files' and q.get('uploadType')=='multipart':
            boundary=headers['Content-Type'].split('boundary=')[1].encode();sections=data.split(b'--'+boundary)
            meta=json.loads(sections[1].split(b'\r\n\r\n',1)[1].rstrip(b'\r\n'))
            content=sections[2].split(b'\r\n\r\n',1)[1][:-2]
            if meta['id'] in self.files:return self.answer(409)
            return self.answer(body=self.make(meta['id'],meta['name'],meta['mimeType'],meta['parents'],content,meta.get('appProperties')))
        if path.startswith('/upload/drive/v3/files/') and method=='PATCH':
            ident=path.rsplit('/',1)[1]
            if ident not in self.files:return self.answer(404)
            f=self.files[ident];f.update(data=data,size=str(len(data)),sha256Checksum=sha(data),md5Checksum=hashlib.md5(data).hexdigest(),version=str(int(f['version'])+1))
            return self.answer(body=self.meta(ident))
        raise AssertionError((method,path,q))

    def complete(self,session):
        v=session['metadata'];self.make(v['id'],v['name'],v['mimeType'],v['parents'],session['data'],v.get('appProperties'))


class Fixture:
    def __init__(self,tmp_path,monkeypatch):
        self.env=Env(tmp_path);self.repo=self.env.repo;self.wire=Wire();self.client=api.Client(transport=self.wire,sleeper=lambda s:None)
        for key,value in self.env.env.items():
            if key.startswith(('ARCHIVE_GENERAL_','ICLOUD_ARCHIVE_')):monkeypatch.setenv(key,value)
        monkeypatch.delenv('ICLOUD_ARCHIVE_ROOT',raising=False);monkeypatch.delenv('ARCHIVE_GENERAL_ROOT',raising=False)
        monkeypatch.setenv('ARCHIVE_GENERAL_CONFIG',str(tmp_path/'targets.json'));monkeypatch.setenv('ARCHIVE_GENERAL_UPLOAD_CHUNK',str(256*1024))
        monkeypatch.setattr(api,'Client',lambda *a,**kw:self.client)
        monkeypatch.setattr(api,'client_for',lambda value:self.client)
        monkeypatch.setattr(archive,'client_for',lambda value:self.client)
        name='drive_test_subject_'+str(id(self));spec=importlib.util.spec_from_file_location(name,SKILL/'archive.py');self.core=importlib.util.module_from_spec(spec);sys.modules[name]=self.core;spec.loader.exec_module(self.core)
        monkeypatch.chdir(self.repo)
        assert self.run('target','add','cloud','--kind','google-drive-api','--drive-folder-id','archive-folder','--oauth-file',str(tmp_path/'private-auth.json'),'--default')==0

    def run(self,*args):return self.core.main(['--repo',str(self.repo),*map(str,args)])
    def write(self,*args,**kwargs):return self.env.write(*args,**kwargs)
    def store(self):
        a=self.core.parse_args(['--repo',str(self.repo),'status']);self.core.configure_session(a,self.repo)
        return archive.Store(self.core,self.repo,self.core.TARGET)
    def manifest(self):return (self.repo/'ARCHIVE.manifest.jsonl').read_bytes()


@pytest.fixture
def d(tmp_path,monkeypatch):return Fixture(tmp_path,monkeypatch)


def test_raw_roundtrip_metadata_unicode_layout_and_remote_receipt(d):
    p=d.write('data/café/report.csv','a,b\n1,2\n');p.chmod(0o640);info=p.stat()
    assert d.run('sync','data')==0 and not p.exists()
    store=d.store();r=store.records['data/café/report.csv'];assert r['format']==3 and r['by']==api.SKILL_VERSION
    assert d.wire.files[r['drive']['objects'][0]['id']]['data']==b'a,b\n1,2\n'
    assert r['drive']['objects'][0]['name']=='report.csv'
    assert store.client.folder('archive-folder',[*Path(store.prefix).parts,'files','data','café'])
    assert d.run('verify')==0
    assert d.run('restore','data/café/report.csv')==0
    assert p.read_bytes()==b'a,b\n1,2\n' and (p.stat().st_mtime_ns,p.stat().st_mode&0o777)==(info.st_mtime_ns,0o640)
    assert not d.store().records


def test_zero_length_file(d):
    p=d.write('empty',b'');assert d.run('sync','empty')==0;assert d.run('restore','empty')==0;assert p.read_bytes()==b''


def test_metadata_snapshot_is_fresh_and_never_leaks_to_the_next_operation(d):
    c=d.client
    first=c.batch_get(['archive-folder','root-id'])
    assert set(first)=={'archive-folder','root-id'}
    with c.metadata_snapshot(['archive-folder']):
        d.wire.files['archive-folder']['name']='changed after snapshot'
        assert c.get('archive-folder')['name']=='Test archives'
    assert c.get('archive-folder')['name']=='changed after snapshot'
    with c.metadata_snapshot(['archive-folder']):
        assert c.get('archive-folder')['name']=='changed after snapshot'


def test_metadata_batch_refuses_missing_or_wrong_identity_responses(d):
    with pytest.raises(api.DriveError):d.client.batch_get(['missing-id'])
    def wrong(method,path,q,data,headers):
        if path=='/drive/v3/files/archive-folder' and method=='GET':
            value=d.wire.meta('archive-folder');value['id']='another-object'
            return d.wire.answer(body=value)
    d.wire.inject=wrong
    with pytest.raises(api.DriveError,match='identity mismatch'):
        d.client.batch_get(['archive-folder'])


def test_metadata_batch_validates_cached_folder_ancestry_again(d):
    d.write('media/sub/a',b'bytes');assert d.run('sync','media')==0
    store=d.store();r=store.records['media/sub/a'];store.verify_record(r)
    folder=store.client.folder(store.project,['files','media'])
    d.wire.files[folder]['parents']=['root-id']
    with pytest.raises(api.DriveError):store.verify_record(r)
    assert not (d.repo/r['path']).exists()


def test_metadata_batch_refuses_fresh_checksum_change(d):
    d.write('m/a',b'bytes');assert d.run('sync','m')==0
    store=d.store();r=store.records['m/a'];store.verify_record(r)
    d.wire.files[r['drive']['objects'][0]['id']]['sha256Checksum']='0'*64
    with pytest.raises(api.DriveError):store.verify_record(r)


def test_scope_one_file_restores_siblings_stay_archived(d):
    d.write('m/a','a');d.write('m/b','b');assert d.run('sync','m')==0
    assert d.run('restore','_archive/m/a')==0
    assert set(d.store().records)=={'m/b'} and not (d.repo/'m/b').exists()


def test_raw_head_read_leaves_cloud_record(d,capsys):
    d.write('a','first\nsecond\nthird\n');assert d.run('sync','a')==0
    capsys.readouterr();assert d.run('read','a','--head','2')==0
    assert capsys.readouterr().out=='first\nsecond\n'
    assert 'a' in d.store().records and not (d.repo/'a').exists()


def test_packed_stream_head_and_restore(d,capsys):
    data=b'first\nsecond\n'+os.urandom(800000);p=d.write('p/log.csv',data)
    assert d.run('sync','p','--pack')==0
    record=d.store().records['p/log.csv'];assert record['form'].startswith('zst×')
    capsys.readouterr();assert d.run('read','p/log.csv','--head','2')==0
    assert capsys.readouterr().out=='first\nsecond\n'
    assert d.run('restore','p')==0 and p.read_bytes()==data


def test_changed_file_needs_update_and_old_copy_retained(d):
    d.write('a','old');assert d.run('sync','a')==0;old=d.store().records['a']['drive']['objects'][0]['id']
    p=d.write('a','new');assert d.run('sync','a')==0 and p.exists()
    assert d.run('sync','a','--update')==0 and not p.exists()
    assert d.wire.files[old]['data']==b'old' and not d.wire.files[old]['trashed']
    assert d.wire.files[old]['name'].startswith(d.core.today())
    assert d.run('restore','a')==0 and p.read_bytes()==b'new'


def test_existing_local_restore_destination_never_overwritten(d):
    d.write('a','cloud');assert d.run('sync','a')==0;p=d.write('a','local work')
    assert d.run('restore','a')==1 and p.read_text()=='local work' and 'a' in d.store().records


def test_bad_cloud_checksum_preserves_source_and_no_record(d):
    p=d.write('a','original')
    original=d.wire.complete
    def corrupt(session):
        original(session);d.wire.files[session['metadata']['id']]['sha256Checksum']='0'*64
    d.wire.complete=corrupt
    assert d.run('sync','a')==1 and p.read_text()=='original'
    assert not d.store().records


def test_missing_cloud_sha256_falls_back_to_download(d):
    p=d.write('a','original');original=d.wire.complete
    def omit(session):original(session);d.wire.files[session['metadata']['id']].pop('sha256Checksum')
    d.wire.complete=omit
    assert d.run('sync','a')==0 and not p.exists()
    assert any(q.get('alt')=='media' and path.endswith(d.store().records['a']['drive']['objects'][0]['id']) for _,path,q in d.wire.calls)


def test_bad_download_refuses_restore_and_preserves_cloud(d):
    d.write('a','archive');assert d.run('sync','a')==0
    ident=d.store().records['a']['drive']['objects'][0]['id'];d.wire.download_override=lambda i,data:b'changed' if i==ident else data
    assert d.run('restore','a')==1
    assert not (d.repo/'a').exists() and not d.wire.files[ident]['trashed']


@pytest.mark.parametrize('point',['drive-after-session','drive-after-chunk','drive-after-upload','drive-after-publish','drive-after-record','drive-after-delete'])
def test_upload_crash_resumes_without_duplicate_and_preserves_bytes(d,monkeypatch,point):
    p=d.write('a',os.urandom(800000));data=p.read_bytes()
    monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ARCHIVE_GENERAL_FAULT',point);monkeypatch.setenv('ICLOUD_ARCHIVE_FAULT',point)
    assert d.run('sync','a')==99
    assert p.exists() or point=='drive-after-delete'
    monkeypatch.delenv('ARCHIVE_GENERAL_FAULT');monkeypatch.delenv('ICLOUD_ARCHIVE_FAULT')
    if p.exists():assert d.run('sync','a')==0
    else:assert d.run('verify','--fix')==0
    assert d.run('restore','a')==0 and p.read_bytes()==data
    uploads=[f for f in d.wire.files.values() if f['data']==data]
    assert len(uploads)==1


def test_source_changes_while_uploading_is_not_deleted(d):
    p=d.write('a','original');original=d.wire.complete
    def change(session):original(session);p.write_text('new work')
    d.wire.complete=change
    assert d.run('sync','a')==1 and p.read_text()=='new work'


def test_remote_map_failure_does_not_remove_local_original(d):
    p=d.write('a','original')
    def fail(method,path,q,data,headers):
        if path=='/upload/drive/v3/files' and q.get('uploadType')=='multipart' and b'.manifest.jsonl' in data:return d.wire.answer(403)
    d.wire.inject=fail
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_wrong_account_and_wrong_marker_refuse_all_mutations(d):
    p=d.write('a','original');store=d.store();before=d.manifest() if (d.repo/'ARCHIVE.manifest.jsonl').exists() else None
    ident=store.target.value['drive_marker_id'];d.wire.files[ident]['data']=b'{}'
    assert d.run('sync','a')==1 and p.read_text()=='original'
    assert not (d.repo/'ARCHIVE.manifest.jsonl').exists() if before is None else d.manifest()==before


def test_quota_and_offline_failures_preserve_source(d):
    p=d.write('a','original');d.wire.inject=lambda method,path,q,data,headers:d.wire.answer(403) if path.startswith('/upload') else None
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_remote_destination_collision_preserves_both(d):
    p=d.write('a','original');store=d.store();parent=store.client.folder(store.ensure_project(),['files'],True)
    d.wire.make('foreign','a',api.BINARY,[parent],b'unknown file')
    assert d.run('sync','a')==1 and p.read_text()=='original' and d.wire.files['foreign']['data']==b'unknown file'


def test_busy_and_protected_files_stay_local(d):
    d.write('m/a','a');d.write('m/job.cursor','job')
    assert d.run('sync','m')==0 and (d.repo/'m/a').exists()
    assert d.run('sync','ARCHIVE.manifest.jsonl')==1


def test_metadata_only_cache_has_no_archived_payload(d):
    d.write('a',os.urandom(800000));assert d.run('sync','a')==0
    root=d.store().target.root
    assert not list(root.glob('repos/**/files/**/*'))
    assert not list((root/'.staging').glob('*'))


@pytest.mark.parametrize('point',['drive-restore-after-create','drive-restore-after-local-rename','drive-restore-after-publish','drive-restore-after-record'])
def test_restore_interruptions_recover_without_overwrite_or_loss(d,monkeypatch,point):
    p=d.write('a','original exact bytes');assert d.run('sync','a')==0
    monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ARCHIVE_GENERAL_FAULT',point);monkeypatch.setenv('ICLOUD_ARCHIVE_FAULT',point)
    assert d.run('restore','a')==99
    monkeypatch.delenv('ARCHIVE_GENERAL_FAULT');monkeypatch.delenv('ICLOUD_ARCHIVE_FAULT')
    assert d.run('verify','--fix')==0
    assert p.read_text()=='original exact bytes' and not d.store().records


def test_restore_racing_local_file_is_not_overwritten(d):
    p=d.write('a','cloud bytes');assert d.run('sync','a')==0;ident=d.store().records['a']['drive']['objects'][0]['id']
    def appear(i,data):
        if i==ident:p.write_text('new local work')
        return data
    d.wire.download_override=appear
    assert d.run('restore','a')==1 and p.read_text()=='new local work'
    assert not d.wire.files[ident]['trashed'] and 'a' in d.store().records


def test_resume_refuses_a_replaced_local_restore_object(d,monkeypatch):
    p=d.write('a','original');assert d.run('sync','a')==0
    monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ICLOUD_ARCHIVE_FAULT','drive-restore-after-publish')
    assert d.run('restore','a')==99
    monkeypatch.delenv('ICLOUD_ARCHIVE_FAULT')
    p.unlink();p.write_text('original')
    assert d.run('verify','--fix')==2
    assert 'a' in d.store().records and p.read_text()=='original'


def test_remote_account_switch_preserves_source(d):
    p=d.write('a','keep')
    def wrong(method,path,q,data,headers):
        if path=='/drive/v3/about':return d.wire.answer(body={'user':{'permissionId':'another-account'}})
    d.wire.inject=wrong
    assert d.run('sync','a')==1 and p.read_text()=='keep'


def test_expired_resumable_session_restarts_same_file_id(d,monkeypatch):
    p=d.write('a',os.urandom(800000));data=p.read_bytes()
    monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ARCHIVE_GENERAL_FAULT','drive-after-chunk')
    assert d.run('sync','a')==99;ident=d.store().pending()[0][1]['objects'][0]['id']
    monkeypatch.delenv('ARCHIVE_GENERAL_FAULT');d.wire.sessions.clear()
    assert d.run('sync','a')==0 and d.store().records['a']['drive']['objects'][0]['id']==ident
    assert d.run('restore','a')==0 and p.read_bytes()==data


def test_server_bad_range_does_not_remove_original(d):
    p=d.write('a',os.urandom(800000))
    def bad(method,path,q,data,headers):
        if path.startswith('/session/'):return d.wire.answer(308,headers={'Range':'bytes=0-999999999'})
    d.wire.inject=bad
    assert d.run('sync','a')==1 and p.exists()
    assert sum(method=='PUT' and path.startswith('/session/') for method,path,_ in d.wire.calls)==1


def test_packed_update_preserves_old_pack_and_restores_new(d):
    data=b'original\n'*10000;p=d.write('p/a',data);assert d.run('sync','p','--pack')==0
    old=d.store().records['p/a']['drive']['container_id']
    d.write('p/a',b'new\n'*10000);assert d.run('sync','p','--pack','--update')==0
    assert not d.wire.files[old]['trashed'] and d.wire.files[old]['name'].endswith('.big')
    assert d.run('restore','p/a')==0 and p.read_bytes()==b'new\n'*10000


@pytest.mark.parametrize('point',['drive-after-version','drive-after-publish'])
def test_update_publication_crash_keeps_older_bytes_and_resumes(d,monkeypatch,point):
    p=d.write('a','old');assert d.run('sync','a')==0;old=d.store().records['a']['drive']['objects'][0]['id']
    d.write('a','new')
    monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ICLOUD_ARCHIVE_FAULT',point)
    assert d.run('sync','a','--update')==99 and p.read_text()=='new'
    monkeypatch.delenv('ICLOUD_ARCHIVE_FAULT')
    assert d.run('sync','a','--update')==0
    assert d.wire.files[old]['data']==b'old' and not d.wire.files[old]['trashed']
    assert d.run('restore','a')==0 and p.read_text()=='new'


def test_moved_remote_project_is_not_accepted_before_source_removal(d):
    p=d.write('a','original');original=d.wire.complete
    def move_project(session):
        original(session)
        if session['metadata']['name']=='a':
            parent=session['metadata']['parents'][0];project=d.wire.files[parent]['parents'][0]
            d.wire.files[project]['parents']=['root-id']
    d.wire.complete=move_project
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_case_collision_in_remote_folder_is_refused(d):
    p=d.write('a','original');store=d.store();parent=store.client.folder(store.ensure_project(),['files'],True)
    d.wire.make('foreign','A',api.BINARY,[parent],b'keep')
    assert d.run('sync','a')==1 and p.exists() and d.wire.files['foreign']['data']==b'keep'


def test_read_cache_checks_bytes_and_large_read_requires_full(d,monkeypatch,capsys):
    d.write('a','original');assert d.run('sync','a')==0
    monkeypatch.setattr(d.core,'READ_FULL_LIMIT',1)
    assert d.run('read','a')==1
    capsys.readouterr();assert d.run('read','a','--full')==0
    p=Path(capsys.readouterr().out.strip());assert p.read_text()=='original'
    p.write_text('modified cache');assert d.run('read','a','--full')==1


def test_private_operation_journal_is_owner_only_and_contains_no_credentials(d,monkeypatch):
    d.write('a','original');monkeypatch.setattr(api.os,'_exit',lambda code:(_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.setenv('ARCHIVE_GENERAL_FAULT','drive-after-session');assert d.run('sync','a')==99
    path,op=d.store().pending()[0]
    assert path.stat().st_mode&0o777==0o600
    assert not any(k in path.read_text() for k in ('refresh_token','access_token','client_secret'))


def test_untrusted_session_endpoint_is_refused_without_bearer_leak():
    client=api.Client()
    with pytest.raises(api.DriveError,match='untrusted'):client.request('PUT','https://attacker.invalid/upload',data=b'private')


def test_retryable_errors_are_bounded_and_do_not_loop_forever():
    calls=[]
    def unavailable(*args):calls.append(1);return 503,{},b'unavailable'
    client=api.Client(transport=unavailable,sleeper=lambda seconds:None)
    with pytest.raises(api.DriveError):client.about()
    assert len(calls)==5


def test_missing_sha256_with_bad_remote_bytes_refuses(d):
    p=d.write('a','original');original=d.wire.complete
    def omit(session):original(session);d.wire.files[session['metadata']['id']].pop('sha256Checksum')
    d.wire.complete=omit;d.wire.download_override=lambda i,data:b'wrong' if d.wire.files[i]['name']=='a' else data
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_remote_wrong_size_refuses_original_removal(d):
    p=d.write('a','original');original=d.wire.complete
    def wrong(session):original(session);d.wire.files[session['metadata']['id']]['size']='999'
    d.wire.complete=wrong
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_unknown_cloud_import_and_implicit_migration_are_refused(d):
    p=d.write('foreign/a','source')
    assert d.run('import','foreign','--kind','mirror','--plan')==1
    assert p.read_text()=='source'
    other=d.repo.parent/'other-target'
    assert d.run('target','add','local','--root',other,'--kind','local')==0
    d.write('a','archive');assert d.run('sync','a')==0
    assert d.run('--target','local','sync','foreign')==1
    assert p.read_text()=='source'


def test_raw_head_has_bounded_memory_and_explicit_byte_cap(d,monkeypatch,capsys):
    d.write('a','x'*1000);assert d.run('sync','a')==0
    monkeypatch.setenv('ARCHIVE_GENERAL_HEAD_BYTES','64');capsys.readouterr()
    assert d.run('read','a','--head','1')==0
    answer=capsys.readouterr();assert answer.out=='x'*64 and 'sample byte limit' in answer.err
    assert 'a' in d.store().records


def test_marker_change_after_cloud_record_commit_prevents_source_removal(d):
    p=d.write('a','original');marker=d.store().target.value['drive_marker_id'];original=d.client.write_bytes
    def replace_marker(parent,name,data,existing=None):
        result=original(parent,name,data,existing)
        if name.endswith('.json') and name!=storage.MARKER:d.wire.files[marker]['data']=b'{}'
        return result
    d.client.write_bytes=replace_marker
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_corrupt_cloud_map_is_not_accepted_before_local_removal(d):
    p=d.write('a','original');original=d.wire.make
    def corrupt(ident,name,mime,parents,data,props=None):
        result=original(ident,name,mime,parents,data,props)
        if name=='.manifest.jsonl':d.wire.files[ident]['sha256Checksum']='f'*64
        return result
    d.wire.make=corrupt
    assert d.run('sync','a')==1 and p.read_text()=='original'


def test_native_oauth_refresh_keeps_secrets_in_memory(tmp_path,monkeypatch):
    private=tmp_path/'auth.json';private.write_text(json.dumps(dict(client_id='fixture-client',client_secret='fixture-secret',refresh_token='fixture-refresh')));private.chmod(0o600)
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"access_token":"fixture-access","expires_in":3600}'
    def exchange(request,timeout):
        assert request.full_url=='https://oauth2.googleapis.com/token'
        body=urllib.parse.parse_qs(request.data.decode());assert body['refresh_token']==['fixture-refresh']
        calls.append(1);return Response()
    monkeypatch.setattr(api.urllib.request,'urlopen',exchange)
    credentials=api.Credentials(dict(kind='authorized-user',file=str(private)))
    assert credentials.access()=='fixture-access' and credentials.access()=='fixture-access' and len(calls)==1
    assert 'fixture-access' not in private.read_text()


def test_drive_metadata_version_change_does_not_block_second_file(d):
    d.write('m/a','first');d.write('m/b','second');original=d.wire.complete
    def metadata_change(session):
        original(session)
        if session['metadata']['name']=='b':
            for obj in d.wire.files.values():
                if obj['name']=='.manifest.jsonl':obj['version']=str(int(obj['version'])+1)
    d.wire.complete=metadata_change
    assert d.run('sync','m')==0
    assert not (d.repo/'m/a').exists() and not (d.repo/'m/b').exists()
    assert set(d.store().records)=={'m/a','m/b'}


def test_actual_cloud_manifest_content_change_keeps_next_local_file(d):
    d.write('m/a','first');p=d.write('m/b','second');original=d.wire.complete
    def content_change(session):
        original(session)
        if session['metadata']['name']=='b':
            for obj in d.wire.files.values():
                if obj['name']=='.manifest.jsonl':
                    obj['data']+=b'\n';obj['sha256Checksum']=sha(obj['data']);obj['version']=str(int(obj['version'])+1)
    d.wire.complete=content_change
    assert d.run('sync','m')==1 and p.read_text()=='second'


def test_folder_creation_retries_do_not_duplicate_after_lost_response():
    wire=Wire();first=[True]
    def lost(method,url,data,headers):
        answer=wire(method,url,data,headers)
        if method=='POST' and urllib.parse.urlsplit(url).path=='/drive/v3/files' and first[0]:
            first[0]=False;raise ConnectionError('reply lost after creation')
        return answer
    client=api.Client(transport=lost,sleeper=lambda seconds:None)
    result=client.create_folder('archive-folder','new-folder')
    assert result['name']=='new-folder'
    assert len([v for v in wire.files.values() if v['name']=='new-folder'])==1


def test_cloud_map_creation_retries_do_not_duplicate_after_lost_response():
    wire=Wire();first=[True]
    def lost(method,url,data,headers):
        answer=wire(method,url,data,headers)
        if method=='POST' and urllib.parse.urlsplit(url).path=='/upload/drive/v3/files' and first[0]:
            first[0]=False;raise ConnectionError('reply lost after map creation')
        return answer
    client=api.Client(transport=lost,sleeper=lambda seconds:None)
    result=client.write_bytes('archive-folder','.manifest.jsonl',b'expected map')
    assert result['sha256Checksum']==sha(b'expected map')
    assert len([v for v in wire.files.values() if v['name']=='.manifest.jsonl'])==1


def test_restore_mixed_valid_missing_scope_is_reported_before_changes(d):
    d.write('a','original');assert d.run('sync','a')==0
    assert d.run('restore','a','does-not-exist')==1
    assert not (d.repo/'a').exists() and 'a' in d.store().records


def test_restore_multiple_named_files_leaves_siblings_archived(d):
    for name in ('a','b','c'):d.write('m/'+name,name)
    assert d.run('sync','m')==0
    assert d.run('restore','m/a','m/b')==0
    assert (d.repo/'m/a').read_text()=='a' and (d.repo/'m/b').read_text()=='b'
    assert set(d.store().records)=={'m/c'}


def test_pack_intent_survives_interruption_before_staging(d,monkeypatch):
    p=d.write('a',b'compressible\n'*10000);original=d.core.pack_file
    monkeypatch.setattr(d.core,'pack_file',lambda *args,**kwargs:(_ for _ in ()).throw(SystemExit(99)))
    assert d.run('sync','a','--pack')==99 and p.exists()
    monkeypatch.setattr(d.core,'pack_file',original)
    assert d.run('verify','--fix')==0
    assert d.store().records['a']['form'].startswith('zst×')


def test_adopt_existing_api_root_after_local_configuration_loss(d,monkeypatch,tmp_path,capsys):
    d.write('a','original\n');assert d.run('sync','a')==0;original=d.store().target.value
    rescued=tmp_path/'recovered/config.json';monkeypatch.setenv('ARCHIVE_GENERAL_CONFIG',str(rescued))
    args=['target','add','recovered','--kind','google-drive-api','--drive-folder-id','archive-folder','--oauth-file',str(tmp_path/'new-credential-location.json'),'--adopt-existing']
    assert d.run(*args,'--plan')==0 and not rescued.exists()
    before=len(d.wire.calls)
    assert d.run(*args)==0
    assert all(method=='GET' for method,path,q in d.wire.calls[before:])
    store=d.store();assert store.target.value['id']==original['id'] and store.target.root!=Path(original['root'])
    assert d.run('restore','a')==0 and (d.repo/'a').read_text()=='original\n'


def test_adoption_refuses_unknown_nonempty_drive_folder(d,monkeypatch,tmp_path):
    d.wire.make('other-folder','unknown',api.FOLDER,['root-id'],b'');d.wire.make('precious','precious.txt',api.BINARY,['other-folder'],b'user data')
    monkeypatch.setenv('ARCHIVE_GENERAL_CONFIG',str(tmp_path/'new-config.json'))
    assert d.run('target','add','other','--kind','google-drive-api','--drive-folder-id','other-folder','--oauth-file','unused','--adopt-existing')==1
    assert d.wire.files['precious']['data']==b'user data' and not d.wire.files['precious']['trashed']


def test_adoption_refuses_a_copied_marker_with_mismatching_registry(d,monkeypatch,tmp_path):
    d.write('a','original');assert d.run('sync','a')==0;store=d.store()
    registry=store.client.folder('archive-folder',['registry']);item=store.client.children(registry)[0];body=json.loads(d.wire.files[item['id']]['data']);body['archive_target']['account_id']='different-account';d.wire.files[item['id']]['data']=json.dumps(body).encode()
    monkeypatch.setenv('ARCHIVE_GENERAL_CONFIG',str(tmp_path/'new-config.json'))
    assert d.run('target','add','recover','--kind','google-drive-api','--drive-folder-id','archive-folder','--oauth-file','unused','--adopt-existing')==1
    assert not (tmp_path/'new-config.json').exists()


def test_frozen_reader_gets_lock_after_parent_releases_it(d,monkeypatch):
    import fcntl
    d.write('a','original');assert d.run('sync','a')==0
    def reader(store,rel,command,args=None):
        lockfile=d.core.LOCK_DIR/('icloud-archive-'+d.core.repo_id(d.repo)+'.lock')
        with lockfile.open('a') as f:
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        assert rel=='a' and command=='read'
        return 0
    monkeypatch.setattr(d.core,'via_history',reader)
    assert d.run('read','a','--via-history','--head','1')==0


def test_frozen_restore_refuses_multiple_scopes_without_changes(d):
    d.write('m/a','a');d.write('m/b','b');assert d.run('sync','m')==0
    assert d.run('restore','m/a','m/b','--via-history')==1
    assert not (d.repo/'m/a').exists() and not (d.repo/'m/b').exists()


def test_failed_upload_summary_never_claims_cloud_verification(d,capsys):
    d.write('a','original');d.wire.inject=lambda method,path,q,data,headers:d.wire.answer(403) if path.startswith('/upload') else None
    capsys.readouterr();assert d.run('sync','a')==1
    text=capsys.readouterr().out
    assert 'no completed files' in text and 'VERIFIED' not in text


def test_list_distinguishes_recorded_state_from_a_fresh_cloud_check(d,capsys):
    d.write('a','original');assert d.run('sync','a')==0;capsys.readouterr()
    assert d.run('list')==0
    text=capsys.readouterr().out
    assert 'not reverified' in text and 'cloud VERIFIED' not in text
