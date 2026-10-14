"""SNTP raw-packet RTL regression and independent request/timestamp checking."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,hashlib,os,shutil,subprocess
from generate_sntp_golden import generate
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/logs';i=1
 while (parent/f'sntp_{i:03d}').exists():i+=1
 run=parent/f'sntp_{i:03d}';run.mkdir(parents=True)
 inputs=[ROOT/'rtl/afdx_sntp_client.v',ROOT/'sim/tb_sntp.sv',ROOT/'scripts/generate_sntp_golden.py',Path(__file__)]
 for p in inputs:shutil.copy2(p,run/p.name)
 manifest=generate(run/'golden');shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 (run/'run.do').write_text('\n'.join(['onerror {quit -code 2 -force}','vlib work','vmap work work',
  'vlog afdx_sntp_client.v','vlog -sv +incdir+. tb_sntp.sv',
  'vopt -O5 +acc=nr+tb_sntp work.tb_sntp -o sntp_optimized','vsim -t 1ps -wlf waves.wlf work.sntp_optimized',
  'log /tb_sntp/reset /tb_sntp/sync_valid /tb_sntp/timeout /tb_sntp/tx_data /tb_sntp/tx_valid /tb_sntp/rx_data /tb_sntp/rx_valid','run -all','quit -code 0 -force'])+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 summary={'result':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'golden':manifest,
          'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'command':command}
 with (run/'console.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
  summary['modelsim_pid']=process.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
  print(f'SNTP_RUN {run} PID {process.pid}',flush=True);code=process.wait(timeout=600)
 text=(run/'transcript.log').read_text(errors='replace')
 passed=code==0 and 'SNTP_CLIENT = PASS' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
 error=None;checked=0
 if passed:
  try:
   cases=json.loads((run/'golden/cases.json').read_text());rows=list(csv.DictReader((run/'sync.csv').open()))
   assert len(rows)==len(cases)
   for r,c in zip(rows,cases):
    assert int(r['case_id'])==c['id'] and int(r['accepted'])==int(not c['bad']) and int(r['rejected'])==int(c['bad'])
    if not c['bad']:assert [int(r[k],16) for k in ('t1','t2','t3','t4')]==[c[k] for k in ('t1','t2','t3','t4')]
    checked+=1
   tx=list(csv.DictReader((run/'requests.csv').open()));expected=(run/'golden/requests.mem').read_text().splitlines()
   assert [r['data'] for r in tx]==expected
   assert all(int(r['group'])==n//48 and int(r['byte_index'])==n%48 for n,r in enumerate(tx))
  except AssertionError:passed=False;error=f'Independent SNTP check at row {checked}'
 summary.update(result='PASS' if passed else 'FAIL',exit_code=code,independent_cases=checked,error=error,
                completed_utc=datetime.now(timezone.utc).isoformat(),
                artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(text[-1300:])
 print(json.dumps({'run':str(run),'result':summary['result'],'cases':checked,'error':error}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
