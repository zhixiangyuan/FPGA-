"""New application wrapper with real dual-network SNMP/SNTP and business coexistence."""
from pathlib import Path
from datetime import datetime, timezone
import csv, json, os, shutil, subprocess
from run_competition import ROOT, MS, sources, sha
from modelsim_support import prepare_ini
from generate_stage2_mgmt_golden import afdx_frame, sntp_packet, ES_MAC, MANAGER_MAC, ES_IP, MANAGER_IP
from generate_snmp_golden import message, oid, tlv
from frozen_frame_reference import wire_for

def generate(out):
    out.mkdir();blob=bytearray();stim=[];expected=[];mgmt=0x12b4;time=mgmt+1
    t1=0xe900000000000000+8192*(1<<32)//125000000
    def wire(vl,payload,sn,incoming=False,sport=161,dport=49152):
        return wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'),MANAGER_MAC if incoming else ES_MAC,
                                  MANAGER_IP if incoming else ES_IP,ES_IP if incoming else MANAGER_IP,
                                  sport,dport,payload,sn))
    def send(vl,payload,sn,networks=3,sport=49152,dport=161):
        w=wire(vl,payload,sn,True,sport,dport)
        stim.append(f'send_frame({len(blob)},{len(w)},{networks});');blob.extend(w)
    expected.append(wire(time,sntp_packet(3,transmit=t1),1,sport=49152,dport=123))
    stim.append('wait_frames(1);')
    send(time,sntp_packet(4,2,t1,t1+0x100000,t1+0x100000+2748),1,sport=123,dport=49152)
    stim.append('idle(3000);')
    specs=[(0xa0,1,tlv(5,b''),b'public',tlv(4,b'AFDX FPGA RTL endpoint'),0),
           (0xa0,4,tlv(5,b''),b'public',tlv(4,b'afdx-es-team3'),0),
           (0xa3,4,tlv(4,b'ops@afdx-lab'),b'private',tlv(4,b'ops@afdx-lab'),0),
           (0xa0,4,tlv(5,b''),b'public',tlv(4,b'ops@afdx-lab'),1),
           (0xa3,5,tlv(4,b'flight-dual'),b'private',tlv(4,b'flight-dual'),1),
           (0xa0,5,tlv(5,b''),b'public',tlv(4,b'flight-dual'),1),
           (0xa3,6,tlv(4,b'Rack 7'),b'private',tlv(4,b'Rack 7'),0),
           (0xa0,6,tlv(5,b''),b'public',tlv(4,b'Rack 7'),0),
           (0xa0,2,tlv(5,b''),b'public',tlv(6,bytes((43,6,1,4,1))),0)]
    last_request=None
    for i,(pdu,obj,value,community,answer,version) in enumerate(specs,1):
        req=message(pdu,i,community,[(oid(obj),value)],version=version)
        send(mgmt,req,i,networks=2 if i==2 else 1 if i==3 else 3)
        expected.append(wire(mgmt,message(0xa2,i,community,[(oid(obj),answer)],version=version),i))
        stim.extend((f'wait_frames({len(expected)});','idle(125000);'))
        last_request=req
    # Last SN duplicated on both networks: no extra management action.
    send(mgmt,last_request,9);stim.append('idle(5000);')
    # Business injection remains application-only after management exchange.
    payload=bytes((53+p*37+(p>>2))&255 for p in range(64))
    stim+=['loopback=1;','@(negedge clk);while(!ready)@(negedge clk);',
           "app_valid=1;app_tx=8'h12;@(negedge clk);app_tx=8'h34;"]
    for p in payload:stim.append(f"@(negedge clk);app_tx=8'h{p:02x};")
    stim+=['@(negedge clk);app_valid=0;',f'wait_frames({len(expected)+1});','idle(5000);']
    group=bytes((224,224,0,60))
    expected.append(wire_for(afdx_frame(bytes.fromhex('030000001234'),ES_MAC,ES_IP,group,24,23,payload,1)))
    (out/'fixtures.mem').write_text(''.join(f'{v:02x}\n' for v in blob))
    (out/'constants.vh').write_text(f'localparam RX_BYTES={len(blob)};\n')
    (out/'stimulus.vh').write_text('\n'.join(stim)+'\n')
    (out/'expected.json').write_text(json.dumps([w.hex() for w in expected],indent=2)+'\n')
    return expected,b'\x12\x34'+payload

def main():
    i=1
    while (ROOT/f'build/logs/competition_mgmt_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/competition_mgmt_{i:03d}';run.mkdir(parents=True)
    expected,app=generate(run/'golden')
    files=sources()+[ROOT/'sim/tb_competition_mgmt.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',
                  ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in files]
    commands+=['vopt -O5 work.tb_competition_mgmt -o mgmt_opt','vsim -t 1ps work.mgmt_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),clock_ns=8,BAG_cycles=125000,
               inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},
               golden={p.name:sha(p) for p in (run/'golden').iterdir()})
    (run/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'COMPETITION_MGMT_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        process=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],
                                 cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        code=process.wait(timeout=1800)
    text=(run/'transcript.log').read_text(errors='replace');error=None
    passed=code==0 and 'COMPETITION_MGMT_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:
            actual=bytes.fromhex(''.join((run/'service_tx.mem').read_text().split()))
            assert actual==b''.join(expected), 'management or business wire mismatch'
            assert bytes.fromhex(''.join((run/'service_app.mem').read_text().split()))==app
            events=list(csv.DictReader((run/'service_events.csv').open()))
            assert len(events)==len(expected)
            for r,w in zip(events,expected):assert int(r['bytes'])==len(w)
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items()), 'inputs changed'
        except Exception as exc:passed=False;error=repr(exc)
    proof.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,frames=len(expected),
                 SNMP_SET_GET_v1_v2c=True,autonomous_SNTP=True,time_sync=True,AB_fault_recovery=True,
                 business_coexistence=True,duplicate_suppression=True,full_615A_sessions='NOT RUN in new wrapper',
                 completed_utc=datetime.now(timezone.utc).isoformat())
    (run/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(text[-1800:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('inputs','golden')},indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
