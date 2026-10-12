"""Finalize verified fallback artifacts; never launches FPGA tools."""
from pathlib import Path
import hashlib,json,shutil
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 package=ROOT/'delivery/V1.0'
 v=json.loads((package/'runs/rtl_001/verification.json').read_text());a=json.loads((ROOT/'runs/elinx_001/synthesis_audit.json').read_text())
 integrity=json.loads((ROOT/'runs/production_integrity.json').read_text());b2=ROOT.parent/'stage5B2_rx_arch_20261011/runs/full_004'
 assert v['result']==a['result']==integrity['result']=='PASS'
 assert json.loads((b2/'verification.json').read_text())['result']=='PASS'
 report=ROOT/'阶段1_正式顶层集成与V1.0验收报告.md'
 # Synchronize utility scripts after the portable-parent-directory bug fix.
 for p in (ROOT/'scripts').glob('*'):
  if p.is_file():shutil.copy2(p,package/'scripts'/p.name)
 for p in (ROOT/'README.md',ROOT/'.gitattributes',report):shutil.copy2(p,package/p.name)
 status={'generated_local':datetime.now(timezone(timedelta(hours=8))).isoformat(),'STAGE1_EXECUTION':'COMPLETE','STAGE1_RESULT':'PENDING_CAPTAIN_REVIEW','V1_RTL_FUNCTIONAL':'PASS','V1_INDEPENDENT_PACKAGE_REPLAY':'PASS','V1_GOLDEN':'PASS','V1_EXCEPTION_RECOVERY':'PASS','V1_HISTORY_REGRESSION':'PASS','V1_SYNTHESIS_SMOKE':'PASS','resources':a['resources'],'warning_count':a['warning_count'],'metrics':{k:v[k] for k in ('golden_cases','tx_frames','tx_bytes','app_frames','app_bytes','SN_wrap','BAG_gaps_checked','minimum_BAG_cycles','decisions_compared')},'OFFICIAL_INTERFACE_COMPATIBILITY':'NOT VERIFIED','V1_FUNCTIONAL_VO':'NOT RUN','POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','PHYSICAL_IO_FIT':'NOT VERIFIED','DIAGNOSTIC_IO_FIT':'INCOMPATIBLE','B2_WRAPPER_DIAG_ADDR_1':'UNSUPPORTED','100_MBPS':'NOT VERIFIED','Implementation':'NOT RUN','Bitstream':'NOT RUN','hardware_download':'NOT RUN','stage2':'NOT RUN','original_frozen_modules_modified':False}
 for p in (ROOT/'runs/current_status.json',package/'STATUS.json'):p.write_text(json.dumps(status,indent=2)+'\n')
 dev=[*ROOT.glob('rtl/*.v'),*ROOT.glob('vendor/frozen/*.v'),*ROOT.glob('scripts/*.*'),*ROOT.glob('sim/*.*'),ROOT/'README.md',ROOT/'.gitattributes',ROOT/'FROZEN_CORE_MANIFEST.json',report]
 manifest={'scope':'stage1 single-VL team GMII echo V1.0 fallback','status':status,'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in dev if p.is_file()},'golden_inputs_sha256':sha(package/'runs/rtl_001/golden/sha256.json'),'independent_replay':str(package/'runs/rtl_001'),'independent_verification_sha256':sha(package/'runs/rtl_001/verification.json'),'synthesis_audit_sha256':sha(ROOT/'runs/elinx_001/synthesis_audit.json'),'production_integrity_sha256':sha(ROOT/'runs/production_integrity.json'),'B2_regression_sha256':sha(b2/'verification.json'),'report_sha256':sha(report)}
 (ROOT/'V1_0_EVIDENCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copy2(ROOT/'V1_0_EVIDENCE_MANIFEST.json',package/'V1_0_EVIDENCE_MANIFEST.json')
 files={str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file() and 'work' not in p.relative_to(package).parts and p.name not in ('PACKAGE_MANIFEST.json','PACKAGE_CONTENT_HASHES.json')}
 (package/'PACKAGE_CONTENT_HASHES.json').write_text(json.dumps(files,indent=2)+'\n')
 # Supersede the initial preparation manifest after the proven standalone run.
 (package/'PACKAGE_MANIFEST.json').write_text(json.dumps({'version':'V1.0','profile':'TEAM_GMII_CANDIDATE_NOT_OFFICIAL_COMPATIBILITY','standalone_full_replay':'PASS','files':files,'tool_dependencies':['Python >=3.10','ModelSim 2020.4'],'external_production_source_compile_dependency':False},indent=2)+'\n')
 print('V1_FINALIZED PASS',len(files),'package files hashed')
if __name__=='__main__':main()
