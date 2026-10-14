"""Export a real functional VO from the audited Stage2 synthesis database."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,re,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True)
 project=parser.parse_args().project_dir.resolve();audit_path=project/'synthesis_audit.json'
 audit=json.loads(audit_path.read_text());assert audit['result']=='PASS'
 source_run=project/'AFDXS2.runs/synth_1'
 for name,digest in audit['synthesis_artifact_hashes'].items():assert sha(source_run/name)==digest
 manifest=json.loads((project/'project_manifest.json').read_text())
 for row in manifest['sources']:assert sha(project/row['snapshot'])==row['sha256']==sha(ROOT/row['canonical_source'])
 parent=ROOT/'build/logs';i=1
 while (parent/f'eda_stage2_export_{i:03d}').exists():i+=1
 run=parent/f'eda_stage2_export_{i:03d}';work=run/'export_work/AFDXS2';work.parent.mkdir(parents=True)
 shutil.copytree(project,work)
 qsf=work/'AFDXS2.qsf';qsf.write_text(qsf.read_text().replace(project.as_posix(),work.as_posix()))
 tool=Path(r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_eda.exe')
 command=[str(tool),'--read_settings_files=on','--write_settings_files=off','--simulation=on','--functional=on','--tool=modelsim','--format=verilog','AFDXS2']
 with (run/'export.log').open('wb') as log:
  code=subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
 generated=work/'simulation/modelsim/AFDXS2.vo'
 assert code==0 and generated.exists()
 assert re.search(r'\bmodule\s+afdx_stage2_top\b',generated.read_text(errors='replace'))
 delivered=run/'afdx_stage2_top.vo';shutil.copy2(generated,delivered)
 proof={'result':'PASS','scope':'real database functional VO export; full simulation not yet executed',
  'completed_utc':datetime.now(timezone.utc).isoformat(),'command':command,'exit_code':code,'source_project':str(project),
  'delivered_netlist':str(delivered),'delivered_netlist_sha256':sha(delivered),'export_log_sha256':sha(run/'export.log'),
  'tool_sha256':sha(tool),'source_manifest_sha256':sha(project/'project_manifest.json'),'synthesis_audit_sha256':sha(audit_path),
  'device_GUI':'EQ6HL45/CSG225','model_backend':'EP1S80F1508C6 / Stratix compatibility primitives',
  'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED',
  'synthesis_or_implementation_invoked_by_export':False}
 (run/'provenance.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
