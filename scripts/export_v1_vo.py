"""Export a real functional VO from a successful database copy; no map/fit."""
from pathlib import Path
import json,hashlib,shutil,subprocess,re
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 gui=ROOT/'runs/elinx_001/AFDXV1';base=gui.parent
 audit=json.loads((base/'synthesis_audit.json').read_text());assert audit['result']=='PASS'
 for n,h in audit['synthesis_artifact_hashes'].items():assert sha(gui/'AFDXV1.runs/synth_1'/n)==h,n
 for row in json.loads((base/'project_manifest.json').read_text())['sources']:
  assert sha(Path(row['original']))==row['sha256'] and sha(Path(row['snapshot']))==row['snapshot_sha256']
 i=1
 while (ROOT/f'runs/eda_export_{i:03d}').exists():i+=1
 run=ROOT/f'runs/eda_export_{i:03d}';work=run/'export_work/AFDXV1';work.parent.mkdir(parents=True);shutil.copytree(gui,work)
 qsf=work/'AFDXV1.qsf';qsf.write_text(qsf.read_text().replace(gui.as_posix(),work.as_posix()))
 tool=Path(r'D:\FPGA\eLinx3.0\bin\Passkey\bin\quartus_eda.exe')
 command=[str(tool),'--read_settings_files=on','--write_settings_files=off','--simulation=on','--functional=on','--tool=modelsim','--format=verilog','AFDXV1']
 started=datetime.now(timezone.utc).isoformat();r=subprocess.run(command,cwd=work,capture_output=True,timeout=300)
 log=r.stdout+r.stderr;(run/'export.log').write_bytes(log);vo=work/'simulation/modelsim/AFDXV1.vo'
 passed=r.returncode==0 and vo.is_file() and '0 errors' in log.decode(errors='replace').lower()
 assert passed and re.search(r'\bmodule\s+AFDX_top\b',vo.read_text(errors='replace'))
 dst=run/'AFDX_top.vo';shutil.copy2(vo,dst)
 p={'result':'PASS','started_utc':started,'completed_utc':datetime.now(timezone.utc).isoformat(),'command':command,'exit_code':r.returncode,'gui_project':str(gui),'copy_work':str(work),'eda_tool_sha256':sha(tool),'export_log_sha256':sha(run/'export.log'),'delivered_netlist':str(dst),'delivered_netlist_sha256':sha(dst),'synthesis_audit_sha256':sha(base/'synthesis_audit.json'),'device_GUI':'EQ6HL45/CSG225','model_backend':'EP1S80F1508C6 / Stratix compatibility primitive model','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED','synthesis_or_fit_executed':False}
 (run/'provenance.json').write_text(json.dumps(p,indent=2)+'\n');print(log.decode(errors='replace')[-1500:]);print('V1_REAL_VO_EXPORT PASS',dst)
if __name__=='__main__':main()
