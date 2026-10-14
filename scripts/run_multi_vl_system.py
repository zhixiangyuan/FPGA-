"""Sixteen-VL GMII RX -> parser/SN -> queue/scheduler -> B0 MAC TX."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict,deque
import argparse,json,csv,hashlib,os,shutil,subprocess,struct
from generate_multi_vl_rx_golden import generate
from frozen_frame_reference import make_client,wire_for
ROOT=Path(__file__).resolve().parents[1]
MS=Path(os.environ.get('MODELSIM_BIN',r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--performance',action='store_true');args=parser.parse_args()
 parent=ROOT/'build/logs';i=1
 while (parent/f'multi_vl_system_{i:03d}').exists():i+=1
 run=parent/f'multi_vl_system_{i:03d}';run.mkdir(parents=True)
 sources=sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in
  ('afdx_multi_vl_rx_parser.v','afdx_multi_vl_sn_gate.v','afdx_multi_vl_echo_queue.v','afdx_multi_vl_tx.v','afdx_stage2_top.v')]+[ROOT/'sim/tb_multi_vl_rx.sv']
 scripts=[Path(__file__),ROOT/'scripts/generate_multi_vl_rx_golden.py',ROOT/'scripts/frozen_frame_reference.py']
 for p in sources+scripts:shutil.copy2(p,run/p.name)
 manifest=generate(run/'golden',performance=args.performance);shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
 commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']
 defines='+define+SYSTEM_ECHO'+('+PERFORMANCE_LOAD' if args.performance else '')
 commands += [f'vlog {"-sv "+defines+" " if p.suffix==".sv" else ""}+incdir+. {p.name}' for p in sources]
 commands += ['vopt -O5 +acc=nr+tb_multi_vl_rx work.tb_multi_vl_rx -o system_optimized','vsim -t 1ps -wlf waves.wlf work.system_optimized',
  'log /tb_multi_vl_rx/reset /tb_multi_vl_rx/gmii_rxd /tb_multi_vl_rx/gmii_rx_dv /tb_multi_vl_rx/tx_data /tb_multi_vl_rx/tx_valid','run -all','quit -code 0 -force']
 (run/'run.do').write_text('\n'.join(commands)+'\n')
 env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
 command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
 summary={'result':'RUNNING','started_utc':datetime.now(timezone.utc).isoformat(),'golden':manifest,
          'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sources+scripts},'command':command}
 with (run/'console.log').open('wb') as log:
  process=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
  summary['modelsim_pid']=process.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
  print(f'MULTI_VL_SYSTEM_RUN {run} PID {process.pid}',flush=True);code=process.wait(timeout=3600)
 text=(run/'transcript.log').read_text(errors='replace');error=None;checked=0;latencies=[]
 passed=code==0 and 'MULTI_VL_SYSTEM = PASS' in text and 'Errors: 0' in text and '** Fatal' not in text and '** Error' not in text
 if passed:
  try:
   cases=json.loads((run/'golden/cases.json').read_text());expected=defaultdict(deque);next_sn=defaultdict(lambda:1)
   expected_payload=[];payload=(run/'golden/payload.mem').read_text().splitlines()
   for c in cases:
    if c['action']!=1:continue
    client,_=make_client(c['id'],c['length'],next_sn[c['vlid']]);next_sn[c['vlid']]=next_sn[c['vlid']]%255+1
    client=client[:4]+struct.pack('!H',c['vlid'])+client[6:34]+struct.pack('!HH',c['src_port'],c['dst_port'])+client[38:]
    expected[c['vlid']].append((c,wire_for(client)))
    expected_payload+=payload[c['payload_offset']:c['payload_offset']+c['length']]
   assert (run/'actual_app.mem').read_text().splitlines()==expected_payload
   actual=bytes.fromhex((run/'actual_echo.mem').read_text());events=list(csv.DictReader((run/'tx_events.csv').open()))
   inputs={int(r['case_id']):r for r in csv.DictReader((run/'input_events.csv').open())}
   offset=0;last={};gaps=[]
   for event in events:
    size=int(event['wire_bytes']);wire=actual[offset:offset+size];offset+=size
    vl=int(event['vlid']);c,golden=expected[vl].popleft();assert wire==golden
    start=int(event['start_cycle']);end=int(event['end_cycle']);assert end-start+1==len(wire)
    if vl in last:gaps.append(start-last[vl]);assert start-last[vl]>=125000
    last[vl]=start;r=inputs[c['id']]
    latencies.append({'case_id':c['id'],'vlid':vl,'tx_start_cycle':start,'tx_end_cycle':end,'wire_bytes':len(wire),
                      'rx_first_to_tx_first_ns':(start-int(r['start_cycle']))*8,
                      'rx_last_to_tx_first_ns':(start-int(r['end_cycle']))*8,'rx_first_to_tx_last_ns':(end-int(r['start_cycle']))*8})
    checked+=1
   assert offset==len(actual) and all(not q for q in expected.values())
   assert len(events)==manifest['accepted']
   performance={'scope':'4404 directed correctness cases, not continuous maximum offered-load throughput',
    'clock_ns':8,'frames_compared':checked,'minimum_per_VL_BAG_cycles':min(gaps),
    'latency_ranges':{key:{'min':min(r[key] for r in latencies),'max':max(r[key] for r in latencies)} for key in latencies[0] if key.endswith('_ns')},
    '100Mbps_system_compliance':'NOT VERIFIED','physical_timing':'NOT VERIFIED'}
   if args.performance:
    load=[r for r in latencies if r['case_id']<4096]
    duration=(max(r['tx_end_cycle'] for r in load)-min(r['tx_start_cycle'] for r in load)+1)*8
    payload_bytes=sum(c['length'] for c in cases[:4096]);wire_bytes=sum(r['wire_bytes'] for r in load)
    rates={'Payload_Mbps':payload_bytes*8000/duration,'GMII_wire_Mbps':wire_bytes*8000/duration,
           'Ethernet_frame_Mbps':(wire_bytes-8*len(load))*8000/duration}
    latency_keys=('rx_first_to_tx_first_ns','rx_last_to_tx_first_ns','rx_first_to_tx_last_ns')
    load_latency={k:{'min':min(r[k] for r in load),'max':max(r[k] for r in load),
                     'range_jitter_ns':max(r[k] for r in load)-min(r[k] for r in load)} for k in latency_keys}
    performance.update(scope='4096 full-payload frames, 16VL, real 1ms minimum BAG; 8000-cycle global offered interval',
                       sustained_window_ns=duration,rates=rates,loaded_latency_ranges=load_latency,
                       **{'100Mbps_system_compliance':'PASS for this explicitly bounded offered-load profile'})
    assert rates['Payload_Mbps']>=100 and all(load_latency[k]['max']<=2000000 for k in latency_keys)
   (run/'latencies.json').write_text(json.dumps(latencies,indent=2)+'\n');(run/'performance.json').write_text(json.dumps(performance,indent=2)+'\n')
  except (AssertionError,IndexError,KeyError):passed=False;error=f'Independent echo comparison at frame {checked}'
 summary.update(result='PASS' if passed else 'FAIL',exit_code=code,echo_frames_compared=checked,error=error,
                completed_utc=datetime.now(timezone.utc).isoformat(),artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
 (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(text[-1500:])
 print(json.dumps({'run':str(run),'result':summary['result'],'frames':checked,'error':error}))
 return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
