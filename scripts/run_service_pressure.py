"""Identical application/management stimulus for arbiter baseline and candidate.

Two management requests form a deliberate control-plane burst (not a claim of
legal 1ms peer BAG). Both variants use 16 VL / 1471 bytes / 8100 cycles.
The benchmark proves isolation under backlog; normal official load is separate.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse,csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sources,sha
from modelsim_support import prepare_ini
from generate_stage2_mgmt_golden import afdx_frame,sntp_packet,ES_MAC,MANAGER_MAC,ES_IP,MANAGER_IP
from generate_snmp_golden import message,oid,tlv
from frozen_frame_reference import wire_for,make_client,payload

def generate(out,business_frames=24):
    out.mkdir();blob=bytearray();positions={};mgmt=0x12b4
    t1=0xe900000000000000+8192*(1<<32)//125000000
    def wire(vl,data,sn,incoming=False,sport=161,dport=49152):
        return wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'),MANAGER_MAC if incoming else ES_MAC,
             MANAGER_IP if incoming else ES_IP,ES_IP if incoming else MANAGER_IP,sport,dport,data,sn))
    expected={0x12b5:[wire(0x12b5,sntp_packet(3,transmit=t1),1,sport=49152,dport=123)],mgmt:[]}
    def fixture(name,w):positions[name]=(len(blob),len(w));blob.extend(w)
    fixture('TIME',wire(0x12b5,sntp_packet(4,2,t1,t1+0x100000,t1+0x100000+2748),1,True,123,49152))
    value=tlv(4,b'isolation-verified')
    bad_req=message(0xa0,99,b'public',[(oid(5),tlv(5,b''))])
    bad_frame=afdx_frame(bytes.fromhex('0300000012b4'),MANAGER_MAC,MANAGER_IP,ES_IP,49152,161,bad_req,1)
    bad=bytearray(wire_for(bad_frame));bad[-1]^=1;fixture('BADCRC',bytes(bad))
    bad=bytearray(bad_frame);bad[24]^=1;fixture('BADIP',wire_for(bytes(bad)))
    bad=bytearray(bad_frame);bad[40:42]=b'\x01\x01';fixture('BADUDP',wire_for(bytes(bad)))
    for sn,pdu,name in ((1,0xa3,'SET'),(2,0xa0,'GET')):
        community=b'private' if pdu==0xa3 else b'public'
        req=message(pdu,sn,community,[(oid(5),value if pdu==0xa3 else tlv(5,b''))])
        fixture(name,wire(mgmt,req,sn,True,49152,161))
        expected[mgmt].append(wire(mgmt,message(0xa2,sn,community,[(oid(5),value)]),sn))
    for cid in range(business_frames):
        vl=0x1234+cid%16;sn=1+cid//16;frame,_=make_client(cid,1471,sn)
        frame=frame[:4]+vl.to_bytes(2,'big')+frame[6:]
        expected.setdefault(vl,[]).append(wire_for(frame))
    (out/'fixtures.mem').write_text(''.join(f'{b:02x}\n' for b in blob))
    constants=f'localparam FIXTURE_BYTES={len(blob)},BUSINESS_FRAMES={business_frames};\n'
    constants+=''.join(f'localparam {n}_OFFSET={o},{n}_LENGTH={l};\n' for n,(o,l) in positions.items())
    (out/'constants.vh').write_text(constants)
    (out/'expected.json').write_text(json.dumps({str(k):[w.hex() for w in v] for k,v in expected.items()},indent=2)+'\n')
    return expected

def verify(run,expected):
    raw=bytes.fromhex(''.join((run/'wire.mem').read_text().split()));events=list(csv.DictReader((run/'wire_events.csv').open()))
    actual={};offset=0;last={};gaps=[]
    for e in events:
        size=int(e['bytes']);w=raw[offset:offset+size];offset+=size;vl=int.from_bytes(w[12:14],'big')
        actual.setdefault(vl,[]).append(w);start=int(e['start'])
        if vl in last:gaps.append(start-last[vl]);assert start-last[vl]>=125000
        last[vl]=start
    assert offset==len(raw) and actual==expected,'wire/FCS/per-VL order oracle mismatch'
    offered={int(r['id']):r for r in csv.DictReader((run/'inputs.csv').open())}
    count=sum(len(v) for k,v in expected.items() if k<0x12b4);assert len(offered)==count
    packets={};data=bytearray();first=None
    for r in csv.DictReader((run/'application.csv').open()):
        if int(r['sop']):assert not data;first=int(r['cycle'])
        data.append(int(r['data']))
        if int(r['eop']):
            vl=int.from_bytes(data[:2],'big');matches=[c for c in offered if c not in packets and int(offered[c]['vl'])==vl and data[2:]==payload(c,1471)]
            assert len(matches)==1,'application duplicate/data mismatch'
            cid=matches[0];packets[cid]=dict(first=first,last=int(r['cycle']),vl=vl);data.clear()
    assert not data and len(packets)==count
    latency={c:(p['last']-int(offered[c]['cycle']))*8 for c,p in packets.items()}
    ranges=[]
    for vl in range(0x1234,0x1244):
        values=[v for c,v in latency.items() if packets[c]['vl']==vl]
        if values:ranges.append(max(values)-min(values))
    first=min(int(r['cycle']) for r in offered.values());last_input=max(int(r['cycle']) for r in offered.values())+1473
    last=max(p['last'] for p in packets.values())
    return dict(application_messages=count,wire_frames=len(events),payload_bytes=count*1471,
                payload_input_Mbps=count*1471*1000/(last_input-first),payload_delivered_Mbps=count*1471*1000/(last-first),
                max_application_first_to_last_ns=max(latency.values()),max_same_VL_same_length_range_ns=max(ranges),
                minimum_per_VL_BAG_cycles=min(gaps),SET_GET_persistence=True,autonomous_SNTP_sync=True,
                rejected_bad_FCS_IP_UDP_without_SN_state_poisoning=True,
                no_application_loss=True,no_duplicate_application_delivery=True,
                workload=f'deliberate two-request control-plane burst; {count} business frames, 16VL, 1471 bytes, 8100-cycle interval',
                within_engineering_50us_jitter=max(ranges)<=50000)

def main():
    p=argparse.ArgumentParser();p.add_argument('--arbiter',type=Path);p.add_argument('--vo',type=Path)
    p.add_argument('--provenance',type=Path);p.add_argument('--rtl-reference',type=Path);p.add_argument('--timeout',type=int,default=7200)
    p.add_argument('--business-frames',type=int,choices=(2,24),default=24)
    args=p.parse_args();assert not(args.vo and args.arbiter)
    family='service_pressure_vo' if args.vo else 'service_pressure';i=1
    while (ROOT/f'build/logs/{family}_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/{family}_{i:03d}';run.mkdir(parents=True);expected=generate(run/'golden',args.business_frames)
    rtl=sources();tb=ROOT/'sim/tb_service_pressure.sv'
    if args.arbiter:rtl=[args.arbiter.resolve() if x.name=='afdx_service_tx_arbiter_615a.v' else x for x in rtl]
    helpers=[Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',
             ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    inputs=rtl+[tb]+helpers
    fingerprints={str(x):sha(x) for x in inputs}
    golden={x.name:sha(x) for x in (run/'golden').iterdir()}
    if args.vo:
        assert args.provenance and args.rtl_reference
        export=json.loads(args.provenance.read_text());assert export['result']=='PASS' and sha(args.vo)==export['delivered_netlist_sha256']
        project=Path(export['source_project']);manifest=json.loads((project/'project_manifest.json').read_text())
        assert sha(project/'project_manifest.json')==export['source_manifest_sha256']
        for r in manifest['sources']:assert sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot'])
        ref=json.loads((args.rtl_reference/'summary.json').read_text());assert ref['result']=='PASS' and ref['inputs']==fingerprints and ref['golden']==golden
        compiled=[ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]+[args.vo.resolve(),tb]
    else:compiled=rtl+[tb]
    for x in set(inputs+compiled):shutil.copy2(x,run/x.name)
    prepare_ini(run,MS)
    cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if x.suffix==".sv" else ""}{x.name}' for x in compiled]
    cmd+=['vopt -O5 work.tb_service_pressure -o pressure_opt','vsim -t 1ps work.pressure_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(cmd)+'\n')
    proof=dict(result='RUNNING',backend='VO' if args.vo else 'RTL',started_utc=datetime.now(timezone.utc).isoformat(),
               inputs=fingerprints,golden=golden,compiled={str(x):sha(x) for x in compiled},clock_ns=8,BAG_cycles=125000,
               arbiter_override=str(args.arbiter) if args.arbiter else None)
    proof['business_frames']=args.business_frames
    if args.vo:proof.update(provenance_sha256=sha(args.provenance),rtl_reference_sha256=sha(args.rtl_reference/'summary.json'))
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'SERVICE_PRESSURE_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        proof['pid']=proc.pid;path.write_text(json.dumps(proof,indent=2)+'\n')
        try:code=proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT);code=proc.wait()
    text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'SERVICE_PRESSURE_PASS' in text and '** Error' not in text and '** Fatal' not in text
    error=None;evidence={}
    if passed:
        try:
            evidence=verify(run,expected)
            assert all(sha(Path(n))==h for n,h in fingerprints.items()),'source changed'
            assert all(sha(Path(n))==h for n,h in proof['compiled'].items()),'compiled input changed'
        except Exception as exc:passed=False;error=repr(exc)
    proof.update(result='PASS' if passed else 'FAIL',error=error,exit_code=code,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n');print(text[-1200:]);print(json.dumps(dict(run=str(run),result=proof['result'],error=error,evidence=evidence),indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
