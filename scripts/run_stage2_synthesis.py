"""Run the bundled synthesis front end and official eHiWay synthesis packing.

Reuse GUI-generated project settings in a fresh ignored build. No fitting,
implementation, programming, or vendor-model substitution is invoked.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,os,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--project-dir',type=Path,required=True);parser.add_argument('--settings-reference',type=Path,required=True)
 parser.add_argument('--optimization-technique',choices=('BALANCED','SPEED'),default='BALANCED')
 args=parser.parse_args();project=args.project_dir.resolve();reference=args.settings_reference.resolve()
 manifest=json.loads((project/'project_manifest.json').read_text())
 family=project.name.split('_',1)[0];top=manifest['top']
 assert (family,top) in (('AFDXS2','afdx_stage2_top'),('AFDXS2M','afdx_stage2_mgmt_top'),('AFDXSUB','AFDX_top'),('AFDXTFTP','afdx_tftp_file_endpoint'),('AFDX615','afdx_615a_endpoint'))
 assert manifest['device']=='EQ6HL45' and manifest['package']=='CSG225' and manifest['clock_constraint_ns']==8
 for r in manifest['sources']:
  assert sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot'])
 for suffix in ('.qsf','.qpf'):
  name=family+suffix;target=project/name
  text=(reference/('AFDXS2'+suffix)).read_text().replace('AFDXS2',family)
  text=text.replace(reference.as_posix().replace('AFDXS2',family),project.as_posix())
  if name.endswith('.qsf'):
   text,count=re.subn(r'set_global_assignment -name STRATIX_OPTIMIZATION_TECHNIQUE \w+',
    'set_global_assignment -name STRATIX_OPTIMIZATION_TECHNIQUE '+args.optimization_technique,text)
   assert count==1,'expected one explicit synthesis optimization setting'
   constraint=project/f'{family}.srcs/constrs_1/new/clock_125mhz.edc'
   text=re.sub(r'set_global_assignment -name VERILOG_FILE "[^"]+"\n','',text)
   text='\n'.join(line for line in text.splitlines() if not line.startswith('set_global_assignment -name SDC_FILE'))+'\n'
   text=text.replace('TOP_LEVEL_ENTITY afdx_stage2_top',f'TOP_LEVEL_ENTITY {top}')
   text+=''.join(f'set_global_assignment -name VERILOG_FILE "{(project/r["snapshot"]).as_posix()}"\n' for r in manifest['sources'])
   text+='\nset_global_assignment -name SDC_FILE "'+constraint.as_posix()+'"\n'
   assert f'TOP_LEVEL_ENTITY {top}' in text
   assert f'PROJECT_OUTPUT_DIRECTORY "{(project/f"{family}.runs/synth_1").as_posix()}"' in text
   paths=re.findall(r'VERILOG_FILE "([^"]+)"',text)
   assert set(paths)=={(project/r['snapshot']).as_posix() for r in manifest['sources']}
  if target.exists():
   if target.read_text()!=text:raise RuntimeError(f'Existing settings differ: {target}')
  else:target.write_text(text,encoding='utf-8')
 out=project/f'{family}.runs/synth_1';out.mkdir(parents=True,exist_ok=True)
 psf=(reference/'AFDXS2.runs/synth_1/AFDXS2.run.psf').read_text().replace('AFDXS2',family)
 (out/f'{family}.run.psf').write_text(psf)
 # GUI branding says ehiway_map; the installed executable is quartus_map.
 # Record the actual tool rather than inventing an absent binary.
 def find_map_tool():
  candidates=[os.environ.get('ELINX_MAP_EXE'),
              r'D:\elinx\eLinx3.0\bin\Passkey\bin\quartus_map.exe',
              r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_map.exe']
  for candidate in candidates:
   if candidate and Path(candidate).is_file():return Path(candidate)
  raise SystemExit('quartus_map.exe not found; set ELINX_MAP_EXE to its absolute path')
 tool=find_map_tool()
 command=[str(tool),'--read_settings_files=on','--write_settings_files=off',family]
 proof={'result':'RUNNING','command':command,'started_utc':datetime.now(timezone.utc).isoformat(),
        'optimization_technique':args.optimization_technique,'settings_qsf_sha256':sha(project/f'{family}.qsf'),
        'source_manifest_sha256':sha(project/'project_manifest.json'),
        'driver_sha256':sha(tool),'settings_reference':str(reference),'settings_reference_sha256':sha(reference/'AFDXS2.qsf'),
        'GUI_invocation':False,'bundled_frontend_executable':'quartus_map.exe','device_GUI_profile':'EQ6HL45/CSG225',
        'functional_model_backend':'EP1S80F1508C6 / Stratix compatibility','Implementation':'NOT RUN','Bitstream':'NOT RUN',
        'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED'}
 (project/'synthesis_runner.json').write_text(json.dumps(proof,indent=2)+'\n')
 with (project/'synthesis_console.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=project,stdout=log,stderr=subprocess.STDOUT)
  proof['pid']=process.pid;(project/'synthesis_runner.json').write_text(json.dumps(proof,indent=2)+'\n')
  print(f'STAGE2_OFFICIAL_SYNTHESIS {project} PID {process.pid}',flush=True);code=process.wait(timeout=1800)
 report=out/f'{family}.map.rpt';text=report.read_text(errors='replace') if report.exists() else ''
 passed=code==0 and 'Analysis & Synthesis was successful' in text and 'Error (' not in text
 backend_code=None
 if passed:
  mapping_command=[sys.executable,str(ROOT/'scripts/complete_stage2_database_mapping.py'),'--project-dir',str(project)]
  proof['database_mapping_command']=mapping_command
  with (project/'mapping_closure.log').open('wb') as log:
   backend_code=subprocess.run(mapping_command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=900).returncode
  mapping=json.loads((project/'database_mapping_provenance.json').read_text())
  passed=backend_code==0 and mapping['result']=='PASS'
 proof.update(result='PASS' if passed else 'FAIL',exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat(),
              artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()},
              backend_exit_code=backend_code,eHiWay_backend_artifacts_present=(out/f'{family}_netlist.pb').exists())
 (project/'synthesis_runner.json').write_text(json.dumps(proof,indent=2)+'\n');print(text[-1600:]);print(json.dumps(proof,indent=2))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
