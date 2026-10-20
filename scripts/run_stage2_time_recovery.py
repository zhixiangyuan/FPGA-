"""Full management-top SNTP repeated exchange, invalid origin, 1s timeout and reset."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import shutil
import subprocess
from run_stage2_mgmt import RTL, MS, ROOT
from generate_stage2_mgmt_golden import afdx_frame, sntp_packet, SNTP_DA, ES_MAC, ES_IP, MANAGER_MAC, MANAGER_IP
from frozen_frame_reference import wire_for

INITIAL=0xe900000000000000
MASK=(1<<64)-1


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(run):
    events=list(csv.DictReader((run/'time_events.csv').open()))
    txrows=list(csv.DictReader((run/'tx_bytes.csv').open()))
    rxrows=list(csv.DictReader((run/'rx_bytes.csv').open()))
    corrections=[];expected_t1={};sync_count=0;timeouts=[]
    signed=lambda n:n-(1<<64) if n>>63 else n
    def utc(cycle):
        return (INITIAL+cycle*(1<<32)//125000000+sum(offset for edge,offset in corrections if edge<cycle))&MASK
    capture={};route_delays=[]
    for e in events:
        assert int(e['epoch'])==0
        cycle=int(e['cycle']);group=int(e['group'])
        if e['event']=='trigger':
            assert group not in expected_t1
            expected_t1[group]=utc(cycle)
        elif e['event']=='capture':capture[group]=cycle
        elif e['event']=='sync':
            a,b,c,d=(int(e[k],16) for k in ('t1','t2','t3','t4'))
            assert a==expected_t1[group] and b==a+0x100000 and c==b+2748
            assert d==utc(capture[group]), f'RTC receive reference group {group}'
            delay=signed((d-a)&MASK)-signed((c-b)&MASK)
            offset=(signed((b-a)&MASK)+signed((c-d)&MASK))>>1
            assert 0<=delay<=1<<32
            corrections.append((cycle,offset));sync_count+=1
        elif e['event']=='timeout':
            trigger=next(int(x['cycle']) for x in events if x['event']=='trigger' and int(x['group'])==group)
            assert group==2 and 125000000<=cycle-trigger<=125000100
            timeouts.append(cycle-trigger)
    assert sorted(expected_t1)==[0,1,2,3,4] and sync_count==3 and len(timeouts)==1
    tx_groups={}
    for row in txrows: tx_groups.setdefault(int(row['group']),[]).append(row)
    queue_delays=[]
    for group, rows in tx_groups.items():
        assert [int(r['index']) for r in rows]==list(range(103))
        data=bytes(int(r['data'],16) for r in rows)
        reference=wire_for(afdx_frame(SNTP_DA,ES_MAC,ES_IP,MANAGER_IP,49152,123,
                                      sntp_packet(3,transmit=expected_t1[group]),group+1))
        assert data==reference, f'outgoing request {group}'
        trigger=next(int(e['cycle']) for e in events if e['event']=='trigger' and int(e['group'])==group)
        queue_delays.append((int(rows[0]['cycle'])-trigger)*8)
    assert len(tx_groups)==5
    packets=[]
    for row in rxrows:
        if int(row['index'])==0:packets.append([])
        packets[-1].append(row)
    assert len(packets)==5
    for packet_index,(packet,(group,wrong,sn)) in enumerate(zip(packets,[(0,False,1),(1,True,3),(1,False,3),(1,False,4),(3,False,5)])):
        a=expected_t1[group]
        reference=wire_for(afdx_frame(SNTP_DA,MANAGER_MAC,MANAGER_IP,ES_IP,123,49152,
                         sntp_packet(4,stratum=2,origin=a^int(wrong),receive=a+0x100000,transmit=a+0x100000+2748),sn))
        assert bytes(int(r['data'],16) for r in packet)==reference
        next_wire=int(packets[packet_index+1][0]['cycle']) if packet_index+1<len(packets) else 1<<63
        matching=[int(e['cycle']) for e in events if e['event']=='capture' and int(e['group'])==group and int(packet[0]['cycle'])<=int(e['cycle'])<next_wire]
        if packet_index==2:assert not matching, 'duplicate reached SNTP'
        else:route_delays.append((min(matching)-int(packet[0]['cycle']))*8)
    counters={r['key']:int(r['value']) for r in csv.DictReader((run/'counters.csv').open())}
    assert counters==dict(accepted=3,rejected=1,timeout=1,sync=3,gate_duplicate=1,gate_missing=1),counters
    return dict(requests=5,valid_synchronizations=3,invalid_origin_rejected=1,duplicate_SN_rejected=1,missing_SN_count=1,
                real_timeout_cycles=timeouts[0],reset_cancels_pending=True,
                request_enqueue_to_GMII_ns=queue_delays,reply_GMII_to_routed_timestamp_ns=route_delays,
                UTC_reference='independent cycle/rational tick plus independently recomputed accepted offsets',
                source_timestamp='enqueue',destination_timestamp='routed first payload byte',VO='NOT RUN')


def main():
    parent=ROOT/'build/logs';index=1
    while (parent/f'mgmt_time_{index:03d}').exists():index+=1
    run=parent/f'mgmt_time_{index:03d}';run.mkdir(parents=True)
    sources=sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in RTL]+[ROOT/'sim/tb_stage2_time_recovery.sv']
    scripts=[Path(__file__),ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/frozen_frame_reference.py']
    inputs=sources+scripts
    for p in inputs:shutil.copy2(p,run/p.name)
    template=wire_for(afdx_frame(SNTP_DA,MANAGER_MAC,MANAGER_IP,ES_IP,123,49152,sntp_packet(4,stratum=2),1))
    assert len(template)==103
    (run/'reply_template.mem').write_text(''.join(f'{b:02x}\n' for b in template))
    shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
    commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""} {p.name}' for p in sources]
    commands += ['vopt -O5 work.tb_stage2_time_recovery -o time_optimized','vsim -t 1ps work.time_optimized','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),
                 inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs})
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        summary['pid']=proc.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(f'TIME_RECOVERY_RUN {run} PID {proc.pid}',flush=True);code=proc.wait(timeout=3600)
    transcript=(run/'transcript.log').read_text(errors='replace')
    passed=code==0 and 'TIME_SYSTEM_RECOVERY = PASS' in transcript and '** Fatal' not in transcript and '** Error' not in transcript
    evidence={};error=None
    if passed:
        try:
            evidence=verify(run)
            for p in inputs:assert sha(p)==summary['inputs'][str(p.relative_to(ROOT))]==sha(run/p.name)
        except (AssertionError,KeyError,ValueError,IndexError) as exc:passed=False;error=str(exc)
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,
                   completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(transcript[-1400:]);print(json.dumps(dict(run=str(run),result=summary['result'],error=error,evidence=evidence),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
