"""Eight-port production target: real GMII, independent wire Golden, real BAG."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import json
import os
import shutil
import subprocess

from run_stage2_mgmt import MS, ROOT, sha
from submission_sources import sources
from modelsim_support import prepare_ini
from generate_stage2_mgmt_golden import (
    afdx_frame, sntp_packet, ES_MAC, MANAGER_MAC,
    ES_IP, MANAGER_IP,
)
from generate_snmp_golden import message, oid, tlv, integer
from frozen_frame_reference import wire_for

def generate(out):
    out.mkdir()
    rx = bytearray()
    expected = []
    stimulus = []
    t1 = 0xe900000000000000 + 16*(1 << 32)//125000000
    def expect(name, payload, epoch, vl=0x1244, sn=1):
        sport, dport = (49152, 123) if vl == 0x1245 else (161, 49152)
        wire = wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'), ES_MAC,
                                  ES_IP, MANAGER_IP, sport, dport, payload, sn))
        expected.append(dict(name=name, epoch=epoch, wire=wire.hex(), vlid=vl))
    def send(name, payload, sn=1, vl=0x1244, partial=None):
        sport, dport = (123, 49152) if vl == 0x1245 else (49152, 161)
        wire = wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'), MANAGER_MAC,
                                  MANAGER_IP, ES_IP, sport, dport, payload, sn))
        size = len(wire) if partial is None else partial
        stimulus.append(f'// {name}\nsend_frame({len(rx)},{size});')
        rx.extend(wire)
    null = tlv(5,b'')
    def request(pdu, rid, obj, value=null, community=b'public'):
        return message(pdu,rid,community,[(oid(obj),value)])
    def response(rid, obj, value, community=b'public'):
        return message(0xa2,rid,community,[(oid(obj),value)])
    stimulus += ['restart();', 'wait_frames(1);']
    expect('autonomous request before reset',sntp_packet(3,transmit=t1),0,0x1245)
    send('reset during incomplete GMII frame',request(0xa0,1,1),partial=20)
    stimulus += ['restart();', 'wait_frames(2);']
    expect('autonomous request after reset',sntp_packet(3,transmit=t1),1,0x1245)
    send('valid autonomous SNTP reply',sntp_packet(4,stratum=2,origin=t1,
         receive=t1+0x100000,transmit=t1+0x100000+2748),vl=0x1245)
    stimulus += ['synchronized_time();', 'require_frames(2);']
    data = bytes((0x5a+p*31+(p>>3))&255 for p in range(64))
    wire = wire_for(afdx_frame(bytes.fromhex('030000001234'),ES_MAC,ES_IP,
                             bytes((224,224,0,60)),24,23,data,1))
    stimulus.append(f'send_frame({len(rx)},{len(wire)});');rx.extend(wire)
    expected.append(dict(name='business echo',epoch=1,wire=wire.hex(),vlid=0x1234))
    stimulus += ['wait_frames(3);', 'idle(125000);']
    send('GET sysDescr',request(0xa0,2,1),1)
    expect('GET sysDescr',response(2,1,tlv(4,b'AFDX FPGA RTL endpoint')),1,sn=1)
    stimulus += ['wait_frames(4);', 'idle(125000);']
    send('SET sysName',request(0xa3,3,5,tlv(4,b'flight-prod'),b'private'),2)
    expect('SET sysName',response(3,5,tlv(4,b'flight-prod'),b'private'),1,sn=2)
    stimulus += ['wait_frames(5);', 'idle(125000);']
    send('GET modified sysName',request(0xa0,4,5),3)
    expect('GET modified sysName',response(4,5,tlv(4,b'flight-prod')),1,sn=3)
    stimulus += ['wait_frames(6);', 'idle(125000);']
    send('duplicate SN rejected',request(0xa0,4,5),3)
    stimulus += ['idle(3000);', 'require_frames(6);']
    send('bad community silent',request(0xa0,5,1,community=b'guess'),4)
    stimulus += ['idle(3000);', 'require_frames(6);', 'while(age<1300000)idle(1);']
    send('real sysUpTime after 10ms',request(0xa0,6,3),5)
    expect('real sysUpTime after 10ms',response(6,3,integer(1,0x43)),1,sn=4)
    stimulus += ['wait_frames(7);', 'restart();', 'wait_frames(8);']
    expect('second reset restarts auto poll',sntp_packet(3,transmit=t1),2,0x1245)
    send('reset restores sysName',request(0xa0,7,5),1)
    expect('reset restores sysName',response(7,5,tlv(4,b'afdx-s2')),2,sn=1)
    stimulus += ['wait_frames(9);', 'idle(3000);', 'require_frames(9);']
    (out/'rx_wire.mem').write_text(''.join(f'{b:02x}\n' for b in rx))
    (out/'constants.vh').write_text(f'localparam RX_BYTES={len(rx)};\n')
    (out/'stimulus.vh').write_text('\n'.join(stimulus)+'\n')
    (out/'expected.json').write_text(json.dumps(expected,indent=2)+'\n')
    return expected


def verify(run, expected):
    actual = bytes.fromhex(''.join((run/'actual_tx.mem').read_text().split()))
    events = list(csv.DictReader((run/'tx_events.csv').open()))
    assert len(events)==len(expected)==9, f'outputs {len(events)}'
    offset=0
    last={}
    gaps=[]
    for event, case in zip(events,expected):
        size=int(event['bytes']); frame=actual[offset:offset+size]; offset+=size
        assert frame==bytes.fromhex(case['wire']), f'wire mismatch: {case["name"]}'
        assert int(event['epoch'])==case['epoch'], case['name']
        assert int(event['end_cycle'])-int(event['start_cycle'])+1==size
        key=(case['epoch'],case['vlid'])
        if key in last:
            gap=int(event['start_cycle'])-last[key];assert gap>=125000;gaps.append(gap)
        last[key]=int(event['start_cycle'])
    assert offset==len(actual)
    return dict(frames=9,wire_bytes=len(actual),minimum_repeated_VL_BAG_cycles=min(gaps),
                production_ports=8,io_bits=22,clock_ns=8,auto_SNTP_requests=3,
                valid_SNTP_sync=1,real_10ms_sysUpTime=True,reset_recovery=True,
                SET_GET=True,duplicate_and_bad_community_silent=True,
                periodic_timer_checked=True,VO='NOT RUN')


def main():
    i=1
    while (ROOT/f'build/logs/submission_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/submission_{i:03d}';run.mkdir(parents=True)
    inputs=sources()+[ROOT/'sim/tb_submission.sv',Path(__file__),ROOT/'scripts/submission_sources.py',
        ROOT/'scripts/prepare_stage2_mgmt_elinx.py',ROOT/'scripts/modelsim_support.py',
        ROOT/'scripts/run_stage2_mgmt.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',
        ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    expected=generate(run/'golden')
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in sources()+[ROOT/'sim/tb_submission.sv']]
    commands += ['vopt -O5 work.tb_submission -o submission_opt','vsim -t 1ps work.submission_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),
                 inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                 golden={p.name:sha(p) for p in (run/'golden').iterdir()},VO='NOT RUN')
    proof=run/'summary.json';proof.write_text(json.dumps(summary,indent=2)+'\n')
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini',
             '-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        print(f'SUBMISSION_RUN {run} PID {proc.pid}',flush=True)
        code=proc.wait(timeout=1200)
    transcript=(run/'transcript.log').read_text(errors='replace');error=None;evidence={}
    passed=code==0 and 'SUBMISSION_RTL_PASS' in transcript and '** Error' not in transcript and '** Fatal' not in transcript
    if passed:
        try:evidence=verify(run,expected)
        except (AssertionError,KeyError,ValueError) as exc:error=str(exc);passed=False
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,
                   completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    proof.write_text(json.dumps(summary,indent=2)+'\n')
    print(transcript[-1200:]);print(json.dumps(dict(run=str(run),result=summary['result'],evidence=evidence,error=error),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
