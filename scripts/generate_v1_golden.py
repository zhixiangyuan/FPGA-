"""Independent wire/Payload/PSN/TX-SN oracle for the team echo profile."""
from pathlib import Path
import argparse,json,hashlib
from frozen_frame_reference import make_client,wire_for,write_mem
def nxt(sn):return 1 if sn in (0,255) else sn+1
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);out=ap.parse_args().out;out.mkdir(parents=True)
 cases=[];incoming=bytearray();outgoing=bytearray();payload=bytearray();commands=[]
 psn=None;missing=0;txsn=1;epoch=0
 def reset():
  nonlocal psn,missing,txsn,epoch
  psn=None;missing=0;txsn=1;epoch+=1;commands.append('reset_epoch();')
 def add(name,p,sn,mutation=None,override=None,command=True):
  nonlocal psn,missing,txsn
  ident=len(cases);client,data=make_client(ident,p,sn);c=bytearray(client)
  edits={'da':(0,2),'vlid':(5,1),'ether':(13,1),'ip_checksum':(25,1),'ip_version':(14,0x20),'udp_length':(39,1),'udp_port':(37,1),'udp_checksum':(41,1),'padding':(43,0xa5)}
  if mutation in edits:o,mask=edits[mutation];c[o]^=mask
  if mutation=='truncate':c.pop()
  action=override
  if action is None:
   if mutation=='fcs':action=4
   elif mutation:action=3
   elif sn==0:action=2;psn=0
   else:
    action=0 if psn is None or sn in (nxt(psn),nxt(nxt(psn))) else 1
    if psn is not None and sn==nxt(nxt(psn)):missing+=1
    psn=sn
  # Explicit pressure/reset cases are independently specified transactions.
  if override in (0,6):
   if psn is not None and sn==nxt(nxt(psn)):missing+=1
   psn=sn
  w=wire_for(bytes(c),mutation=='fcs');echo=b'';sent_sn=0
  if action==0:
   outclient,_=make_client(ident,p,txsn);echo=wire_for(outclient);sent_sn=txsn;txsn=nxt(txsn)
  row={'id':ident,'epoch':epoch,'name':name,'rx_sn':sn,'tx_sn':sent_sn,'action':action,'mutation':mutation,
       'incoming_offset':len(incoming),'incoming_length':len(w),'outgoing_offset':len(outgoing),'outgoing_length':len(echo),
       'payload_offset':len(payload),'payload_length':p,'expected_psn':psn or 0,'expected_valid':psn is not None,'expected_missing':missing}
  cases.append(row);incoming.extend(w);outgoing.extend(echo);payload.extend(data)
  if command:commands.append(f'exercise({ident});')
  return ident
 reset()
 for i,p in enumerate((1,16,17,18,1471,64,33)):add('boundary_'+str(p),p,77+i)
 reset()
 for i in range(256):add('wrap_'+str(i+1),1,i%255+1)
 for name,sn in [('plus2',3),('duplicate',3),('after_duplicate',4),('old',2),('after_old',3),('jump',100),('after_jump',101),('control_zero',0),('recover_zero',2)]:add(name,18,sn)
 for mut in ('da','vlid','ether','ip_checksum','ip_version','udp_length','udp_port','udp_checksum','padding','truncate','fcs'):
  add('bad_'+mut,1 if mut=='padding' else 64,200,mut);add('recover_'+mut,17,nxt(psn))
 add('bad_protocol_zero',18,0,'ip_checksum');add('recover_protocol_zero',18,nxt(psn))
 reset();add('first254',18,254);add('plus2_wrap1',18,1);add('old255',18,255);add('recover_wrap1',18,1)
 reset();prime=add('pressure_prime',18,10)
 retained=[add('pressure_retained_'+str(sn),18,sn,override=0,command=False) for sn in range(11,17)]
 drop=add('capacity_drop_17',18,17,override=5,command=False)
 recovery=add('capacity_recovery_18',18,18,override=0,command=False)
 cancel=add('reset_cancel_19',18,19,override=6,command=False)
 commands.append('pressure_phase('+','.join(str(x) for x in retained+[drop,recovery,cancel])+');')
 reset();add('first_after_reset',33,200);add('after_reset',18,201)
 partial=add('reset_mid_wire',1471,202,override=7,command=False);commands.append(f'partial_reset({partial});')
 reset();add('first_after_partial',64,77);add('after_partial',18,78)
 fields=('incoming_offset','incoming_length','payload_offset','payload_length','rx_sn','outgoing_offset','outgoing_length','action')
 write_mem(out/'incoming.mem',incoming);write_mem(out/'outgoing.mem',outgoing);write_mem(out/'payload.mem',payload)
 (out/'meta.mem').write_text(''.join(''.join(f'{c[n]:08X}' for n in fields)+'\n' for c in cases))
 (out/'expect.mem').write_text(''.join(f"{c['expected_psn']:08X}{int(c['expected_valid']):08X}{c['expected_missing']:08X}{c['tx_sn']:08X}\n" for c in cases))
 (out/'scenario.vh').write_text('\n'.join(commands)+'\n')
 tx=sum(c['action']==0 for c in cases);apps=sum(c['action'] in (0,6) for c in cases)
 (out/'constants.vh').write_text(f'localparam integer CASE_COUNT={len(cases)},EXPECTED_TX_FRAMES={tx},EXPECTED_APP_FRAMES={apps};\n')
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
 (out/'sha256.json').write_text(json.dumps(hashes,indent=2)+'\n')
 print('V1_GOLDEN',len(cases),'cases',tx,'TX',apps,'app frames')
if __name__=='__main__':main()
