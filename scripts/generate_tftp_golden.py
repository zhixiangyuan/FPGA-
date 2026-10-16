"""Independent RFC1350 packet encoder and bounded transfer/atomicity scenarios."""
from pathlib import Path
import json
import struct


def request(write=False,name=b'config.bin',mode=b'octet'):
    return struct.pack('!H',2 if write else 1)+name+b'\0'+mode+b'\0'


def data(block,payload):return struct.pack('!HH',3,block)+payload
def ack(block):return struct.pack('!HH',4,block)
def error(code):return struct.pack('!HH',5,code)+b'\0'


def generate(out):
    out.mkdir(parents=True)
    incoming=bytearray();expected=bytearray();actions=['restart();'];packets=[];commits=[];cases=[]
    def case(name):cases.append(name);actions.append('// '+name)
    def send(packet,src=50000,dst='tid'):
        actions.append(f'send_packet({len(incoming)},{len(packet)},{src},{dst});');incoming.extend(packet)
    def expect(packet,src='tid',dst=50000):
        actions.append(f'expect_packet({len(expected)},{len(packet)},{src},{dst});')
        packets.append(dict(index=len(packets),data=packet.hex(),src=str(src),dst=dst));expected.extend(packet)
    def wrq():
        send(request(True),dst='69');expect(ack(0),'0');actions.append('old_tid=tid;tid=last_src;')
    def rrq(blob):
        send(request(False),src=50002,dst='69');expect(data(1,blob[:512]),'0',50002)
        actions.append('old_tid=tid;tid=last_src;if(tid==old_tid)$fatal(1,"TID reused");')
    def upload(blob):
        wrq()
        for i in range(len(blob)//512+1):
            part=blob[i*512:(i+1)*512]
            send(data(i+1,part));expect(ack(i+1))
        commits.append(blob.hex())
    p=bytes((i*37+(i>>2)+0x53)&255 for i in range(512))
    tail=bytes(range(17));image=p+tail
    case('WRQ duplicate, wrong TID, duplicate DATA, out of order, short EOF')
    wrq();actions.append('saved_opens=opens;')
    send(request(True),dst='69');expect(ack(0));actions.append('if(opens!=saved_opens)$fatal(1,"Duplicate WRQ reopened file");')
    send(data(1,b'poison'),src=50001);expect(error(5),dst=50001)
    send(data(1,p));expect(ack(1));actions.append('saved_writes=writes;')
    send(data(1,b'changed duplicate'));expect(ack(1));actions.append('if(writes!=saved_writes)$fatal(1,"Duplicate DATA wrote twice");')
    send(data(3,b'future'));actions.append('quiet(30);')
    send(data(2,tail));expect(ack(2));commits.append(image.hex());actions.append('saved_commits=commits;')
    send(data(2,tail));expect(ack(2));actions.append('if(commits!=saved_commits)$fatal(1,"Duplicate EOF committed twice");')
    case('RRQ timeout resends DATA, duplicate ACK stays silent, short EOF')
    rrq(image);send(ack(0),src=50002);actions.append('quiet(40);')
    expect(data(1,p),dst=50002)
    packets[-1]['retry_wait_cycles']=5000
    send(ack(1),src=50002);expect(data(2,tail),dst=50002);send(ack(2),src=50002);actions.append('quiet(20);')
    case('zero length file')
    upload(b'');rrq(b'');send(ack(1),src=50002);actions.append('quiet(20);')
    case('exact 512-byte multiple needs an empty final DATA block')
    upload(p);rrq(p);send(ack(1),src=50002);expect(data(2,b''),dst=50002);send(ack(2),src=50002);actions.append('quiet(20);')
    case('4096-byte boundary')
    big=(p+bytes(reversed(p)))*4
    upload(big)
    case('4097-byte failure preserves previous image')
    wrq()
    for i in range(8):send(data(i+1,big[i*512:(i+1)*512]));expect(ack(i+1))
    send(data(9,b'x'));expect(error(3));actions += ['quiet(20);','if(active_length!=4096)$fatal(1,"Overflow changed active image");']
    case('backend CRC/commit failure preserves previous image')
    wrq();actions.append('file_finish_error=3;');send(data(1,b'bad-check-value'));expect(error(3));actions.append('file_finish_error=0;quiet(20);')
    case('remote ERROR cancels partial transfer')
    wrq();send(data(1,p));expect(ack(1));send(error(0));actions.append('quiet(20);if(active_length!=4096)$fatal(1,"Abort changed image");')
    case('finite retries and recovery')
    wrq();send(data(1,p));expect(ack(1))
    for retry in range(3):
        expect(ack(1));packets[-1]['retry_wait_cycles']=5000*(1<<retry)
    actions += ['saved_failures=failures;','idle(40100);','if(failures!=saved_failures+1||busy)$fatal(1,"Timeout did not terminate");']
    case('file denied before open')
    actions.append('file_open_error=1;');send(request(False),src=50002,dst='69');expect(error(1),'0',50002)
    actions.append('file_open_error=0;quiet(20);')
    case('invalid mode and malformed requests recover')
    send(request(False,mode=b'netascii'),src=50002,dst='69');expect(error(4),'0',50002);actions.append('quiet(20);')
    send(request(False,name=b'X'*33),src=50002,dst='69');expect(error(4),'0',50002);actions.append('quiet(20);')
    case('reset cancels staged data and volatile image')
    wrq();send(data(1,p));expect(ack(1));actions.append('restart();quiet(20);if(active_length!=0)$fatal(1,"Cold reset metadata");')
    case('client RRQ learns peer TID and receives a complete file')
    actions.append('client_start(0);');expect(request(False),'0',69);actions.append('tid=last_src;')
    send(data(1,tail),src=51000);expect(ack(1),dst=51000);commits.append(tail.hex());actions.append('quiet(20);')
    case('client WRQ learns peer TID and ignores duplicate ACK')
    actions.append('client_start(1);');expect(request(True),'0',69);actions.append('tid=last_src;')
    send(ack(0),src=51001);expect(data(1,tail),dst=51001)
    send(ack(0),src=51001);actions.append('quiet(30);')
    send(ack(1),src=51002);expect(error(5),dst=51002)
    send(ack(1),src=51001);actions += ['quiet(20);','if(busy)$fatal(1,"Client WRQ not closed");']
    case('local cancel discards only the staged image')
    wrq();send(data(1,p));expect(ack(1))
    actions += ['cancel=1;idle(1);cancel=0;quiet(20);','if(busy||active_length!=17)$fatal(1,"Local cancel");']
    case('cancel under output backpressure finishes the already offered packet')
    actions.append('stall_output=1;');send(request(False),src=50002,dst='69')
    actions += ['while(!out_valid)idle(1);','cancel=1;idle(1);cancel=0;quiet(20);stall_output=0;']
    expect(data(1,tail),'0',50002);actions.append('quiet(20);if(busy)$fatal(1,"Cancel left stream busy");')
    (out/'rx.mem').write_text(''.join(f'{b:02x}\n' for b in incoming))
    (out/'expected.mem').write_text(''.join(f'{b:02x}\n' for b in expected))
    (out/'constants.vh').write_text(f'localparam RX_BYTES={len(incoming)}, EXPECTED_BYTES={len(expected)};\n')
    (out/'stimulus.vh').write_text('\n'.join(actions)+'\n')
    result=dict(cases=cases,packets=packets,commits=commits,expected_bytes=len(expected))
    (out/'cases.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def generate_endpoint(out):
    """Packet-only oracle for real RAM RTL/VO, using production timeout values."""
    import binascii
    out.mkdir(parents=True)
    incoming=bytearray();expected=bytearray();actions=['restart();'];packets=[];metadata=[];cases=[]
    generation=0
    def case(name):cases.append(name);actions.append('// '+name)
    def send(packet,src=50000,dst='tid'):
        actions.append(f'send_packet({len(incoming)},{len(packet)},{src},{dst});');incoming.extend(packet)
    def expect(packet,src='tid',dst=50000):
        actions.append(f'expect_packet({len(expected)},{len(packet)},{src},{dst});')
        packets.append(dict(data=packet.hex(),dst=dst));expected.extend(packet)
    def wrq():
        send(request(True),dst='69');expect(ack(0),'0');actions.append('tid=last_src;')
    def upload(blob):
        nonlocal generation
        wrq()
        for i in range(len(blob)//512+1):send(data(i+1,blob[i*512:(i+1)*512]));expect(ack(i+1))
        generation+=1;snapshot(blob)
    def download(blob):
        send(request(False),src=50002,dst='69');expect(data(1,blob[:512]),'0',50002);actions.append('tid=last_src;')
        for i in range(len(blob)//512+1):
            send(ack(i+1),src=50002)
            if i<len(blob)//512:expect(data(i+2,blob[(i+1)*512:(i+2)*512]),dst=50002)
        actions.append('quiet(20);')
    def snapshot(blob,valid=1):
        actions.append(f'snapshot({len(metadata)});')
        metadata.append(dict(generation=generation,valid=valid,length=len(blob),crc=binascii.crc_hqx(blob,0xffff)))
    p=bytes((i*37+(i>>2)+0x53)&255 for i in range(512));tail=bytes(range(17));image=p+tail
    case('missing file')
    send(request(False),src=50002,dst='69');expect(error(1),'0',50002);snapshot(b'',0)
    case('atomic 529-byte upload and readback from synchronous RAM')
    upload(image);download(image)
    case('partial transfer ERROR preserves old bank')
    wrq();send(data(1,bytes(reversed(p))));expect(ack(1));send(error(0));actions.append('quiet(30);');snapshot(image);download(image)
    case('duplicate request and DATA do not reopen or rewrite')
    wrq();send(request(True),dst='69');expect(ack(0));send(data(1,p));expect(ack(1))
    send(data(1,b'changed duplicate'));expect(ack(1));send(data(3,b'future'));actions.append('quiet(20);')
    send(data(2,tail));expect(ack(2));generation+=1;snapshot(image)
    send(data(2,tail));expect(ack(2));snapshot(image)
    case('maximum length and overflow preserve committed content')
    big=(p+bytes(reversed(p)))*4;upload(big)
    wrq()
    for i in range(8):send(data(i+1,big[i*512:(i+1)*512]));expect(ack(i+1))
    send(data(9,b'x'));expect(error(3));snapshot(big);download(big)
    case('zero byte file')
    upload(b'');download(b'')
    case('client RRQ and WRQ share the real backend')
    actions.append('client_start(0);');expect(request(False),'0',69);actions.append('tid=last_src;')
    send(data(1,tail),src=51000);expect(ack(1),dst=51000);generation+=1;snapshot(tail)
    actions.append('client_start(1);');expect(request(True),'0',69);actions.append('tid=last_src;')
    send(ack(0),src=51001);expect(data(1,tail),dst=51001);send(ack(1),src=51001);actions.append('quiet(20);')
    case('reset invalidates metadata and cancels partial staging')
    wrq();send(data(1,p));expect(ack(1));actions.append('restart();');generation=0;snapshot(b'',0)
    send(request(False),src=50002,dst='69');expect(error(1),'0',50002);actions.append('quiet(30);')
    for name,blob in [('rx.mem',incoming),('expected.mem',expected)]:(out/name).write_text(''.join(f'{b:02x}\n' for b in blob))
    (out/'constants.vh').write_text(f'localparam RX_BYTES={len(incoming)},EXPECTED_BYTES={len(expected)};\n')
    (out/'stimulus.vh').write_text('\n'.join(actions)+'\n')
    result=dict(cases=cases,packets=packets,metadata=metadata)
    (out/'cases.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
