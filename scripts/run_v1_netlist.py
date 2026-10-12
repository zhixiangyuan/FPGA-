"""Run exactly one real VO full suite; immutable inputs and durable live logs."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
LIB=Path(r'D:\FPGA\eLinx3.0\Simulation\elinx_lib')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(p,s):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(s,indent=2)+'\n');t.replace(p)
def main():
 lock=ROOT/'runs/V1_NETLIST_RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 i=1
 while (ROOT/f'runs/netlist_{i:03d}').exists():i+=1
 run=ROOT/f'runs/netlist_{i:03d}';run.mkdir();os.write(fd,json.dumps({'runner_pid':os.getpid(),'run':str(run),'started_utc':now()}).encode());os.close(fd)
 s={'result':'PREPARING','run':str(run),'started_utc':now(),'runner_pid':os.getpid()};write(run/'summary.json',s)
 try:
  provenance=ROOT/'runs/eda_export_001/provenance.json';exp=json.loads(provenance.read_text());vo=Path(exp['delivered_netlist']);assert exp['result']=='PASS' and sha(vo)==exp['delivered_netlist_sha256']
  observer=ROOT/'sim/v1_netlist_observer.vh';mapping=json.loads((ROOT/'runs/eda_export_001/observer_mapping.json').read_text());assert mapping['VO_sha256']==sha(vo) and mapping['observer_sha256']==sha(observer)
  compiled=[LIB/'altera_primitives.v',LIB/'220model.v',LIB/'stratix_atoms.v',vo,ROOT/'sim/tb_v1_netlist.sv']
  inputs=compiled+[observer,ROOT/'scripts/generate_v1_golden.py',ROOT/'scripts/frozen_frame_reference.py',Path(__file__)]
  for p in inputs:shutil.copy2(p,run/p.name)
  s['sources']=[{'path':str(p),'sha256':sha(p),'snapshot_sha256':sha(run/p.name)} for p in inputs]
  with (run/'golden_generation.log').open('wb') as log:r=subprocess.run([sys.executable,str(ROOT/'scripts/generate_v1_golden.py'),'--out',str(run/'golden')],stdout=log,stderr=subprocess.STDOUT,timeout=60)
  assert r.returncode==0;s['golden_sha256']=sha(run/'golden/sha256.json')
  shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
  top='tb_v1_netlist';do=['onerror {quit -code 2 -force}','vlib work','vmap work work']
  do += [f'vlog {"-sv" if p.suffix==".sv" else ""} +incdir+{{{run.as_posix()}}} {{{(run/p.name).as_posix()}}}' for p in compiled]
  do += [f'vopt -O5 -inlineFactor=100 +acc=nr+{top} work.{top} -o v1_real_optimized','vsim -t 1ps -onfinish stop -wlf waves.wlf work.v1_real_optimized']
  signals=('reset','rx_data','rx_valid','tx_data','tx_valid','rx_ready','obs_psn','obs_psn_valid','obs_committed','obs_app_busy','obs_parser_busy','obs_mac_busy0','obs_mac_busy1')
  do+=['log '+' '.join(f'/{top}/{n}' for n in signals),'run -all','quit -code 0 -force'];(run/'run.do').write_text('\n'.join(do)+'\n')
  env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
  command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
  proof={'command':command,'compile_sources':[str(run/p.name) for p in compiled],'RTL_DUT_compiled':False,'DUT':'AFDX_top.vo','export_provenance_sha256':sha(provenance),'observer_mapping_sha256':sha(ROOT/'runs/eda_export_001/observer_mapping.json'),'read_only_actual_VO_probes':True,'force_used':False,'clock_ns':8,'BAG_cycles':125000,'SN_wrap':256,'sources':s['sources'],'golden_sha256':s['golden_sha256'],'POST_SYNTH_TIMING':'NOT VERIFIED','EQ6_NATIVE_NETLIST_EQUIVALENCE':'NOT VERIFIED'}
  write(run/'provenance.json',proof)
  with (run/'console.log').open('wb') as log:
   p=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT);s.update(result='RUNNING',modelsim_pid=p.pid);write(run/'summary.json',s);print('V1_REAL_NETLIST_RUN',run,'PID',p.pid,flush=True)
   try:code=p.wait(timeout=86400)
   except subprocess.TimeoutExpired:
    s.update(result='TIMEOUT',completed_utc=now());write(run/'summary.json',s);subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True);raise
  text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and all(n in text for n in ('V1_REAL_NETLIST = PASS','V1_NETLIST_PRESSURE = PASS','V1_NETLIST_PARTIAL_RESET = PASS','Errors: 0')) and '** Fatal' not in text and '** Error' not in text
  s.update(result='PASS' if passed else 'FAIL',exit_code=code,completed_utc=now());s['artifact_hashes']={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'};write(run/'summary.json',s)
  print(text[-1700:]);print('V1_REAL_NETLIST_RESULT',s['result'],run,flush=True)
  return 0 if passed else 1
 except Exception as e:
  s.update(result=s['result'] if s['result']=='TIMEOUT' else 'FAIL',exception=repr(e),completed_utc=now());write(run/'summary.json',s);raise
 finally:
  if lock.exists():lock.replace(run/'runner_closed.lock')
if __name__=='__main__':raise SystemExit(main())
