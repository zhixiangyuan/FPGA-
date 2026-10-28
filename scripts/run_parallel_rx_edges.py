"""CRC/PHY/truncation/length/header rejection before any application byte."""
from pathlib import Path
from datetime import datetime,timezone
import csv,json,os,shutil,subprocess,zlib
from run_competition import ROOT,MS,sha
from frozen_frame_reference import make_client,checksum
from modelsim_support import prepare_ini

def main():
    i=1
    while (ROOT/f'build/logs/parallel_rx_edges_{i:03d}').exists():i+=1
    run=ROOT/f'build/logs/parallel_rx_edges_{i:03d}';run.mkdir(parents=True);g=run/'golden';g.mkdir()
    blob=bytearray();meta=[];cases=[];expected={}
    def add(kind):
        cid=len(cases);body,app=make_client(cid,64,1);body=bytearray(body);preamble=b'\x55'*7+b'\xd5';phy=65535
        changes={'da':0,'source_mac':6,'type':12,'ihl':14,'tos':15,'id':19,'fragment':20,'ttl':22,'protocol':23,'source_ip':26,'destination_ip':30,'source_port':34,'destination_port':36,'ip_checksum':24,'udp_length':39}
        if kind in changes:body[changes[kind]]^=1
        if kind in ('ihl','tos','id','fragment','ttl','protocol','source_ip','destination_ip'):
            body[24:26]=b'\x00\x00';body[24:26]=checksum(body[14:34]).to_bytes(2,'big')
        if kind in ('zero_ip_length','huge_ip_length'):
            body[16:18]=b'\x00\x00' if kind=='zero_ip_length' else b'\xff\xff'
            body[24:26]=b'\x00\x00';body[24:26]=checksum(body[14:34]).to_bytes(2,'big')
        if kind=='truncated':body=body[:-3]
        if kind=='extra_tail':body.extend(b'\x00\x00')
        if kind=='oversize':body.extend(b'\x00'*(1515-len(body)))
        if kind=='runt':body=body[:59]
        if kind=='short_preamble':preamble=b'\x55'*6+b'\xd5'
        if kind=='long_preamble':preamble=b'\x55'*8+b'\xd5'
        if kind=='sfd':preamble=b'\x55'*7+b'\xd4'
        wire=preamble+body+zlib.crc32(body).to_bytes(4,'little')
        if kind=='fcs':wire=wire[:-1]+bytes([wire[-1]^1])
        if kind=='phy':phy=14
        if kind=='phy_last_fcs':phy=len(wire)-1
        n=64 if kind=='valid' else 0
        meta.append(f'{len(blob):08x}{len(wire):04x}{phy:04x}{n:04x}');blob.extend(wire)
        cases.append(dict(id=cid,kind=kind,expected_bytes=n));expected[cid]=app if n else b''
    add('valid')
    for kind in ['da','source_mac','type','ihl','tos','id','fragment','ttl','protocol','source_ip','destination_ip','source_port','destination_port','ip_checksum','udp_length','zero_ip_length','huge_ip_length','truncated','extra_tail','oversize','runt','short_preamble','long_preamble','sfd','fcs','phy','phy_last_fcs']:
        add(kind);add('valid')
    (g/'wire.mem').write_text(''.join(f'{b:02x}\n' for b in blob));(g/'meta.mem').write_text('\n'.join(meta)+'\n')
    (g/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)},WIRE_BYTES={len(blob)};\n')
    (g/'cases.json').write_text(json.dumps(cases,indent=2)+'\n');(g/'expected.json').write_text(json.dumps({str(k):v.hex() for k,v in expected.items()})+'\n')
    files=[ROOT/'vendor/frozen/mac_crc32_byte.v',ROOT/'rtl/afdx_mac_rx_checked.v',ROOT/'rtl/afdx_multi_vl_rx_parser.v',ROOT/'sim/tb_parallel_rx_edges.sv']
    inputs=files+[Path(__file__),ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/modelsim_support.py']
    for f in inputs:shutil.copy2(f,run/f.name)
    prepare_ini(run,MS);cmd=['onerror {quit -code 2 -force}','vlib work']+[f'vlog {"-sv " if f.suffix==".sv" else ""}{f.name}' for f in files]
    cmd+=['vopt -O5 work.tb_parallel_rx_edges -o edge_opt','vsim -t 1ps work.edge_opt','run -all','quit -code 0 -force'];(run/'run.do').write_text('\n'.join(cmd)+'\n')
    proof=dict(result='RUNNING',clock_ns=8,started_utc=datetime.now(timezone.utc).isoformat(),inputs={str(f.relative_to(ROOT)):sha(f) for f in inputs},golden={f.name:sha(f) for f in g.iterdir()})
    p=run/'summary.json';p.write_text(json.dumps(proof,indent=2)+'\n');env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    with (run/'console.log').open('wb') as log:code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
    text=(run/'transcript.log').read_text(errors='replace');ok=code==0 and 'PARALLEL_RX_EDGES_PASS' in text and '** Error' not in text and '** Fatal' not in text;error=None
    if ok:
        try:
            actual={cid:bytearray() for cid in expected}
            for r in csv.DictReader((run/'application.csv').open()):actual[int(r['case_id'])].append(int(r['data']))
            assert all(bytes(actual[cid])==v for cid,v in expected.items())
            assert all(sha(ROOT/n)==h for n,h in proof['inputs'].items())
        except Exception as exc:ok=False;error=repr(exc)
    proof.update(result='PASS' if ok else 'FAIL',exit_code=code,error=error,cases=len(cases),bad_cases=27,completed_utc=datetime.now(timezone.utc).isoformat())
    p.write_text(json.dumps(proof,indent=2)+'\n');print(text[-850:]);print(json.dumps({k:v for k,v in proof.items() if k not in ('inputs','golden')},indent=2));return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
