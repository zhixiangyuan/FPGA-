"""Run actual 125 MHz RTC RTL and compare rational-clock/sync Golden."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,hashlib,os,shutil,subprocess
from generate_rtc_golden import generate,INITIAL,HZ,MASK
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/logs';i=1
 while (parent/f'rtc_{i:03d}').exists():i+=1
 run=parent/f'rtc_{i:03d}';run.mkdir(parents=True)
 inputs=[ROOT/'rtl/afdx_rtc_timebase.v',ROOT/'sim/tb_rtc_timebase.sv',ROOT/'scripts/generate_rtc_golden.py',Path(__file__)]
 for p in inputs:shutil.copy2(p,run/p.name)
 reference=generate(run/'golden')
 shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 (run/'run.do').write_text('\n'.join(['onerror {quit -code 2 -force}','vlib work','vmap work work',
  'vlog afdx_rtc_timebase.v','vlog -sv tb_rtc_timebase.sv',
  'vopt -O5 +acc=nr+tb_rtc_timebase work.tb_rtc_timebase -o rtc_optimized',
  'vsim -t 1ps -wlf waves.wlf work.rtc_optimized','log /tb_rtc_timebase/utc_time /tb_rtc_timebase/sync_valid /tb_rtc_timebase/reset','run -all','quit -code 0 -force'])+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 with (run/'console.log').open('wb') as log:
  code=subprocess.run(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
 text=(run/'transcript.log').read_text(errors='replace')
 passed=code==0 and 'RTC_TIMEBASE = PASS' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
 checked=0;error=None
 if passed:
  rows=list(csv.DictReader((run/'actual_rtc.csv').open()))
  accumulated_offset=0;accepted=0;rejected=0;last_offset=0;last_delay=0;previous_mono=0
  try:
   assert len(rows)==len(reference)
   for a,r in zip(rows,reference):
    mono=int(a['monotonic_cycles']);assert mono==previous_mono+r['cycles'];previous_mono=mono
    if r['kind']==1:
     if r['valid']:
      accumulated_offset+=r['offset'];accepted+=1;last_offset=r['offset'];last_delay=r['delay']
     else:rejected+=1
    expected=(INITIAL+(mono*(1<<32))//HZ+accumulated_offset)&MASK
    assert int(a['utc_time'],16)==expected
    assert int(a['last_offset'])==last_offset and int(a['last_delay'])==last_delay
    assert int(a['sync_count'])==accepted and int(a['error_count'])==rejected
    checked+=1
  except AssertionError:
   passed=False;error=f'Independent rational/sync comparison at row {checked}'
 summary={'result':'PASS' if passed else 'FAIL','exit_code':code,'independent_samples':checked,'error':error,
          'scope':'Q32.32 timebase and validated four-timestamp arithmetic; network SNTP NOT RUN',
          'clock_Hz':HZ,'quantization_bound_NTP_LSB':1,'completed_utc':datetime.now(timezone.utc).isoformat(),
          'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},
          'artifacts':{p.name:sha(p) for p in run.iterdir() if p.is_file()}}
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(text[-1000:]);print(json.dumps({'run':str(run),'result':summary['result'],'samples':checked,'error':error}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
