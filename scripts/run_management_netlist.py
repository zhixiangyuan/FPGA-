"""Post-synthesis SNMP SET/GET, protocol rejection, SNTP and 1ms BAG check."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,os,shutil,subprocess
from run_competition import ROOT,MS,sources,sha
from modelsim_support import prepare_ini
from generate_stage2_mgmt_golden import afdx_frame,sntp_packet,ES_MAC,MANAGER_MAC,ES_IP,MANAGER_IP
from generate_snmp_golden import message,oid,tlv
from frozen_frame_reference import wire_for

def generate(out):
    out.mkdir();fixtures=bytearray();expected={}
    def input_wire(vl,payload,sn,kind,sport=49152,dport=161):
        raw=afdx_frame(bytes.fromhex(f'03000000{vl:04x}'),MANAGER_MAC,MANAGER_IP,ES_IP,sport,dport,payload,sn)
        if kind=='ip':raw=raw[:24]+bytes([raw[24]^1])+raw[25:]
        elif kind=='udp':raw=raw[:40]+b'\x01\x01'+raw[42:]
        wire=wire_for(raw,corrupt_fcs=(kind=='crc'))
        offset=len(fixtures);fixtures.extend(wire);return offset,len(wire)
    def output_wire(vl,payload,sn,sport,dport):
        return wire_for(afdx_frame(bytes.fromhex(f'03000000{vl:04x}'),ES_MAC,ES_IP,MANAGER_IP,sport,dport,payload,sn))
    mgmt,time=0x12b4,0x12b5
    req=message(0xa0,1,b'public',[(oid(1),tlv(5,b''))])
    offs,lens=input_wire(mgmt,req,1,'crc');c_off,c_len=input_wire(mgmt,req,1,'ip');u_off,u_len=input_wire(mgmt,req,1,'udp')
    contact=tlv(4,b'netlist-check');set_req=message(0xa3,2,b'private',[(oid(4),contact)])
    set_off,set_len=input_wire(mgmt,set_req,1,'ok')
    get_req=message(0xa0,3,b'public',[(oid(4),tlv(5,b''))])
    get_off,get_len=input_wire(mgmt,get_req,2,'ok')
    t1=0xe900000000000000+8192*(1<<32)//125000000
    reply=sntp_packet(4,2,t1,t1+0x100000,t1+0x100000+2748)
    time_off,time_len=input_wire(time,reply,1,'ok',123,49152)
    (out/'fixtures.mem').write_text(''.join(f'{x:02x}\n' for x in fixtures))
    exp={mgmt:[output_wire(mgmt,message(0xa2,2,b'private',[(oid(4),contact)]),1,161,49152),
              output_wire(mgmt,message(0xa2,3,b'public',[(oid(4),contact)]),2,161,49152)],
         time:[output_wire(time,sntp_packet(3,transmit=t1),1,49152,123)]}
    (out/'expected.json').write_text(json.dumps({str(k):[w.hex() for w in v] for k,v in exp.items()},indent=2)+'\n')
    order=[('BADCRC',offs,lens),('BADIP',c_off,c_len),('BADUDP',u_off,u_len),
           ('SET',set_off,set_len),('GET',get_off,get_len),('TIME',time_off,time_len)]
    stim='\n'.join(f'peer({o},{n});' for _,o,n in order[:5])
    stim+='\nwhile(cycle<8200)@(negedge clk);'
    stim+=f'\npeer({time_off},{time_len});'
    (out/'stimulus.vh').write_text(stim+'\n')
    (out/'constants.vh').write_text(f'localparam RX_BYTES={len(fixtures)};\n')
    return exp

def main():
    p=argparse.ArgumentParser();p.add_argument('--vo',type=Path);p.add_argument('--provenance',type=Path)
    p.add_argument('--rtl-reference',type=Path);p.add_argument('--timeout',type=int,default=7200);a=p.parse_args()
    i=1;family='management_netlist_vo' if a.vo else 'management_netlist'
    while (ROOT/f'build/logs/{family}_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/{family}_{i:03d}';run.mkdir(parents=True);expected=generate(run/'golden')
    files=sources()+[ROOT/'sim/tb_management_vo.sv'];helpers=[Path(__file__),ROOT/'scripts/run_competition.py',
        ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/generate_snmp_golden.py',ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    inputs=files+helpers;reference=None
    if a.vo:
        assert a.provenance and a.rtl_reference
        export=json.loads(a.provenance.read_text());assert export['result']=='PASS' and sha(a.vo)==export['delivered_netlist_sha256']
        project=Path(export['source_project']);manifest=json.loads((project/'project_manifest.json').read_text())
        assert sha(project/'project_manifest.json')==export['source_manifest_sha256']
        for row in manifest['sources']:assert sha(ROOT/row['canonical_source'])==row['sha256']==sha(project/row['snapshot'])
        ref=json.loads((a.rtl_reference/'summary.json').read_text());assert ref['result']=='PASS' and ref['inputs']=={str(x.relative_to(ROOT)):sha(x) for x in inputs}
        assert ref['golden']=={x.name:sha(x) for x in (run/'golden').iterdir()}
        libs=[ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]
        compiled=libs+[a.vo.resolve(),files[-1]]
    else:compiled=files
    for x in set(inputs+compiled):shutil.copy2(x,run/x.name)
    prepare_ini(run,MS);cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if x.suffix==".sv" else ""}{x.name}' for x in compiled]
    cmd+=['vopt -O5 work.tb_management_vo -o management_opt','vsim -t 1ps work.management_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(cmd)+'\n')
    proof=dict(result='RUNNING',backend='VO' if a.vo else 'RTL',started_utc=datetime.now(timezone.utc).isoformat(),clock_ns=8,
        BAG_cycles=125000,inputs={str(x.relative_to(ROOT)):sha(x) for x in inputs},golden={x.name:sha(x) for x in (run/'golden').iterdir()},
        compiled={str(x):sha(x) for x in compiled})
    if a.vo:proof.update(provenance_sha256=sha(a.provenance),rtl_reference_sha256=sha(a.rtl_reference/'summary.json'))
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n');env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'MANAGEMENT_NETLIST_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        proof['pid']=proc.pid;path.write_text(json.dumps(proof,indent=2)+'\n');code=proc.wait(timeout=a.timeout)
    text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'MANAGEMENT_NETLIST_PASS' in text and '** Error' not in text and '** Fatal' not in text;error=None
    if passed:
        try:
            actual=bytes.fromhex(''.join((run/'network_tx.mem').read_text().split()));ev=list(csv.DictReader((run/'frames.csv').open()));expected_flat=[]
            byvl={}
            for k,v in expected.items():byvl[int(k)]=list(v)
            for row in ev:
                vl=int(row['vl']);size=int(row['bytes']);start=int(row['start'])
                assert vl in byvl and byvl[vl] and size==len(byvl[vl][0]);w=actual[:size];actual=actual[size:]
                assert w==byvl[vl].pop(0)
            assert not actual and all(not v for v in byvl.values()) and len(ev)==3
            assert sum(len(v) for v in expected.values())==3
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
            assert all(sha(Path(n))==h for n,h in proof['compiled'].items())
        except Exception as exc:passed=False;error=repr(exc)
    proof.update(result='PASS' if passed else 'FAIL',error=error,exit_code=code,
        management_frames=2,SNMP_SET_GET_persistent=True,SNTP_auto_request=True,
        malformed_FCS_IP_UDP_rejected=True,real_SNMP_BAG=True,timeout_preserved=a.timeout,
        completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n');print(text[-1300:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('inputs','golden','compiled')},indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
