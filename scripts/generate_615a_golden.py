"""Independent 615A control encoder and 665-2 configured LSAP reference.

String lengths, byte/word lengths and pointers are computed from sections.
CRC16 uses binascii; non-reflected CRC32 uses zlib with reflected I/O.
"""
import binascii
import json
import struct
import zlib
from pathlib import Path
from generate_tftp_golden import request

BASE=b'AFDX_01'
PN=b'AFDX-P1'
HW=b'AFDX'
HEADER=b'config.LUH'
DATA=b'config.bin'
DATA_PN=b'CFG-0001'
REV=bytes(int(f'{i:08b}'[::-1],2) for i in range(256))


def crc32(data):
    value=zlib.crc32(bytes(REV[b] for b in data))
    return int(f'{value:032b}'[::-1],2)


assert crc32(bytes(range(256)))==0xb6b5ee95


def string16(value):return struct.pack('!H',len(value))+value+b'\0'*(len(value)%2)
def string8(value):return bytes([len(value)+1])+value+b'\0'


def header(data):
    part=string16(PN)
    hardware=struct.pack('!H',1)+string16(HW)
    files=struct.pack('!HH',1,0)+string16(DATA)+string16(DATA_PN)+struct.pack('!IH',(len(data)+1)//2,binascii.crc_hqx(data,0xffff))
    part_offset=28;hardware_offset=part_offset+len(part);files_offset=hardware_offset+len(hardware)
    size=files_offset+len(files)+6
    prefix=struct.pack('!IHHIIIII',size//2,0x8003,0,part_offset//2,hardware_offset//2,files_offset//2,0,0)+part+hardware+files
    body=prefix+struct.pack('!H',binascii.crc_hqx(prefix,0xffff))
    return body+struct.pack('!I',crc32(body+data))


def control(downloading=False):
    body=b'A3'+struct.pack('!H',1)+string8(DATA if downloading else HEADER)
    body+=b'\0' if downloading else string8(PN)
    return struct.pack('!I',len(body)+4)+body


def decode_status(data,downloading):
    """Read the standard fields, independently of the RTL ROM offsets."""
    assert len(data)>=21 and struct.unpack_from('!I',data)[0]==len(data) and data[4:6]==b'A3'
    code=struct.unpack_from('!H',data,6)[0];position=8
    def text():
        nonlocal position
        size=data[position];position+=1;value=data[position:position+size];position+=size
        assert size and len(value)==size and value.endswith(b'\0')
        return value[:-1].rstrip(b' ')
    description=text()
    sequence,exception,estimated=struct.unpack_from('!HHH',data,position);position+=6
    ratio=data[position:position+3];position+=3;assert ratio.isdigit() and 0<=int(ratio)<=100
    count=struct.unpack_from('!H',data,position)[0];position+=2;assert count in (0,1)
    files=[]
    for _ in range(count):
        name=text();part=None;file_ratio=None
        if not downloading:part=text();file_ratio=data[position:position+3];position+=3
        status=struct.unpack_from('!H',data,position)[0];position+=2;detail=text()
        assert name==(DATA if downloading else HEADER)
        if not downloading:assert part==PN and file_ratio==ratio
        assert status==(0x1007 if code>=0x1000 else code)
        files.append(dict(name=name.decode(),status=status,description=detail.decode()))
    assert position==len(data),'trailing or truncated status data'
    assert code in (1,2,3,0x1003,0x1004,0x1005)
    assert description=={1:b'ready',2:b'loading',3:b'done',0x1003:b'failed',0x1004:b'failed',0x1005:b'failed'}[code]
    assert ratio==(b'100' if code==3 else b'000')
    return dict(code=code,sequence=sequence,files=files,ratio=int(ratio),exception=exception,estimated=estimated)


def generate(out,smoke=False,readback_failures=False):
    out.mkdir(parents=True)
    blob=bytearray();cases=[];meta=[];current=b'';valid=False;generation=uploads=downloads=errors=0
    def put(data):offset=len(blob);blob.extend(data);return offset
    templates={}
    for key,name,write in [('LUI',BASE+b'.LUI',False),('LND',BASE+b'.LND',False),('LUR',BASE+b'.LUR',True),('LNR',BASE+b'.LNR',True),
                           ('HEADER',HEADER,False),('DATA',DATA,False),('WRITE_DATA',DATA,True),('UNKNOWN',b'unknown.bin',False)]:
        packet=request(write,name);templates[key]=(put(packet),len(packet))
    for key,text in [('ERROR_WAIT',b'WAIT:1'),('ERROR_WAIT_ZERO',b'WAIT:0'),('ERROR_WAIT_MAX',b'WAIT:65535'),('ERROR_ABORT',b'ABORT:1005'),('ERROR_BAD_WAIT',b'WAIT:65536')]:
        packet=b'\0\x05\0\0'+text+b'\0';templates[key]=(put(packet),len(packet))
    def add(name,kind=1,image=None,mutation=None,flags=0,status=3):
        nonlocal current,valid,generation,uploads,downloads,errors
        raw=current if image is None else image
        h=bytearray(header(raw));wire_data=raw;ctl=control(kind==2)
        if mutation=='data':wire_data=bytes([raw[0]^1])+raw[1:]
        elif mutation=='load_crc':h[-1]^=1
        elif mutation=='header_crc':h[-6]^=1
        elif mutation=='hardware':
            h[42]^=1;h[-6:-4]=struct.pack('!H',binascii.crc_hqx(h[:-6],0xffff));h[-4:]=struct.pack('!I',crc32(h[:-4]+raw))
        elif mutation=='list':ctl=ctl[:6]+b'\0\x02'+ctl[8:]
        elif mutation=='length':wire_data=raw+b'\x12\x34'
        if kind==4:
            current=b'';valid=False;generation=uploads=downloads=errors=0;status=0
        elif kind==1 and status==3:
            current=raw;valid=True;generation+=1;uploads+=1
        elif kind==2 and status==3:downloads+=1
        elif status>=0x1000:errors+=1
        ho=put(h);do=put(wire_data);co=put(ctl)
        row=dict(id=len(cases),name=name,kind=kind,header_offset=ho,header_length=len(h),data_offset=do,data_length=len(wire_data),
                 control_offset=co,control_length=len(ctl),expected_status=status,generation=generation,
                 active_length=len(current),active_crc=binascii.crc_hqx(current,0xffff),active_valid=int(valid),
                 uploads=uploads,downloads=downloads,errors=errors,flags=flags,active_hex=current.hex(),mutation=mutation)
        cases.append(row)
        fields=[kind,ho,len(h),do,len(wire_data),co,len(ctl),status,generation,len(current),binascii.crc_hqx(current,0xffff),int(valid),uploads,downloads,errors,flags]
        meta.append(''.join(f'{x:08x}' for x in fields))
    first=bytes((i*41+(i>>3)+0x37)&255 for i in range(1024));second=bytes((i*13+0xa7)&255 for i in range(128))
    add('download initialization denied without an image',0,status=0)
    add('upload with independent status while header reply is lost',image=first,flags=0 if smoke else 1)
    add('media defined download of committed image',kind=2)
    add('data CRC rejection preserves old bank',image=second,mutation='data',status=0x1003)
    if not smoke or readback_failures:add('download after CRC rejection still returns old image',kind=2)
    add('total load CRC rejection despite valid per-file CRC',image=second,mutation='load_crc',status=0x1003)
    if readback_failures:add('download after total Load CRC rejection returns old image',kind=2)
    if not smoke:
        add('header CRC rejected',image=second,mutation='header_crc',status=0x1003)
        add('wrong hardware identity with valid CRCs',image=second,mutation='hardware',status=0x1003)
        add('unsupported LUR file count rejected',image=second,mutation='list',status=0x1003)
        add('payload length mismatch rejected',image=second,mutation='length',status=0x1003)
    add('subsequent valid upload recovers',image=second)
    add('download recovered image',kind=2)
    if not smoke:
        add('header WAIT grants one second then resumes',image=first,flags=16)
        add('operator ABORT identifies its source',image=second,flags=32,status=0x1005)
        add('data WAIT after a full staged block restarts safely',image=first,flags=128)
        add('status server WAIT before ACK0 is retried',image=second,flags=64)
        add('repeated zero-second WAIT is bounded',image=second,flags=256,status=0x1004)
        add('WAIT above 65535 seconds is rejected',image=second,flags=512,status=0x1004)
        add('wrong TID WAIT cannot change timeout classification',image=first,flags=3072,status=0x1003)
        add('wrong TID WAIT cannot delay valid data',image=first,flags=1024)
        add('maximum WAIT is accepted and operator can abort via status',image=second,flags=4096,status=0x1005)
        add('all header responses lost, status remains live',image=first,flags=2,status=0x1003)
        add('LUR deadline expires with status still live',image=first,flags=4,status=0x1003)
        add('unknown file does not start an operation',kind=3,status=0)
        add('reset discards only volatile metadata and cancels staging',kind=4,image=first,flags=8)
        add('valid upload after reset',image=second)
        maximum=bytes((i*19+5)&255 for i in range(4096));add('full 4096-byte load',image=maximum)
        add('full 4096-byte download',kind=2)
        add('empty load uses a zero-byte final DATA',image=b'')
        add('empty download',kind=2)
    (out/'fixtures.mem').write_text(''.join(f'{b:02x}\n' for b in blob));(out/'cases.mem').write_text('\n'.join(meta)+'\n')
    constants=f'localparam WELL_KNOWN_PORT=59;\nlocalparam CASE_COUNT={len(cases)},FIXTURE_BYTES={len(blob)};\n'
    for key,(offset,length) in templates.items():constants+=f'localparam {key}_OFFSET={offset},{key}_LENGTH={length};\n'
    (out/'constants.vh').write_text(constants)
    result=dict(cases=cases,templates=templates,profile='ARINC615A-2 (A3, UDP 59), canonical 665-2 one-LSAP/config.bin target, 0..4096 even bytes',smoke=smoke)
    (out/'cases.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
