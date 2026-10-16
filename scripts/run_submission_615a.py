"""Official eight-port 615A transfer, coexistence and independent GMII Golden.

All protocol progress and file readback are observed on the wire. No internal
DUT state, force, shortened timers or shortened BAG is used, including VO runs.
"""
import argparse
import csv
import json
import os
import shutil
import struct
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from run_stage2_mgmt import ROOT,MS,sha
from submission_sources import sources
from modelsim_support import prepare_ini
from generate_615a_golden import generate
from run_615a import verify as verify_payloads
from generate_stage2_mgmt_golden import afdx_frame,ES_MAC,MANAGER_MAC,ES_IP,MANAGER_IP,sntp_packet
from generate_snmp_golden import message,oid,tlv
from frozen_frame_reference import wire_for


def generate_wire(out):
    golden=generate(out,smoke=True,readback_failures=True)
    golden['cases'][1]['name']='upload with independent status'
    with (out/'constants.vh').open('a') as f:f.write('localparam BACKGROUND_PACKETS=512;\n')
    fixtures=bytes.fromhex(''.join((out/'fixtures.mem').read_text().split()))
    biz=bytes((i*19+0x53)&255 for i in range(64))
    snmp=message(0xa0,100,b'public',[(oid(1),tlv(5,b''))])
    with (out/'constants.vh').open('a') as f:
        f.write(f'localparam AUX_BIZ_OFFSET={len(fixtures)},AUX_BIZ_LENGTH={len(biz)};\n')
        f.write(f'localparam AUX_SNMP_OFFSET={len(fixtures)+len(biz)},AUX_SNMP_LENGTH={len(snmp)};\n')
    constants=(out/'constants.vh').read_text().replace(f'FIXTURE_BYTES={len(fixtures)}',f'FIXTURE_BYTES={len(fixtures)+len(biz)+len(snmp)}');(out/'constants.vh').write_text(constants)
    (out/'fixtures.mem').write_text(''.join(f'{b:02x}\n' for b in fixtures+biz+snmp))
    golden['aux_biz']=biz.hex();golden['aux_snmp']=snmp.hex()
    golden['aux_response']=message(0xa2,100,b'public',[(oid(1),tlv(4,b'AFDX FPGA RTL endpoint'))]).hex()
    (out/'cases.json').write_text(json.dumps(golden,indent=2)+'\n')
    return golden


def verify(run,golden):
    evidence=verify_payloads(run,golden,check_metadata=False)
    tx=list(csv.DictReader((run/'wire_tx.csv').open()))
    rx=list(csv.DictReader((run/'wire_rx.csv').open()))
    last={};gaps=[];counts={};background_tx={};background_rx={};tx_tftp=[];rx_tftp=[];sntp_requests=[];sntp_replies=[]
    for direction,rows in [('tx',tx),('rx',rx)]:
        sequence={};input_previous={}
        for row in rows:
            wire=bytes.fromhex(row['data']);size=int(row['bytes']);cid=int(row['case_id'])
            assert len(wire)==size and size>=72
            body=wire[8:-4];vl=int.from_bytes(body[4:6],'big');sn=body[-1]
            expected_sn=sequence.get(vl,1);assert sn==expected_sn,f'{direction} VL {vl:04x} SN'
            sequence[vl]=1 if sn==255 else sn+1
            assert 0x1234<=vl<=0x1246
            sport,dport,udp_len,udp_crc=struct.unpack_from('!HHHH',body,34)
            assert 8<=udp_len<=1479 and udp_crc==0
            payload=body[42:42+udp_len-8]
            if direction=='tx':src_mac,src_ip,dst_ip=ES_MAC,ES_IP,(bytes((224,224,0,60)) if vl<=0x1243 else MANAGER_IP)
            elif vl<=0x1243:src_mac,src_ip,dst_ip=ES_MAC,ES_IP,bytes((224,224,0,60))
            else:src_mac,src_ip,dst_ip=MANAGER_MAC,MANAGER_IP,ES_IP
            reference=wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'),src_mac,src_ip,dst_ip,sport,dport,payload,sn))
            assert wire==reference,f'{direction} GMII header/checksum/FCS/padding case {cid} VL {vl:04x}'
            if direction=='rx':
                start=int(row['start_cycle'])
                if vl in input_previous:assert start-input_previous[vl]>=125000,'illegal offered AFDX BAG'
                input_previous[vl]=start
            if direction=='tx':
                start,end=int(row['start_cycle']),int(row['end_cycle']);assert end-start+1==size
                if vl in last:
                    gap=start-last[vl];assert gap>=125000,f'BAG VL {vl:04x}: {gap}';gaps.append(gap)
                last[vl]=start
                counts[(cid,vl)]=counts.get((cid,vl),0)+1
            if vl==0x1246:(tx_tftp if direction=='tx' else rx_tftp).append((cid,sport,dport,payload))
            elif vl<=0x1243:
                assert sport==24 and dport==23
                if len(payload)==1471:
                    index=int.from_bytes(payload[:2],'big');assert 0<=index<512 and vl==0x1235+index%15
                    expected=index.to_bytes(2,'big')+bytes((i*31+index*7+(i>>3))&255 for i in range(2,1471))
                    assert payload==expected
                    stream=background_tx if direction=='tx' else background_rx;assert index not in stream
                    stream[index]=(int(row['start_cycle']),int(row.get('end_cycle',int(row['start_cycle'])+size-1)))
                    if direction=='tx':counts[(cid,vl)]-=1
                else:assert vl==0x1234 and payload.hex()==golden['aux_biz']
            elif vl==0x1244:
                assert (sport,dport)==((161,49152) if direction=='tx' else (49152,161))
                assert payload.hex()==golden['aux_response' if direction=='tx' else 'aux_snmp']
            elif direction=='tx':
                assert (sport,dport)==(49152,123) and len(payload)==48
                t1=int.from_bytes(payload[40:48],'big');assert payload==sntp_packet(3,transmit=t1);sntp_requests.append(t1)
            else:
                assert (sport,dport)==(123,49152) and len(payload)==48
                t1=int.from_bytes(payload[24:32],'big');assert payload==sntp_packet(4,2,t1,t1,t1);sntp_replies.append(t1)
    def raw_packets(name):
        return [(int(r['case_id']),int(r['src_port']),int(r['dst_port']),bytes.fromhex(r['data'])) for r in csv.DictReader((run/name).open())]
    assert tx_tftp==raw_packets('packets.csv') and rx_tftp==raw_packets('peer_packets.csv')
    assert len(sntp_requests)==1 and sntp_replies==sntp_requests
    for case in golden['cases']:
        for vl in (0x1234,0x1244):assert counts.get((case['id'],vl),0)==int(case['kind']!=0),'lost/extra coexistence frame'
    assert set(background_tx)==set(background_rx)==set(range(512)),'continuous-load business frame loss'
    latency=[(background_tx[i][1]-background_rx[i][0])*8 for i in background_tx]
    assert min(latency)>=0 and max(latency)<=2000000,'continuous-load business latency'
    first=min(v[0] for v in background_rx.values());last_end=max(v[1] for v in background_tx.values())
    rate=512*1471*1000/(last_end-first+1)
    assert rate>=100,'continuous-load business throughput below 100 Mbps'
    evidence['continuous_load_business']=dict(frames=512,payload_Mbps=rate,max_first_to_last_ns=max(latency))
    evidence.pop('whole_system_VO',None)
    evidence.update(scope='official eight-port GMII, real 125 MHz and 1 ms BAG',
                    wire_tx_frames=len(tx),wire_rx_frames=len(rx),wire_tx_bytes=sum(int(r['bytes']) for r in tx),
                    minimum_BAG_cycles=min(gaps),SNMP_and_business_coexistence=True,
                    autonomous_SNTP_exchange=True,internal_state_checks=False,
                    shortened_timers=False,force_used=False,rx_interframe_gap_cycles=2048,offered_business_interval_cycles=9000)
    return evidence


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vo',type=Path);parser.add_argument('--provenance',type=Path)
    args=parser.parse_args()
    if args.vo:
        assert args.provenance
        export=json.loads(args.provenance.read_text());assert export['result']=='PASS' and sha(args.vo)==export['delivered_netlist_sha256']
        project=Path(export['source_project']);manifest=project/'project_manifest.json';assert sha(manifest)==export['source_manifest_sha256']
        for r in json.loads(manifest.read_text())['sources']:assert sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot'])
    prefix='submission_615a_vo' if args.vo else 'submission_615a';index=1
    while (ROOT/f'build/logs/{prefix}_{index:03d}').exists():index+=1
    run=ROOT/f'build/logs/{prefix}_{index:03d}';run.mkdir(parents=True)
    rtl=sources()
    compiled=([ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]+[args.vo.resolve()]) if args.vo else rtl
    compiled+=[ROOT/'sim/tb_submission_615a.sv']
    inputs=list(dict.fromkeys(compiled+rtl+[Path(__file__),ROOT/'scripts/submission_sources.py',ROOT/'scripts/prepare_stage2_mgmt_elinx.py',ROOT/'scripts/run_615a.py',ROOT/'scripts/generate_615a_golden.py',ROOT/'scripts/generate_tftp_golden.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/run_stage2_mgmt.py',ROOT/'scripts/modelsim_support.py']))
    if args.vo:inputs+=[args.provenance]
    for p in inputs:shutil.copy2(p,run/p.name)
    golden=generate_wire(run/'golden');prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in compiled]
    commands += ['vopt -O5 work.tb_submission_615a -o sub615a_opt','vsim -t 1ps work.sub615a_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),RTL_DUT_compiled=not bool(args.vo),force_used=False,
                 model_backend=export['model_backend'] if args.vo else 'RTL',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED',
                 clock_ns=8,BAG_cycles=125000,shortened_timers=False,inputs={str(p):sha(p) for p in inputs},golden={p.name:sha(p) for p in (run/'golden').iterdir()})
    proof=run/'summary.json';proof.write_text(json.dumps(summary,indent=2)+'\n')
    timeout_error=None
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        summary['modelsim_pid']=proc.pid;proof.write_text(json.dumps(summary,indent=2)+'\n');print(f'SUB615A_RUN {run} PID {proc.pid}',flush=True)
        limit=43200 if args.vo else 1200
        try:code=proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timeout_error=f'wall-clock execution timeout after {limit} seconds'
            subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
            code=proc.wait(timeout=30)
    text=(run/'transcript.log').read_text(errors='replace');error=timeout_error;evidence={}
    passed=timeout_error is None and code==0 and 'SUBMISSION_615A_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:
            evidence=verify(run,golden)
            for p in inputs:assert sha(p)==summary['inputs'][str(p)]==sha(run/p.name),f'input changed: {p}'
        except (AssertionError,ValueError,KeyError,IndexError) as exc:passed=False;error=str(exc)
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat(),artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    proof.write_text(json.dumps(summary,indent=2)+'\n');print(text[-1400:]);print(json.dumps(dict(run=str(run),result=summary['result'],error=error,evidence=evidence),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
