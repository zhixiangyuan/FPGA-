"""Same application/dual-MAC/RX-boundary smoke on RTL or a fingerprinted real VO."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, csv, json, os, shutil, subprocess
from run_competition import ROOT, MS, sources, sha
from modelsim_support import prepare_ini
from frozen_frame_reference import make_client, wire_for
from generate_stage2_mgmt_golden import afdx_frame, sntp_packet, ES_MAC, ES_IP, MANAGER_IP

def generate(out):
    out.mkdir();app=bytearray();expected=[];wires=[]
    for cid,vl,length in ((900,0x1234,1),(901,0x12b3,1471),(902,0x2233,64)):
        frame,payload=make_client(cid,length,1);frame=frame[:4]+vl.to_bytes(2,'big')+frame[6:]
        packet=vl.to_bytes(2,'big')+payload;expected.append(packet)
        if cid!=902:app.extend(packet);wires.append(wire_for(frame))
        else:peer=wire_for(frame)
    for name,data in (('apps.mem',app),('peer.mem',peer)):(out/name).write_text(''.join(f'{b:02x}\n' for b in data))
    (out/'constants.vh').write_text(f'localparam APP_BYTES={len(app)},PEER_BYTES={len(peer)};\n')
    (out/'expected.json').write_text(json.dumps([p.hex() for p in expected],indent=2)+'\n')
    return expected,wires

def verify(run,expected,wires):
    packets=[];data=bytearray()
    for row in csv.DictReader((run/'smoke_app.csv').open()):
        if int(row['sop']):assert not data
        data.append(int(row['data']))
        if int(row['eop']):packets.append(bytes(data));data.clear()
    assert not data and packets==expected,'application oracle mismatch'
    observed=[];data=bytearray();last=None
    for row in csv.DictReader((run/'smoke_wire.csv').open()):
        cycle=int(row['cycle'])
        if last is not None and cycle!=last+1:observed.append(bytes(data));data.clear()
        data.append(int(row['data'],16));last=cycle
    if data:observed.append(bytes(data))
    business=[w for w in observed if int.from_bytes(w[12:14],'big')<0x12b4]
    assert business==wires,'business wire/FCS mismatch'
    services=[w for w in observed if int.from_bytes(w[12:14],'big')>=0x12b4]
    t1=0xe900000000000000+8192*(1<<32)//125000000
    ntp=wire_for(afdx_frame(bytes.fromhex('0300000012b5'),ES_MAC,ES_IP,MANAGER_IP,49152,123,sntp_packet(3,transmit=t1),1))
    assert services==[ntp],'autonomous time request mismatch'
    return dict(application_messages=3,RX_last_VL='0x2233',TX_last_VL='0x12b3',payload_lengths=[1,1471,64],
                both_networks=True,duplicate_suppression=True,autonomous_SNTP=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vo',type=Path);parser.add_argument('--provenance',type=Path)
    parser.add_argument('--rtl-reference',type=Path);parser.add_argument('--timeout',type=int,default=1800)
    args=parser.parse_args();family='competition_smoke_vo' if args.vo else 'competition_smoke';i=1
    while (ROOT/f'build/logs/{family}_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/{family}_{i:03d}';run.mkdir(parents=True)
    expected,wires=generate(run/'golden');rtl=sources();tb=ROOT/'sim/tb_competition_smoke.sv'
    inputs=rtl+[tb,Path(__file__),ROOT/'scripts/run_competition.py',ROOT/'scripts/frozen_frame_reference.py',
                ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/modelsim_support.py']
    reference=None
    if args.vo:
        assert args.provenance and args.rtl_reference
        export=json.loads(args.provenance.read_text());assert export['result']=='PASS' and sha(args.vo)==export['delivered_netlist_sha256']
        project=Path(export['source_project']);manifest=json.loads((project/'project_manifest.json').read_text())
        assert sha(project/'project_manifest.json')==export['source_manifest_sha256']
        for r in manifest['sources']:assert sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot'])
        reference=json.loads((args.rtl_reference/'summary.json').read_text());assert reference['result']=='PASS'
        assert reference['inputs']=={str(p.relative_to(ROOT)):sha(p) for p in inputs}
        assert reference['golden']=={p.name:sha(p) for p in (run/'golden').iterdir()}
        libs=[ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]
        compiled=libs+[args.vo.resolve(),tb]
    else:compiled=rtl+[tb]
    for p in set(inputs+compiled):shutil.copy2(p,run/p.name)
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in compiled]
    commands+=['vopt -O5 work.tb_competition_smoke -o smoke_opt','vsim -t 1ps work.smoke_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    proof=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),backend='VO' if args.vo else 'RTL',
               inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},clock_ns=8,BAG_cycles=125000,
               golden={p.name:sha(p) for p in (run/'golden').iterdir()},
               compiled={str(p):sha(p) for p in compiled},EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED')
    if args.vo:proof['provenance_sha256']=sha(args.provenance);proof['RTL_reference_sha256']=sha(args.rtl_reference/'summary.json')
    path=run/'summary.json';path.write_text(json.dumps(proof,indent=2)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    print(f'COMPETITION_SMOKE_RUN {run}',flush=True)
    with (run/'console.log').open('wb') as log:
        process=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],
                                 cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        proof['pid']=process.pid;path.write_text(json.dumps(proof,indent=2)+'\n')
        try:code=process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT);code=process.wait()
    text=(run/'transcript.log').read_text(errors='replace');error=None;evidence={}
    passed=code==0 and 'COMPETITION_SMOKE_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:
            evidence=verify(run,expected,wires)
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
            assert all(sha(Path(n))==h for n,h in proof['compiled'].items())
        except Exception as exc:passed=False;error=repr(exc)
    proof.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,
                 completed_utc=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(proof,indent=2)+'\n')
    print(text[-1300:]);print(json.dumps(dict(run=str(run),result=proof['result'],error=error,evidence=evidence),indent=2))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
