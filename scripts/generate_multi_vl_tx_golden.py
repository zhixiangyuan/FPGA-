"""Independent Ethernet/IP/UDP/AFDX and FCS Golden for 16-VL TX."""
from pathlib import Path
import json,hashlib
from frozen_frame_reference import make_client,wire_for

def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    cases=[];wire_blob=bytearray();app_blob=bytearray();meta=[]
    for cid in range(4097):
        vl=cid%16 if cid<4096 else 3
        sn=(cid//16)%255+1 if cid<4096 else 1
        length=1471 if cid<4096 else 17
        client,app=make_client(cid,length,sn)
        client=client[:4]+(0x1234+vl).to_bytes(2,'big')+client[6:]
        wire=wire_for(client)
        row={'id':cid,'vl':vl,'sn':sn,'length':length,'wire_offset':len(wire_blob),'payload_offset':len(app_blob),
             'wire_length':len(wire),'epoch':0 if cid<4096 else 1}
        cases.append(row)
        values=[vl,sn,length,len(wire_blob),len(app_blob),len(wire)]
        meta.append(''.join(f'{v:08x}' for v in values))
        wire_blob+=wire;app_blob+=app
    (out/'wire.mem').write_text(''.join(f'{b:02x}\n' for b in wire_blob))
    (out/'payload.mem').write_text(''.join(f'{b:02x}\n' for b in app_blob))
    (out/'meta.mem').write_text('\n'.join(meta)+'\n')
    (out/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)}, WIRE_BYTES={len(wire_blob)}, APP_BYTES={len(app_blob)};\n')
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    (out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    return {'cases':len(cases),'wire_bytes':len(wire_blob),'payload_bytes':len(app_blob),'VL_count':16,'SN_wrap_frames_per_VL':256}
