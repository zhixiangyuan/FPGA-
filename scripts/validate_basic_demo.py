"""Automated real-RTL suite validation; not a user-recorded demonstration."""
import copy
from basic_demo import BasicEvidence,REQUIRED
from interactive_demo import Session,operation_result,dump,ROOT,sha
from validate_interactive_demo import wait_file,gui_action


def main():
    tracker=BasicEvidence();results=[];text=b'I LOVE FPGA'
    assert all(i['status']=='未运行' for i in tracker.items.values())

    def stage(number,steps):
        session=Session(number,extra_helpers=(ROOT/'scripts/basic_demo.py',));previous=None
        wait_file(session,'ready.txt')
        try:
            for name,fn,expected,complete in steps:
                proof=gui_action(session,lambda:fn(session))
                display=operation_result(session,proof,previous)
                item=tracker.record(number,session,proof,previous,display)
                for value in expected:assert value in display,(name,value,display)
                assert (item['status']=='完成')==complete,(name,item)
                (session.run/f'result_{session.index}.txt').write_text(display+'\n',encoding='utf-8')
                results.append(dict(stage=number,case=name,run=str(session.run),action=session.index,proof=proof,
                                    display=display,coverage=copy.deepcopy(item),result='PASS'))
                previous=copy.deepcopy(proof);print('PASS '+name,flush=True)
        finally:(session.run/'close.txt').write_text('basic suite validation finished')
        assert tracker.items[number]['status']=='完成',(number,tracker.items[number])

    stage(1,[('01 default text',lambda s:s.app(0x1234,text,interval=64),['内容：I LOVE FPGA','11 字节','交付 +1 帧'],True)])
    stage(2,[('02 default batch',lambda s:s.app(0x1234,b'X'*64,32,4,33000),['1234=8 帧','1237=8 帧','交付 +32 帧'],True)])
    stage(3,[
        ('03 normal is not full fault coverage',lambda s:s.app(0x1234,text,interval=64),['交付 +1 帧','消重 +1 次'],False),
        ('03 apply A',lambda s:s.fault(1),['已生效链路：仅 A'],False),
        ('03 A delivery',lambda s:s.app(0x1234,text,interval=64),['交付 +1 帧'],False),
        ('03 apply B',lambda s:s.fault(2),['已生效链路：仅 B'],False),
        ('03 B delivery',lambda s:s.app(0x1234,text,interval=64),['交付 +1 帧'],False),
        ('03 apply A error',lambda s:s.fault(3,1),['A 接收错误注入：开启'],False),
        ('03 A error survives',lambda s:s.app(0x1234,text,interval=64),['交付 +1 帧','本次 MAC 丢弃 A/B：+1/+0'],False),
        ('03 apply disconnect',lambda s:s.fault(0),['已生效链路：双网断开'],False),
        ('03 no stale delivery',lambda s:s.app(0x1234,text,interval=64),['交付 +0 帧','无新数据'],False),
        ('03 apply restore',lambda s:s.fault(3),['已生效链路：双网正常'],False),
        ('03 restored delivery completes fault coverage',lambda s:s.app(0x1234,text,interval=64),['交付 +1 帧'],True),
    ])
    stage(4,[
        ('04 normal is not full error coverage',lambda s:s.inject(0x12a0,text,1,'正常报文'),['交付 +1 帧'],False),
        ('04 FCS rejection',lambda s:s.inject(0x12a0,text,2,'FCS错误'),['交付 +0 帧','本次 MAC 丢弃 A/B：+1/+1'],False),
        ('04 IP rejection',lambda s:s.inject(0x12a0,text,2,'IP校验错误'),['交付 +0 帧','业务解析器拒绝 A/B：+1/+1'],False),
        ('04 UDP rejection',lambda s:s.inject(0x12a0,text,2,'UDP长度错误'),['交付 +0 帧','业务解析器拒绝 A/B：+1/+1'],False),
        ('04 recover correct frame',lambda s:s.inject(0x12a0,text,2,'正常报文'),['交付 +1 帧'],False),
        ('04 abnormal SN completes error coverage',lambda s:s.inject(0x12a0,text,9,'正常报文'),['交付 +0 帧','序号异常 +2 次'],True),
    ])
    stage(5,[
        ('05 GET initial',lambda s:s.snmp(4),['实际 SNMP 响应值：afdx-es-team3'],False),
        ('05 SET is not readback',lambda s:s.snmp(4,text),['实际 SNMP 响应值：I LOVE FPGA'],False),
        ('05 GET actual readback completes management',lambda s:s.snmp(4),['实际 SNMP 响应值：I LOVE FPGA'],True),
    ])
    stage(6,[('06 fresh request synchronization',lambda s:s.sync(250),['RTC 同步状态：0 → 1'],True)])
    negative=copy.deepcopy(tracker)
    negative.reset(3)
    assert negative.items[3]['status']=='未运行' and negative.items[5]['status']=='完成'
    try:tracker.record(1,None,dict(result='FAIL'),None,'')
    except AssertionError:pass
    else:raise AssertionError('failed proof was accepted')
    assert all(i['status']=='完成' for i in tracker.items.values())
    dump(ROOT/'reports/系统基础功能整合验证.json',dict(result='PASS',kind='automated real-RTL implementation check, not human acceptance',
         source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'scripts/basic_demo.py',ROOT/'scripts/interactive_demo.py')},
         items=tracker.items,checks=results,negative_checks=['untested stages remain unrun','partial tests do not complete a stage',
         'SET alone does not count as readback','reset clears only the selected stage','failed proof cannot pass']))
    print('PASS all six stages and coverage checks',flush=True)


if __name__=='__main__':main()
