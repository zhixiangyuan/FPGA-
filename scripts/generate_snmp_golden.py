"""Independent ASN.1 BER encoder and MIB profile vectors, RFC1157/1213."""
from pathlib import Path
import json,hashlib
def tlv(tag,data):
 n=len(data)
 length=bytes([n]) if n<128 else bytes((0x81,n)) if n<256 else b'\x82'+n.to_bytes(2,'big')
 return bytes([tag])+length+data
def integer(n,tag=2):
 if n>=0:
  b=n.to_bytes(max(1,(n.bit_length()+7)//8),'big');b=(b'\0'+b) if b[0]&128 else b
 else:
  size=1
  while not -(1<<(size*8-1))<=n<(1<<(size*8-1)):size+=1
  b=n.to_bytes(size,'big',signed=True)
 return tlv(tag,b)
def oid(id):return tlv(6,bytes((43,6,1,2,1,1,id,0)))
def message(pdu,rid,community,bindings,status=0,index=0,version=0):
 body=integer(rid)+integer(status)+integer(index)+tlv(0x30,b''.join(tlv(0x30,o+v) for o,v in bindings))
 return tlv(0x30,integer(version)+tlv(4,community)+tlv(pdu,body))
def generate(out):
 out.mkdir(parents=True,exist_ok=True);cases=[];rx=bytearray();tx=bytearray();metas=[]
 name=b'afdx-s2';contact=b'afdx-es-team3';location=b'AFDX lab bench';null=tlv(5,b'')
 def add(label,pdu=0xa0,id=1,value=null,community=b'public',ticks=12345,rid=42,mutation=None,multi=False,version=0):
  nonlocal name,contact,location
  bindings=[(oid(id),value)]
  if multi:bindings.append((oid(3),null))
  packet=message(pdu,rid,community,bindings,version=version);response=b'';status=0;index=0
  valid=community in (b'public',b'private') and pdu in (0xa0,0xa1,0xa3) and mutation is None and version in (0,1)
  if valid:
   if pdu==0xa1:
    selected=next((c for c in range(1,7) if id<c),0)
   else:
    selected=id if id in range(1,7) else 0
   if multi:status=1
   elif not selected:status=2;index=1
   elif pdu==0xa3:
    if community!=b'private' or selected not in (4,5,6):status=4;index=1
    elif not value or value[0]!=4 or len(value[2:])>32:status=3;index=1
    elif selected==4:contact=value[2:]
    elif selected==6:location=value[2:]
    else:name=value[2:]
   if status:response=message(0xa2,rid,community,bindings,status,index,version)
   else:
    if selected==1:v=tlv(4,b'AFDX FPGA RTL endpoint')
    elif selected==2:v=tlv(6,bytes((43,6,1,4,1)))
    elif selected==3:v=integer(ticks,0x43)
    elif selected==4:v=tlv(4,contact)
    elif selected==6:v=tlv(4,location)
    else:v=tlv(4,name)
    response=message(0xa2,rid,community,[(oid(selected),v)],version=version)
  if mutation=='truncated':packet=packet[:-1]
  elif mutation=='outer_length':packet=packet[:1]+bytes([packet[1]+1])+packet[2:]
  elif mutation=='indefinite':packet=packet[:1]+b'\x80'+packet[2:]
  elif mutation=='version':packet=packet[:4]+b'\x01'+packet[5:]
  elif mutation=='long_root':
   # BER long length is legal here; response is generated canonically.
   packet=packet[:1]+b'\x81'+packet[1:]
   selected=id;v=tlv(4,b'AFDX FPGA RTL endpoint')
   response=message(0xa2,rid,community,[(oid(selected),v)],version=version)
  c={'id':len(cases),'name':label,'input_offset':len(rx),'input_length':len(packet),
     'output_offset':len(tx),'output_length':len(response),'uptime_ticks':ticks,'trap':False,
     'expected_sys_name':name.decode('ascii'),'dst_port':49152,'error_status':status}
  cases.append(c);metas.append(''.join(f'{v:08x}' for v in (len(rx),len(packet),len(tx),len(response),ticks,0)))
  rx.extend(packet);tx.extend(response)
 for id in (1,2,3,4,5,6):add(f'get_{id}',id=id)
 for id in (0,1,2,3,4,5,6):add(f'next_{id}',pdu=0xa1,id=id)
 for ticks in (0,127,128,32767,32768,0x7fffffff,0x80000000,0xffffffff):add(f'uptime_{ticks}',id=3,ticks=ticks,rid=-128)
 for rid in (-129,-32769,-8388609,127,128,32768,8388608):add(f'request_id_{rid}',rid=rid)
 add('set_name',pdu=0xa3,id=5,value=tlv(4,b'flight-rtl'),community=b'private')
 add('get_updated_name',id=5)
 add('set_contact',pdu=0xa3,id=4,value=tlv(4,b'ops@afdx-lab'),community=b'private')
 add('get_contact',id=4)
 add('set_location',pdu=0xa3,id=6,value=tlv(4,b'Rack 7 bay 2'),community=b'private')
 add('get_location',id=6)
 add('set_object_id',pdu=0xa3,id=2,value=integer(1),community=b'private')
 add('set_empty_name',pdu=0xa3,id=5,value=tlv(4,b''),community=b'private');add('get_empty_name',id=5)
 add('set_max_name',pdu=0xa3,id=5,value=tlv(4,b'A'*32),community=b'private');add('get_max_name',id=5)
 add('set_too_long',pdu=0xa3,id=5,value=tlv(4,b'B'*33),community=b'private')
 add('set_wrong_type',pdu=0xa3,id=5,value=integer(1),community=b'private')
 add('set_readonly',pdu=0xa3,id=3,value=integer(1),community=b'private')
 add('set_public',pdu=0xa3,id=5,value=tlv(4,b'bad'),community=b'public')
 add('unknown_oid',id=9);add('multiple_bindings',multi=True)
 add('bad_community',community=b'guess');add('unsupported_pdu',pdu=0xa5)
 add('get_v2c',id=1,version=1)
 add('next_v2c',pdu=0xa1,id=3,version=1)
 add('set_v2c_name',pdu=0xa3,id=5,value=tlv(4,b'v2c-name'),community=b'private',version=1)
 add('get_v2c_name',id=5,version=1)
 add('bad_version',id=1,version=2)
 for mutation in ('truncated','outer_length','indefinite','long_root'):
  add(mutation,mutation=mutation);add(mutation+'_recovery')
 for ticks in (0,128,0xffffffff):
  body=tlv(6,b'\0')+tlv(0x40,bytes((10,0,0,9)))+integer(0)+integer(0)+integer(ticks,0x43)+tlv(0x30,b'')
  trap=tlv(0x30,integer(0)+tlv(4,b'public')+tlv(0xa4,body))
  c={'id':len(cases),'name':'coldStart','input_offset':len(rx),'input_length':0,'output_offset':len(tx),'output_length':len(trap),
     'uptime_ticks':ticks,'trap':True,'expected_sys_name':name.decode(),'dst_port':162}
  cases.append(c);metas.append(''.join(f'{v:08x}' for v in (len(rx),0,len(tx),len(trap),ticks,1)));tx.extend(trap)
 for file,blob in (('requests.mem',rx),('responses.mem',tx)):(out/file).write_text(''.join(f'{b:02x}\n' for b in blob))
 (out/'meta.mem').write_text('\n'.join(metas)+'\n')
 (out/'constants.vh').write_text(f'localparam CASE_COUNT={len(cases)}, RX_BYTES={len(rx)}, TX_BYTES={len(tx)};\n')
 (out/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 (out/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},indent=2)+'\n')
 return {'cases':len(cases),'scope':'SNMPv1 single-varbind MIB profile and coldStart; no whole-network claim'}
