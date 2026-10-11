"""Verify and freeze captain-approved B2-4 evidence; no simulator/tool runs."""
from pathlib import Path
import hashlib,json,shutil,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 original=ROOT/'B2_4_EVIDENCE_MANIFEST.json';old=read(original)
 status=ROOT/'runs/current_status.json'
 assert sha(Path(old['report']['path']))==old['report']['sha256']
 assert sha(status)==old['status_sha256']
 for rel,h in old['B2_4_development_hashes'].items():assert sha(ROOT/rel)==h,rel
 run=Path(old['netlist_run'])
 for n,h in old['active_outputs_final_hashes'].items():assert sha(run/n)==h,n
 prior=read(ROOT/'runs/eda_export_001/freeze_audit.json')
 for c in prior['checks']:assert sha(Path(c['verified_path']))==c['expected_sha256'],c
 assert len(prior['checks'])==149
 summary=read(run/'summary.json');v=read(run/'netlist_verification.json')
 assert summary['result']=='PASS' and summary['exit_code']==0 and v['result']=='PASS'
 assert (v['real_b1_tx_frames'],v['gmii_bytes'],v['application_frames'],v['application_bytes'],v['sn_decisions_compared'])==(263,20454,291,2431,303)
 git=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
 assert git=='c2f9f1dbe60d0982c2667033db326be0d1b558b1',git
 assert subprocess.run(['git','diff','--name-only'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()==''
 audit=ROOT/'runs/b2_3_audit_001';audit.mkdir(exist_ok=False)
 frozen=audit/'approved_B2_4_baseline';frozen.mkdir()
 for p in (original,status,Path(old['report']['path']),ROOT/'runs/b2_4_status.json'):
  shutil.copy2(p,frozen/p.name)
 st=read(status);st['generated_utc']=datetime.now(timezone.utc).isoformat()
 st['states'].update(B2_4_RESULT='PASS',B2_4_SYNTHESIS='PASS',B2_4_VO_EXPORT='PASS',B2_POST_SYNTH_FUNCTIONAL='PASS',B2_4_CAPTAIN_APPROVAL='APPROVED_2026_10_11_SINGLE_VL_PROFILE',STAGE5B2_RESULT='IN_PROGRESS_B2_3',B2_3_INTEGRATION_AUDIT='IN_PROGRESS',B2_FORMAL_TOP_INTEGRATION='NOT RUN')
 write(status,st);write(ROOT/'runs/b2_4_status.json',st)
 manifest={'approval_local_date':'2026-10-11','scope':'Captain-approved B2-4 synthesis and functional VO/ModelSim acceptance, verified single-VL engineering profile only','verified_git_commit':git,'approved_tag':'stage5b2-b2-4-approved-2026-10-11','frozen_baseline_archive':str(frozen),'frozen_baseline_items':[{'path':str(p),'sha256':sha(p)} for p in frozen.iterdir()], 'legacy_149_hashes_verified':149,'final_evidence_verified':len(old['active_outputs_final_hashes']),'final_verification':v,'approved_states':st['states'],'current_status_sha256':sha(status),'original_B2_4_manifest_sha256':sha(original),'all_final_evidence_hashes':old['active_outputs_final_hashes'],'B2_4_development_hashes':old['B2_4_development_hashes'],'production_RTL_modified':False,'new_synthesis_or_simulation_executed':False}
 write(ROOT/'B2_4_APPROVAL_MANIFEST.json',manifest)
 print('B2_4_APPROVAL_FREEZE PASS legacy_hashes=149 final_artifacts='+str(len(old['active_outputs_final_hashes'])))
if __name__=='__main__':main()
