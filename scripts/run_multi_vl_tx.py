"""Real B0 MAC + development multi-VL B1-derived builder regression."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess,csv
from generate_multi_vl_tx_golden import generate
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parent=ROOT/'build/logs';i=1
 while (parent/f'multi_vl_tx_{i:03d}').exists():i+=1
 run=parent/f'multi_vl_tx_{i:03d}';run.mkdir(parents=True)
 names=['afdx_bag_gate.v','afdx_ipv4_checksum.v','mac_gmii_tx.v','mac_frame_store.v','afdx_byte_fifo.v','mac_crc32_byte.v']
 sources=[ROOT/'vendor/frozen'/n for n in names]+[ROOT/'rtl/afdx_multi_vl_tx.v',ROOT/'sim/tb_multi_vl_tx.sv']
 scripts=[Path(__file__),ROOT/'scripts/generate_multi_vl_tx_golden.py',ROOT/'scripts/frozen_frame_reference.py']
 for p in sources+scripts:shutil.copy2(p,run/p.name)
 golden=generate(run/'golden')
 shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']
 commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}+incdir+. {p.name}' for p in sources]
 commands += ['vopt -O5 +acc=nr+tb_multi_vl_tx work.tb_multi_vl_tx -o tx_optimized','vsim -t 1ps -wlf waves.wlf work.tx_optimized',
              'log /tb_multi_vl_tx/reset /tb_multi_vl_tx/gmii_txd /tb_multi_vl_tx/gmii_tx_en','run -all','quit -code 0 -force']
 (run/'run.do').write_text('\n'.join(commands)+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 summary={'result':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'golden':golden,'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sources+scripts},'command':command}
 with (run/'console.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
  summary['modelsim_pid']=process.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
  print(f'MULTI_VL_TX_RUN {run} PID {process.pid}',flush=True)
  code=process.wait(timeout=3600)
 transcript=(run/'transcript.log').read_text(errors='replace')
 passed=code==0 and 'MULTI_VL_TX = PASS' in transcript and 'Errors: 0' in transcript and '** Error' not in transcript and '** Fatal' not in transcript
 performance=None
 if passed:
  actual=(run/'actual_wire.mem').read_bytes();expected=(run/'golden/wire.mem').read_bytes()
  passed=actual==expected
  rows=list(csv.DictReader((run/'frames.csv').open()));cases=json.loads((run/'golden/cases.json').read_text())
  assert len(rows)==len(cases)
  last={};gaps=[]
  for r,c in zip(rows,cases):
   assert int(r['case_id'])==c['id'] and int(r['vl'])==c['vl'] and int(r['wire_bytes'])==c['wire_length']
   assert int(r['end_cycle'])-int(r['start_cycle'])+1==c['wire_length']
   key=(c['epoch'],c['vl']);start=int(r['start_cycle'])
   if key in last:gaps.append(start-last[key])
   last[key]=start
  assert min(gaps)>=125000
  # Exclude post-reset recovery from the sustained window, no artificial byte-rate shortcut.
  duration=(int(rows[4095]['end_cycle'])-int(rows[0]['start_cycle'])+1)*8
  payload=sum(c['length'] for c in cases[:4096]);wire=sum(c['wire_length'] for c in cases[:4096])
  performance={'clock_ns':8,'sustained_frames':4096,'window_ns':duration,'payload_bytes':payload,'wire_bytes':wire,
               'payload_Mbps':payload*8000/duration,'wire_Mbps':wire*8000/duration,
               'ethernet_frame_Mbps':(wire-8*4096)*8000/duration,
               'minimum_per_VL_BAG_cycles':min(gaps),'maximum_per_VL_BAG_cycles':max(gaps),
               'scope':'TX descriptor/payload -> real B0 MAC GMII; RX-to-TX latency NOT RUN',
               'physical_timing':'NOT VERIFIED','full_system_100Mbps':'NOT VERIFIED'}
  (run/'performance.json').write_text(json.dumps(performance,indent=2)+'\n')
 summary.update(result='PASS' if passed else 'FAIL',exit_code=code,completed_utc=datetime.now(timezone.utc).isoformat(),performance=performance,
                artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(transcript[-1800:]);print(json.dumps({'run':str(run),'result':summary['result'],'performance':performance},indent=2))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
