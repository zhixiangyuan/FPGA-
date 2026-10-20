"""Independent multi-VL wire/error/SN reference, with correctly recomputed FCS."""
from pathlib import Path
import struct,json,hashlib
from frozen_frame_reference import make_client,wire_for,checksum

def generate(out,performance=False):
 out.mkdir(parents=True,exist_ok=True);cases=[];wireblob=bytearray();appblob=bytearray();meta=[];psn={}
 def packet(vl,sn,length,mutation=None,udp_checked=True,srcport=24,dstport=23):
  cid=len(cases);client,app=make_client(cid,length,sn);b=bytearray(client)
  vlid=0x1234+vl;b[4:6]=struct.pack('!H',vlid)
  b[34:38]=struct.pack('!HH',srcport,dstport)
  if udp_checked:
   pseudo=b[26:34]+bytes((0,17))+b[38:40]
   csum=checksum(pseudo+b[34:42+length]);b[40:42]=struct.pack('!H',csum or 0xffff)
  if mutation=='ip_checksum':b[24]^=1
  elif mutation=='udp_checksum':b[40]^=1
  elif mutation=='payload':b[42]^=1
  elif mutation=='padding':b[42+length]=1
  elif mutation=='length':b[39]^=1
  action=1;reason=0;previous=psn.get(vl)
  step=lambda n:1 if n in (0,255) else n+1
  if mutation=='fcs':action=5;reason=0
  elif not 0<=vl<16:action=4;reason=2
  elif mutation:
   action=4;reason={'ip_checksum':4,'udp_checksum':5,'payload':5,'padding':7,'length':6}[mutation]
  elif sn==0:action=3;psn[vl]=0
  else:
   if previous is not None and sn not in (step(previous),step(step(previous))):action=2
   psn[vl]=sn
  wire=wire_for(bytes(b),corrupt_fcs=mutation=='fcs')
  case={'id':cid,'vl':vl,'vlid':vlid,'sn':sn,'length':length,'action':action,'reason':reason,
        'src_port':srcport,'dst_port':dstport,'wire_offset':len(wireblob),'wire_length':len(wire),
        'payload_offset':len(appblob),'psn_after':psn.get(vl),'mutation':mutation,'BAG_cycles':125000}
  vals=[len(wireblob),len(wire),len(appblob),length,vlid,sn,action,reason]
  meta.append(''.join(f'{v:08x}' for v in vals));cases.append(case);wireblob.extend(wire);appblob.extend(app)
 for n in range(256):
  for vl in range(16):packet(vl,n%255+1,1471 if performance else 1+(n*7+vl)%64,udp_checked=(n%3!=0))
 for vl in range(16):
  for sn,length,mutation in ((3,1471,None),(3,17,None),(2,18,None),(100,19,None),(101,20,None),
                            (102,33,'ip_checksum'),(102,34,None),(103,35,'udp_checksum'),(103,36,None),
                            (104,37,'payload'),(104,38,None),(105,1,'padding'),(105,1,None),
                            (106,64,'length'),(106,64,None),(107,65,'fcs'),(107,65,None),
                            (0,3,None),(1,4,None)):
   packet(vl,sn,length,mutation)
 packet(16,5,17)
 for dst in (161,69,123):packet(0,psn[0]+1,48,srcport=49152,dstport=dst)
 for name,blob in (('wire.mem',wireblob),('payload.mem',appblob)):
  (out/name).write_text(''.join(f'{v:02x}\n' for v in blob))
 (out/'meta.mem').write_text('\n'.join(meta)+'\n')
 (out/'ports.mem').write_text('\n'.join(f"{c['src_port']:04x}{c['dst_port']:04x}" for c in cases)+'\n')
 (out/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)}, WIRE_BYTES={len(wireblob)}, APP_BYTES={len(appblob)};\n')
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 (out/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},indent=2)+'\n')
 return {'cases':len(cases),'accepted':sum(c['action']==1 for c in cases),'VL_count':16,'wrap_per_VL':256,
         'profile':'1471-byte sustained load, 8000-cycle global source interval' if performance else 'directed variable lengths'}
