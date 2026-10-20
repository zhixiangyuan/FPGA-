from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
BUILD_ROOT=Path(os.environ.get('AFDX_BUILD_ROOT',ROOT/'build'))
RUN_ROOT=BUILD_ROOT/'logs'
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 frozen=json.loads((ROOT/'FROZEN_CORE_MANIFEST.json').read_text())
 originals_checked=0
 for x in frozen:
  local=ROOT/'vendor/frozen'/Path(x['snapshot']).name
  assert sha(local)==x['sha256']
  if Path(x['original']).exists():
   assert sha(Path(x['original']))==x['sha256'];originals_checked+=1
 RUN_ROOT.mkdir(parents=True,exist_ok=True)
 i=1
 while (RUN_ROOT/f'rtl_{i:03d}').exists():i+=1
 run=RUN_ROOT/f'rtl_{i:03d}';run.mkdir()
 # V1 regression has an explicit sealed profile. Unrelated development RTL
 # is tested by its own runner and must not become a mutable V1 input.
 sources=[*sorted((ROOT/'vendor/frozen').glob('*.v')),
          *[ROOT/'rtl'/n for n in ('AFDX_top.v','afdx_app_echo_queue.v','afdx_gmii_candidate_boundary.v')],
          ROOT/'sim/tb_v1_echo.sv']
 inputs=sources+[ROOT/'scripts/generate_v1_golden.py',ROOT/'scripts/frozen_frame_reference.py',Path(__file__)]
 for p in inputs:shutil.copy2(p,run/p.name)
 with (run/'golden_generation.log').open('wb') as log:
  result=subprocess.run([sys.executable,str(ROOT/'scripts/generate_v1_golden.py'),'--out',str(run/'golden')],stdout=log,stderr=subprocess.STDOUT,timeout=60)
 assert result.returncode==0
 shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 do=['onerror {quit -code 2 -force}','vlib work','vmap work work']
 do += [f'vlog {"-sv" if p.suffix==".sv" else ""} +incdir+{{{run.as_posix()}}} {{{(run/p.name).as_posix()}}}' for p in sources]
 do+=['vopt -O5 -inlineFactor=100 +acc=nr+tb_v1_echo work.tb_v1_echo -o v1_optimized','vsim -t 1ps -onfinish stop -wlf waves.wlf work.v1_optimized',
        'log /tb_v1_echo/reset /tb_v1_echo/rx_data /tb_v1_echo/rx_valid /tb_v1_echo/tx_data /tb_v1_echo/tx_valid /tb_v1_echo/dut/app_data /tb_v1_echo/dut/app_valid /tb_v1_echo/dut/app_ready /tb_v1_echo/dut/psn /tb_v1_echo/dut/echo_banks_busy /tb_v1_echo/dut/candidate_banks_busy','run -all','quit -code 0 -force']
 (run/'run.do').write_text('\n'.join(do)+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 s={'result':'RUNNING','run':str(run),'started_utc':datetime.now(timezone.utc).isoformat(),'sources':[{'path':str(p),'sha256':sha(p),'snapshot_sha256':sha(run/p.name)} for p in inputs],'golden_sha256':sha(run/'golden/sha256.json'),'command':command,'profile':'TEAM_GMII_CANDIDATE_NOT_OFFICIAL_COMPATIBILITY','local_frozen_sources_verified':len(frozen),'upstream_sources_present_and_verified':originals_checked,'source_dependency':'local vendor/frozen only; upstream paths are optional provenance checks'}
 with (run/'console.log').open('wb') as log:
  p=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
  s['modelsim_pid']=p.pid;(run/'summary.json').write_text(json.dumps(s,indent=2)+'\n')
  print('V1_RTL_RUN',run,'PID',p.pid,flush=True);code=p.wait(timeout=3600)
 text=(run/'transcript.log').read_text(errors='replace')
 passed=code==0 and all(x in text for x in ('V1_FULL_ECHO = PASS','V1_PRESSURE_RESET = PASS','V1_PARTIAL_RESET = PASS','Errors: 0')) and '** Fatal' not in text and '** Error' not in text
 s.update(result='PASS' if passed else 'FAIL',exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat())
 s['artifact_hashes']={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'}
 (run/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(text[-3000:]);print('V1_RTL_RESULT',s['result'],run,flush=True)
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
