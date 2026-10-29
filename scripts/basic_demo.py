"""One manual control window, isolated real simulations, evidence-based coverage."""
from datetime import datetime
from pathlib import Path
import collections
from interactive_demo import ROOT,TITLES,Controller,app_packets,frames,snmp_response,dump,sha


REQUIRED={
    1:('原样收发',),
    2:('多 VL 完整交付','同 VL BAG',),
    3:('双网交付与消重','仅 A 交付','仅 B 交付','A 错误时 B 交付','双网断开无交付','恢复后交付'),
    4:('正常报文交付','FCS 错误拒收','IP 错误拒收','UDP 错误拒收','异常序号拒收','错误后正常交付'),
    5:('GET 初始值','SET 新值','GET 读回新值'),
    6:('四时间戳校时',),
}


class BasicEvidence:
    def __init__(self):
        self.items={};self.state={}
        for n in REQUIRED:self.reset(n)

    def reset(self,n):
        self.items[n]=dict(status='未运行',covered=[],required=list(REQUIRED[n]),run=None,last_result='')
        self.state[n]=dict(had_fault=False,had_bad=False,reads={},writes={})

    def record(self,n,s,proof,previous,result):
        assert proof['result']=='PASS','failed proof cannot populate a passing summary'
        old=previous or {};status=proof['status'];before=old.get('status',{})
        delta=lambda k:int(status[k])-int(before.get(k,0))
        new=app_packets(s.run/'application.csv')[old.get('application_messages',0):]
        action=s.plan['actions'][-1];detail=action.get('detail') or {};label=action['label']
        item=self.items[n];state=self.state[n];covered=set(item['covered'])
        if n==1 and label=='手动发送' and len(new)==1 and new[0][2].hex()==s.plan['app'][-1]:covered.add('原样收发')
        if n==2 and label=='用户确认批量负载':
            counts=collections.Counter(int.from_bytes(p[2][:2],'big') for p in new)
            if detail['VLs']>=2 and len(counts)==detail['VLs'] and len(new)==detail['count']:
                covered.add('多 VL 完整交付')
                if all(v>=2 for v in counts.values()) and proof['minimum_per_VL_BAG_cycles'] is not None:
                    covered.add('同 VL BAG')
        if n==3:
            if label=='选择链路故障或恢复' and (s.mask!=3 or s.error):state['had_fault']=True
            if label=='手动发送' and delta('sent')==1:
                if s.mask==3 and not s.error and len(new)==1:
                    if delta('duplicates')==1:covered.add('双网交付与消重')
                    if state['had_fault']:covered.add('恢复后交付')
                if s.mask==1 and len(new)==1:covered.add('仅 A 交付')
                if s.mask==2 and len(new)==1:covered.add('仅 B 交付')
                if s.mask==3 and s.error and len(new)==1 and delta('dropa')==1:covered.add('A 错误时 B 交付')
                if s.mask==0 and not new:covered.add('双网断开无交付')
        if n==4 and label=='手动对端报文注入':
            bad=detail['mutation']
            if bad=='正常报文' and len(new)==1:
                covered.add('正常报文交付')
                if state['had_bad']:covered.add('错误后正常交付')
            if not new:
                if bad=='FCS错误' and delta('dropa')>0 and delta('dropb')>0:covered.add('FCS 错误拒收')
                if bad=='IP校验错误' and delta('parsea')>0 and delta('parseb')>0:covered.add('IP 错误拒收')
                if bad=='UDP长度错误' and delta('parsea')>0 and delta('parseb')>0:covered.add('UDP 错误拒收')
                if bad=='正常报文' and delta('integrity')>0:covered.add('异常序号拒收')
                state['had_bad']=True
        if n==5 and label.startswith('SNMP'):
            replies=frames(s.run/'wire_a.csv')[old.get('wire_frames',0):]
            reply=snmp_response(next(w for _,_,w,_ in reversed(replies) if int.from_bytes(w[12:14],'big')==0x12b4))
            obj=str(reply['object']);value=reply['value']
            if label=='SNMP GET':
                if obj in state['writes'] and value==state['writes'][obj]:covered.add('GET 读回新值')
                else:covered.add('GET 初始值')
                state['reads'][obj]=value
            elif obj in state['reads'] and value!=state['reads'][obj]:
                state['writes'][obj]=value;covered.add('SET 新值');covered.discard('GET 读回新值')
        if n==6 and proof['rtc'] and int(status['sync'])==1:covered.add('四时间戳校时')
        item.update(status='完成' if set(REQUIRED[n])<=covered else '进行中',covered=[k for k in REQUIRED[n] if k in covered],
                    run=str(s.run),last_action=action['id'],last_result=result)
        return item


class BasicDemo:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        self.root=tk.Tk();self.root.title('视频1 · 系统基础功能 · 真实 RTL 手动演示')
        self.root.option_add('*Font',('Microsoft YaHei',10))
        self.root.geometry(f'{min(1140,self.root.winfo_screenwidth()-80)}x{min(920,self.root.winfo_screenheight()-100)}')
        ttk.Label(self.root,text='系统基础功能',font=('Microsoft YaHei',20,'bold')).pack(anchor='w',padx=18,pady=10)
        self.overall=tk.StringVar(value='基础功能完成：0 / 6 项 · 真实 RTL · 125 MHz')
        ttk.Label(self.root,textvariable=self.overall).pack(anchor='w',padx=18,pady=4)
        self.book=ttk.Notebook(self.root);self.book.pack(fill='both',expand=True,padx=8,pady=8)
        self.pages=[];self.active=None;self.pending=None;self.alive=False;self.evidence=BasicEvidence()
        self.run=ROOT/'build/interactive_suite'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');self.run.mkdir(parents=True)
        for n in range(1,7):
            frame=ttk.Frame(self.book);self.book.add(frame,text=f'{n:02d} {TITLES[n-1]}')
            self.pages.append(Controller(n,parent=frame,suite=self))
        summary=ttk.Frame(self.book);self.book.add(summary,text='结果汇总')
        self.table=ttk.Treeview(summary,columns=('name','state','coverage'),show='headings',height=6)
        for key,title,width in (('name','功能测试',240),('state','实际验证状态',120),('coverage','已完成子测试',520)):
            self.table.heading(key,text=title);self.table.column(key,width=width,stretch=True)
        self.table.pack(fill='x',padx=12,pady=12)
        self.summary=tk.Text(summary,wrap='word',height=12);self.summary.pack(fill='both',expand=True,padx=12,pady=8)
        self.book.bind('<<NotebookTabChanged>>',self.select)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();self.root.after(100,self.select);self.root.mainloop()

    def refresh(self):
        done=sum(v['status']=='完成' for v in self.evidence.items.values())
        self.overall.set(f'基础功能完成：{done} / 6 项 · 真实 RTL · 125 MHz')
        for i in self.table.get_children():self.table.delete(i)
        lines=[]
        for n,item in self.evidence.items.items():
            coverage='；'.join(item['covered']) or '尚无实际验证结果'
            self.table.insert('', 'end',values=(TITLES[n-1],item['status'],f"{len(item['covered'])}/{len(REQUIRED[n])}：{coverage}"))
            missing=[k for k in REQUIRED[n] if k not in item['covered']]
            lines.append(f"{n:02d} {TITLES[n-1]}：{item['status']}"+('；尚未完成：'+'、'.join(missing) if missing else '；全部子测试通过'))
        self.summary.config(state='normal');self.summary.delete('1.0','end');self.summary.insert('end','\n\n'.join(lines));self.summary.config(state='disabled')
        dump(self.run/'summary.json',dict(kind='manual suite results; not full official acceptance',completed=done,
              source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'scripts/basic_demo.py',ROOT/'scripts/interactive_demo.py')},items=self.evidence.items))

    def retire(self):
        if self.active is not None and self.alive:
            page=self.pages[self.active]
            if page.s:(page.s.run/'close.txt').write_text('suite changed active experiment')
            page.state.set('本项仿真已结束；已完成结果保留');self.alive=False

    def select(self,event=None):
        index=self.book.index('current')
        if index==self.active:return
        if self.active is not None and self.alive and self.pages[self.active].busy:
            self.book.select(self.active);return
        self.retire()
        self.active=index if index<6 else None
        if self.active is not None and self.pages[index].s is None:self.start_page(self.pages[index])

    def start_page(self,page,callback=None):
        if self.alive:self.retire()
        self.evidence.reset(page.scenario);page.last_proof=None;page.failed=False;page.busy=True
        if page.scenario==3:page.entries['fault'].set('双网正常')
        self.pending=callback;self.alive=True;self.refresh()
        page.state.set('正在加载本项独立仿真……');page.log('本项新测试：尚未运行。')
        page.start(page.scenario)

    def dispatch(self,page,callback):
        if page.busy:page.mb.showinfo('请稍候','仿真启动或运行中，请等待结果。');return
        if not self.alive or page.failed or page.s.process.poll() is not None or (page.scenario==6 and page.s.plan.get('sync')):
            self.start_page(page,callback);return
        page.execute(callback)

    def ready(self,page):
        if self.pending is not None:
            callback=self.pending;self.pending=None;page.execute(callback)

    def record(self,page,proof,previous,result):
        self.evidence.record(page.scenario,page.s,proof,previous,result);self.refresh()

    def failed(self,page,error):
        self.pending=None
        self.evidence.items[page.scenario].update(status='失败',error=error)
        self.refresh()

    def close(self):
        self.retire();self.root.destroy()


if __name__=='__main__':BasicDemo()
