"""Commit and byte-verify completed stage1; archive new package, preserve V1.0."""
from pathlib import Path
import json,hashlib,subprocess,shutil
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,check=True).stdout
def main():
 manifest=json.loads((ROOT/'V1_SYSTEM_EVIDENCE_MANIFEST.json').read_text(encoding='utf-8'))
 assert manifest['status']['V1_FULL_NETLIST']=='PASS' and manifest['status']['STAGE1_EXECUTION']=='COMPLETE'
 package=Path(manifest['status']['package']);tag='afdx-v1.0-stage1-system-verified-2026-10-12'
 # Stage only this task's explicit new source/document paths.
 paths=['README_SYSTEM.md','V1_SYSTEM_EVIDENCE_MANIFEST.json','阶段1_V1.0正式系统验收与交付报告.md',
        'sim/tb_v1_netlist.sv','sim/v1_netlist_observer.vh',*[f'scripts/{n}' for n in ('export_v1_vo.py','prepare_v1_netlist_observer.py','run_v1_netlist.py','verify_v1_netlist.py','check_v1_netlist.py','analyze_v1_performance.py','replay_v1_netlist.py','finish_v1_system.py','archive_v1_system.py','complete_v1_on_exit.py')]]
 git('add','--',*paths)
 if git('diff','--cached','--name-only').strip():git('commit','-m','Freeze complete stage1 candidate V1.0 real functional VO acceptance and delivery')
 commit=git('rev-parse','HEAD').decode().strip()
 git('tag','-a',tag,'-m','Complete stage1 team GMII candidate: real VO full Golden PASS; no official interface/timing/native EQ6 compliance claim')
 for rel,h in manifest['source_hashes'].items():assert hashlib.sha256(git('show','HEAD:'+Path(rel).as_posix())).hexdigest()==h,rel
 restore={'commit':commit,'tag':tag,'branch':'candidate/gmii-v1','Git_blob_byte_hash_check':'PASS','source_hashes_checked':len(manifest['source_hashes']),'full_VO_reference':manifest['status']['netlist_run'],'approval':'PENDING_CAPTAIN_REVIEW'}
 (package/'RESTORE_POINT.json').write_text(json.dumps(restore,indent=2)+'\n');shutil.copy2(ROOT/'V1_SYSTEM_EVIDENCE_MANIFEST.json',package/'V1_SYSTEM_EVIDENCE_MANIFEST.json')
 files={str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file() and not any(n in p.relative_to(package).parts for n in ('work','__pycache__')) and p.name!='PACKAGE_CONTENT_HASHES.json'}
 (package/'PACKAGE_CONTENT_HASHES.json').write_text(json.dumps(files,indent=2)+'\n')
 bundle=ROOT/'delivery/V1.0_complete_20261012.git.bundle';git('bundle','create',str(bundle),'--all');git('bundle','verify',str(bundle))
 archive=ROOT/'delivery/V1.0_complete_20261012.zip'
 with ZipFile(archive,'w',ZIP_DEFLATED) as z:
  for p in package.rglob('*'):
   if p.is_file() and not any(n in p.relative_to(package).parts for n in ('work','__pycache__')):z.write(p,package.name+'/'+p.relative_to(package).as_posix())
 with ZipFile(archive) as z:
  assert z.testzip() is None
  for n,h in files.items():assert hashlib.sha256(z.read(package.name+'/'+Path(n).as_posix())).hexdigest()==h,n
 final={'result':'PASS','restore':restore,'ZIP_sha256':sha(archive),'ZIP_bytes':archive.stat().st_size,'Git_bundle_sha256':sha(bundle),'package_files_verified':len(files),'full_VO_verification_sha256':manifest['netlist_verification_sha256'],'report_sha256':manifest['report_sha256'],'stage2':'NOT RUN'}
 (ROOT/'delivery/V1_SYSTEM_DELIVERY_HASHES.json').write_text(json.dumps(final,indent=2)+'\n');print('V1_SYSTEM_ARCHIVED PASS',commit,archive)
if __name__=='__main__':main()
