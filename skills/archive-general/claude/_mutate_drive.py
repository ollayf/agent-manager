#!/usr/bin/env python3
"""Disable one Drive safety check in an isolated copy and require its regression to fail."""
import argparse,ast,json,re,shutil,subprocess,sys,tempfile
from pathlib import Path
SKILL=Path(__file__).resolve().parents[1]
CASES=[
 (1,'cloud SHA-256 ignored','drive_api.py',[("if value['sha256Checksum']!=sha:raise DriveError",'if False:raise DriveError')],'test_bad_cloud_checksum_preserves_source_and_no_record'),
 (2,'cloud size ignored','drive_api.py',[("int(value.get('size',-1))!=size or ",'False or ')],'test_remote_wrong_size_refuses_original_removal'),
 (3,'cloud download fallback ignored','drive_api.py',[("elif self.checksum(ident)!=(size,sha):raise DriveError",'elif False:raise DriveError')],'test_missing_sha256_with_bad_remote_bytes_refuses'),
 (4,'source identity not rechecked before unlink','drive_archive.py',[("if not same_source(source,op['source']):raise DriveError('source changed during upload; cloud copy retained and local NOT removed')",'if False:raise DriveError(\'source changed\')')],'test_source_changes_while_uploading_is_not_deleted'),
 (5,'cloud map commit skipped','drive_archive.py',[("record=op['record'];store.verify_record(record);store.records[rel]=record;store.save()","record=op['record'];store.verify_record(record);store.records[rel]=record")],'test_remote_map_failure_does_not_remove_local_original'),
 (6,'wrong Google account allowed','drive_api.py',[("if who.get('permissionId')!=value.get('account_id'):raise DriveError",'if False:raise DriveError')],'test_remote_account_switch_preserves_source'),
 (7,'Drive target marker identity ignored','drive_api.py',[("if body.get('format')!=1 or body.get('id')!=value['id'] or body.get('kind')!='google-drive-api':raise DriveError",'if False:raise DriveError')],'test_wrong_account_and_wrong_marker_refuse_all_mutations'),
 (8,'resumed upload uses another allocated ID','drive_api.py',[("if not state.get('id'):state['id']=self.generate_id();persist()","if True:state['id']=self.generate_id();persist()")],'test_upload_crash_resumes_without_duplicate_and_preserves_bytes[drive-after-chunk]'),
 (9,'restore publication overwrites a racing local file','drive_archive.py',[("with local_io(core):core.publish(temporary,path)","with local_io(core):os.replace(temporary,path)")],'test_restore_racing_local_file_is_not_overwritten'),
 (10,'downloaded bytes not hashed before restore','drive_archive.py',[("if (size,h.hexdigest())!=(obj['size'],obj['sha256']):raise DriveError",'if False:raise DriveError'),("if storage.fingerprint(destination)['sha256']!=record['sha256'] or destination.stat().st_size!=record['size']:raise DriveError",'if False:raise DriveError')],'test_bad_download_refuses_restore_and_preserves_cloud'),
 (11,'restore ownership tag ignored','drive_archive.py',[("path.is_symlink() or identity!=op['local_identity']['identity'] or info.st_dev!=op['local_identity']['device'] or ",'False or ')],'test_resume_refuses_a_replaced_local_restore_object'),
 (12,'upload acknowledged range is trusted blindly','drive_api.py',[("if not match or int(match[1])+1>size:raise DriveError('invalid server upload range')","if not match:raise DriveError('invalid server upload range')"),("if new<=offset or new>offset+len(chunk):raise DriveError('invalid upload acknowledgement; source retained')","if False:raise DriveError('invalid upload acknowledgement')")],'test_server_bad_range_does_not_remove_original'),
 (13,'observed cloud manifest content change ignored','drive_archive.py',[("if cloud_sha!=self.mirror_sha:",'if False:')],'test_actual_cloud_manifest_content_change_keeps_next_local_file'),
 (14,'frozen reader launched while parent holds its lock','drive_archive.py',[("        return core.via_history(store,rel,command,args if command=='read' else None)", "        with core.lock(core.repo_id(repo)):\n            return core.via_history(store,rel,command,args if command=='read' else None)")],'test_frozen_reader_gets_lock_after_parent_releases_it'),
]

def main():
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path);p.add_argument('--validate',action='store_true');p.add_argument('ids',nargs='*',type=int);a=p.parse_args();results=[]
 for number,guard,file,changes,test in CASES:
  if a.ids and number not in a.ids:continue
  source=(SKILL/file).read_text()
  for before,after in changes:
   if source.count(before)!=1:raise ValueError('bad mutation '+str(number)+' matches='+str(source.count(before)))
   source=source.replace(before,after)
  ast.parse(source)
  if a.validate:print(number,'valid');continue
  root=Path(tempfile.mkdtemp(prefix='archive-drive-mutant-'+str(number)+'-'));copy=root/'archive-general'
  shutil.copytree(SKILL,copy,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'));(copy/file).write_text(source)
  answer=subprocess.run([sys.executable,'-m','pytest','-q','-x',str(copy/'claude/test_drive_api.py')+'::'+test,'--tb=short'],capture_output=True,text=True,timeout=180)
  log=answer.stdout+answer.stderr;(root/'pytest.log').write_text(log)
  status='KILLED' if answer.returncode==1 and 'ERROR collecting' not in log else 'SURVIVED' if answer.returncode==0 else 'INVALID'
  errors=[v for v in log.splitlines() if v.startswith('E ')];result=dict(id=number,guard=guard,test=test,status=status,reason=errors[0] if errors else '',evidence=str(root));results.append(result);print(number,status,result['reason'],flush=True)
 if a.report:a.report.write_text(json.dumps(results,indent=2)+'\n')
 return any(v['status']!='KILLED' for v in results)
if __name__=='__main__':raise SystemExit(main())
