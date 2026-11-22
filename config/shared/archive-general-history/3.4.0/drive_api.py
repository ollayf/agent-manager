"""Direct Drive REST transport: resumable, checked uploads; no mounted-folder assumptions."""
from __future__ import annotations
import configparser
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import storage

SKILL_VERSION = '3.4.0'
FOLDER = 'application/vnd.google-apps.folder'
BINARY = 'application/octet-stream'
FIELDS = 'id,name,mimeType,parents,size,sha256Checksum,md5Checksum,version,trashed,appProperties,webViewLink,capabilities(canAddChildren,canDownload,canTrash)'
ID = re.compile(r'^[A-Za-z0-9_-]+$')


class DriveError(storage.TargetError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def checked_id(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise DriveError('invalid Google Drive object ID')
    return value


def sha_bytes(data):return hashlib.sha256(data).hexdigest()


def private_json(path, value):
    path=Path(path).absolute()
    if path.is_symlink() or path.parent.resolve()!=path.parent:raise DriveError('linked private state path; refusing')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name('.'+path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,sort_keys=True,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,path);storage.fsync_dir(path.parent)
    finally:temp.unlink(missing_ok=True)


class Credentials:
    """Read existing authorization privately. Refresh via Google; never print secrets."""
    def __init__(self, profile):
        self.profile=profile;self.token=None;self.expiry=0

    def source(self):
        if self.profile['kind']=='rclone':
            p=Path(self.profile.get('config',str(Path.home()/'.config/rclone/rclone.conf'))).expanduser()
            c=configparser.ConfigParser(interpolation=None)
            if not c.read(p):raise DriveError('rclone credential configuration is unavailable')
            name=self.profile['remote']
            if name not in c or c[name].get('type')!='drive':raise DriveError('named credential profile is not a Google Drive remote')
            v=c[name]
            if 'readonly' in v.get('scope',''):raise DriveError('Google Drive credential profile is read-only')
            try:t=json.loads(v.get('token','{}'))
            except ValueError:raise DriveError('invalid credential token; reconnect the named Google Drive account')
            return dict(t,client_id=v.get('client_id'),client_secret=v.get('client_secret'))
        if self.profile['kind']=='authorized-user':
            p=Path(self.profile['file']).expanduser()
            if p.is_symlink():raise DriveError('credential file must not be a symlink')
            return json.loads(p.read_text())
        raise DriveError('unknown Google credential profile type')

    def access(self, force=False):
        if self.token and self.expiry>time.time()+60 and not force:return self.token
        v=self.source()
        expiry=v.get('expiry','')
        try:expiry=dt.datetime.fromisoformat(expiry.replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):expiry=0
        token=v.get('access_token') or v.get('token')
        if not force and token and expiry>time.time()+60:
            self.token,self.expiry=token,expiry;return token
        if not all(v.get(k) for k in ('client_id','client_secret','refresh_token')):
            raise DriveError('Google authorization needs renewal; use a profile with a desktop OAuth client and refresh token')
        data=urllib.parse.urlencode(dict(client_id=v['client_id'],client_secret=v['client_secret'],refresh_token=v['refresh_token'],grant_type='refresh_token')).encode()
        request=urllib.request.Request('https://oauth2.googleapis.com/token',data=data,method='POST')
        try:
            with urllib.request.urlopen(request,timeout=30) as response:answer=json.load(response)
        except (OSError,ValueError):raise DriveError('Google authorization refresh failed; reconnect the named account (no file changed)')
        self.token=answer['access_token'];self.expiry=time.time()+int(answer.get('expires_in',3600))
        return self.token


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Resumable 308 is a protocol response, never a redirect. Do not leak a bearer.
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


class Client:
    def __init__(self, profile=None, transport=None, base='https://www.googleapis.com', sleeper=time.sleep):
        if transport is None and base!='https://www.googleapis.com':raise DriveError('custom Drive endpoints require an explicit test transport')
        self.credentials=Credentials(profile) if profile else None
        self.base=base;self.transport=transport;self.sleeper=sleeper
        self.opener=urllib.request.build_opener(NoRedirect())
        self.folders={}

    def request(self, method, path, params=None, data=None, headers=None, accepted=(), stream=False):
        url=self.base+path if path.startswith('/') else path
        parsed=urllib.parse.urlsplit(url)
        if self.transport is None and (parsed.scheme!='https' or parsed.netloc!='www.googleapis.com'):
            raise DriveError('untrusted Drive/session endpoint; refusing')
        if params:url+='?'+urllib.parse.urlencode(params)
        headers=dict(headers or {})
        for attempt in range(5):
            if self.credentials:headers['Authorization']='Bearer '+self.credentials.access(force=attempt==1 and refresh)
            refresh=False
            try:
                if self.transport:
                    status,h,body=self.transport(method,url,data,headers)
                else:
                    request=urllib.request.Request(url,data=data,headers=headers,method=method)
                    try:response=self.opener.open(request,timeout=90)
                    except urllib.error.HTTPError as error:response=error
                    status,h=response.code,dict(response.headers.items())
                    if stream and status==200:return response
                    body=response.read();response.close()
                if status==401 and attempt==0:
                    refresh=True;continue
                if status in (429,500,502,503,504) and attempt<4:
                    self.sleeper(min(2**attempt,8));continue
                if 200<=status<300 or status in accepted:return status,h,body
                # Error bodies can contain request/session details. Keep them private.
                raise DriveError('Google Drive request refused (HTTP '+str(status)+'); source and uncertain copies retained',status)
            except (urllib.error.URLError,TimeoutError,ConnectionError) as error:
                if attempt==4:raise DriveError('Google Drive connection failed; source retained') from None
                self.sleeper(min(2**attempt,8))
        raise DriveError('Google Drive retry limit reached; source retained')

    def json(self, method, path, params=None, value=None, headers=None):
        headers=dict(headers or {})
        if value is not None:headers['Content-Type']='application/json; charset=UTF-8'
        status,h,body=self.request(method,path,params,json.dumps(value).encode() if value is not None else None,headers)
        return json.loads(body) if body else {}

    def about(self):return self.json('GET','/drive/v3/about',{'fields':'user(permissionId,emailAddress),storageQuota'})
    def get(self, ident):return self.json('GET','/drive/v3/files/'+checked_id(ident),{'fields':FIELDS,'supportsAllDrives':'true'})
    def generate_id(self):return self.json('GET','/drive/v3/files/generateIds',{'count':1,'space':'drive','type':'files'})['ids'][0]

    def children(self,parent):
        result=[];page=None
        while True:
            q=dict(q="'"+checked_id(parent)+"' in parents and trashed = false",fields='nextPageToken,files('+FIELDS+')',pageSize=1000,supportsAllDrives='true',includeItemsFromAllDrives='true')
            if page:q['pageToken']=page
            answer=self.json('GET','/drive/v3/files',q);result.extend(answer.get('files',[]));page=answer.get('nextPageToken')
            if not page:return result

    def named(self,parent,name):
        matches=[v for v in self.children(parent) if v['name'].casefold()==name.casefold()]
        if len(matches)>1 or (matches and matches[0]['name']!=name):raise DriveError('duplicate or case-colliding Google Drive name: '+name)
        return matches[0] if matches else None

    def create_folder(self,parent,name,ident=None):
        value=dict(name=name,mimeType=FOLDER,parents=[checked_id(parent)],appProperties={'archive_general_by':SKILL_VERSION})
        value['id']=ident or self.generate_id()
        status,headers,body=self.request('POST','/drive/v3/files',{'fields':FIELDS,'supportsAllDrives':'true'},json.dumps(value).encode(),{'Content-Type':'application/json'},accepted=(409,))
        result=self.get(value['id']) if status==409 else json.loads(body)
        if result.get('name')!=name or result.get('mimeType')!=FOLDER or result.get('parents')!=[parent] or result.get('trashed'):raise DriveError('folder creation identity/location conflict')
        return result

    def folder(self,parent,parts,create=False):
        cursor=parent
        for name in parts:
            if name in ('','.','..') or '/' in name or any(ord(c)<32 for c in name):raise DriveError('unsafe Drive folder component')
            key=(cursor,name)
            if key in self.folders:
                known=self.get(self.folders[key])
                if known.get('parents')==[cursor] and known.get('name')==name and not known.get('trashed') and known.get('mimeType')==FOLDER:
                    cursor=known['id'];continue
                self.folders.pop(key,None)
            value=self.named(cursor,name)
            if value is None:
                if not create:return None
                value=self.create_folder(cursor,name)
            if value.get('mimeType')!=FOLDER or value.get('trashed'):raise DriveError('expected a real Drive folder; shortcuts and ordinary files refused')
            self.folders[key]=value['id'];cursor=value['id']
        return cursor

    def body(self,ident):
        return self.request('GET','/drive/v3/files/'+checked_id(ident),{'alt':'media','supportsAllDrives':'true'})[2]

    def chunks(self,ident):
        result=self.request('GET','/drive/v3/files/'+checked_id(ident),{'alt':'media','supportsAllDrives':'true'},stream=True)
        if isinstance(result,tuple):yield result[2];return
        try:
            for chunk in iter(lambda:result.read(1024**2),b''):yield chunk
        finally:result.close()

    def checksum(self,ident):
        h=hashlib.sha256();size=0
        for chunk in self.chunks(ident):h.update(chunk);size+=len(chunk)
        return size,h.hexdigest()

    def verify(self,ident,size,sha,parent=None,name=None):
        value=self.get(ident)
        if value.get('trashed') or value.get('mimeType','').startswith('application/vnd.google-apps.'):
            raise DriveError('Drive object is trashed, a shortcut or a converted document')
        if int(value.get('size',-1))!=size or (parent is not None and value.get('parents')!=[parent]) or (name is not None and value.get('name')!=name):
            raise DriveError('Drive object size/location does not match the archive receipt')
        if value.get('sha256Checksum'):
            if value['sha256Checksum']!=sha:raise DriveError('cloud SHA-256 mismatch; source retained')
        elif self.checksum(ident)!=(size,sha):raise DriveError('downloaded cloud SHA-256 mismatch; source retained')
        return value

    def upload(self,source,parent,name,state,persist,chunk_size=8*1024**2):
        """Persist a preallocated ID/session; query acknowledged range before resuming."""
        source=Path(source);size=source.stat().st_size
        if chunk_size%(256*1024) or chunk_size<=0:raise DriveError('upload chunk size must be a positive multiple of 256 KiB')
        if not state.get('id'):state['id']=self.generate_id();persist()
        ident=state['id']
        try:
            existing=self.get(ident)
        except DriveError as e:
            if e.status!=404:raise
            existing=None
        if existing:return self.verify(ident,size,state['sha256'],parent,name)
        occupied=self.named(parent,name)
        if occupied and occupied['id']!=ident:raise DriveError('unrecorded Drive destination exists; refusing to overwrite: '+name)
        for restart in range(2):
            session=state.get('session');offset=0
            if session:
                status,headers,body=self.request('PUT',session,data=b'',headers={'Content-Range':'bytes */'+str(size),'Content-Length':'0'},accepted=(308,404,410))
                if status in (200,201):return self.verify(ident,size,state['sha256'],parent,name)
                if status in (404,410):state.pop('session',None);persist();session=None
                else:offset=self.acknowledged(headers,size)
            if not session:
                value=dict(id=ident,name=name,mimeType=BINARY,parents=[parent],appProperties={'archive_general_by':SKILL_VERSION,'archive_general_sha256':state['sha256']})
                status,headers,body=self.request('POST','/upload/drive/v3/files',{'uploadType':'resumable','fields':FIELDS,'supportsAllDrives':'true'},json.dumps(value).encode(),{'Content-Type':'application/json','X-Upload-Content-Type':BINARY,'X-Upload-Content-Length':str(size)},accepted=(409,))
                if status==409:return self.verify(ident,size,state['sha256'],parent,name)
                session=next((v for k,v in headers.items() if k.lower()=='location'),None)
                if not session:raise DriveError('Google did not provide a resumable upload session')
                state['session']=session;persist()
                if os.environ.get('ARCHIVE_GENERAL_FAULT')=='drive-after-session':os._exit(99)
            with source.open('rb') as stream:
                while offset<size or size==0:
                    stream.seek(offset);chunk=stream.read(min(chunk_size,size-offset));end=offset+len(chunk)-1
                    content_range='bytes '+str(offset)+'-'+str(end)+'/'+str(size) if size else 'bytes */0'
                    status,headers,body=self.request('PUT',session,data=chunk,headers={'Content-Length':str(len(chunk)),'Content-Range':content_range},accepted=(308,404,410))
                    if status in (404,410):state.pop('session',None);persist();break
                    if status in (200,201):
                        state.pop('session',None);state['complete']=True;persist()
                        if os.environ.get('ARCHIVE_GENERAL_FAULT')=='drive-after-upload':os._exit(99)
                        return self.verify(ident,size,state['sha256'],parent,name)
                    new=self.acknowledged(headers,size)
                    if new<=offset or new>offset+len(chunk):raise DriveError('invalid upload acknowledgement; source retained')
                    offset=new;state['acknowledged']=offset;persist()
                    if os.environ.get('ARCHIVE_GENERAL_FAULT')=='drive-after-chunk':os._exit(99)
        raise DriveError('resumable upload expired repeatedly; rerun sync with source intact')

    @staticmethod
    def acknowledged(headers,size):
        value=next((v for k,v in headers.items() if k.lower()=='range'),'')
        match=re.fullmatch(r'bytes=0-(\d+)',value)
        if not value:return 0
        if not match or int(match[1])+1>size:raise DriveError('invalid server upload range')
        return int(match[1])+1

    def move(self,ident,parent,name):
        self.folders.clear()
        before=self.get(ident)
        return self.json('PATCH','/drive/v3/files/'+checked_id(ident),{'addParents':checked_id(parent),'removeParents':','.join(before.get('parents',[])),'supportsAllDrives':'true','fields':FIELDS},{'name':name})

    def trash(self,ident):
        self.folders.clear()
        self.json('PATCH','/drive/v3/files/'+checked_id(ident),{'supportsAllDrives':'true','fields':'id,trashed'},{'trashed':True})

    def write_bytes(self,parent,name,data,existing=None):
        """Maps are verified remotely before a source can be removed."""
        if existing is None:existing=self.named(parent,name)
        if existing:
            if existing.get('mimeType')==FOLDER:raise DriveError('folder occupies archive map name')
            ident=existing['id']
            self.request('PATCH','/upload/drive/v3/files/'+checked_id(ident),{'uploadType':'media','supportsAllDrives':'true'},data,{'Content-Type':BINARY})
        else:
            # Multipart avoids converting Markdown/CSV to Google-native documents.
            ident=self.generate_id();boundary='archive-'+uuid.uuid4().hex
            metadata=json.dumps(dict(id=ident,name=name,mimeType=BINARY,parents=[parent],appProperties={'archive_general_by':SKILL_VERSION})).encode()
            payload=b'--'+boundary.encode()+b'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+metadata+b'\r\n--'+boundary.encode()+b'\r\nContent-Type: '+BINARY.encode()+b'\r\n\r\n'+data+b'\r\n--'+boundary.encode()+b'--\r\n'
            self.request('POST','/upload/drive/v3/files',{'uploadType':'multipart','supportsAllDrives':'true'},payload,{'Content-Type':'multipart/related; boundary='+boundary},accepted=(409,))
        return self.verify(ident,len(data),sha_bytes(data),parent,name)


_CLIENTS={}
_VALIDATED={}
def clear_validation_cache():
    _VALIDATED.clear()

def client_for(value):
    key=json.dumps(value.get('credential',{}),sort_keys=True)
    if key not in _CLIENTS:_CLIENTS[key]=Client(value['credential'])
    return _CLIENTS[key]


def validate_target(value, force=False):
    key=(value['id'],value['account_id'],value['drive_folder_id'],value['drive_marker_id'])
    client=client_for(value)
    if not force and time.monotonic()-_VALIDATED.get(key,-1000000)<30:return client
    client.folders.clear();who=client.about()['user']
    if who.get('permissionId')!=value.get('account_id'):raise DriveError('Google account identity differs from the registered archive account')
    folder=client.get(value['drive_folder_id'])
    if folder.get('trashed') or folder.get('mimeType')!=FOLDER:raise DriveError('registered Drive archive folder is unavailable or replaced')
    marker=client.get(value['drive_marker_id'])
    if marker.get('parents')!=[folder['id']] or marker.get('name')!=storage.MARKER or marker.get('trashed'):raise DriveError('Drive target marker moved or is missing; refusing')
    try:body=json.loads(client.body(marker['id']))
    except (ValueError,UnicodeDecodeError):raise DriveError('invalid Drive target marker')
    if body.get('format')!=1 or body.get('id')!=value['id'] or body.get('kind')!='google-drive-api':raise DriveError('Drive target marker identity mismatch; refusing')
    _VALIDATED[key]=time.monotonic()
    return client


def register(args):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',args.name):raise DriveError('target name must be a short plain name')
    if not args.drive_folder_id:raise DriveError('direct Drive setup requires --drive-folder-id; ask before choosing a permanent destination')
    if args.root or args.removable:raise DriveError('direct Drive setup uses a remote folder ID, not a filesystem root')
    if args.oauth_file:profile=dict(kind='authorized-user',file=str(Path(args.oauth_file).expanduser().resolve()))
    elif args.credential_remote:profile=dict(kind='rclone',remote=args.credential_remote,config=str(Path(args.credential_config or '~/.config/rclone/rclone.conf').expanduser().resolve()))
    else:raise DriveError('specify --credential-remote or --oauth-file for existing Google authorization')
    client=Client(profile);folder=client.get(args.drive_folder_id);who=client.about()['user']
    if folder.get('mimeType')!=FOLDER or folder.get('trashed') or folder['id']==client.get('root')['id']:raise DriveError('choose a real dedicated Drive archive folder')
    with storage.config_lock():
        config=storage.load_config();previous=config['targets'].get(args.name)
        if previous:
            if previous.get('kind')!='google-drive-api' or previous.get('drive_folder_id')!=folder['id'] or previous.get('account_id')!=who['permissionId']:
                raise DriveError('target name already bound; no target or archive was migrated')
            validate_target(previous);print('existing Drive target verified: '+args.name);return
        for value in config['targets'].values():
            if value.get('kind')=='google-drive-api' and value.get('drive_folder_id')==folder['id'] and value.get('account_id')==who['permissionId']:
                raise DriveError('Drive archive folder is already registered under another name')
        entries=client.children(folder['id']);marker=None;ident=None
        if entries:
            if not args.adopt_existing:raise DriveError('Drive archive folder is not empty; use an explicitly planned --adopt-existing for a recognized Archive General root')
            marker=client.named(folder['id'],storage.MARKER)
            if not marker or marker.get('mimeType')==FOLDER:raise DriveError('existing Drive root has no recognizable archive marker; nothing taken over')
            identity=json.loads(client.body(marker['id']))
            if identity.get('format')!=1 or identity.get('kind')!='google-drive-api' or not identity.get('id'):raise DriveError('existing Drive root marker is incompatible')
            if identity.get('account_id',who['permissionId'])!=who['permissionId']:raise DriveError('existing Drive root belongs to another account')
            ident=str(uuid.UUID(identity['id']))
            registry=client.folder(folder['id'],['registry'])
            if registry:
                for entry in client.children(registry):
                    if not entry['name'].endswith('.json'):raise DriveError('unrecognized registry entry; inspect before adoption')
                    descriptor=json.loads(client.body(entry['id'])).get('archive_target',{})
                    if (descriptor.get('id'),descriptor.get('account_id'),descriptor.get('drive_folder_id'),descriptor.get('drive_marker_id'))!=(ident,who['permissionId'],folder['id'],marker['id']):raise DriveError('existing registry account/root/marker identity mismatch; nothing adopted')
        if args.plan:
            print('PLAN: '+('adopt existing' if marker else 'register empty')+' direct Drive folder '+folder['id']+'; preserve repos/files/.big/.versions structure; no cloud data or configuration changed');return
        ident=ident or str(uuid.uuid4());root=storage.config_path().parent/'drive-state'/ident
        if marker is None:marker=client.write_bytes(folder['id'],storage.MARKER,json.dumps(dict(format=1,by=SKILL_VERSION,id=ident,kind='google-drive-api',account_id=who['permissionId'])).encode())
        value=dict(name=args.name,id=ident,root=str(root),kind='google-drive-api',account_id=who['permissionId'],drive_folder_id=folder['id'],drive_marker_id=marker['id'],credential=profile,file_limit=0)
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if root.is_symlink() or root.resolve()!=root:raise DriveError('linked metadata cache root; refusing')
        private_json(root/storage.MARKER,dict(format=1,by=SKILL_VERSION,id=ident,kind='google-drive-api'))
        config['targets'][args.name]=value;config['by']=SKILL_VERSION
        if args.default or not config.get('default'):config['default']=args.name
        storage.atomic_json(storage.config_path(),config)
        print('registered '+args.name+': https://drive.google.com/drive/folders/'+folder['id'])
        print('direct API; cloud size/SHA-256 verification precedes removal; existing project targets unchanged')
