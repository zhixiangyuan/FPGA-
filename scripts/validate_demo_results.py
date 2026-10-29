"""Automated real-RTL checks for the manual's inputs and per-operation display.

This is implementation validation, not human acceptance or a recorded demonstration.
"""
import copy
from interactive_demo import (Session,run_batch,operation_result,dump,ROOT,
                              compare_provenance,compare_actual_inputs)
from validate_interactive_demo import wait_file,gui_action


def main():
    evidence=[]

    def scenario(number,steps):
        s=Session(number);previous=None
        wait_file(s,'ready.txt')
        try:
            for name,fn,checks in steps:
                proof=gui_action(s,lambda:fn(s))
                result=operation_result(s,proof,previous)
                for wanted in checks:assert wanted in result,(name,wanted,result)
                (s.run/f'result_{s.index}.txt').write_text(result+'\n',encoding='utf-8')
                evidence.append(dict(case=name,run=str(s.run),action=s.index,result='PASS',display=result))
                previous=copy.deepcopy(proof)
                print('PASS '+name,flush=True)
        finally:
            (s.run/'close.txt').write_text('implementation validation completed')

    scenario(1,[
        ('01 default',lambda s:s.app(0x1234,b'HELLO_FPGA',interval=64),['内容：HELLO_FPGA','交付 +1 帧']),
        ('01 edited longer data',lambda s:s.app(0x1235,b'FPGA_0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ',interval=64),['VLID=0x1235','42 字节','交付 +1 帧']),
        ('01 repeated data matches current action',lambda s:s.app(0x1235,b'FPGA_0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ',interval=64),['交付 +1 帧']),
    ])
    scenario(2,[
        ('02 4 VL',lambda s:s.app(0x1234,b'X'*64,32,4,33000),['1234=8 帧','1237=8 帧','交付 +32 帧','最小发送间隔：']),
    ])
    scenario(3,[
        ('03 both normal',lambda s:s.app(0x1234,b'NET_TEST',interval=64),['交付 +1 帧','消重 +1 次']),
        ('03 apply A only',lambda s:s.fault(1),['已生效链路：仅 A','未发送业务数据']),
        ('03 A only',lambda s:s.app(0x1234,b'ONLY_A',interval=64),['交付 +1 帧','内容：ONLY_A']),
        ('03 apply B only',lambda s:s.fault(2),['已生效链路：仅 B']),
        ('03 B only',lambda s:s.app(0x1234,b'ONLY_B',interval=64),['交付 +1 帧','内容：ONLY_B']),
        ('03 inject A error',lambda s:s.fault(3,1),['A 接收错误注入：开启']),
        ('03 B survives A error',lambda s:s.app(0x1234,b'A_ERROR_B_OK',interval=64),['交付 +1 帧','本次 MAC 丢弃 A/B：+1/+0']),
        ('03 restore',lambda s:s.fault(3),['已生效链路：双网正常']),
        ('03 restored delivery',lambda s:s.app(0x1234,b'RECOVER_OK',interval=64),['交付 +1 帧','内容：RECOVER_OK']),
        ('03 disconnect both',lambda s:s.fault(0),['已生效链路：双网断开']),
        ('03 no stale data while disconnected',lambda s:s.app(0x1234,b'NO_DELIVERY',interval=64),['发送 +1 帧；交付 +0 帧','无新数据','无交付样本']),
    ])
    scenario(4,[
        ('04 valid SN1',lambda s:s.inject(0x12a0,b'CHECK_TEST',1,'正常报文'),['交付 +1 帧']),
        ('04 FCS bad',lambda s:s.inject(0x12a0,b'BAD_FCS',2,'FCS错误'),['交付 +0 帧','本次 MAC 丢弃 A/B：+1/+1','无新数据']),
        ('04 IP bad',lambda s:s.inject(0x12a0,b'BAD_IP',2,'IP校验错误'),['交付 +0 帧','业务解析器拒绝 A/B：+1/+1']),
        ('04 UDP bad',lambda s:s.inject(0x12a0,b'BAD_UDP',2,'UDP长度错误'),['交付 +0 帧','业务解析器拒绝 A/B：+1/+1']),
        ('04 valid SN2',lambda s:s.inject(0x12a0,b'GOOD_FRAME',2,'正常报文'),['交付 +1 帧','内容：GOOD_FRAME']),
        ('04 abnormal SN9',lambda s:s.inject(0x12a0,b'BAD_SN',9,'正常报文'),['交付 +0 帧','序号异常 +2 次','无新数据']),
        ('04 recover SN10',lambda s:s.inject(0x12a0,b'NEXT_OK',10,'正常报文'),['交付 +1 帧','内容：NEXT_OK']),
    ])
    scenario(5,[
        ('05 GET original',lambda s:s.snmp(4),['实际 SNMP 响应值：afdx-es-team3']),
        ('05 SET new',lambda s:s.snmp(4,b'FPGA_TEST_2026'),['本次 SET 输入：FPGA_TEST_2026','实际 SNMP 响应值：FPGA_TEST_2026']),
        ('05 GET new',lambda s:s.snmp(4),['实际 SNMP 响应值：FPGA_TEST_2026','本次 SNMP 请求/响应：+1/+1']),
        ('05 SET other object',lambda s:s.snmp(5,b'FPGA_NODE_1'),['对象：sysName','实际 SNMP 响应值：FPGA_NODE_1']),
        ('05 GET other object',lambda s:s.snmp(5),['实际 SNMP 响应值：FPGA_NODE_1']),
    ])
    scenario(6,[('06 synchronize',lambda s:s.sync(250),['RTC 同步状态：0 → 1','实际 RTC offset：','绝对 UTC 精度：未测量'])])
    scenario(7,[('07 default performance',lambda s:s.app(0x1234,b'X'*1471,64,16,8100),['交付 +64 帧','达标状态：达标（本次负载）','本次同 VL 同长度时延极差：'])])
    baseline=ROOT/'build/logs/service_pressure_010/afdx_service_tx_arbiter_615a.v'
    reference=ROOT/'build/logs/service_pressure_011'
    left=Session(8,batch=True,arbiter=baseline,reference=reference)
    right=Session(8,batch=True,reference=reference)
    ld=left.pressure(24);rd=right.pressure(24)
    provenance=compare_provenance(left,right)
    lp=run_batch(left,[ld]);rp=run_batch(right,[rd])
    provenance=compare_actual_inputs(left,right,provenance)
    evidence.append(dict(case='08 comparison',result='PASS',before=lp,after=rp,provenance=provenance))
    report=dict(result='PASS',kind='automated implementation validation; not human acceptance',checks=evidence)
    path=ROOT/'reports/交互演示可视结果验证.json';dump(path,report)
    print('PASS '+str(path),flush=True)


if __name__=='__main__':main()
