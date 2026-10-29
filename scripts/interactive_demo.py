"""Manual ModelSim demonstrations. No DUT force/deposit and no production edits.

GUI waits at time boundaries; a Tcl timer resumes only after a user command.
The same mailbox and independent oracle are exercised by --self-test.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, collections, csv, hashlib, json, os, shutil, subprocess, sys, time, zlib
from run_competition import ROOT, MS, sources, sha
from modelsim_support import prepare_ini
from frozen_frame_reference import wire_for, checksum, payload
from generate_stage2_mgmt_golden import afdx_frame, sntp_packet, ES_MAC, ES_IP, MANAGER_MAC, MANAGER_IP
from generate_snmp_golden import message, oid, tlv

DELIVERY = Path(r'D:\FPGA\功能演示')
TITLES = ['业务收发与帧格式', '多VL与BAG调度', '双网故障与消重', '错误校验与异常序号',
          'SNMP管理读写', 'RTC与SNTP网络校时', '吞吐时延与极差', '调度优化前后对照']

def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def rows(path):
    return list(csv.DictReader(path.open(encoding='ascii')))

def frames(path):
    result=[]; data=bytearray(); first=last=None; error=0
    for row in rows(path):
        cycle=int(row['cycle'])
        if last is not None and cycle!=last+1:
            result.append((first,last,bytes(data),error)); data.clear(); first=None;error=0
        if first is None:first=cycle
        data.append(int(row['data'],16)); error |= int(row.get('error',0));last=cycle
    if data:result.append((first,last,bytes(data),error))
    return result

def app_packets(path):
    result=[]; data=bytearray(); start=None
    for r in rows(path):
        if int(r['sop']):
            assert not data,'application SOP inside packet'
            start=int(r['cycle'])
        assert start is not None,'application data without SOP'
        data.append(int(r['data']))
        if int(r['eop']):result.append((start,int(r['cycle']),bytes(data)));data.clear();start=None
    assert not data,'incomplete application packet'
    return result

def business_frame(vl, data, sn):
    return afdx_frame(bytes.fromhex('03000000')+vl.to_bytes(2,'big'), ES_MAC, ES_IP,
                      bytes((224,224,0,60)),24,23,data,sn)

def service_wire(vl,data,sn,incoming=False,sport=161,dport=49152):
    return wire_for(afdx_frame(bytes.fromhex('03000000')+vl.to_bytes(2,'big'),
        MANAGER_MAC if incoming else ES_MAC,MANAGER_IP if incoming else ES_IP,
        ES_IP if incoming else MANAGER_IP,sport,dport,data,sn))

def rx_oracle(run):
    """Independent pin-stream FCS/IP/UDP/SN/redundancy oracle for business.

    SN state updates even on an integrity reject, matching the documented RX
    policy. No DUT result/counter is used to decide expected application bytes.
    """
    events=[]; malformed=collections.Counter()
    for channel in ('a','b'):
        for start,end,w,error in frames(run/f'ingress_{channel}.csv'):
            if error or len(w)<72 or w[:8]!=bytes.fromhex('55555555555555d5') or zlib.crc32(w[8:-4])!=int.from_bytes(w[-4:],'little'):
                malformed['MAC']+=1;continue
            f=w[8:-4];vl=int.from_bytes(f[4:6],'big')
            if vl>=0x12b4:continue  # management is verified by exact response BER/wire
            length=int.from_bytes(f[38:40],'big')-8
            legal=(f[:4]==bytes.fromhex('03000000') and 0x1234<=vl<0x12b4 and
                   f[6:12]==ES_MAC and f[12:14]==b'\x08\x00' and f[14:16]==b'\x45\x00' and
                   checksum(f[14:34])==0 and f[23]==17 and f[26:30]==ES_IP and
                   f[30:34]==bytes((224,224,0,60)) and f[34:38]==bytes.fromhex('00180017') and
                   f[40:42]==b'\0\0' and int.from_bytes(f[16:18],'big')==28+length and
                   1<=length<=1471 and len(f)==43+max(17,length) and
                   not any(f[42+length:-1]))
            if not legal:malformed['parser']+=1;continue
            events.append((end,channel,vl,f[-1],vl.to_bytes(2,'big')+f[42:42+length]))
    events.sort()
    network={}; delivery={}; expected=[]; duplicate=integrity=control=0
    for end,ch,vl,sn,data in events:
        key=(vl,ch);prev=network.get(key);network[key]=sn
        if sn==0:
            control+=1;delivery.pop(vl,None);continue
        nxt=lambda v:v%255+1
        if prev is not None and sn not in (nxt(prev),nxt(nxt(prev))):integrity+=1;continue
        old=delivery.get(vl);distance=(sn-old[0])%255 if old else 1
        if old and end-old[1]<625000 and not 1<=distance<=127:
            duplicate+=1;continue
        delivery[vl]=(sn,end);expected.append(data)
    return expected,dict(duplicates=duplicate,integrity=integrity,control=control,malformed=dict(malformed))

def verify(run, plan):
    a=frames(run/'wire_a.csv');b=frames(run/'wire_b.csv')
    assert a==b,'A/B TX bytes or timing differ'
    expected=collections.defaultdict(list)
    for h in plan['wire']:
        w=bytes.fromhex(h);expected[int.from_bytes(w[12:14],'big')].append(w)
    actual=collections.defaultdict(list);last={};gaps=[]
    for start,end,w,_ in a:
        vl=int.from_bytes(w[12:14],'big');actual[vl].append(w)
        if vl in last:gaps.append(start-last[vl]);assert start-last[vl]>=125000,f'BAG violated VL={vl:04x}'
        last[vl]=start
    assert dict(actual)==dict(expected),'independent TX wire/FCS/SN/BER oracle mismatch'
    packets=app_packets(run/'application.csv');wanted,rx=rx_oracle(run)
    # Across VLs the redundant RX arbitrates independently; per-VL order is exact.
    def by_vl(items):
        out=collections.defaultdict(list)
        for data in items:out[int.from_bytes(data[:2],'big')].append(data)
        return dict(out)
    assert by_vl(p[2] for p in packets)==by_vl(wanted),'independent RX application loss/duplicate/data mismatch'
    # Every physical ingress frame must be accounted for by a user operation.
    for ch,bit in (('a',1),('b',2)):
        expected_in=[]
        for event in plan['ingress']:
            if event['mask']&bit:expected_in.append((bytes.fromhex(event['wire']),event['error'] if ch=='a' else 0))
        actual_in=[(w,e) for _,_,w,e in frames(run/f'ingress_{ch}.csv')]
        assert actual_in==expected_in,f'{ch.upper()} physical ingress differs from requested link/peer traffic'
    status=rows(run/'status.csv')[-1]
    assert int(status['delivered'])==len(packets)
    assert int(status['duplicates'])==rx['duplicates'],'duplicate counter differs from independent RX oracle'
    assert int(status['integrity'])==rx['integrity'],'integrity counter differs from independent RX oracle'
    rtc=[]
    for r in rows(run/'rtc.csv'):
        t1,t2,t3,t4=[int(r[k],16) for k in ('t1','t2','t3','t4')]
        offset=((t2-t1)+(t3-t4))//2;delay=(t4-t1)-(t3-t2)
        assert int(r['offset'])==offset and int(r['delay'])==delay,'RTC four-timestamp arithmetic mismatch'
        rtc.append(dict(offset_us=offset*1e6/2**32,delay_us=delay*1e6/2**32))
    if plan.get('sync'):assert rtc and int(status['sync'])==1,'SNTP response did not synchronize RTC'
    metrics={};offered=rows(run/'inputs.csv');remaining=list(packets);samples=[]
    assert len(offered)==len(plan['app']),'Actual application offers differ from user command count'
    assert int(status['accepted'])==int(status['sent'])==len(plan['app']) and int(status['rejected'])==0,'Application acceptance/send counters differ'
    for row,entry in zip(offered,plan['app']):
        target=bytes.fromhex(entry)
        matches=[(idx,p) for idx,p in enumerate(remaining) if p[2]==target]
        if matches:
            idx,p=matches[0];remaining.pop(idx)
            samples.append((int(row['vl']),len(target)-2,(p[1]-int(row['cycle']))*8,int(row['cycle']),p[1]))
    if samples:
        groups=collections.defaultdict(list)
        for vl,length,latency,_,_ in samples:groups[(vl,length)].append(latency)
        ranges=[max(v)-min(v) for v in groups.values() if len(v)>1]
        metrics=dict(delivered_payload_Mbps=sum(s[1] for s in samples)*1000/(max(s[4] for s in samples)-min(s[3] for s in samples)),
                     max_application_first_to_last_us=max(s[2] for s in samples)/1000,
                     max_same_VL_same_length_range_us=max(ranges)/1000 if ranges else None,
                     range_groups_with_at_least_2_samples=sum(len(v)>1 for v in groups.values()),
                     matched_application_messages=len(samples))
        intervals=[int(b['cycle'])-int(a['cycle']) for a,b in zip(offered,offered[1:])]
        metrics['actual_application_input_start_interval_min_cycles']=min(intervals) if intervals else None
        metrics['actual_application_input_start_interval_max_cycles']=max(intervals) if intervals else None
    transcript=(run/'transcript.log').read_text(errors='replace')
    assert '** Fatal' not in transcript and '** Error' not in transcript,'ModelSim error/fatal'
    assert all(sha(ROOT/p)==h for p,h in plan['inputs'].items()),'source fingerprint changed during session'
    return dict(result='PASS',scope='independent manual-scenario RTL verification; not official full acceptance',
                clock_ns=8,BAG_cycles=125000,wire_frames=len(a),application_messages=len(packets),
                minimum_per_VL_BAG_cycles=min(gaps) if gaps else None,status=status,rx_oracle=rx,rtc=rtc,metrics=metrics)

def readable_result(run,proof,compact=False,data_only=False):
    if proof['result']!='PASS':return '核对失败：'+proof.get('error','查看 transcript.log')
    s=proof['status'];text=[f"本次场景 PASS｜应用发送 {s['sent']} 帧，交付 {s['delivered']} 帧，消重 {s['duplicates']} 次，序号异常 {s['integrity']} 次",
        f"MAC 丢弃 A/B：{s['dropa']}/{s['dropb']}；协议拒绝 A/B：{s['parsea']}/{s['parseb']}；SNMP 请求/响应：{s['requests']}/{s['responses']}"]
    if not data_only and proof['minimum_per_VL_BAG_cycles'] is not None:
        text.append(f"同 VL 实测最小发送间隔：{proof['minimum_per_VL_BAG_cycles']*8/1e6:.6f} ms；独立 BAG 核对通过")
    packets=app_packets(run/'application.csv')
    for first,last,data in ([] if compact else packets[-1:] if data_only else packets[-2:]):
        try:
            decoded=data[2:82].decode('utf-8')
            if not decoded.isprintable():decoded='二进制载荷（见 HEX）'
        except UnicodeDecodeError:decoded='二进制载荷（见 HEX）'
        text.append(f"实际应用输出 VLID=0x{data[:2].hex().upper()}，载荷 {len(data)-2} 字节：{decoded}")
        text.append('实际输出 HEX：'+data[:34].hex(' ').upper()+(' …' if len(data)>34 else ''))
    wire=frames(run/'wire_a.csv')
    if wire and not compact:
        start,end,w,_=wire[-1];vl=int.from_bytes(w[12:14],'big');length=int.from_bytes(w[46:48],'big')-8
        text.append(f"最近真实 GMII 帧：VLID=0x{vl:04X}，UDP 载荷={length}，SN={w[-5]}，FCS={w[-4:].hex().upper()}（独立 CRC 核对通过）")
        if vl==0x12b4:
            # Show OCTET STRING values from actual response bytes only after exact Golden comparison.
            p=w[50:50+length];strings=[];i=0
            while i+2<=len(p):
                if p[i]==4 and p[i+1]<=32 and i+2+p[i+1]<=len(p):
                    d=p[i+2:i+2+p[i+1]]
                    if all(32<=v<127 for v in d):strings.append(d.decode('ascii'))
                i+=1
            text.append('实际 SNMP 响应字符串：'+' | '.join(strings))
    m=proof['metrics']
    if m:
        text.append(f"有效载荷吞吐：{m['delivered_payload_Mbps']:.4f} Mbps；应用首字节至末字节最大观测时延：{m['max_application_first_to_last_us']:.3f} μs")
        value=m['max_same_VL_same_length_range_us']
        if not data_only:text.append('同 VL 同长度时延极差：'+(f'{value:.3f} μs' if value is not None else '样本不足（每组至少 2 帧）'))
    if proof['rtc'] and not data_only:
        r=proof['rtc'][-1];text.append(f"RTC 已同步：实际 offset={r['offset_us']:.6f} μs，delay={r['delay_us']:.6f} μs；四时间戳算术核对通过")
    if not data_only:text.append('以上仅为本次声明输入条件的 RTL 场景结果；完整证据：'+str(run/'verification.json'))
    return '\n'.join(text)

def snmp_response(w):
    """Read the actual response BER, never the controller's expected MIB value."""
    length=int.from_bytes(w[46:48],'big')-8
    def children(blob):
        result=[];i=0
        while i<len(blob):
            assert i+2<=len(blob),'truncated BER header'
            tag=blob[i];n=blob[i+1];i+=2
            if n&128:
                width=n&127;assert 1<=width<=2 and i+width<=len(blob),'invalid BER length'
                n=int.from_bytes(blob[i:i+width],'big');i+=width
            assert i+n<=len(blob),'truncated BER value'
            result.append((tag,blob[i:i+n]));i+=n
        return result
    root=children(w[50:50+length]);assert len(root)==1 and root[0][0]==0x30
    msg=children(root[0][1]);assert len(msg)==3 and msg[2][0]==0xa2
    pdu=children(msg[2][1]);assert len(pdu)==4 and pdu[3][0]==0x30
    bindings=children(pdu[3][1]);assert len(bindings)==1 and bindings[0][0]==0x30
    binding=children(bindings[0][1]);assert len(binding)==2 and binding[1][0]==4
    return dict(request_id=int.from_bytes(pdu[0][1],'big'),error_status=int.from_bytes(pdu[1][1],'big'),
                value=binding[1][1].decode('ascii'),object=binding[0][1][-2])


def operation_result(session,proof,previous=None):
    """Only describe this completed operation; cumulative evidence stays in verification.json."""
    run=session.run;plan=session.plan;old=previous or {};status=proof['status'];before=old.get('status',{})
    delta=lambda key:int(status[key])-int(before.get(key,0))
    action=plan['actions'][-1];detail=action.get('detail') or {};label=action['label']
    old_count=old.get('application_messages',0);packets=app_packets(run/'application.csv')[old_count:]
    all_wire=frames(run/'wire_a.csv');wire=all_wire[old.get('wire_frames',0):]
    text=[f"本次操作：{label}｜功能核对：通过",f"本次计数变化：发送 +{delta('sent')} 帧；交付 +{delta('delivered')} 帧；消重 +{delta('duplicates')} 次；序号异常 +{delta('integrity')} 次",
          f"本次 MAC 丢弃 A/B：+{delta('dropa')}/+{delta('dropb')}；业务解析器拒绝 A/B：+{delta('parsea')}/+{delta('parseb')}"]
    if label=='选择链路故障或恢复':
        text.append(f"已生效链路：{ {0:'双网断开',1:'仅 A',2:'仅 B',3:'双网正常'}[session.mask]}；A 接收错误注入：{'开启' if session.error else '关闭'}")
        text.append('本次只切换链路，未发送业务数据。')
    elif label in ('手动发送','用户确认批量负载'):
        text.append(f"本次输入：起始 VLID=0x{detail['vlid']:04X}；{detail['count']} 帧；{detail['VLs']} 个 VL；每帧 {detail['length']} 字节")
        if detail['generated_pattern']:text.append('载荷来源：测试环境生成的批量字节。')
        else:text.append('本次输入内容：'+bytes.fromhex(plan['app'][-1])[2:].decode('utf-8',errors='replace'))
        text.append(f"已生效链路：{ {0:'双网断开',1:'仅 A',2:'仅 B',3:'双网正常'}[session.mask]}；本次未交付：{detail['count']-len(packets)} 帧")
    elif label=='手动对端报文注入':
        text.append(f"本次注入：{detail['mutation']}；VLID=0x{detail['vlid']:04X}；SN={detail['SN']}；内容："+bytes.fromhex(detail['payload']).decode('utf-8',errors='replace'))
    if packets:
        for _,_,data in packets[-2:]:
            content=data[2:82].decode('utf-8',errors='replace')
            if not content.isprintable() or '\ufffd' in content:content='二进制载荷（见 HEX）'
            text.append(f"本次实际接收：VLID=0x{data[:2].hex().upper()}；{len(data)-2} 字节；内容：{content}")
            text.append('本次接收 HEX：'+data[:34].hex(' ').upper()+(' …' if len(data)>34 else ''))
        counts=collections.Counter(int.from_bytes(p[2][:2],'big') for p in packets)
        text.append('本次各 VL 交付：'+'；'.join(f'{vl:04X}={n} 帧' for vl,n in sorted(counts.items())))
    elif label in ('手动发送','用户确认批量负载','手动对端报文注入'):
        text.append('本次实际接收：无新数据（不显示上次接收内容）。')
        if delta('integrity'):text.append('接收侧检测到序号异常；本次功能通过表示拒收行为符合独立参考。')
    if label.startswith('SNMP'):
        replies=[f for f in wire if int.from_bytes(f[2][12:14],'big')==0x12b4]
        response=snmp_response(replies[-1][2])
        obj={4:'sysContact',5:'sysName',6:'sysLocation'}.get(response['object'],str(response['object']))
        text.append(f"本次 SNMP 请求/响应：+{delta('requests')}/+{delta('responses')}；对象：{obj}")
        if detail['value'] is not None:text.append('本次 SET 输入：'+detail['value'])
        text.append(f"实际 SNMP 响应值：{response['value']}｜响应内容核对：通过")
        text.append(f"实际响应请求编号：{response['request_id']}；错误状态：{response['error_status']}")
        ingress=frames(run/'ingress_a.csv')
        elapsed=(replies[-1][1]-ingress[-1][0])*8/1000
        text.append(f"本次 SNMP 请求首字节至响应末字节：{elapsed:.3f} μs")
    if label=='发送模拟时间服务器响应':
        r=proof['rtc'][-1]
        text.append(f"RTC 同步状态：{before.get('sync','0')} → {status['sync']}｜四时间戳计算核对：通过")
        text.append(f"实际 RTC offset：{r['offset_us']:.6f} μs；delay：{r['delay_us']:.6f} μs")
        text.append('绝对 UTC 精度：未测量（本次使用模拟时间服务器）。')
    if label in ('手动发送','用户确认批量负载'):
        offered=rows(run/'inputs.csv')[int(before.get('accepted',0)):]
        remaining=list(packets);samples=[]
        # Match only this action's inputs to this action's outputs, including repeated text.
        wanted=plan['app'][-detail['count']:]
        for row,h in zip(offered,wanted):
            match=next((i for i,p in enumerate(remaining) if p[2]==bytes.fromhex(h)),None)
            if match is not None:
                p=remaining.pop(match);samples.append((int(row['vl']),len(p[2])-2,(p[1]-int(row['cycle']))*8,int(row['cycle']),p[1]))
        if samples:
            maximum=max(s[2] for s in samples)/1000
            text.append(f"本次应用首字节至末字节最大观测时延：{maximum:.3f} μs｜达标状态：{'达标（本次样本）' if maximum<2000 else '未达标（本次样本）'}")
            if len(samples)!=len(offered):text.append('时延仅统计已交付样本，未交付帧不参与时延达标判断。')
            groups=collections.defaultdict(list)
            for vl,length,ns,_,_ in samples:groups[(vl,length)].append(ns)
            ranges=[max(g)-min(g) for g in groups.values() if len(g)>1]
            text.append(f"本次同 VL 同长度时延极差：{max(ranges)/1000:.3f} μs" if ranges else '本次同 VL 同长度时延极差：样本不足')
            duration=max(s[4] for s in samples)-min(s[3] for s in samples)
            rate=sum(s[1] for s in samples)*1000/duration
            eligible=plan['scenario']==7 and len(samples)>=2 and len(samples)==len(offered) and session.mask==3 and not session.error
            verdict=('｜达标状态：达标（本次负载）' if rate>=100 else '｜达标状态：未达标（本次负载）') if eligible else ''
            text.append(f"本次有效载荷交付吞吐：{rate:.4f} Mbps{verdict}")
        else:text.append('本次时延／吞吐／极差：无交付样本')
        gaps=[];last={}
        for i,(start,_,w,_) in enumerate(all_wire):
            vl=int.from_bytes(w[12:14],'big')
            if vl<0x12b4 and vl in last and i>=old.get('wire_frames',0):gaps.append(start-last[vl])
            last[vl]=start
        text.append(f"本次同 VL 最小发送间隔：{min(gaps)*8/1e6:.6f} ms｜达标状态：{'达标' if min(gaps)>=125000 else '未达标'}" if gaps else '本次同 VL 最小发送间隔：样本不足')
    if wire:
        _,_,w,_=wire[-1]
        text.append(f"本次最近发送帧：VLID=0x{int.from_bytes(w[12:14],'big'):04X}；SN={w[-5]}；FCS={w[-4:].hex().upper()}｜帧字节核对：通过")
    text.append(f"本会话累计：发送 {status['sent']} 帧；交付 {status['delivered']} 帧；SNMP 请求/响应 {status['requests']}/{status['responses']}")
    return '\n'.join(text)


def focus_wave(run,previous=None):
    packets=app_packets(run/'application.csv')
    if packets and (previous is None or len(packets)>previous.get('application_messages',0)):
        first,last,_=packets[-1];left=max(0,first*8-18000);right=last*8+5000
    else:
        candidates=frames(run/'wire_a.csv')+frames(run/'ingress_a.csv')+frames(run/'ingress_b.csv')
        if not candidates:return
        first,last,_,_=max(candidates,key=lambda f:f[1])
        left=max(0,first*8-1000);right=last*8+2000
    (run/'zoom.txt').write_text(f'{left} {right}')

class Session:
    def __init__(self, scenario=1, batch=False, arbiter=None, reference=None, extra_helpers=()):
        if not (MS/'vsim.exe').is_file():raise RuntimeError(f'ModelSim missing: {MS}')
        self.run=ROOT/'build'/'interactive_demo'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.run.mkdir(parents=True);self.batch=batch;self.index=0;self.sn={};self.msn=0;self.rid=0
        self.mask=3;self.error=0;self.values={4:b'afdx-es-team3',5:b'afdx-s2',6:b'AFDX lab bench'}
        rtl=sources()
        if reference:
            manifest=json.loads((reference/'summary.json').read_text())
            assert manifest['result']=='PASS','Historical production snapshot is not PASS'
            rtl=[]
            for p,h in manifest['inputs'].items():
                if Path(p).suffix=='.v':
                    snapshot=reference/Path(p).name
                    assert sha(snapshot)==h,f'Historical production snapshot hash mismatch: {snapshot}'
                    rtl.append(snapshot)
        files=rtl+[ROOT/'sim/tb_interactive_demo.sv']
        if arbiter:files=[arbiter if p.name=='afdx_service_tx_arbiter_615a.v' else p for p in files]
        helpers=[Path(__file__),ROOT/'scripts/interactive_demo.tcl',ROOT/'scripts/run_competition.py',ROOT/'scripts/modelsim_support.py',
                 ROOT/'scripts/frozen_frame_reference.py',ROOT/'scripts/generate_stage2_mgmt_golden.py',ROOT/'scripts/generate_snmp_golden.py']
        helpers += list(extra_helpers)
        self.plan=dict(scenario=scenario,created_utc=datetime.now(timezone.utc).isoformat(),wire=[],ingress=[],app=[],actions=[],
                       inputs={str(p.relative_to(ROOT)):sha(p) for p in files+helpers},clock_ns=8,BAG_cycles=125000)
        self.plan['production_reference']=str(reference) if reference else 'current rtl + vendor/frozen'
        for p in files+helpers:shutil.copy2(p,self.run/p.name)
        prepare_ini(self.run,MS)
        commands=['onerror {quit -code 2 -force}','vlib work']
        commands += [f'vlog {"-sv " if p.suffix==".sv" else ""}{p.name}' for p in files]
        commands += ['vopt +acc work.tb_interactive_demo -o demo_opt','vsim -suppress 3534 -t 1ps work.demo_opt']
        if not batch:
            commands += ['view wave', 'add wave -divider {125MHz_clock}',
                         'add wave /tb_interactive_demo/clk /tb_interactive_demo/reset /tb_interactive_demo/init',
                         'add wave -divider {Application}',
                         'add wave -hex /tb_interactive_demo/tx_data /tb_interactive_demo/rx_data',
                         'add wave /tb_interactive_demo/tx_valid /tb_interactive_demo/tx_ready /tb_interactive_demo/rv /tb_interactive_demo/rs /tb_interactive_demo/re',
                         'add wave -divider {Real_GMII}',
                         'add wave -hex /tb_interactive_demo/a /tb_interactive_demo/b /tb_interactive_demo/net_data',
                         'add wave /tb_interactive_demo/ae /tb_interactive_demo/be /tb_interactive_demo/net_valid /tb_interactive_demo/mask /tb_interactive_demo/error_a',
                         'add wave -divider {Observed_status}',
                         'add wave -unsigned /tb_interactive_demo/dut/app_accepted /tb_interactive_demo/dut/app_sent /tb_interactive_demo/dut/rx_delivered /tb_interactive_demo/dut/rx_duplicates /tb_interactive_demo/dut/rx_integrity_errors',
                         'add wave -unsigned /tb_interactive_demo/dut/mac_a_dropped /tb_interactive_demo/dut/parser_a_rejected /tb_interactive_demo/dut/snmp_requests /tb_interactive_demo/dut/snmp_responses',
                         'add wave /tb_interactive_demo/ts',
                         'add wave -hex /tb_interactive_demo/dut/core/services/plane/rtc_utc_time /tb_interactive_demo/dut/core/services/plane/sntp_t1 /tb_interactive_demo/dut/core/services/plane/sntp_t2 /tb_interactive_demo/dut/core/services/plane/sntp_t3 /tb_interactive_demo/dut/core/services/plane/sntp_t4',
                         'configure wave -namecolwidth 280', 'configure wave -valuecolwidth 110']
        commands += ['run 100000 ns']
        if not batch:commands += ['wave zoom full','source interactive_demo.tcl','set f [open ready.txt w]; puts $f READY; close $f']
        self.base_commands=commands
        (self.run/'start.do').write_text('\n'.join(commands)+'\n',encoding='utf-8')
        self.t1=0xe900000000000000+8192*(1<<32)//125000000
        self.plan['wire'].append(service_wire(0x12b5,sntp_packet(3,transmit=self.t1),1,sport=49152,dport=123).hex())
        self.persist()
        if not batch:
            env=self.environment()
            self.process=subprocess.Popen([str(MS/'vsim.exe'),'-gui','-modelsimini','modelsim.ini','-l','transcript.log','-do','do start.do'],cwd=self.run,env=env)
    def environment(self):
        env=os.environ.copy();env.setdefault('MGLS_LICENSE_FILE',str(MS.parent/'LICENSE.TXT'));return env
    def persist(self):dump(self.run/'plan.json',self.plan)
    def command(self, ops, cycles, label, detail=None):
        self.index+=1;lines=[]
        for op,n,x,data in ops:
            lines.append(f'{op} {n} {x}')
            if data is not None:lines.extend(str(v) for v in data)
        (self.run/f'cmd_{self.index}.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
        self.plan['actions'].append(dict(id=self.index,label=label,detail=detail,cycles=cycles));self.persist()
        return cycles*8
    def app(self, vl, data, count=1, vl_count=1, interval=0):
        assert 0x1234<=vl and vl+vl_count<=0x12b4,'VLID 范围为 1234～12B3；VL 基值加 VL 数不能越界。'
        assert 1<=len(data)<=1471,'数据不能为空，UTF-8 编码后的载荷长度须为 1～1471 字节。'
        assert 1<=count<=512 and 1<=vl_count<=128,'批量帧数须为 1～512，VL 数须为 1～128。'
        assert interval>=len(data)+3,'输入间隔至少为载荷字节数加 3 个周期。'
        ops=[]
        for i in range(count):
            v=vl+i%vl_count;sn=self.sn.get(v,0)%255+1;self.sn[v]=sn
            d=data if count==1 else payload(i,len(data))
            raw=v.to_bytes(2,'big')+d;w=wire_for(business_frame(v,d,sn))
            self.plan['wire'].append(w.hex());self.plan['app'].append(raw.hex())
            self.plan['ingress'].append(dict(wire=w.hex(),mask=self.mask,error=self.error))
            ops += [(1,len(raw),0,raw),(4,interval-len(raw)-1,0,None)]
        cycles=count*(interval+128)+((count//vl_count)+2)*125000+20000
        return self.command(ops,cycles,'手动发送' if count==1 else '用户确认批量负载',dict(vlid=vl,length=len(data),count=count,VLs=vl_count,interval_cycles=interval,generated_pattern=count>1))
    def fault(self,mask,error=0):
        assert mask in (0,1,2,3) and error in (0,1)
        self.mask=mask;self.error=error
        return self.command([(2,mask,error,None)],2048,'选择链路故障或恢复',dict(mask=mask,A_RX_ER=error))
    def inject(self,vl,data,sn,mutation):
        assert 0x1234<=vl<0x12b4 and 0<=sn<=255 and 1<=len(data)<=1471,'VLID 须为 1234～12B3，SN 须为 0～255，数据须为 1～1471 字节且不为空。'
        f=bytearray(business_frame(vl,data,sn))
        if mutation=='IP校验错误':f[24]^=1
        if mutation=='UDP长度错误':f[39]^=1
        w=wire_for(bytes(f),mutation=='FCS错误')
        self.plan['ingress'].append(dict(wire=w.hex(),mask=self.mask,error=self.error))
        return self.command([(3,len(w),0,w)],20000,'手动对端报文注入',dict(vlid=vl,SN=sn,mutation=mutation,payload=data.hex()))
    def snmp(self,obj,value=None):
        assert obj in (4,5,6)
        if value is not None:assert 1<=len(value)<=32,'SET 值不能为空，长度须为 1～32 个 ASCII 字节。'
        self.msn=self.msn%255+1;self.rid+=1
        community=b'private' if value is not None else b'public'
        if value is not None:self.values[obj]=value
        req=message(0xa3 if value is not None else 0xa0,self.rid,community,[(oid(obj),tlv(4,value) if value is not None else tlv(5,b''))])
        answer=message(0xa2,self.rid,community,[(oid(obj),tlv(4,self.values[obj]))])
        w=service_wire(0x12b4,req,self.msn,True,49152,161)
        self.plan['ingress'].append(dict(wire=w.hex(),mask=self.mask,error=self.error))
        self.plan['wire'].append(service_wire(0x12b4,answer,self.msn).hex())
        return self.command([(3,len(w),0,w)],160000,'SNMP SET' if value is not None else 'SNMP GET',dict(object=obj,value=value.decode('ascii') if value else None,expected=self.values[obj].decode('ascii')))
    def sync(self,offset_us):
        assert not self.plan.get('sync'),'本会话已响应过一次自动 SNTP 请求。请重新启动入口以更换参数。'
        t2=self.t1+round(offset_us*2**32/1e6);t3=t2+2748
        w=service_wire(0x12b5,sntp_packet(4,2,self.t1,t2,t3),1,True,123,49152)
        self.plan['ingress'].append(dict(wire=w.hex(),mask=self.mask,error=self.error));self.plan['sync']=True
        return self.command([(3,len(w),0,w)],20000,'发送模拟时间服务器响应',dict(server_t2_minus_t1_us=offset_us,t1=f'{self.t1:016x}',t2=f'{t2:016x}',t3=f'{t3:016x}'))
    def pressure(self,count):
        assert self.index==0,'Comparison must start from a fresh session'
        assert count==24,'Controlled comparison uses 24 frames / 16 VL / 1471 bytes / 8100 cycles'
        durations=[self.sync(244.140625),self.snmp(5,b'isolation-verified'),self.snmp(5),self.app(0x1234,b'X'*1471,count,16,8100)]
        parts=[(self.run/f'cmd_{i}.txt').read_text() for i in range(1,5)]
        merged=parts[0]+'4 1000 0\n'+parts[1]+'4 256 0\n'+parts[2]+parts[3]
        (self.run/'cmd_1.txt').write_text(merged)
        for i in range(2,5):(self.run/f'cmd_{i}.txt').unlink()
        self.index=1;self.plan['comparison_workload']='24 frames, 16VL, 1471 bytes, 8100 cycles; two-request control-plane burst (not legal 1ms peer BAG)'
        self.persist();return sum(durations)
    def result(self):
        try:
            proof=verify(self.run,self.plan)
        except Exception as exc:proof=dict(result='FAIL',error=str(exc))
        proof['run']=str(self.run);proof['updated_utc']=datetime.now(timezone.utc).isoformat()
        dump(self.run/'verification.json',proof);return proof

def run_batch(session,durations):
    # Exercise the identical polling mailbox; commands are pre-written in self-test only.
    commands=[c for c in session.base_commands if not c.startswith('run ')]
    commands += [f'run {sum(durations)+200000} ns','quit -code 0 -force']
    (session.run/'test.do').write_text('\n'.join(commands)+'\n')
    with (session.run/'console.log').open('wb') as log:
        p=subprocess.run([str(MS/'vsim.exe'),'-batch','-modelsimini','modelsim.ini','-l','transcript.log','-do','do test.do'],cwd=session.run,env=session.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=1200)
    assert p.returncode==0,(session.run/'console.log').read_text(errors='replace')[-2500:]
    proof=session.result();assert proof['result']=='PASS',proof
    return proof

def self_test():
    results=[]
    # One scenario per independent simulator run avoids pre-written commands
    # crossing intended user wait boundaries in the batch transport check.
    s=Session(batch=True);results.append(run_batch(s,[s.app(0x1234,b'Hello AFDX!',interval=64)]))
    s=Session(2,batch=True);results.append(run_batch(s,[s.app(0x1234,b'X'*64,32,4,33000)]))
    for mask,error in ((1,0),(2,0),(3,1),(0,0)):
        s=Session(3,batch=True);results.append(run_batch(s,[s.fault(mask,error),s.app(0x1234,b'fault-link',interval=64)]))
    for mutation in ('FCS错误','IP校验错误','UDP长度错误','正常报文'):
        s=Session(4,batch=True);results.append(run_batch(s,[s.inject(0x12a0,b'peer-data',1,mutation)]))
    # GET/SET/GET need genuine sequential settle boundaries.
    s=Session(5,batch=True);d=[]
    for value in (None,b'user-changed',None):
        duration=s.snmp(4,value)
        # Bake real wait into each mailbox for batch self-test only.
        with (s.run/f'cmd_{s.index}.txt').open('a') as f:f.write('4 160000 0\n')
        d.append(duration)
    results.append(run_batch(s,d))
    s=Session(6,batch=True);results.append(run_batch(s,[s.sync(250)]))
    s=Session(7,batch=True);results.append(run_batch(s,[s.app(0x1234,b'X'*1471,64,16,8100)]))
    out=ROOT/'reports'/'交互演示自检.json';dump(out,dict(result='PASS',kind='automated transport and independent oracle self-test; user GUI acceptance is separate',runs=results))
    print(json.dumps(dict(result='PASS',report=str(out)),ensure_ascii=False))

class Controller:
    def __init__(self,scenario,parent=None,suite=None):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.tk=tk;self.ttk=ttk;self.mb=messagebox;self.suite=suite;self.scenario=scenario
        self.window=ttk.Frame(parent) if parent is not None else tk.Tk()
        if parent is None:
            self.window.title(f'{scenario:02d} {TITLES[scenario-1]} · 真实 RTL 手动演示')
            self.window.geometry(f"{min(1120,self.window.winfo_screenwidth()-80)}x{min(900,self.window.winfo_screenheight()-100)}");self.window.option_add('*Font',('Microsoft YaHei',10))
        self.busy=True;self.failed=False;self.entries={};self.s=None;self.last_proof=None
        if parent is None:
            ttk.Label(self.window,text=TITLES[scenario-1],font=('Microsoft YaHei',20,'bold')).pack(anchor='w',padx=18,pady=12)
            ttk.Label(self.window,text='真实 RTL 仿真 · 125 MHz').pack(anchor='w',padx=18)
        self.state=tk.StringVar(value='尚未启动本项仿真' if suite else '检查环境并启动 ModelSim；首次编译请稍候……')
        ttk.Label(self.window,textvariable=self.state,wraplength=900).pack(anchor='w',padx=18,pady=8)
        self.body=ttk.Frame(self.window);self.body.pack(fill='x',padx=18)
        if scenario in (1,2,3,7):
            self.field('VLID（十六进制）','vl','1234');self.field('单帧数据（UTF-8）','data','I LOVE FPGA')
            ttk.Button(self.body,text='发送本人输入的数据',command=self.send).pack(anchor='w',pady=4)
        if scenario in (2,7):
            self.field('批量帧数（1～512）','count','32' if scenario==2 else '64');self.field('批量 VL 数','vls','4' if scenario==2 else '16')
            self.field('每帧有效载荷字节数','length','64' if scenario==2 else '1471');self.field('应用输入间隔（125 MHz 周期）','interval','33000' if scenario==2 else '8100')
            ttk.Button(self.body,text='确认参数并生成批量负载',command=self.load).pack(anchor='w',pady=4)
        if scenario==3:
            self.choice('链路选择','fault',['双网正常','断开 B，仅 A','断开 A，仅 B','A 接收错误，B 正常','双网断开'])
            ttk.Button(self.body,text='应用所选故障／恢复',command=self.fault).pack(anchor='w',pady=6)
        if scenario==4:
            self.field('对端 VLID（十六进制；建议单独使用 12A0）','vl','12A0')
            self.field('对端数据（UTF-8）','data','I LOVE FPGA');self.field('SN（十进制，0～255）','sn','1')
            self.choice('对端报文类型','mutation',['正常报文','FCS错误','IP校验错误','UDP长度错误'])
            ttk.Button(self.body,text='注入本人选择的对端报文',command=self.inject).pack(anchor='w',pady=4)
        if scenario==5:
            self.choice('MIB 对象','object',['4 · sysContact','5 · sysName','6 · sysLocation'])
            self.field('SET 值（1～32 个 ASCII 字节）','value','I LOVE FPGA')
            ttk.Button(self.body,text='GET：从真实响应读取',command=lambda:self.snmp(False)).pack(anchor='w',pady=4)
            ttk.Button(self.body,text='SET：写入本人填写的值',command=lambda:self.snmp(True)).pack(anchor='w',pady=4)
        if scenario==6:
            self.field('服务器 t2 相对请求 t1 的偏移（微秒）','offset','250')
            ttk.Button(self.body,text='发送本人确认的时间响应',command=self.sync).pack(anchor='w',pady=6)
        result_frame=ttk.Frame(self.window);result_frame.pack(fill='both',expand=True,padx=18,pady=12)
        scrollbar=ttk.Scrollbar(result_frame);scrollbar.pack(side='right',fill='y')
        self.output=tk.Text(result_frame,height=16,wrap='word',yscrollcommand=scrollbar.set)
        self.output.pack(side='left',fill='both',expand=True);scrollbar.config(command=self.output.yview)
        self.output.tag_configure('result',foreground='#135b34')
        self.output.tag_configure('attention',foreground='#9b3b12')
        self.log('本次测试：尚未运行。')
        if parent is None:
            self.window.after(100,lambda:self.start(scenario));self.window.protocol('WM_DELETE_WINDOW',self.close)
            self.window.mainloop()
        else:self.window.pack(fill='both',expand=True)
    def field(self,label,key,value):
        row=self.ttk.Frame(self.body);row.pack(fill='x',pady=2)
        self.ttk.Label(row,text=label,width=46).pack(side='left')
        v=self.tk.StringVar(value=value);self.entries[key]=v;self.ttk.Entry(row,textvariable=v,width=36).pack(side='left')
    def choice(self,label,key,values):
        row=self.ttk.Frame(self.body);row.pack(fill='x',pady=2);self.ttk.Label(row,text=label,width=46).pack(side='left')
        v=self.tk.StringVar(value=values[0]);self.entries[key]=v;self.ttk.Combobox(row,textvariable=v,values=values,state='readonly',width=34).pack(side='left')
    def get(self,key):return self.entries[key].get()
    def log(self,text):
        self.output.config(state='normal');self.output.delete('1.0','end')
        for line in text.splitlines():
            tag='attention' if any(word in line for word in ('未达标','无新数据','序号异常；')) else 'result' if any(word in line for word in ('实际接收：','实际 SNMP 响应值：','RTC 同步状态：','功能核对：')) else ''
            self.output.insert('end',line+'\n',tag)
        self.output.config(state='disabled');self.output.yview_moveto(0)
    def start(self,scenario):
        try:
            self.s=Session(scenario,extra_helpers=(ROOT/'scripts/basic_demo.py',) if self.suite else ())
            self.deadline=time.time()+240;self.await_ready()
        except Exception as exc:
            self.busy=False;self.failed=True;self.state.set('启动失败');self.mb.showerror('启动失败',str(exc))
            if self.suite:self.suite.failed(self,str(exc))
    def await_ready(self):
        if (self.s.run/'ready.txt').exists():
            self.busy=False;self.state.set('等待本人操作：仿真已加载并停在 100 μs')
            if self.suite:self.suite.ready(self)
            return
        if self.s.process.poll() is not None or time.time()>self.deadline:
            self.busy=False;self.failed=True;self.state.set('启动未完成，请查看 transcript.log');self.mb.showerror('启动未完成','ModelSim 未返回 READY。')
            if self.suite:self.suite.failed(self,'ModelSim 未返回 READY')
            return
        self.window.after(300,self.await_ready)
    def action(self,callback):
        if self.suite:return self.suite.dispatch(self,callback)
        return self.execute(callback)
    def execute(self,callback):
        if self.busy:self.mb.showinfo('请稍候','仿真启动或运行中，请等待结果。');return
        if self.failed:self.mb.showerror('本次核对失败','保留本次日志并重新启动入口；不要继续累积结果。');return
        try:
            duration=callback();self.busy=True;self.state.set('真实仿真运行中……');self.deadline=time.time()+240
            self.log(f"本次操作：{self.s.plan['actions'][-1]['label']}｜仿真运行中，结果待生成。")
            (self.s.run/'response.txt').unlink(missing_ok=True)
            temp=self.s.run/'request.tmp';temp.write_text(str(duration));temp.replace(self.s.run/'request.txt')
            self.window.after(300,self.await_result)
        except Exception as exc:self.mb.showerror('输入未执行',str(exc))
    def await_result(self):
        path=self.s.run/'response.txt'
        if path.exists():
            response=path.read_text();path.unlink();self.busy=False
            proof=self.s.result() if response.strip()=='DONE' else dict(result='FAIL',error=response)
            self.failed=proof['result']!='PASS'
            self.state.set('本次独立核对通过；等待下一次本人操作' if not self.failed else '本次核对失败，请保留日志')
            if self.failed:
                self.log('本次功能核对：失败\n'+proof.get('error','查看 transcript.log'));self.mb.showerror('本次核对失败',proof.get('error','查看 transcript.log'))
                if self.suite:self.suite.failed(self,proof.get('error','核对失败'))
            else:
                try:
                    result=operation_result(self.s,proof,self.last_proof)
                    self.log(result)
                    (self.s.run/f'result_{self.s.index}.txt').write_text(result+'\n',encoding='utf-8')
                    if self.s.plan['actions'][-1]['label']!='选择链路故障或恢复':focus_wave(self.s.run,self.last_proof or {})
                    if self.suite:self.suite.record(self,proof,self.last_proof,result)
                    self.last_proof=proof
                except Exception as exc:
                    self.failed=True;self.state.set('结果显示失败，请保留日志');self.log('结果显示失败：'+str(exc))
                    if self.suite:self.suite.failed(self,str(exc))
            return
        if self.s.process.poll() is not None or time.time()>self.deadline:
            self.busy=False;self.failed=True;self.state.set('仿真退出或超时；本次未通过');self.log('本次功能核对：未通过（仿真退出或超时）');self.mb.showerror('仿真退出或超时','查看 transcript.log 与 plan.json。')
            if self.suite:self.suite.failed(self,'仿真退出或超时')
            return
        self.window.after(300,self.await_result)
    def send(self):
        self.action(lambda:self.s.app(int(self.get('vl'),16),self.get('data').encode('utf-8'),interval=max(64,len(self.get('data').encode('utf-8'))+3)))
    def load(self):
        if self.busy:return
        try:
            count=int(self.get('count'));vls=int(self.get('vls'));length=int(self.get('length'));interval=int(self.get('interval'));vl=int(self.get('vl'),16)
            if not self.mb.askyesno('确认真实负载参数',f'{count} 帧，{vls} 个 VL，每帧 {length} 字节，输入间隔 {interval} 周期。\n数据由测试环境按公开确定性公式生成。确认执行？'):return
            self.action(lambda:self.s.app(vl,b'X'*length,count,vls,interval))
        except Exception as exc:self.mb.showerror('参数错误',str(exc))
    def fault(self):
        values={'双网正常':(3,0),'断开 B，仅 A':(1,0),'断开 A，仅 B':(2,0),'A 接收错误，B 正常':(3,1),'双网断开':(0,0)}
        self.action(lambda:self.s.fault(*values[self.get('fault')]))
    def inject(self):self.action(lambda:self.s.inject(int(self.get('vl'),16),self.get('data').encode('utf-8'),int(self.get('sn')),self.get('mutation')))
    def snmp(self,write):
        def work():
            obj=int(self.get('object')[0])
            try:value=self.get('value').encode('ascii') if write else None
            except UnicodeEncodeError:raise ValueError('SET 值只支持英文字母、数字、空格和英文标点；请移除中文，例如使用 I LOVE FPGA。')
            return self.s.snmp(obj,value)
        self.action(work)
    def sync(self):self.action(lambda:self.s.sync(float(self.get('offset'))))
    def close(self):
        # Closing the controller does not destroy the ModelSim wave evidence.
        self.window.destroy()

def compare_provenance(left,right):
    li=left.plan['inputs'];ri=right.plan['inputs'];name='afdx_service_tx_arbiter_615a.v'
    l={p:h for p,h in li.items() if Path(p).name!=name};r={p:h for p,h in ri.items() if Path(p).name!=name}
    assert l==r,'Comparison changed inputs other than arbiter'
    for key in ('wire','ingress','app','clock_ns','BAG_cycles','comparison_workload','production_reference'):
        assert left.plan[key]==right.plan[key],f'Comparison differs: {key}'
    return dict(only_changed_source=name,other_inputs_equal=True,Golden_equal=True,clock_ns=8,BAG_cycles=125000,production_reference=left.plan['production_reference'],
                left_arbiter={p:h for p,h in li.items() if Path(p).name==name},right_arbiter={p:h for p,h in ri.items() if Path(p).name==name})

def compare_actual_inputs(left,right,provenance):
    assert sha(left.run/'inputs.csv')==sha(right.run/'inputs.csv'),'Actual application input cycles differ; comparison invalid'
    # Peer commands precede any returned business traffic; compare their actual
    # GMII bytes/cycles independently from the expected plan as well.
    for channel in ('a','b'):
        peer=lambda s:[(start,end,w.hex(),error) for start,end,w,error in frames(s.run/f'ingress_{channel}.csv') if int.from_bytes(w[12:14],'big')>=0x12b4]
        assert peer(left)==peer(right),'Actual peer input cycles/bytes differ; comparison invalid'
    return dict(provenance,identical_actual_application_input_csv_sha256=sha(left.run/'inputs.csv'),identical_actual_peer_GMII_input=True)

def comparison_gui():
    import tkinter as tk
    from tkinter import ttk,messagebox
    window=tk.Tk();window.title('08 调度优化前后对照 · 相同输入重新仿真');window.geometry('950x760');window.option_add('*Font',('Microsoft YaHei',10))
    ttk.Label(window,text='调度优化前后对照',font=('Microsoft YaHei',20,'bold')).pack(anchor='w',padx=18,pady=16)
    ttk.Label(window,text='24 帧 · 16 VL · 1471 字节 · 8100 周期输入间隔 · 125 MHz · 1 ms BAG\n含两个管理请求突发；仅声明此压力条件。两套 ModelSim 停下后等待确认。\n本项使用 service_pressure_011 已验证配套生产 RTL 快照；仅仲裁器不同。01～07 使用当前 RTL。').pack(anchor='w',padx=18)
    state=tk.StringVar(value='正在加载两套真实 RTL……');ttk.Label(window,textvariable=state).pack(anchor='w',padx=18,pady=12)
    output=tk.Text(window,wrap='word');output.pack(side='bottom',fill='both',expand=True,padx=18,pady=12)
    sessions=[];started=[False];deadline=[time.time()+240]
    def log(s):output.insert('end',s+'\n');output.see('end')
    def boot():
        try:
            baseline=ROOT/'build/logs/service_pressure_010/afdx_service_tx_arbiter_615a.v'
            original=json.loads((baseline.parent/'summary.json').read_text())
            assert original['result']=='PASS','Historical baseline is not PASS'
            fingerprints=[h for p,h in original['inputs'].items() if Path(p).name==baseline.name]
            assert fingerprints==[sha(baseline)],'Historical baseline snapshot hash mismatch'
            reference=ROOT/'build/logs/service_pressure_011'
            sessions.extend([Session(8,arbiter=baseline,reference=reference),Session(8,reference=reference)])
            for label,s in zip(('优化前','优化后'),sessions):log(label+'：'+str(s.run))
            poll_ready()
        except Exception as exc:state.set('加载失败');log(str(exc))
    def poll_ready():
        if all((s.run/'ready.txt').exists() for s in sessions):state.set('等待本人确认实际负载；两套仿真均已停下');return
        if time.time()>deadline[0]:state.set('加载超时；查看各自 transcript.log');return
        window.after(400,poll_ready)
    def start():
        if started[0] or len(sessions)!=2 or not all((s.run/'ready.txt').exists() for s in sessions):return
        if not messagebox.askyesno('确认对照条件','确认以页面中的相同压力条件重新运行优化前、后两套设计？\n仅发送仲裁器源码不同。'):return
        try:
            durations=[s.pressure(24) for s in sessions];provenance=compare_provenance(*sessions)
            for s,d in zip(sessions,durations):(s.run/'request.txt').write_text(str(d))
            started[0]=True;deadline[0]=time.time()+300;state.set('正在运行相同负载并独立核对……');poll_done(provenance)
        except Exception as exc:state.set('对照失败');log(str(exc))
    def poll_done(provenance):
        if all((s.run/'response.txt').exists() for s in sessions):
            proofs=[s.result() if (s.run/'response.txt').read_text().strip()=='DONE' else dict(result='FAIL') for s in sessions]
            try:provenance=compare_actual_inputs(*sessions,provenance)
            except Exception as exc:state.set('实际输入不一致，对照失败');log(str(exc));return
            result=dict(result='PASS' if all(p['result']=='PASS' for p in proofs) else 'FAIL',provenance=provenance,before=proofs[0],after=proofs[1])
            dump(sessions[1].run/'comparison.json',result);state.set('本次对照 '+result['result'])
            output.delete('1.0','end')
            for label,s,p in zip(('优化前','优化后'),sessions,proofs):
                log(label+'\n'+readable_result(s.run,p,compact=True))
                if p['result']=='PASS':
                    m=p['metrics'];log(f"最大观测时延达标状态：{'达标（本次样本）' if m['max_application_first_to_last_us']<2000 else '未达标（本次样本）'}")
                    focus_wave(s.run)
            if result['result']=='PASS':
                lm=proofs[0]['metrics'];rm=proofs[1]['metrics']
                log(f"本次吞吐变化：{(rm['delivered_payload_Mbps']/lm['delivered_payload_Mbps']-1)*100:+.2f}%；最大观测时延变化：{(rm['max_application_first_to_last_us']/lm['max_application_first_to_last_us']-1)*100:+.2f}%")
            log('源码与 Golden 一致，仅仲裁器不同；实际应用和对端输入字节／周期一致。')
            log('完整对照证据：'+str(sessions[1].run/'comparison.json'));return
        if time.time()>deadline[0]:state.set('运行超时；本次未通过');return
        window.after(400,lambda:poll_done(provenance))
    ttk.Button(window,text='确认条件并开始两套新仿真',command=start).pack(anchor='w',padx=18,pady=6)
    window.after(100,boot);window.mainloop()

def main():
    p=argparse.ArgumentParser();p.add_argument('--scenario',type=int,choices=range(1,9),default=1);p.add_argument('--self-test',action='store_true');p.add_argument('--basic',action='store_true');args=p.parse_args()
    if args.self_test:self_test()
    elif args.basic:
        from basic_demo import BasicDemo
        BasicDemo()
    elif args.scenario==8:comparison_gui()
    else:Controller(args.scenario)

if __name__=='__main__':main()
