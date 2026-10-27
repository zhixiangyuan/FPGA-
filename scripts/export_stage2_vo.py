"""Export a real functional VO from the audited Stage2 synthesis database."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,re,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True)
 project=parser.parse_args().project_dir.resolve();family=project.name.split('_',1)[0]
 assert family in ('AFDXS2','AFDXS2M','AFDXSUB','AFDXTFTP','AFDX615')
 runner_path=project/'synthesis_runner.json';runner=json.loads(runner_path.read_text())
 mapping_path=project/'database_mapping_provenance.json';mapping=json.loads(mapping_path.read_text())
 assert runner['result']=='PASS' and mapping['result']=='PASS'
 source_run=project/f'{family}.runs/synth_1'
 for name,digest in runner['artifacts'].items():
  # TimeQuest rewrites the combined flow report when post-map STA is run.
  # Validate the synthesis database and netlist artifacts, not this mutable summary.
  if name.endswith('.flow.rpt'):continue
  assert sha(source_run/name)==digest
 manifest=json.loads((project/'project_manifest.json').read_text())
 for row in manifest['sources']:assert sha(project/row['snapshot'])==row['sha256']==sha(ROOT/row['canonical_source'])
 parent=ROOT/'build/logs';i=1
 while (parent/f'eda_stage2_export_{i:03d}').exists():i+=1
 run=parent/f'eda_stage2_export_{i:03d}';work=run/f'export_work/{family}';work.parent.mkdir(parents=True)
 shutil.copytree(project,work)
 qsf=work/f'{family}.qsf';qsf.write_text(qsf.read_text().replace(project.as_posix(),work.as_posix()))
 tool=Path(r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_eda.exe')
 command=[str(tool),'--read_settings_files=on','--write_settings_files=off','--simulation=on','--functional=on','--tool=modelsim','--format=verilog',family]
 with (run/'export.log').open('wb') as log:
  code=subprocess.run(command,cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
 generated=work/f'simulation/modelsim/{family}.vo'
 assert code==0 and generated.exists()
 top=manifest['top']
 assert re.search(r'\bmodule\s+'+re.escape(top)+r'\b',generated.read_text(errors='replace'))
 delivered=run/f'{top}.vo';shutil.copy2(generated,delivered)
 proof={'result':'PASS','scope':'real database functional VO export; full simulation not yet executed',
  'completed_utc':datetime.now(timezone.utc).isoformat(),'command':command,'exit_code':code,'source_project':str(project),
  'delivered_netlist':str(delivered),'delivered_netlist_sha256':sha(delivered),'export_log_sha256':sha(run/'export.log'),
  'tool_sha256':sha(tool),'source_manifest_sha256':sha(project/'project_manifest.json'),
  'synthesis_runner_sha256':sha(runner_path),'database_mapping_provenance_sha256':sha(mapping_path),
  'device_GUI':manifest['device']+'/'+manifest['package'],'model_backend':'EP1S80F1508C6 / Stratix compatibility primitives',
  'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED',
  'synthesis_or_implementation_invoked_by_export':False}
 (run/'provenance.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
