"""RFC4330 unicast packet vectors; controlled input time, no DUT values."""
from pathlib import Path
import json,struct,hashlib
def generate(out):
 out.mkdir(parents=True,exist_ok=True);cases=[];blob=bytearray();requests=bytearray();meta=[]
 mutations=['valid','origin','li','version','mode','stratum','root','peer','port','truncated']
 for group,mutation in enumerate(mutations):
  t1=0xe900000000000000+(group<<32);t2=t1+(1<<24);t3=t2+(1<<20);t4=t1+(1<<21)
  request=bytearray(48);request[0]=0x23;request[2]=6;request[3]=0xe8;request[40:48]=struct.pack('!Q',t1);requests+=request
  valid=bytearray(48);valid[0]=0x24;valid[1]=2;valid[24:48]=struct.pack('!QQQ',t1,t2,t3)
  variants=[(mutation,False)] if mutation=='valid' else [(mutation,True),('recovery',False)]
  for name,bad in variants:
   packet=bytearray(valid);peer=0x0a000002;port=123
   if name=='origin':packet[31]^=1
   elif name=='li':packet[0]|=0xc0
   elif name=='version':packet[0]=0x1c
   elif name=='mode':packet[0]=0x23
   elif name=='stratum':packet[1]=0
   elif name=='root':packet[8:12]=struct.pack('!I',0x00020000)
   elif name=='peer':peer+=1
   elif name=='port':port=124
   elif name=='truncated':packet=packet[:-1]
   row={'id':len(cases),'group':group,'new_request':name==mutation,'bad':bad,'name':name,
        'offset':len(blob),'length':len(packet),'t1':t1,'t2':t2,'t3':t3,'t4':t4,'peer':peer,'port':port}
   meta.append(''.join(f'{v:08x}' for v in (int(row['new_request']),len(blob),len(packet),int(not bad),group,peer,port)))
   blob.extend(packet);cases.append(row)
 (out/'responses.mem').write_text(''.join(f'{b:02x}\n' for b in blob))
 (out/'requests.mem').write_text(''.join(f'{b:02x}\n' for b in requests))
 (out/'meta.mem').write_text('\n'.join(meta)+'\n')
 (out/'times.mem').write_text('\n'.join(''.join(f"{r[k]:016x}" for k in ('t1','t2','t3','t4')) for r in cases)+'\n')
 (out/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)}, RX_BYTES={len(blob)}, TX_BYTES={len(requests)};\n')
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 (out/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},indent=2)+'\n')
 return {'cases':len(cases),'requests':len(mutations),'timeout_cycles':125000000}
