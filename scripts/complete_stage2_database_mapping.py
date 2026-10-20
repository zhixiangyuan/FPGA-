"""Export post-map VQM from the successful database, then official EQ6 pack."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True)
 project=parser.parse_args().project_dir.resolve();family=project.name.split('_',1)[0]
 assert family in ('AFDXS2','AFDXS2M','AFDXSUB','AFDXTFTP','AFDX615')
 out=project/f'{family}.runs/synth_1'
 manifest=json.loads((project/'project_manifest.json').read_text())
 for row in manifest['sources']:assert sha(project/row['snapshot'])==row['sha256']==sha(ROOT/row['canonical_source'])
 report=out/f'{family}.map.rpt';assert 'Analysis & Synthesis was successful' in report.read_text(errors='replace')
 vqm=out/f'{family}_database.vqm'
 if vqm.exists():raise FileExistsError('Preserve previous VQM export')
 tool=Path(r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_cdb.exe')
 command=[str(tool),'--read_settings_files=on','--write_settings_files=off','--netlist_type=map',f'--vqm={vqm}',family]
 proof={'result':'RUNNING','scope':'actual post-map database VQM and official EQ6 synthesis packing',
  'started_utc':datetime.now(timezone.utc).isoformat(),'command':command,'tool_sha256':sha(tool),
  'source_manifest_sha256':sha(project/'project_manifest.json'),'source_map_report_sha256':sha(report),
  'Implementation':'NOT RUN','Bitstream':'NOT RUN','POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED'}
 with (project/'database_vqm_export.log').open('wb') as log:
  code=subprocess.run(command,cwd=project,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
 proof['export_exit_code']=code;passed=code==0 and vqm.exists()
 if passed:
  template=(ROOT/'build/elinx/AFDXV1_001/AFDXV1.runs/synth_1/AFDXV1_pack.tcl').read_text()
  pack=template.replace('D:/FPGA/captain_integration/build/elinx/AFDXV1_001',project.as_posix()).replace('AFDXV1',family).replace('set topEntity AFDX_top',f'set topEntity {manifest["top"]}')
  # run_pack locates PROJECT.vqm. Copy without changing the exported source.
  regular=out/f'{family}.vqm'
  if regular.exists():raise FileExistsError('Do not overwrite existing VQM')
  regular.write_bytes(vqm.read_bytes())
  packfile=out/f'{family}_database_pack.tcl';packfile.write_text(pack,encoding='utf-8')
  # Captured from the real GUI Run Synthesis process trace: this shared
  # executable runs ONLY the synthesis run_pack Tcl, never place or route.
  assert 'run_pack $dir $prj $topEntity $seriesName $deviceName $packageName $synthName' in pack
  official_pack=Path(r'D:\FPGA\eLinx3.0\bin\shell\bin\run_pack.tcl').read_text(errors='replace')
  assert not any(cmd in official_pack for cmd in ('run_place ', 'run_route ', 'DoPlace', 'DoRoute', 'BitGenerator'))
  infra=Path(r'D:\FPGA\eLinx3.0\bin\shell\bin\Implementation.exe');packcmd=[str(infra),'-f',str(packfile)]
  proof.update(pack_command=packcmd,pack_tool_sha256=sha(infra),pack_script_sha256=sha(packfile),vqm_sha256=sha(vqm))
  with (project/'database_pack.log').open('wb') as log:
   packcode=subprocess.run(packcmd,cwd=infra.parent,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
  proof['pack_exit_code']=packcode
  text=(project/'database_pack.log').read_text(errors='replace')
  passed=packcode==0 and (out/f'{family}_utilization_synth.rpt').exists() and (out/f'{family}_netlist.pb').exists() and (out/f'{family}_eHiChip6.ecp').exists()
  if passed:passed='Synthesis Status : Successful' in (out/f'{family}_utilization_synth.rpt').read_text()
 proof.update(result='PASS' if passed else 'FAIL',completed_utc=datetime.now(timezone.utc).isoformat(),
  artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 (project/'database_mapping_provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({k:v for k,v in proof.items() if k!='artifacts'},indent=2))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
