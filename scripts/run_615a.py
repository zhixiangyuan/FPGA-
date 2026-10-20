"""615A endpoint against a packet-only loader/server and independent Golden."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,os,shutil,struct,subprocess
from run_stage2_mgmt import ROOT,MS,sha
from modelsim_support import prepare_ini
from generate_615a_golden import generate,decode_status,BASE,HEADER,DATA,PN
from generate_tftp_golden import request


def verify(run,golden,check_metadata=True):
    packets=list(csv.DictReader((run/'packets.csv').open()))
    peer=list(csv.DictReader((run/'peer_packets.csv').open()))
    metadata=list(csv.DictReader((run/'metadata.csv').open()))
    if check_metadata:assert len(metadata)==len(golden['cases'])
    fixtures=bytes.fromhex(''.join((run/'golden/fixtures.mem').read_text().split()))
    evidence=[];last_sequence=-1;seen_status={}
    for index,case in enumerate(golden['cases']):
        cid=case['id'];rows=[r for r in packets if int(r['case_id'])==cid]
        inputs=[r for r in peer if int(r['case_id'])==cid]
        if check_metadata:
            meta=metadata[index]
            for name,key in [('generation','generation'),('valid','active_valid'),('length','active_length'),('crc','active_crc'),
                             ('uploads','uploads'),('downloads','downloads'),('errors','errors')]:
                assert int(meta[name],16 if name=='crc' else 10)==case[key],f'{case["name"]} metadata {name}'
        statuses=[];requests=[];unloaded={};initializations=[]
        status_transactions={}
        for row in rows:
            raw=bytes.fromhex(row['data']);src=int(row['src_port']);dst=int(row['dst_port'])
            assert len(raw)==int(row['bytes']) and 4<=len(raw)<=516 and src>=49152
            op=struct.unpack_from('!H',raw)[0]
            if src>=57344:
                assert case['kind'] not in (0,3),'unexpected status without operation'
                if op==2:
                    assert dst==59 and raw==request(True,BASE+(b'.LNS' if case['kind']==2 else b'.LUS'))
                    if src not in status_transactions:
                        last_sequence=(last_sequence+1)&65535
                        status_transactions[src]=(raw,last_sequence)
                    else:assert status_transactions[src][0]==raw
                else:
                    assert op==3 and dst==55000 and raw[2:4]==b'\0\x01' and src in status_transactions
                    status=decode_status(raw[4:],case['kind']==2)
                    identity=(cid,src)
                    assert status['sequence']==status_transactions[src][1],'status counter'
                    if identity in seen_status:assert seen_status[identity]==raw,'status changed during retransmission'
                    else:seen_status[identity]=raw
                    statuses.append(status)
                continue
            if op in (1,2):
                assert dst==59
                if op==1:
                    assert raw in (request(False,HEADER),request(False,DATA));requests.append((row,HEADER if raw==request(False,HEADER) else DATA))
                else:assert case['kind']==2 and raw==request(True,DATA)
            elif op==3:
                block=struct.unpack_from('!H',raw,2)[0]
                if dst==40000:
                    reason=b'no image\0' if case['kind']==0 else b'\0'
                    body=b'A3'+struct.pack('!H',0x1000 if case['kind']==0 else 1)+bytes([len(reason)])+reason
                    assert raw==b'\0\x03\0\x01'+struct.pack('!I',len(body)+4)+body,'initialization file'
                    initializations.append(raw)
                else:
                    assert case['kind']==2 and dst==35000
                    if block in unloaded:assert unloaded[block]==raw[4:]
                    else:unloaded[block]=raw[4:]
            elif op==4:assert len(raw)==4 and dst in (40000,30001,30002)
            elif op==5:assert raw[-1:]==b'\0' and struct.unpack_from('!H',raw,2)[0] in (2,3,4,5)
            else:raise AssertionError(f'unknown output op {op}')
        for row in inputs:
            raw=bytes.fromhex(row['data']);src=int(row['src_port']);dst=int(row['dst_port'])
            assert len(raw)==int(row['bytes']) and len(raw)>=4
            op,block=struct.unpack_from('!HH',raw)
            if op==3:
                if src==40000:key='control'
                elif src==30001:key='header'
                elif src==30002:key='data'
                else:raise AssertionError('unexpected peer DATA')
                start=case[key+'_offset']+(block-1)*512;size=max(0,min(512,case[key+'_length']-(block-1)*512))
                assert raw[4:]==fixtures[start:start+size],f'peer fixture {key}'
        if case['kind']==2:
            assert list(sorted(unloaded))==list(range(1,len(unloaded)+1))
            assert len(unloaded[max(unloaded)])<512
            assert b''.join(unloaded[b] for b in sorted(unloaded))==bytes.fromhex(case['active_hex']),'downloaded bytes'
        if case['kind'] in (1,4):
            names=[name for _,name in requests]
            if case['mutation']=='list' or case['flags']&4:assert not names,'invalid/missing LUR fetched a file'
            else:
                assert HEADER in names
                if case['mutation'] in ('header_crc','hardware') or case['flags']&(2|32|256|512|4096):assert DATA not in names
                else:assert names.index(HEADER)<names.index(DATA),'data fetched before header'
        expected=case['expected_status']
        if expected:
            assert statuses and statuses[-1]['code']==expected,f'{case["name"]} terminal status'
            if expected>=0x1000:assert all(s['code']!=3 for s in statuses),'false completion on failed load'
        if case['flags']&2:
            header_requests=[row for row,name in requests if name==HEADER]
            assert len(header_requests)==4,'unbounded or missing retries'
            assert len({r['src_port'] for r in header_requests})==1
            assert len(statuses)>=10,'status blocked behind lost header data'
            for retry,(a,b) in enumerate(zip(header_requests,header_requests[1:])):
                assert int(b['start_cycle'])-int(a['end_cycle'])>=5000*(1<<retry)
        if case['flags']&4:assert len(statuses)>=10,'status not alive while waiting for LUR'
        if case['flags']&(16|128):
            assert any(s['exception']==1 for s in statuses),'WAIT did not appear in status exception timer'
        if case['flags']&256:assert sum(name==HEADER for _,name in requests)==3,'WAIT retry bound'
        if case['flags']&1024:assert all(s['exception']==0 for s in statuses),'wrong-TID WAIT was honored'
        if case['flags']&4096:assert any(s['exception']==65535 for s in statuses),'maximum WAIT not accepted'
        for status in statuses:
            if status['code']>=3:assert status['exception']==0,'terminal status carries stale exception timer'
        evidence.append(dict(name=case['name'],status_files=len(statuses),bulk_requests=len(requests),expected_generation=case['generation']))
        if case['kind']==4:last_sequence=-1;seen_status={}
    return dict(cases=len(golden['cases']),packets=len(packets),peer_packets=len(peer),
                tx_payload_bytes=sum(int(r['bytes']) for r in packets),case_results=evidence,
                clock_ns=8,profile=golden['profile'],whole_system_VO='NOT RUN')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--vo',type=Path);parser.add_argument('--provenance',type=Path)
    args=parser.parse_args()
    if args.vo:
        assert args.provenance and args.smoke
        export=json.loads(args.provenance.read_text());assert export['result']=='PASS' and sha(args.vo)==export['delivered_netlist_sha256']
        project=Path(export['source_project']);manifest=project/'project_manifest.json';assert sha(manifest)==export['source_manifest_sha256']
        for r in json.loads(manifest.read_text())['sources']:assert sha(ROOT/r['canonical_source'])==r['sha256']==sha(project/r['snapshot'])
    prefix='a615a_vo' if args.vo else 'a615a';index=1
    while (ROOT/f'build/logs/{prefix}_{index:03d}').exists():index+=1
    run=ROOT/f'build/logs/{prefix}_{index:03d}';run.mkdir(parents=True)
    sources=[ROOT/'rtl'/n for n in ('afdx_tftp_engine.v','afdx_atomic_file_store.v','afdx_615a_error_decoder.v','afdx_615a_endpoint.v')]
    if args.vo:sources=[ROOT/'build/logs/netlist_001'/n for n in ('altera_primitives.v','220model.v','stratix_atoms.v')]+[args.vo.resolve()]
    sources+=[ROOT/'sim/tb_615a_endpoint.sv']
    inputs=sources+[Path(__file__),ROOT/'scripts/generate_615a_golden.py',ROOT/'scripts/generate_tftp_golden.py',ROOT/'scripts/run_stage2_mgmt.py',ROOT/'scripts/modelsim_support.py']
    if args.vo:inputs+=[args.provenance]
    for p in inputs:shutil.copy2(p,run/p.name)
    golden=generate(run/'golden',args.smoke)
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work']
    commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{"+define+A615A_VO " if args.vo else ""}{p.name}' for p in sources]
    commands += ['vopt -O5 work.tb_615a_endpoint -o a615a_opt','vsim -t 1ps work.a615a_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    summary=dict(result='RUNNING',started_utc=datetime.now(timezone.utc).isoformat(),scope=golden['profile'],
                 RTL_DUT_compiled=not bool(args.vo),force_used=False,
                 fault_timeout_scaling=not bool(args.vo),inputs={str(p):sha(p) for p in inputs},golden={p.name:sha(p) for p in (run/'golden').iterdir()})
    proof=run/'summary.json';proof.write_text(json.dumps(summary,indent=2)+'\n')
    with (run/'console.log').open('wb') as log:
        proc=subprocess.Popen([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        summary['modelsim_pid']=proc.pid;proof.write_text(json.dumps(summary,indent=2)+'\n');print(f'A615A_RUN {run} PID {proc.pid}',flush=True);code=proc.wait(timeout=3600)
    text=(run/'transcript.log').read_text(errors='replace');error=None;evidence={}
    passed=code==0 and 'A615A_DIRECTED_PASS' in text and '** Error' not in text and '** Fatal' not in text
    if passed:
        try:evidence=verify(run,golden)
        except (AssertionError,ValueError,KeyError,IndexError) as exc:passed=False;error=str(exc)
    summary.update(result='PASS' if passed else 'FAIL',exit_code=code,error=error,evidence=evidence,completed_utc=datetime.now(timezone.utc).isoformat(),
                   artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='summary.json'})
    proof.write_text(json.dumps(summary,indent=2)+'\n');print(text[-1700:]);print(json.dumps(dict(run=str(run),result=summary['result'],error=error,cases=evidence.get('cases')),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
