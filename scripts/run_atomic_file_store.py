"""Verify the actual RAM bank swap, CRC, length, abort and read lease."""
import binascii
import json
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime,timezone
from run_stage2_mgmt import ROOT,MS,sha
from modelsim_support import prepare_ini


def main():
    index=1
    while (ROOT/f'build/logs/atomic_store_{index:03d}').exists():index+=1
    run=ROOT/f'build/logs/atomic_store_{index:03d}';g=run/'golden';g.mkdir(parents=True)
    a=b'123456789';b=bytes((i*23+17)&255 for i in range(4096));bad=b+b'x';vectors=a+bad
    crc=lambda x:binascii.crc_hqx(x,0xffff)
    actions=[];readback=bytearray()
    def begin(blob,wrong_crc=0,size=None):actions.append(f'begin_file({len(blob) if size is None else size},{crc(blob)^wrong_crc});')
    def write(offset,size):actions.append(f'write_blob({offset},{size});')
    def read(offset,blob,gen):actions.append(f'read_blob({offset},{len(blob)},{crc(blob)},{gen});');readback.extend(blob)
    begin(a);write(0,len(a));actions.append('finish_file(0);');read(0,a,1)
    begin(a,wrong_crc=1);write(0,len(a));read(0,a,1);actions.append('finish_file(3);');read(0,a,1)
    begin(a,size=10);write(0,len(a));actions.append('finish_file(3);');read(0,a,1)
    begin(b);write(len(a),37);actions.append('abort_stage=1;idle(1);abort_stage=0;idle(1);');read(0,a,1)
    begin(bad);write(len(a),len(bad));actions.append('finish_file(3);');read(0,a,1)
    begin(a);actions.append('write_valid=1;write_address=1;write_data=8\'h55;idle(1);write_valid=0;finish_file(3);');read(0,a,1)
    begin(b);write(len(a),len(b));actions.append('read_lock=1;finish_valid=1;idle(8);if(finish_ready||generation!=1)$fatal(1,"Read lease ignored");finish_valid=0;read_lock=0;finish_file(0);');read(len(a),b,2)
    begin(a);write(0,3);actions.append('reset=1;idle(2);reset=0;idle(1);if(active_valid||staging_active||generation!=0)$fatal(1,"Reset metadata");')
    begin(b'');actions.append('finish_file(0);');read(0,b'',1)
    begin(a);write(0,len(a));actions.append('finish_file(0);');read(0,a,2)
    (g/'vectors.mem').write_text(''.join(f'{v:02x}\n' for v in vectors));(g/'constants.vh').write_text(f'localparam VECTOR_BYTES={len(vectors)};\n')
    (g/'stimulus.vh').write_text('\n'.join(actions)+'\n');(g/'expected.mem').write_text(''.join(f'{v:02x}\n' for v in readback))
    sources=[ROOT/'rtl/afdx_atomic_file_store.v',ROOT/'sim/tb_atomic_file_store.sv'];inputs=sources+[Path(__file__),ROOT/'scripts/run_stage2_mgmt.py',ROOT/'scripts/modelsim_support.py']
    for p in inputs:shutil.copy2(p,run/p.name)
    prepare_ini(run,MS)
    commands=['onerror {quit -code 2 -force}','vlib work','vlog afdx_atomic_file_store.v','vlog -sv tb_atomic_file_store.sv',
              'vopt -O5 work.tb_atomic_file_store -o store_opt','vsim -t 1ps work.store_opt','run -all','quit -code 0 -force']
    (run/'run.do').write_text('\n'.join(commands)+'\n')
    env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'))
    with (run/'console.log').open('wb') as log:
        code=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do run.do'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120).returncode
    text=(run/'transcript.log').read_text(errors='replace');passed=code==0 and 'ATOMIC_STORE_PASS' in text and '** Fatal' not in text and '** Error' not in text
    if passed:passed=bytes.fromhex(''.join((run/'readback.mem').read_text().split()))==readback
    summary=dict(result='PASS' if passed else 'FAIL',exit_code=code,scenarios=10,readback_bytes=len(readback),
                 CRC16_reference='Python binascii.crc_hqx, init FFFF; 123456789 = 29B1',
                 inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},completed_utc=datetime.now(timezone.utc).isoformat(),
                 golden={p.name:sha(p) for p in g.iterdir()},artifacts={p.name:sha(p) for p in run.iterdir() if p.is_file()})
    (run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(text[-1000:]);print(json.dumps(dict(run=str(run),result=summary['result'],scenarios=10),indent=2))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
