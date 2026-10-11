"""Independent approved single-VL SN model plus real-wire vectors."""
from pathlib import Path
import argparse, hashlib, json
from generate_b2_golden import make_client, wire_for, write_mem

def successor(sn):
    return 1 if sn in (0,255) else sn+1

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    out=ap.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=True)
    cases=[];clients=bytearray();wires=bytearray();payloads=bytearray();commands=[]
    psn=None;missing=0;epoch=0
    def reset():
        nonlocal psn,missing,epoch
        epoch+=1;psn=None;missing=0;commands.append('reset_epoch();')
    def add(name,length,sn,source=0,mutation=None,action_override=None,command=True):
        nonlocal psn,missing
        ident=len(cases);client,app=make_client(ident,length,sn);c=bytearray(client)
        edits={'da':(0,2),'vlid':(5,1),'ether':(13,1),'ip_checksum':(25,1),
               'ip_version':(14,0x20),'udp_length':(39,1),'udp_port':(37,1),
               'padding':(43,0xa5)}
        if mutation in edits:
            offset,mask=edits[mutation];c[offset]^=mask
        if mutation=='truncate':c.pop()
        client=bytes(c);wire=wire_for(client,mutation=='fcs')
        action=action_override
        if action is None:
            if mutation=='fcs':action=4
            elif mutation:action=3
            elif sn==0:action=2;psn=0
            else:
                allowed=psn is None or sn in (successor(psn),successor(successor(psn)))
                if psn is not None and sn==successor(successor(psn)):missing+=1
                action=0 if allowed else 1;psn=sn
        case={'id':ident,'epoch':epoch,'name':name,'sn':sn,'source':'B1' if source else 'GMII_INJECT',
              'mutation':mutation,'action':action,'expected_psn':0 if psn is None else psn,
              'expected_psn_valid':psn is not None,'expected_missing':missing,
              'client_offset':len(clients),'client_length':len(client),
              'wire_offset':len(wires),'wire_length':len(wire),
              'payload_offset':len(payloads),'payload_length':length}
        cases.append(case);clients.extend(client);wires.extend(wire);payloads.extend(app)
        if command:commands.append(f'exercise({ident},{source});')
        return ident
    reset()
    for i,p in enumerate((1,16,17,18,1471,64,33)):add(f'boundary_{p}',p,i+1,1)
    reset()
    for i in range(256):add(f'wrap_{i+1}',1,(i%255)+1,1)
    for name,sn in [('plus2',3),('duplicate',3),('after_duplicate',4),('old',2),
                    ('after_old',3),('jump',100),('after_jump',101),('reset_control',0),
                    ('after_control_plus2',2)]:add(name,18,sn)
    for mutation in ('da','vlid','ether','ip_checksum','ip_version','udp_length',
                     'udp_port','padding','truncate','fcs'):
        add('bad_'+mutation,1 if mutation=='padding' else 64,200,mutation=mutation)
        add('recover_'+mutation,17,successor(psn))
    add('bad_protocol_zero',18,0,mutation='ip_checksum')
    add('recover_protocol_zero',18,successor(psn))
    reset();add('first_arbitrary',64,77);add('after_first',18,78)
    reset();add('first254',18,254);add('plus2_wrap1',18,1)
    add('old255',18,255);add('recover_wrap1',18,1)
    # Pressure phase is driven separately; four retained frames are checked
    # only after release. The fifth is a MAC capacity drop, so PSN stays 13.
    reset();pressure=[]
    for sn in range(10,14):pressure.append(add(f'pressure_{sn}',18,sn,command=False))
    dropped=add('capacity_drop_14',18,14,action_override=5,command=False)
    recovery=add('capacity_recovery_15',18,15,command=False)
    paused=add('accepted_reset_cancel_16',18,16,command=False)
    commands.append('pressure_reset_phase();')
    reset();add('first_after_cancel',33,200);add('after_cancel',18,201)
    write_mem(out/'client.mem',clients);write_mem(out/'wire.mem',wires);write_mem(out/'payload.mem',payloads)
    fields=('client_offset','client_length','wire_offset','wire_length','payload_offset','payload_length','sn','action')
    (out/'meta.mem').write_text(''.join(''.join(f'{c[f]:08X}' for f in fields)+'\n' for c in cases))
    (out/'expect.mem').write_text(''.join(f"{c['action']:08X}{c['expected_psn']:08X}{int(c['expected_psn_valid']):08X}{c['expected_missing']:08X}\n" for c in cases))
    (out/'scenario.vh').write_text('\n'.join(commands)+'\n')
    (out/'constants.vh').write_text(f'localparam integer CASE_COUNT={len(cases)};\n'+
        ''.join(f'localparam integer PRESSURE_{i}={v};\n' for i,v in enumerate(pressure))+
        f'localparam integer CAPACITY_DROP={dropped}, CAPACITY_RECOVERY={recovery}, RESET_CANCEL={paused};\n')
    (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    (out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(f'B2_FULL_GOLDEN = PASS cases={len(cases)} psn_model=APPROVED_XAPP_PROFILE')
if __name__=='__main__':main()
