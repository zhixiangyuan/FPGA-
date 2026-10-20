"""Execute SNMP agent RTL; compare raw BER and actual MIB/counter changes."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,hashlib,os,shutil,subprocess
from generate_snmp_golden import generate
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/logs';i=1
 while (parent/f'snmp_{i:03d}').exists():i+=1
 run=parent/f'snmp_{i:03d}';run.mkdir(parents=True)
 inputs=[ROOT/'rtl/afdx_snmp_agent.v',ROOT/'sim/tb_snmp.sv',ROOT/'scripts/generate_snmp_golden.py',Path(__file__)]
 for p in inputs:shutil.copy2(p,run/p.name)
 manifest=generate(run/'golden');shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 (run/'run.do').write_text('\n'.join(['onerror {quit -code 2 -force}','vlib work','vmap work work',
  'vlog afdx_snmp_agent.v','vlog -sv +incdir+. tb_snmp.sv',
  'vopt -O5 +acc=nr+tb_snmp work.tb_snmp -o snmp_optimized','vsim -t 1ps -wlf waves.wlf work.snmp_optimized',
  'log /tb_snmp/reset /tb_snmp/in_data /tb_snmp/in_valid /tb_snmp/out_data /tb_snmp/out_valid','run -all','quit -code 0 -force'])+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 with (run/'console.log').open('wb') as log:
  code=subprocess.run(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
 text=(run/'transcript.log').read_text(errors='replace');error=None;checked=0
 passed=code==0 and 'SNMP_AGENT = PASS' in text and 'Errors: 0' in text and '** Error' not in text and '** Fatal' not in text
 if passed:
  try:
   cases=json.loads((run/'golden/cases.json').read_text());expected=(run/'golden/responses.mem').read_text().splitlines()
   actual=list(csv.DictReader((run/'actual_snmp.csv').open()));events=list(csv.DictReader((run/'snmp_events.csv').open()))
   assert [r['data'] for r in actual]==expected
   position=0;counts=[0,0,0,0]
   for c,event in zip(cases,events):
    for k in range(c['output_length']):
     assert int(actual[position]['case_id'])==c['id'] and int(actual[position]['byte_index'])==k;position+=1
    if c['trap']:counts[3]+=1
    elif c['output_length']:
     counts[0]+=1;counts[1]+=1;counts[2]+=int(c['error_status']!=0)
    else:counts[2]+=1
    assert int(event['case_id'])==c['id'] and int(event['response_bytes'])==c['output_length']
    assert int(event['name_length'])==len(c['expected_sys_name'])
    assert [int(event[k]) for k in ('request_count','response_count','error_count','trap_count')]==counts
    checked+=1
   assert len(events)==len(cases)
  except AssertionError:passed=False;error=f'Independent BER/MIB check at case {checked}'
 summary={'result':'PASS' if passed else 'FAIL','exit_code':code,'independent_cases':checked,'error':error,'golden':manifest,
          'scope':'SNMPv1 bounded MIB agent RTL; GMII system integration NOT RUN',
          'completed_utc':datetime.now(timezone.utc).isoformat(),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},
          'artifacts':{p.name:sha(p) for p in run.iterdir() if p.is_file()}}
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(text[-1500:]);print(json.dumps({'run':str(run),'result':summary['result'],'cases':checked,'error':error}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
