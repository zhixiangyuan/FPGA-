"""B0 real GMII receive -> multivl parser/SN -> actual application Golden."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,hashlib,os,shutil,subprocess
from generate_multi_vl_rx_golden import generate
from modelsim_support import prepare_ini
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/logs';i=1
 while (parent/f'parallel_rx_{i:03d}').exists():i+=1
 run=parent/f'parallel_rx_{i:03d}';run.mkdir(parents=True)
 names=['mac_crc32_byte.v']
 sources=[ROOT/'vendor/frozen'/n for n in names]+[ROOT/'rtl/afdx_mac_rx_checked.v',ROOT/'rtl/afdx_multi_vl_rx_parser.v',ROOT/'rtl/afdx_multi_vl_sn_gate.v',ROOT/'sim/tb_parallel_rx.sv']
 scripts=[Path(__file__),ROOT/'scripts/generate_multi_vl_rx_golden.py',ROOT/'scripts/frozen_frame_reference.py']
 for p in sources+scripts:shutil.copy2(p,run/p.name)
 manifest=generate(run/'golden')
 prepare_ini(run,MS)
 commands=['onerror {quit -code 2 -force}','vlib work','echo parallel_receive_validation']
 commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}+incdir+. {p.name}' for p in sources]
 commands += ['vopt -O5 +acc=nr+tb_parallel_rx work.tb_parallel_rx -o rx_optimized','vsim -t 1ps -wlf waves.wlf work.rx_optimized',
              'log /tb_parallel_rx/reset /tb_parallel_rx/gmii_rxd /tb_parallel_rx/gmii_rx_dv /tb_parallel_rx/app_data /tb_parallel_rx/app_valid','run -all','quit -code 0 -force']
 (run/'run.do').write_text('\n'.join(commands)+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 summary={'result':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'golden':manifest,
          'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sources+scripts},'command':command}
 with (run/'console.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
  summary['modelsim_pid']=process.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
  print(f'PARALLEL_RX_RUN {run} PID {process.pid}',flush=True);code=process.wait(timeout=3600)
 text=(run/'transcript.log').read_text(errors='replace')
 passed=code==0 and 'PARALLEL_RX = PASS' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
 checked=0;error=None
 if passed:
  cases=json.loads((run/'golden/cases.json').read_text());rows=list(csv.DictReader((run/'decisions.csv').open()))
  payload=(run/'golden/payload.mem').read_text().splitlines();expected=[]
  try:
   assert len(rows)==len(cases)
   for row,case in zip(rows,cases):
    assert [int(row[k]) for k in ('case_id','vlid','sn','action')]==[case[k] for k in ('id','vlid','sn','action')]
    assert int(row['psn'])==(case['psn_after'] if case['psn_after'] is not None else -1)
    assert int(row['app_bytes'])==(case['length'] if case['action']==1 else 0)
    if case['action']==1:expected+=payload[case['payload_offset']:case['payload_offset']+case['length']]
    checked+=1
   assert (run/'actual_app.mem').read_text().splitlines()==expected
  except AssertionError:
   passed=False;error=f'Independent application/SN check at case {checked}'
 summary['parallel_MAC_CRC']=True
 summary.update(result='PASS' if passed else 'FAIL',exit_code=code,independent_cases=checked,error=error,
                completed_utc=datetime.now(timezone.utc).isoformat(),
                artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(text[-1500:]);print(json.dumps({'run':str(run),'result':summary['result'],'cases':checked,'error':error}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
