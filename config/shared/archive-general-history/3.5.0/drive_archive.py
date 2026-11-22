"""Format-3 Drive archives. Cloud verification and durable maps precede local removal."""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.parse
import uuid
import storage
from drive_api import Client, DriveError, FOLDER, SKILL_VERSION, client_for, private_json, validate_target


@contextlib.contextmanager
def local_io(core):
    # Pure local staging/index IO keeps filesystem guards; remote validation occurs
    # explicitly at transaction boundaries and again before destructive actions.
    previous=core.TARGET;core.TARGET=None
    try:yield
    finally:core.TARGET=previous


def fingerprint(path):
    info=path.stat()
    return dict(size=info.st_size,sha256=storage.fingerprint(path)['sha256'],mtime_ns=info.st_mtime_ns,mode=stat.S_IMODE(info.st_mode),device=info.st_dev,inode=info.st_ino)


def same_source(path,expected):
    if path.is_symlink() or not path.is_file():return False
    info=path.stat()
    return (info.st_size,info.st_mtime_ns,info.st_dev,info.st_ino)==tuple(expected[k] for k in ('size','mtime_ns','device','inode')) and storage.fingerprint(path)['sha256']==expected['sha256']


def remove_journal(path):
    path.unlink(missing_ok=True);storage.fsync_dir(path.parent)


class Store:
    def __init__(self,core,repo,target):
        self.core,self.repo,self.target=core,repo,target
        self.client=validate_target(target.value);self.v1=[];self.park_note=None;self.park_missing=False
        self.manifest=repo/'ARCHIVE.manifest.jsonl' if repo else None
        self.index=repo/'ARCHIVE.md' if repo else None
        self.header={};self.records={};self.gen=0;self.mirror_id=None;self.mirror_version=None;self.mirror_sha=None
        if self.manifest and self.manifest.exists():self.header,self.records=self.parse(self.manifest.read_bytes())
        self.id=self.header.get('id') or core.repo_id(repo)
        prefix=self.header.get('drive_prefix')
        if not prefix and self.index and self.index.exists():
            match=re.search(r'^Root: `gdrive://([^/]+)/([^`]+)/?`$',self.index.read_text(),re.M)
            if not match or match[1]!=target.value['drive_folder_id']:raise DriveError('Drive index root differs from the registered target')
            prefix=urllib.parse.unquote(match[2]).rstrip('/')
        if prefix is None:
            try:rel=repo.relative_to(core.HOME)
            except ValueError:rel=Path('_abs')/str(repo).lstrip('/')
            prefix=(Path('repos')/rel).as_posix()
        prefix=core.stored_rel(prefix)
        if Path(prefix).parts[0]!='repos':raise DriveError('direct Drive project root must retain the agreed repos/ structure')
        self.prefix=prefix;self.root=target.root/prefix
        self.uri='gdrive://'+target.value['drive_folder_id']+'/'+urllib.parse.quote(prefix,safe='/')
        self.project=self.client.folder(target.value['drive_folder_id'],Path(prefix).parts)
        if self.project:
            mirror=self.client.named(self.project,'.manifest.jsonl')
            if mirror:
                remote_text=self.client.body(mirror['id']);rh,rr=self.parse(remote_text)
                if rh.get('id')!=self.id or rh.get('drive_prefix')!=prefix:raise DriveError('remote manifest belongs to another project/root')
                if rh['archive_target']['id']!=target.value['id']:raise DriveError('remote manifest target identity differs')
                self.mirror_id,self.mirror_version=mirror['id'],mirror.get('version');self.mirror_sha=hashlib.sha256(remote_text).hexdigest()
                if rh.get('gen',0)>self.header.get('gen',0) or not self.header:self.header,self.records=rh,rr
                elif rh.get('gen',0)==self.header.get('gen',0) and rr!=self.records:raise DriveError('same-generation Drive manifests conflict; copies preserved')
        if self.header and (self.header.get('drive_prefix')!=prefix or self.header.get('archive_target',{}).get('id')!=target.value['id']):raise DriveError('project is bound to a different Drive target/root')
        self.gen=self.header.get('gen',0)
        self.parked=self.header.get('parked')
        if not self.header:
            reason=core.Store.taken(self,'_archive')
            self.parked=None if reason else '_archive'
            if reason:self.park_note=reason
        self.pending_dir=target.root/'.drive-operations'/self.id
        self.registry_path=target.root/'registry'/(self.id+'.json')

    def parse(self,text):
        header={};records={}
        for line in text.decode('utf-8').splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if 'icloud_archive_manifest' in row:
                if row['icloud_archive_manifest']!=3:raise DriveError('direct Drive requires format 3; no implicit migration')
                header=row
            elif row.get('op')=='add':
                rel=self.core.stored_rel(row['path'])
                if row.get('format')!=3 or row.get('storage')!='google-drive-api':raise DriveError('unsupported direct Drive record format')
                if any(p.casefold()==rel.casefold() and p!=rel for p in records):raise DriveError('case-colliding Drive manifest records')
                objects=row.get('drive',{}).get('objects')
                if not isinstance(objects,list) or not objects or (row.get('form')=='file' and len(objects)!=1):raise DriveError('invalid cloud object inventory')
                for obj in objects:
                    if not isinstance(obj,dict) or not all(k in obj for k in ('id','name','size','sha256')) or not isinstance(obj['size'],int) or obj['size']<0 or not re.fullmatch(r'[0-9a-f]{64}',obj['sha256']):raise DriveError('invalid cloud object receipt')
                    if '/' in obj['name'] or obj['name'] in ('.','..'):raise DriveError('unsafe cloud object receipt name')
                value=dict(row);value.pop('op');records[rel]=value
            elif row.get('op')=='del':records.pop(self.core.stored_rel(row['path']),None)
            else:raise DriveError('invalid Drive manifest operation')
        if not header:raise DriveError('Drive manifest has no valid header')
        return header,records

    def rel(self,*args,**kwargs):return self.core.Store.rel(self,*args,**kwargs)
    def taken(self,*args,**kwargs):return self.core.Store.taken(self,*args,**kwargs)

    def ensure_project(self):
        if not self.project:self.project=self.client.folder(self.target.value['drive_folder_id'],Path(self.prefix).parts,True)
        return self.project

    def header_value(self):
        return dict(icloud_archive_manifest=3,by=SKILL_VERSION,id=self.id,root=self.uri,drive_prefix=self.prefix,gen=self.gen,parked=self.parked,archive_target=self.target.value)

    def text(self):
        return ('\n'.join([json.dumps(self.header_value(),sort_keys=True,ensure_ascii=False)]+[json.dumps(dict(self.records[p],op='add'),sort_keys=True,ensure_ascii=False) for p in sorted(self.records)])+'\n').encode()

    def render(self):
        prose=[]
        if self.index.exists():
            lines=self.index.read_text().splitlines();end=next((i for i,v in enumerate(lines) if v.startswith('| Path |')),len(lines))
            prose=[v for v in lines[:end] if not v.startswith(('Root:','Parked folders:','Cloud folder:'))]
        if not prose:prose=['# Archive General','','Direct Google Drive archive. Change records through Archive General only.','']
        prose += ['Root: `'+self.uri+'`','Cloud folder: https://drive.google.com/drive/folders/'+self.ensure_project()]
        if self.parked:prose+=['Parked folders: `'+self.parked+'/` — empty structure at the same project-relative path.']
        prose+=['','| Path | Form | Archived |','|---|---|---|']
        prose += ['| `'+p.replace('|','\\|')+'` | '+r['form']+' | '+r['date']+' |' for p,r in sorted(self.records.items())]
        prose+=['','Format 3; each file has verified cloud object IDs, SHA-256, original metadata and writer version in ARCHIVE.manifest.jsonl.','']
        return '\n'.join(prose)

    def save(self):
        validate_target(self.target.value, force=True);self.ensure_project()
        # Reject a remote writer observed since this command loaded the manifest.
        current=self.client.named(self.project,'.manifest.jsonl')
        if bool(current)!=bool(self.mirror_id) or (current and current['id']!=self.mirror_id):
            raise DriveError('Drive manifest was replaced/removed by another writer; original retained')
        if current:
            cloud_sha=current.get('sha256Checksum') or self.client.checksum(current['id'])[1]
            if cloud_sha!=self.mirror_sha:
                raise DriveError('Drive manifest contents changed in another writer; original retained; re-run after reviewing')
        self.gen+=1;body=self.text()
        with local_io(self.core):
            self.core.atomic_write(self.manifest,body.decode())
        mirror=self.client.write_bytes(self.project,'.manifest.jsonl',body,current)
        self.mirror_id,self.mirror_version=mirror['id'],mirror.get('version')
        self.mirror_sha=hashlib.sha256(body).hexdigest()
        self.header=self.header_value()
        with local_io(self.core):self.core.atomic_write(self.index,self.render())
        registry=dict(format=3,by=SKILL_VERSION,id=self.id,repo=str(self.repo),root=self.uri,drive_prefix=self.prefix,drive_project_id=self.project,archive_target=self.target.value,files=len(self.records),bytes=sum(r['size'] for r in self.records.values()),updated=self.core.today())
        private_json(self.registry_path,registry)
        registry_folder=self.client.folder(self.target.value['drive_folder_id'],['registry'],True)
        self.client.write_bytes(registry_folder,self.id+'.json',json.dumps(registry,sort_keys=True).encode())

    def journal_path(self,rel):return self.pending_dir/(hashlib.sha256(rel.encode()).hexdigest()+'.json')
    def pending(self):
        return [(p,json.loads(p.read_text())) for p in sorted(self.pending_dir.glob('*.json'))] if self.pending_dir.exists() else []

    def verify_record(self,record,deep=False):
        rel=self.core.stored_rel(record['path']);parts=Path(rel).parts
        if record.get('format')!=3:raise DriveError('unknown direct Drive format')
        if not self.project:raise DriveError('remote project folder is missing; copies preserved')
        actual_project=self.client.folder(self.target.value['drive_folder_id'],Path(self.prefix).parts)
        if actual_project != self.project:raise DriveError('cloud project folder moved or was replaced; copies retained')
        parent=self.client.folder(self.project,['files',*parts[:-1]]) if record['form']=='file' else self.client.folder(self.project,['.big',*parts])
        if not parent:raise DriveError('recorded cloud folder is missing; copies preserved')
        for obj in record['drive']['objects']:
            expected_name=parts[-1] if record['form']=='file' else obj['name']
            if '/' in expected_name or expected_name in ('.','..'):raise DriveError('unsafe cloud object name')
            self.client.verify(obj['id'],obj['size'],obj['sha256'],parent,expected_name)
            if deep and self.client.checksum(obj['id'])!=(obj['size'],obj['sha256']):raise DriveError('deep cloud download hash mismatch')
        return record


def op_save(path,op):private_json(path,op)


def create_container(store,op,journal):
    rel=op['record']['path'];parts=Path(rel).parts
    parent=store.client.folder(store.ensure_project(),['.big',*parts[:-1]],True)
    name=('.ag-upload-'+op['operation']) if op.get('old') else parts[-1]
    if not op.get('container'):
        if store.client.named(parent,name):raise DriveError('unrecorded packed destination exists; refusing overwrite')
        op['container']=dict(id=store.client.generate_id(),parent=parent,name=name);op_save(journal,op)
    value=op['container']
    try:existing=store.client.get(value['id'])
    except DriveError as error:
        if error.status!=404:raise
        try:existing=store.client.create_folder(parent,name,value['id'])
        except DriveError as retry:
            if retry.status!=409:raise
            existing=store.client.get(value['id'])
    if existing.get('mimeType')!=FOLDER or existing.get('parents')!=[parent] or existing.get('name')!=name:raise DriveError('packed container identity/location conflict')
    return value['id']


def publish_uploaded(store,op,journal):
    rel=op['record']['path'];parts=Path(rel).parts;packed=op['record']['form']!='file'
    if op.get('old'):
        old=op['old'];oldpacked=old['form']!='file'
        version_parent=store.client.folder(store.ensure_project(),['.versions',*parts],True)
        version_name=old['date']+'-'+old['sha256'][:8]+'-'+op['operation'][:8]+('.big' if oldpacked else '')
        old_id=old['drive']['container_id'] if oldpacked else old['drive']['objects'][0]['id']
        existing=store.client.get(old_id)
        if existing.get('parents')!=[version_parent] or existing.get('name')!=version_name:
            store.verify_record(old)
            collision=store.client.named(version_parent,version_name)
            if collision and collision['id']!=old_id:raise DriveError('older-version destination collision')
            store.client.move(old_id,version_parent,version_name)
        op['old_retained']=True;op_save(journal,op)
        store.core.fault('drive-after-version')
    parent=store.client.folder(store.ensure_project(),['.big' if packed else 'files',*parts[:-1]],True)
    ident=op['container']['id'] if packed else op['objects'][0]['id']
    existing=store.client.get(ident);collision=store.client.named(parent,parts[-1])
    if collision and collision['id']!=ident:raise DriveError('destination appeared during upload; copies retained')
    if existing.get('parents')!=[parent] or existing.get('name')!=parts[-1]:store.client.move(ident,parent,parts[-1])
    objects=[]
    for obj in op['objects']:
        value={k:obj[k] for k in ('id','name','size','sha256')}
        if not packed:value['name']=parts[-1]
        objects.append(value)
    op['record']['drive']=dict(objects=objects,container_id=op['container']['id'] if packed else None)
    op['phase']='published';op_save(journal,op)
    store.verify_record(op['record']);store.core.fault('drive-after-publish')


def archive_one(store,rel,args,ledger):
    core=store.core;source=store.repo/rel;journal=store.journal_path(rel)
    op=json.loads(journal.read_text()) if journal.exists() else None
    if op and op.get('action')!='archive':raise DriveError('a restore is pending for this path; use verify')
    if op:
        if source.exists() and not same_source(source,op['source']):raise DriveError('source changed since the interrupted upload; all copies retained')
        if not source.exists() and op.get('phase')!='published':raise DriveError('pending upload has no complete local source; inspect copies')
    else:
        if not source.is_file() or source.is_symlink():raise DriveError('source vanished or is not a regular file')
        info=fingerprint(source);old=store.records.get(rel)
        if old and old['sha256']==info['sha256']:
            store.verify_record(old);store.save();store.target.available()
            if not same_source(source,info):raise DriveError('source changed while verifying; kept local')
            validate_target(store.target.value,force=True)
            ledger.unlink(source);return old['size']
        if old and not args.update:return None
        if any(p.casefold()==rel.casefold() and p!=rel for p in store.records):raise DriveError('case-only archive path collision')
        record=dict(path=rel,size=info['size'],sha256=info['sha256'],mode=info['mode'],mtime_ns=info['mtime_ns'],form='file',date=core.today(),format=3,storage='google-drive-api',by=SKILL_VERSION)
        op=dict(format=3,by=SKILL_VERSION,target=store.target.value['id'],action='archive',operation=uuid.uuid4().hex,source=info,record=record,old=copy.deepcopy(old),pack=bool(args.pack),fast=bool(args.fast),phase='prepared',objects=[])
        op_save(journal,op)
    if op['phase']=='prepared':
        if op.get('pack',args.pack or op['record']['form']!='file'):
            stage=store.target.root/'.staging'/op['operation']
            if not stage.exists():
                core.ensure_free(store.target.root,op['source']['size']+core.MARGIN)
                with local_io(core):meta=core.pack_file(source,stage,op.get('fast',args.fast))
            else:
                with local_io(core):meta=core.read_pack(stage)
                if meta['original_sha256']!=op['record']['sha256']:raise DriveError('packed staging does not match original')
            op['record']['form']='zst×'+str(len(meta['parts']));op_save(journal,op)
            parent=create_container(store,op,journal)
            candidates=sorted(p for p in stage.iterdir() if p.is_file())
        else:
            parts=Path(rel).parts;parent=store.client.folder(store.ensure_project(),['files',*parts[:-1]],True);candidates=[source]
        for candidate in candidates:
            name=candidate.name if op['record']['form']!='file' else ('.ag-upload-'+op['operation'] if op.get('old') else Path(rel).name)
            item=next((v for v in op['objects'] if v['name']==name),None)
            if item is None:
                item=dict(name=name,size=candidate.stat().st_size,sha256=storage.fingerprint(candidate)['sha256']);op['objects'].append(item);op_save(journal,op)
            store.client.upload(candidate,parent,name,item,lambda:op_save(journal,op),int(os.environ.get('ARCHIVE_GENERAL_UPLOAD_CHUNK',8*1024**2)))
        op['phase']='uploaded';op_save(journal,op)
    if op['phase']=='uploaded':publish_uploaded(store,op,journal)
    record=op['record'];store.verify_record(record);store.records[rel]=record;store.save()
    core.fault('drive-after-record')
    validate_target(store.target.value,force=True);store.verify_record(record)
    if source.exists():
        if not same_source(source,op['source']):raise DriveError('source changed during upload; cloud copy retained and local NOT removed')
        validate_target(store.target.value,force=True)
        ledger.unlink(source)
    core.fault('drive-after-delete')
    stage=store.target.root/'.staging'/op['operation']
    if stage.exists():storage.safe_remove_tree(stage)
    remove_journal(journal);return record['size']


def collect(store,args):
    core=store.core;found=[];skipped=[];seen={};scopes=[]
    for value in args.paths:
        rel,parked=store.rel(value,'sync');scopes.append(rel)
        if parked:skipped.append((rel,'parked structure'));continue
        path=store.repo/rel
        if not path.exists():
            if any(core.under(p,[rel]) for p in store.records):continue
            raise DriveError('requested path is absent: '+rel)
        if path.is_symlink():raise DriveError('symlink named directly')
        candidates=[]
        if path.is_file():
            if path.name=='.keep' or core.litter(path.name):raise DriveError('protected metadata/keep file')
            candidates=[path]
        else:
            for parent,dirs,names in os.walk(path,followlinks=False):
                for d in dirs:
                    if core.scope_root(Path(parent)/d):skipped.append((core.nfc((Path(parent)/d).relative_to(store.repo).as_posix())+'/','nested archive scope with its own index; archive it from there'))
                dirs[:]=[d for d in dirs if d!='.git' and not (Path(parent)/d).is_symlink() and not core.scope_root(Path(parent)/d) and not core.match_path((Path(parent)/d).relative_to(store.repo).as_posix(),args.exclude)]
                candidates += [Path(parent)/n for n in sorted(names) if n not in ('.git','.keep','ARCHIVE.md','ARCHIVE.manifest.jsonl','ICLOUD.md','ICLOUD.manifest.jsonl',core.SCOPE_FILE) and not core.litter(n)]
        opened,error=core.lsof_paths(path,path.is_dir())
        if error:raise DriveError('cannot confirm whether files are open; '+error)
        for item in candidates:
            name=core.nfc(item.relative_to(store.repo).as_posix())
            core.stored_rel(name)
            if core.match_path(name,args.exclude):continue
            if item.is_symlink() or storage.reserved_collision(item):skipped.append((name,'symlink or reserved ._ name'));continue
            reason=core.live_reason(item,opened,args.min_age)
            if reason:skipped.append((name,reason));continue
            if name.casefold() in seen:
                if seen[name.casefold()]!=name:raise DriveError('case-only selected path collision')
                continue
            seen[name.casefold()]=name;found.append(name)
    return found,skipped,scopes


def tidy(store,scopes,ledger=None,plan=False,min_age=None,excludes=None):
    kwargs=dict(ledger=ledger)
    if min_age is not None:kwargs['min_age']=min_age
    if excludes is not None:kwargs['excludes']=excludes
    folder=store.core.tidy_plan(store,scopes,**kwargs)
    if not plan:folder.apply()
    folder.report();return folder


def sync(store,args):
    core=store.core;core.check_protection(store.repo,args.allow_protected)
    paths,skipped,scopes=collect(store,args);ledger=core.Ledger();done=[];changed=[];refused=[];before=shutil.disk_usage(store.repo).free
    for rel in paths:
        try:
            size=archive_one(store,rel,args,ledger)
            if size is None:changed.append(rel);print('changed, kept local: '+rel+'; --update needs approval')
            else:done.append((rel,size));print('archived and cloud-verified '+rel)
        except (DriveError,OSError,core.Refused) as error:refused.append(rel);print('REFUSED: '+rel+': '+str(error),file=sys.stderr)
    folder=tidy(store,scopes,ledger,min_age=args.min_age,excludes=args.exclude) if done else None
    after=shutil.disk_usage(store.repo).free
    verification=('VERIFIED for '+str(len(done))+' completed file(s)') if done else 'no completed files'
    print('SUMMARY\n  archived: '+str(len(done))+'; cloud verification: '+verification+'; refused: '+str(len(refused))+'; skipped: '+str(len(skipped))+'; changed: '+str(len(changed)))
    for rel,reason in skipped:print('  skipped '+rel+': '+reason)
    print('  source bytes removed: '+str(sum(size for _,size in done))+'; observed disk-free delta: '+str(after-before)+' bytes (includes other activity)')
    print('  direct Drive upload; no mounted-folder archive copy or eviction required')
    return 1 if refused or (folder and folder.problems()) else 0


def download_object(store,obj,destination,created=None):
    h=hashlib.sha256();size=0
    with destination.open('xb') as stream:
        if created:created(stream.fileno())
        for chunk in store.client.chunks(obj['id']):h.update(chunk);size+=len(chunk);stream.write(chunk)
        stream.flush();os.fsync(stream.fileno())
    if (size,h.hexdigest())!=(obj['size'],obj['sha256']):raise DriveError('download size/SHA-256 mismatch; cloud copy retained')


def fetch(store,record,destination,created=None):
    core=store.core;store.verify_record(record)
    if record['form']=='file':download_object(store,record['drive']['objects'][0],destination,created)
    else:
        stage=Path(tempfile.mkdtemp(prefix='drive-download-',dir=store.target.root))
        try:
            core.ensure_free(stage,sum(v['size'] for v in record['drive']['objects'])+record['size'])
            for obj in record['drive']['objects']:download_object(store,obj,stage/obj['name'])
            with local_io(core):
                with destination.open('xb') as output:
                    if created:created(output.fileno())
                    core.unpack(stage,output);output.flush();os.fsync(output.fileno())
        finally:storage.safe_remove_tree(stage)
    if storage.fingerprint(destination)['sha256']!=record['sha256'] or destination.stat().st_size!=record['size']:raise DriveError('restored original size/SHA-256 mismatch; cloud copy retained')


def restore_one(store,rel,into=None):
    core=store.core;journal=store.journal_path(rel)
    op=json.loads(journal.read_text()) if journal.exists() else None
    if op and op.get('action')!='restore':raise DriveError('upload is pending for this path; run verify')
    # restore --into (3.5+): the journal remembers the destination folder, so a resumed
    # restore finishes where it started.
    base=Path(op['into']) if op and op.get('into') else (into or store.repo)
    if op and into and Path(op.get('into') or store.repo)!=Path(into):raise DriveError('a restore of this path is pending to another destination; run verify')
    path=base/rel
    if op is None:
        if core.exists(path):raise DriveError('restore destination exists; not overwriting')
        record=copy.deepcopy(store.records[rel]);store.verify_record(record);core.ensure_free(base,record['size'])
        op=dict(format=3,by=SKILL_VERSION,target=store.target.value['id'],action='restore',operation=uuid.uuid4().hex,record=record,phase='prepared')
        if into:op['into']=str(into)
        op_save(journal,op)
    record=op['record'];path.parent.mkdir(parents=True,exist_ok=True)
    def owned(candidate):
        if not op.get('local_identity') or candidate.is_symlink() or not candidate.is_file():return False
        fd=os.open(candidate,os.O_RDONLY)
        try:identity=storage.publication_identity(fd)
        finally:os.close(fd)
        return identity==op['local_identity']['identity'] and candidate.stat().st_dev==op['local_identity']['device']
    if op['phase']=='prepared':
        temporary=path.with_name(path.name+'.restoring-'+op['operation'])
        if core.exists(path):
            if not owned(path) or storage.fingerprint(path)['sha256']!=record['sha256']:raise DriveError('restore destination appeared; cloud copy retained')
        else:
            if temporary.exists():
                if not owned(temporary):raise DriveError('restore temporary was replaced; copies preserved')
                temporary.unlink()
            def created(fd):
                token=storage.publication_identity(fd,op['operation'])
                if token!=op['operation']:raise DriveError('cannot mark restore ownership; cloud copy retained')
                os.fsync(fd);op['local_identity']=dict(identity=token,device=os.fstat(fd).st_dev);op_save(journal,op)
                core.fault('drive-restore-after-create')
            try:
                fetch(store,record,temporary,created);os.chmod(temporary,record['mode']);os.utime(temporary,ns=(record['mtime_ns'],record['mtime_ns']))
                with local_io(core):core.publish(temporary,path)
                core.fault('drive-restore-after-local-rename')
            except BaseException:
                if owned(temporary):temporary.unlink()
                raise
        op['phase']='local';op_save(journal,op);core.fault('drive-restore-after-publish')
    info=path.lstat();fd=os.open(path,os.O_RDONLY)
    try:identity=storage.publication_identity(fd)
    finally:os.close(fd)
    if path.is_symlink() or identity!=op['local_identity']['identity'] or info.st_dev!=op['local_identity']['device'] or storage.fingerprint(path)['sha256']!=record['sha256']:
        raise DriveError('restored local object changed or was replaced; cloud copies retained')
    if op['phase']=='local':
        store.verify_record(record);store.records.pop(rel,None);store.save();op['phase']='record-removed';op_save(journal,op);core.fault('drive-restore-after-record')
    validate_target(store.target.value,force=True)
    # The verified local file survives before owned cloud objects are put in Trash.
    for obj in record['drive']['objects']:
        remote=store.client.get(obj['id'])
        if remote.get('trashed'):continue
        if storage.fingerprint(path)['sha256']!=record['sha256']:raise DriveError('local restored bytes changed; remaining cloud copies retained')
        parts=Path(rel).parts
        actual_project=store.client.folder(store.target.value['drive_folder_id'],Path(store.prefix).parts)
        if actual_project!=store.project:raise DriveError('cloud project moved; remaining objects preserved')
        parent=store.client.folder(store.project,['files',*parts[:-1]]) if record['form']=='file' else store.client.folder(store.project,['.big',*parts])
        if not parent:raise DriveError('cloud folder moved; remaining objects preserved')
        store.client.verify(obj['id'],obj['size'],obj['sha256'],parent,parts[-1] if record['form']=='file' else obj['name'])
        store.client.trash(obj['id'])
    if record['drive'].get('container_id'):
        folder=store.client.get(record['drive']['container_id'])
        if store.client.children(folder['id']):raise DriveError('unexpected objects remain in packed cloud folder; left for inspection')
        store.client.trash(folder['id'])
    remove_journal(journal);print('restored and checked '+rel);return record['size']


def restore(store,args):
    selected=[]
    for value in args.paths:
        rel,_=store.rel(value,'restore');matches=[p for p in store.records if core_under(store,p,rel)]
        if not matches and store.journal_path(rel).exists():matches=[rel]
        if not matches:raise DriveError('requested path has no archived entries: '+rel)
        selected += matches
    if not selected:raise DriveError('requested path has no archived entries')
    into=store.core.restore_into(store.repo,getattr(args,'into',None))
    for rel in dict.fromkeys(selected):restore_one(store,rel,into)
    if into:
        for rel in store.core.drop_empty_parks(store,list(dict.fromkeys(selected))):print('retired empty parked folder '+rel+'/ (its files left the project)')
    else:tidy(store,[str(Path(p).parent) for p in selected])
    return 0


def core_under(store,path,scope):return store.core.under(path,[scope])


def read(store,args):
    core=store.core;rel,_=store.rel(args.path,'read')
    if rel not in store.records:raise DriveError('requested file is not archived')
    record=store.records[rel];store.verify_record(record)
    if args.head is not None and args.head<0:raise DriveError('--head must be nonnegative')
    if args.head is not None and record['form']=='file':
        if args.head==0:return 0
        remaining=args.head;written=0;limit=int(os.environ.get('ARCHIVE_GENERAL_HEAD_BYTES',16*1024**2))
        if limit<=0:raise DriveError('sample byte limit must be positive')
        chunks=store.client.chunks(record['drive']['objects'][0]['id'])
        try:
            for incoming in chunks:
                chunk=incoming[:limit-written];offset=0
                for _ in range(min(remaining,chunk.count(b'\n'))):
                    offset=chunk.index(b'\n',offset)+1;remaining-=1
                    if remaining==0:sys.stdout.buffer.write(chunk[:offset]);return 0
                sys.stdout.buffer.write(chunk);written+=len(chunk)
                if written>=limit:
                    print('sample byte limit reached; use a full read for the remaining bytes',file=sys.stderr);return 0
        finally:chunks.close()
        return 0
    if args.head is None and record['size']>core.READ_FULL_LIMIT and not args.full:raise DriveError('large cloud read requires --head N or --full and local space')
    if args.head is not None:
        stage=Path(tempfile.mkdtemp(prefix='drive-sample-',dir=store.target.root))
        try:
            core.ensure_free(stage,sum(v['size'] for v in record['drive']['objects']))
            for obj in record['drive']['objects']:download_object(store,obj,stage/obj['name'])
            with local_io(core):core.unpack(stage,sys.stdout.buffer,head=args.head)
        finally:storage.safe_remove_tree(stage)
    else:
        cache=store.target.root/'reads'/store.id/record['sha256']/Path(rel).name;cache.parent.mkdir(parents=True,exist_ok=True)
        if cache.exists():
            if storage.fingerprint(cache)['sha256']!=record['sha256']:raise DriveError('read cache changed; refusing reuse')
        else:
            core.ensure_free(cache.parent,record['size']);temporary=cache.with_name('.read-'+uuid.uuid4().hex)
            try:
                fetch(store,record,temporary)
                with local_io(core):core.publish(temporary,cache)
            finally:temporary.unlink(missing_ok=True)
        print(cache)
    return 0


def verify(store,args):
    core=store.core;problems=0;unresolved=0
    for path,op in store.pending():
        problems+=1;rel=op['record']['path'];print('[pending-'+op['action']+'] '+rel)
        if not args.fix:unresolved+=1;continue
        try:
            if op['action']=='archive':
                from types import SimpleNamespace
                local=store.repo/rel
                if local.exists():
                    opened,error=core.lsof_paths(local,False)
                    if error or core.live_reason(local,opened,core.MIN_AGE):raise DriveError('source is in use or process state unknown; not resumed')
                settings=SimpleNamespace(pack=op['record']['form']!='file',fast=False,update=bool(op.get('old')))
                archive_one(store,rel,settings,core.Ledger())
            else:restore_one(store,rel)
            print('  fixed')
        except (OSError,ValueError,core.Refused) as error:unresolved+=1;print('  left for inspection: '+str(error))
    for rel,record in list(store.records.items()):
        try:
            store.verify_record(record,deep=getattr(args,'deep',False))
            if (store.repo/rel).exists():
                problems+=1
                if storage.fingerprint(store.repo/rel)['sha256']==record['sha256']:print('[duplicate-local] '+rel+'; rerun sync to finish with live/source checks')
                else:print('[changed-local] '+rel)
                unresolved+=1
        except (OSError,ValueError) as error:problems+=1;unresolved+=1;print('[cloud-copy] '+rel+': '+str(error))
    if not problems:print('clean: cloud objects verified')
    return 2 if unresolved else 0


def registry(core,target,args):
    client=validate_target(target.value);folder=client.folder(target.value['drive_folder_id'],['registry'])
    if getattr(args,'scan',None):raise DriveError('direct Drive registry scan does not migrate filesystem archives')
    if folder:
        for obj in client.children(folder):
            if obj['name'].endswith('.json'):
                value=json.loads(client.body(obj['id']))
                if value.get('archive_target',{}).get('id')!=target.value['id']:raise DriveError('registry target identity mismatch')
                print(str(value['repo'])+'\t'+value['root']+'\t'+str(value['files'])+' files')
    return 0


def dispatch(core,repo,args):
    if args.command=='registry':return registry(core,core.TARGET,args)
    if repo is None:raise DriveError('direct Drive bulk migration requires a separate explicit plan; existing targets unchanged')
    command=args.command
    if getattr(args,'via_history',False):
        if getattr(args,'into',None):raise DriveError('restore --via-history writes into the project; it does not take --into')
        if command=='restore' and len(args.paths)!=1:raise DriveError('frozen restore accepts one named path per invocation')
        with core.lock(core.repo_id(repo)):
            store=Store(core,repo,core.TARGET)
            rel,_=store.rel(args.paths[0] if command=='restore' else args.path,command)
            store.parked=None
        # The frozen child takes its own project lock; never hold the parent lock across it.
        return core.via_history(store,rel,command,args if command=='read' else None)
    with core.lock(core.repo_id(repo)):
        store=Store(core,repo,core.TARGET)
        if command in ('sync','archive'):return sync(store,args)
        if command=='restore':return restore(store,args)
        if command=='read':return read(store,args)
        if command=='verify':return verify(store,args)
        if command=='tidy':
            scopes=[store.rel(v,'tidy')[0] for v in args.paths];plan=tidy(store,scopes,plan=args.plan,min_age=args.min_age,excludes=args.exclude)
            return 1 if plan.problems() else 0
        if command in ('list','status','upload-status'):
            scopes=[store.rel(v,command)[0] for v in getattr(args,'paths',[])]
            for rel,record in sorted(store.records.items()):
                if not core.under(rel,scopes):continue
                if command!='list':store.verify_record(record,deep=getattr(args,'deep',False))
                state='recorded; not reverified by list' if command=='list' else 'cloud VERIFIED'
                print(rel+'\tformat 3\t'+record['form']+'\tby '+record['by']+'\t'+state+'\thttps://drive.google.com/file/d/'+record['drive']['objects'][0]['id']+'/view')
            if command=='status':
                for _,op in store.pending():print('[pending-'+op['action']+'] '+op['record']['path'])
            return 0
        if command=='evict':print('Direct API archive: no mounted-folder archive cache to evict; source removal already follows verified cloud upload. Explicit read caches remain local.');return 0
        if command=='upgrade':
            if store.header:print('already format 3; agreed Drive folder layout retained');return 0
            raise DriveError('no direct Drive archive to upgrade; filesystem-to-API migration requires an explicit plan')
        if command=='import':raise DriveError('direct Drive import is not implemented; no foreign files moved; use a separately planned migration')
        raise DriveError('unsupported direct Drive operation')
