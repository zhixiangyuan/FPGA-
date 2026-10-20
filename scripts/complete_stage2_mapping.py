"""Complete the documented eLinx VQM + official run_pack synthesis flow."""
from pathlib import Path
import argparse,json,hashlib,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(r'D:\FPGA\eLinx3.0\bin\shell\bin')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True)
 project=parser.parse_args().project_dir.resolve();out=project/'AFDXS2.runs/synth_1'
 manifest=json.loads((project/'project_manifest.json').read_text())
 for r in manifest['sources']:assert sha(project/r['snapshot'])==r['snapshot_sha256']==sha(ROOT/r['canonical_source'])
 assert 'Analysis & Synthesis was successful' in (out/'AFDXS2.map.rpt').read_text(errors='replace')
 if (out/'AFDXS2.vqm').exists():raise FileExistsError('Never overwrite a produced VQM')
 script=out/'AFDXS2_vendor_synthesis.ys'
 commands=[f'read_verilog "{(project/r["snapshot"]).as_posix()}"' for r in manifest['sources']]
 commands.append(f'synth_stratix -top afdx_stage2_top -family eHiChip6 -vqm "{(out/"AFDXS2.vqm").as_posix()}"')
 script.write_text('\n'.join(commands)+'\n')
 command=[str(BIN/'eLinx_synthesis.exe'),'-s',str(script)]
 proof={'result':'RUNNING','scope':'official eLinx VQM synthesis and packing; no placement/routing',
        'started_utc':datetime.now(timezone.utc).isoformat(),'command':command,'source_manifest_sha256':sha(project/'project_manifest.json'),
        'tool_sha256':sha(BIN/'eLinx_synthesis.exe'),'script_sha256':sha(script),
        'native_VQM_and_compatibility_VO_equivalence':'NOT VERIFIED','POST_SYNTH_TIMING':'NOT VERIFIED'}
 (project/'mapping_provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
 with (project/'vendor_synthesis.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=BIN,stdout=log,stderr=subprocess.STDOUT)
  proof['pid']=process.pid;(project/'mapping_provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
  print(f'STAGE2_VENDOR_MAPPING {project} PID {process.pid}',flush=True);code=process.wait(timeout=1800)
 passed=code==0 and (out/'AFDXS2.vqm').exists();pack_code=None
 if passed:
  template=(ROOT/'build/elinx/AFDXV1_001/AFDXV1.runs/synth_1/AFDXV1_pack.tcl').read_text()
  pack=template.replace('D:/FPGA/captain_integration/build/elinx/AFDXV1_001',project.as_posix()).replace('AFDXV1','AFDXS2').replace('set topEntity AFDX_top','set topEntity afdx_stage2_top')
  packfile=out/'AFDXS2_pack.tcl';packfile.write_text(pack,encoding='utf-8')
  pack_command=[str(BIN/'Infrastructure.exe'),'-f',str(packfile)];proof['pack_command']=pack_command;proof['pack_script_sha256']=sha(packfile)
  with (project/'pack_console.log').open('wb') as log:
   pack_code=subprocess.run(pack_command,cwd=BIN,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
  text=(project/'pack_console.log').read_text(errors='replace')
  passed=pack_code==0 and 'pack_gene is 1' in text and (out/'AFDXS2_utilization_synth.rpt').exists() and (out/'AFDXS2_netlist.pb').exists()
 proof.update(result='PASS' if passed else 'FAIL',synthesis_exit_code=code,pack_exit_code=pack_code,
              completed_utc=datetime.now(timezone.utc).isoformat(),
              artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 (project/'mapping_provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({'result':proof['result'],'synthesis_exit_code':code,'pack_exit_code':pack_code,'project':str(project)}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
