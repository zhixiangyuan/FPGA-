"""Check the real management RTL top under 16-VL sustained mixed traffic."""
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from generate_stage2_mixed_golden import generate
from run_stage2_mgmt import RTL

ROOT = Path(__file__).resolve().parents[1]
MS = Path(os.environ.get('MODELSIM_BIN', r'D:\FPGA\Modlesim20.4\ModelSim20.4\win64'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run, manifest):
    cases = json.loads((run/'golden/cases.json').read_text())
    expected = json.loads((run/'golden/expected.json').read_text())
    golden = bytes.fromhex((run/'golden/expected_tx.mem').read_text())
    actual = bytes.fromhex((run/'actual_tx.mem').read_text())
    tx = list(csv.DictReader((run/'tx_events.csv').open()))
    rx = {int(r['id']): r for r in csv.DictReader((run/'rx_events.csv').open())}
    assert len(rx)==len(cases), 'missing input frame records'
    assert len(tx)==len(expected), f'output count {len(tx)} vs {len(expected)}'
    queues = defaultdict(deque)
    for c in expected:
        queues[c['vlid']].append(c)
    previous = {}
    sntp_wire_start = None
    minimum_gaps = {}
    per_vl_latencies = defaultdict(list)
    records = []
    position = 0
    for event in tx:
        size = int(event['bytes'])
        frame = actual[position:position+size]
        position += size
        vl = int.from_bytes(frame[12:14], 'big')
        assert queues[vl], f'unexpected output VL {vl:04x}'
        c = queues[vl].popleft()
        assert frame == golden[c['tx_offset']:c['tx_offset']+c['tx_length']], c['name']
        start, end = int(event['start_cycle']), int(event['end_cycle'])
        assert end-start+1 == size == c['tx_length'], c['name']
        if vl in previous:
            gap = start-previous[vl]
            assert gap >= 125000, f'BAG {vl:04x}: {gap}'
            minimum_gaps[hex(vl)] = min(minimum_gaps.get(hex(vl), gap), gap)
        previous[vl] = start
        if c['input_id'] is None:
            sntp_wire_start = start
            continue
        source = rx[c['input_id']]
        first, last = int(source['start_cycle']), int(source['end_cycle'])
        row = dict(name=c['name'], kind=c['kind'], vlid=vl, rx_start=first,
                   tx_start=start, tx_end=end, payload_bytes=c['payload_length'], wire_bytes=size,
                   first_to_first_ns=(start-first)*8, last_to_first_ns=(start-last)*8,
                   first_to_last_ns=(end-first)*8)
        assert 0 <= row['first_to_first_ns'] <= row['first_to_last_ns'] <= 2000000, row
        records.append(row)
        if c['kind']=='business':
            per_vl_latencies[vl].append(row['first_to_first_ns'])
    assert position==len(actual)==len(golden), 'trailing bytes'
    assert all(not q for q in queues.values()), 'missing expected output'
    previous_input = {}
    for c in cases:
        source = rx[c['id']]
        assert int(source['bytes'])==c['rx_length']
        assert int(source['start_cycle'])==c['start_cycle'], 'source schedule mismatch'
        if c['kind']=='business':
            start = int(source['start_cycle'])
            if c['vlid'] in previous_input:
                assert start-previous_input[c['vlid']]>=125000, 'illegal offered BAG'
            previous_input[c['vlid']] = start
    business = [r for r in records if r['kind']=='business']
    duration = (max(r['tx_end'] for r in business)-min(r['rx_start'] for r in business)+1)*8
    output_window = (max(r['tx_end'] for r in business)-min(r['tx_start'] for r in business)+1)*8
    payload_bytes = sum(r['payload_bytes'] for r in business)
    rate = payload_bytes*8000/duration
    assert rate>=100, f'whole-window payload throughput {rate}'
    counters = {r['key']:int(r['value'],0) for r in csv.DictReader((run/'counters.csv').open())}
    assert counters['stored']==counters['sent']==manifest['business_frames'], counters
    assert all(counters[k]==0 for k in ('queue_error','snmp_overflow','sntp_overflow','arbiter_error','sntp_rejected','sntp_timeout')), counters
    assert counters['snmp_response']==sum(c['kind']=='snmp' for c in expected)
    assert counters['sntp_accepted']==counters['rtc_sync']==1
    mask=(1<<64)-1
    signed=lambda n:n-(1<<64) if n>>63 else n
    t1,t2,t3,t4=(counters[k] for k in ('t1','t2','t3','t4'))
    assert t1==0xe900000000000000 and t2==t1+0x100000 and t3==t2+2748
    delay=signed((t4-t1)&mask)-signed((t3-t2)&mask)
    offset=(signed((t2-t1)&mask)+signed((t3-t4)&mask))>>1
    assert counters['delay']==delay and counters['offset']==offset&mask
    assert 0<=delay<=1<<32
    # Before the first synchronization, UTC is exactly INITIAL+floor(cycles*2^32/CLK_HZ).
    # Recover the unique cycle represented by T4 without borrowing an internal DUT signal.
    capture_cycle=((t4-t1)*125000000+(1<<32)-1)//(1<<32)
    assert (capture_cycle*(1<<32))//125000000==t4-t1
    reply_case=next(c for c in cases if c['kind']=='sntp_response')
    wire_rx_start=int(rx[reply_case['id']]['start_cycle'])
    latency = {k:dict(min=min(r[k] for r in records),max=max(r[k] for r in records))
               for k in ('first_to_first_ns','last_to_first_ns','first_to_last_ns')}
    jitter={hex(v):max(a)-min(a) for v,a in per_vl_latencies.items()}
    result = dict(frames_compared=len(tx),business_frames=len(business),wire_bytes_compared=len(actual),
                  whole_business_window_ns=duration,payload_Mbps=rate,
                  output_window_payload_Mbps=payload_bytes*8000/output_window,
                  latency_ns=latency,per_VL_first_to_first_latency_range_ns=jitter,
                  engineering_jitter_target_ns=50000,
                  engineering_jitter_target_pass=max(jitter.values())<=50000,
                  SNTP_timestamp_reference=dict(request='enqueue',receive='routed first payload byte',
                    request_enqueue_to_GMII_ns=sntp_wire_start*8,
                    reply_GMII_to_timestamp_ns=(capture_cycle-wire_rx_start)*8),
                  minimum_BAG_cycles=minimum_gaps,counters=counters,
                  scope='bounded 16-VL full-payload sustained load plus complete management vectors; not arbitrary-overload proof',
                  physical_timing='NOT VERIFIED',mixed_VO='NOT RUN')
    (run/'latencies.json').write_text(json.dumps(records,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds',type=int,default=256)
    parser.add_argument('--interval',type=int,default=8000)
    parser.add_argument('--service-interval',type=int,default=600000)
    args=parser.parse_args()
    assert 1<=args.rounds<=256 and args.interval>=1538 and args.service_interval>=125000
    parent=ROOT/'build/logs';index=1
    while (parent/f'mgmt_mixed_{index:03d}').exists(): index+=1
    run=parent/f'mgmt_mixed_{index:03d}';run.mkdir(parents=True)
    sources=sorted((ROOT/'vendor/frozen').glob('*.v'))+[ROOT/'rtl'/n for n in RTL]+[ROOT/'sim/tb_stage2_mixed.sv']
    scripts=[Path(__file__),ROOT/'scripts/generate_stage2_mixed_golden.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py']
    inputs=sources+scripts
    for p in inputs: shutil.copy2(p,run/p.name)
    manifest=generate(run/'golden',args.rounds,args.interval,args.service_interval)
    shutil.copy2(MS.parent/'modelsim.ini',run/'modelsim.ini');os.chmod(run/'modelsim.ini',0o666)
    commands=['onerror {quit -code 2 -force}','vlib work','vmap work work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}+incdir+. {p.name}' for p in sources]
    commands += ['vopt -O5 work.tb_stage2_mixed -o mixed_optimized','vsim -t 1ps work.mixed_optimized','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    command=[str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do']
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),golden=manifest,
                 inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},command=command)
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen(command,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        summary['pid']=proc.pid;(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(f'MIXED_RUN {run} PID {proc.pid}',flush=True)
        code=proc.wait(timeout=3600)
    transcript=(run/'transcript.log').read_text(errors='replace')
    passed=code==0 and 'MIXED_TRAFFIC = PASS' in transcript and '** Fatal' not in transcript and '** Error' not in transcript
    evidence={};error=None
    if passed:
        try:
            evidence=verify(run,manifest)
            assert evidence['engineering_jitter_target_pass'], 'per-VL latency range exceeds provisional 50 us engineering target'
            for p in inputs:
                assert sha(p)==summary['inputs'][str(p.relative_to(ROOT))]==sha(run/p.name), f'input changed: {p}'
        except (AssertionError,KeyError,ValueError,IndexError) as exc:
            passed=False;error=str(exc)
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,
                   completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(transcript[-1200:]);print(json.dumps(dict(run=str(run),result=summary['result'],error=error,evidence=evidence),indent=2))
    return 0 if passed else 1


if __name__=='__main__': raise SystemExit(main())
