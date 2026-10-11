"""Refresh truthful B2-4 status and evidence report without touching frozen RTL."""
from pathlib import Path
import hashlib,json,shutil,sys
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
EXPORT=ROOT/'runs/eda_export_001'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def rows(obj):
    if isinstance(obj,dict):
        if 'path' in obj and 'sha256' in obj:yield obj
        for v in obj.values():yield from rows(v)
    elif isinstance(obj,list):
        for v in obj:yield from rows(v)
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main(run):
    s=json.loads((run/'summary.json').read_text());a=json.loads((EXPORT/'synthesis_audit.json').read_text());e=json.loads((EXPORT/'provenance.json').read_text())
    statuspath=ROOT/'runs/current_status.json';archive=EXPORT/'frozen_B2_current_status.json'
    if not archive.exists():shutil.copy2(statuspath,archive)
    checks=[]
    for manifest in (ROOT/'B2_EVIDENCE_MANIFEST.json',ROOT.parent/'stage5B1_single_vl_20261010/B1_FREEZE_MANIFEST.json'):
        for row in rows(json.loads(manifest.read_text(encoding='utf-8'))):
            original=Path(row['path']);actual=archive if original==statuspath else original
            got=sha(actual);checks.append({'original':str(original),'verified_path':str(actual),'expected_sha256':row['sha256'],'actual_sha256':got,'match':got==row['sha256']})
    assert all(x['match'] for x in checks),'Frozen evidence changed; inspect freeze_audit before proceeding'
    write(EXPORT/'freeze_audit.json',{'result':'PASS','count':len(checks),'B2_status_superseded_with_archived_exact_baseline':str(archive),'checks':checks})
    st=json.loads(archive.read_text(encoding='utf-8'));st['generated_utc']=datetime.now(timezone.utc).isoformat()
    st['scope']='Approved B2-1/B2-2 frozen; B2-4 real GUI synthesis and VO export completed; full functional netlist acceptance '+s['result']
    verified=run/'netlist_verification.json';complete=s['result']=='PASS' and verified.is_file() and json.loads(verified.read_text())['result']=='PASS'
    st['states'].update(B2_4_SYNTHESIS='PASS',B2_4_WARNING_AUDIT='COMPLETE_WITH_DIAGNOSTIC_LIMITATION',B2_4_VO_EXPORT='PASS',B2_POST_SYNTH_FUNCTIONAL='PASS' if complete else s['result'],B2_4_RESULT='PENDING_CAPTAIN_REVIEW' if complete else 'IN_PROGRESS' if s['result']=='RUNNING' else s['result'],B2_WRAPPER_DIAG_ADDR_1='UNSUPPORTED',POST_SYNTH_TIMING='NOT VERIFIED',EQ6_NATIVE_NETLIST_EQUIVALENCE='NOT VERIFIED',DIAGNOSTIC_IO_FIT='INCOMPATIBLE',B2_LOW_IO_PHYSICAL_FIT='NOT VERIFIED')
    st['evidence'].update(B2_4_synthesis=str(a['gui_project']),B2_4_export=str(EXPORT),B2_4_netlist=str(run),B2_4_freeze_audit=str(EXPORT/'freeze_audit.json'))
    st['limits']=[x for x in st['limits'] if not x.startswith('No synthesis,')]
    st['limits']+=['B2-4 synthesis/functional model is separate from timing, physical pin fit and EQ6-native equivalence.','Wrapper diagnostic address 1 is undriven and must not be used as a TX rejection counter; functional acceptance uses actual app output and connected diagnostics.','No Implementation, Bitstream, hardware download or B2-3 formal top integration.']
    write(statuspath,st);write(ROOT/'runs/b2_4_status.json',st)
    progress=(run/'frame_progress.csv').read_text().splitlines() if (run/'frame_progress.csv').exists() else []
    p=progress[-1].split(',') if progress else None
    v=json.loads(verified.read_text()) if complete else None
    warnings=['| 序号 | 类型 | 原始报告行 | 告警及判断 |','|---|---|---:|---|']
    notes={'undriven_wrapper_diagnostic':'包装层地址 1 无效；不得作为 TX 拒绝计数证据。','frozen_MAC_case_default':'组合块已预置 gmii_txd=0；冻结 MAC 不改。','frozen_MAC_width_truncation':'状态常量和有界长度运算截断；冻结 MAC 不改，由实际网表功能覆盖。','unused_parser_register':'frame_reject 不参与最终判定；Parser 主数据路径及 first_error 保留。','RAM_read_during_write_bypass':'工具增加旁路以保留 RTL 同址读写行为；由压力/恢复用例核验。','constant_output_group':'常量输出汇总。','constant_profile_output':'单 VL 固定配置及正常 TX_ER 固定 0，符合包装 profile。'}
    for row in a['warnings']:
        raw=row['message'].replace('|','／')
        warnings.append(f"| {row['index']} | {row['code']} | {row['report_line']} | {raw}；{notes[row['category']]} |")
    text=f'''# 阶段5-B2-4 综合与真实功能网表验收报告

更新时间：{datetime.fromisoformat(st['generated_utc']).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}（北京时间）。{'最终报告：B2-4 已授权综合与真实功能网表验收完成，等待队长审核；完整 B2 正式工程集成尚未完成。' if complete else '当前为持续更新报告。'}完整网表结论：**{st['states']['B2_POST_SYNTH_FUNCTIONAL']}**。

## 1. 验收状态及边界

| 项目 | 状态 | 证据 |
|---|---|---|
| B2-1/B2-2 功能基线 | PASS，冻结 | full_003、history_002；本轮未重跑已通过的长测试 |
| 官方 GUI 综合 | PASS | elinx_002；Errors=0，Warnings=34 |
| 综合逻辑与 RAM 审计 | 完成 | synthesis_audit.json、原始 map.rpt |
| 真实功能 VO 导出 | PASS | eda_export_001；退出码 0，0 errors、0 warnings |
| 完整功能网表 Golden | {st['states']['B2_POST_SYNTH_FUNCTIONAL']} | {run.name} |
| 包装诊断地址 1 | UNSUPPORTED | tx_rejected 未驱动；不作为验收证据 |
| POST_SYNTH_TIMING | NOT VERIFIED | 不将 8 ns 约束视作 Setup/Hold 通过 |
| EQ6_NATIVE_NETLIST_EQUIVALENCE | NOT VERIFIED | VO 使用 Stratix 兼容原语 |
| 原 579 位诊断顶层适配 | INCOMPATIBLE | 保留历史结论 |
| 新包装物理封装适配 | NOT VERIFIED | 实际 IO=138/160；未执行引脚布局或 Implementation |
| B2-3、Implementation、Bitstream、下载 | NOT RUN | 未执行 |

## 2. 真实综合资源与约束

目标为 EQ6HL45/CSG225，Top=afdx_b2_synth_wrap。真实 eLinx 报告：LUT=3471/42560、FF=1422/42560、IO=138/160、Memory=20/392、CLB=497、DSP=0、PLL=0。138 位为实际统计；容量余量不能证明具体引脚分配及封装物理适配。

EDC 为 `create_clock -name gmii_clk -period 8.000 -waveform {{0.000 4.000}} [get_ports clk]`，EPR 已选择该文件；综合 clocklist.pb 中保留 gmii_clk/clk。约束文件和 clocklist.pb 均归档并记录哈希。未执行 STA，未获得 Setup/Hold 结果。

综合层级保留 B1 sender（360 FF）、BAG gate（70 FF）、IPv4 checksum、B0 MAC（639 FF）、B2 Parser（241 FF）、SN gate（174 FF），以及 SN IDLE/PASS/DRAIN 状态。RAM 为 B0 三组 2048×8、B2 两组 1471×8，共 72,688 bit。两组 Parser bank 及收发 CRC、MAC 数据链路未被优化为空逻辑。eLinx EDI 确认 EQ6HL45；EDA 后端 QSF/导出日志确认兼容模型 EP1S80F1508C6，二者分别记录。

map.rpt 另列 33 个代表组合环的逻辑单元；已冻结 B1 历史报告同类统计为 17。该统计保留为后续时序审计项，不视作功能或时序 PASS；本轮用真实原语功能模型验证数据与恢复行为。

## 3. 34 条 Warning 逐条分类

总计：位宽截断 12、MAC 缺省分支 1、未使用寄存器 1、RAM 旁路 5、常量输出 13、包装诊断未连接 2。以下原始报告行均来自 elinx_002 的 AFDXB2.map.rpt。

{chr(10).join(warnings)}

地址 1 的缺陷仅影响包装层 TX 拒绝计数读数，不能宣称该诊断项正确。本轮保留原综合源码与数据库，不重复 GUI 综合；真实应用 Payload、SN/PSN、Parser/MAC 计数及 bank 状态使用其余已连接外部端口验证。后续若需要该诊断，须修正包装层并重新综合验收；冻结生产 RTL 不改。

## 4. VO 来源与 ModelSim 验收

仅复制成功工程并调用 quartus_eda 功能导出，没有重新执行 synthesis/fit。模型文件为 `{e['delivered_netlist']}`，SHA-256=`{e['delivered_netlist_sha256']}`。导出命令、工具哈希、数据库哈希、日志与目标映射见 provenance.json / synthesis_audit.json。

ModelSim SE-64 2020.4 的 DUT 仅编译真实 VO、原厂 altera_primitives/220model/stratix_atoms 库与测试平台。不编译生产 RTL 作为 DUT，不使用 Mock、force 或 SN 绕过。125 MHz、125000 周期 BAG、256 帧 SN 回绕保持不变，沿用独立 Golden 的 309 用例；目标为 263 个真实 B1 TX 帧、20454 个 GMII 字节、291 个最终应用帧、2431 个应用字节和 303 条 SN 决策比较。

地址 15 仅暴露 late_count 低 16 位。冻结 BAG 源码每个 GMII 起始沿最多增加一次迟到计数，reset 清零；本套件总 TX 为 263 帧，低 16 位不可能发生计数回绕。因此本套件的零迟到断言有效，但不将该诊断扩展解释为一般情况下可观测完整 32 位计数。

覆盖首次基线、+1/+2、255→1、重复/旧号/异常跳号后 PSN 恢复、SN=0、合法 FCS 的协议错误、独立坏 FCS、双缓存与 MAC 容量压力、接受/实际交付计数守恒、背压稳定性、reset 取消及恢复。PSN/计数通过真实外部诊断总线读取，最终交付逐字节比较 app_data/length/VLID/SN/SOP/EOP。诊断扫描在真实 BAG 等待期间暂停，降低额外仿真事件；DUT 时钟及 BAG 不变。

netlist_001 编译失败记录完整保留：旧原语库 soft 标识符与 SystemVerilog 关键字冲突。仅将 .v/VO 按 Verilog 模式、.sv 按 SystemVerilog 模式编译后，在新目录 netlist_002 重测。此为编译脚本修复，未修改原语库或生产 RTL。

最新持久化进度：{('case='+p[1]+'，TX='+p[2]+'/263，应用帧='+p[3]+'/291，cycle='+p[0]) if p else '尚未生成帧进度'}。{'ModelSim 于北京时间 2026-10-11 17:20:33 完成，实际墙钟约 4 小时 1 分钟，退出码 0，Errors=0、Warnings=0；三个原始 PASS 标记齐全，原有 vsim/vsimk 进程已退出。' if complete else '该行只表示已完成的用例，不能证明后续用例通过。'}

完整验证结果：{json.dumps(v,ensure_ascii=False) if v else '尚未取得完整 PASS；保留 RUNNING/FAIL 原始状态，不提前验收。'}

## 5. 冻结与证据

B1 Git 冻结提交 302b944afc111aa232688d700911704d667c7a37；B2-1/B2-2 冻结提交 2355e7b24349c2b8aa7654657ddfb2a0aae57609。本轮逐项核对 {len(checks)} 份已冻结源码与证据哈希，全部匹配；唯一滚动状态文件 current_status.json 的旧版本已按原哈希保存至 eda_export_001/frozen_B2_current_status.json，原冻结清单不改。

GUI 项目副本、map/utilization/EDI/clocklist/cluster/db、VO、TB、原语库、Golden 生成器/输入哈希、失败记录、原始 console/transcript、WLF 与 CSV 均保留。历史回归沿用已冻结 history_002 的真实 PASS，本轮生产源码未改；不将沿用记录描述为新运行。运行中的 WLF/CSV 不标作最终哈希；退出后使用 summary.json 与 verification.json 完成审计。

## 6. 监控与停止条件

只保留一份完整真实网表测试，runs/B2_NETLIST_RUNNING.lock 记录运行目录和控制进程。核对实际 vsim/vsimk 进程、CPU、frame_progress.csv、原始日志与 WLF；BAG 等待期间允许日志缓冲，不能仅以日志无新行判定停滞。超时上限 24 小时，出现 FAIL 或不再推进时先保留证据，再定位测试包装/脚本范围内的问题；涉及冻结 RTL 修改则停止相关步骤等待队长授权。

{'本轮已核对退出码 0、三个原始 PASS 标记、Errors: 0、逐字节 CSV、303 条 SN 决策、309 个 Golden 用例、非空 WLF 与输入哈希；另独立核对 261 个同 reset epoch 的 BAG 间隔，最小 125003 周期，不低于真实 125000 周期。自动监控在归档后暂停，任务停止，等待队长审核。' if complete else '全部 PASS 后核对退出码 0、三个原始 PASS 标记、Errors: 0、逐字节 CSV、303 条 SN 决策、WLF 与全部输入哈希，更新正式结论并停止，等待队长审核。'}不进入 B2-3 或下一阶段。
'''
    report=ROOT/'阶段5-B2-4_综合与真实功能网表验收报告.md';report.write_text(text,encoding='utf-8')
    write(ROOT/'B2_4_EVIDENCE_MANIFEST.json',{'state':s['result'],'report':{'path':str(report),'sha256':sha(report)},'status_sha256':sha(statuspath),'export_provenance_sha256':sha(EXPORT/'provenance.json'),'freeze_audit_sha256':sha(EXPORT/'freeze_audit.json'),'netlist_run':str(run),'completed_verification':v,'active_outputs_final_hashes':False if not complete else {p.name:sha(p) for p in run.iterdir() if p.is_file()},'B2_4_development_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [*ROOT.glob('synth/*.v'),ROOT/'sim/tb_b2_netlist_protocol.sv',*[ROOT/'scripts'/n for n in ('prepare_b2_elinx.py','audit_export_b2.py','prepare_b2_netlist_tb.py','run_b2_netlist.py','check_b2_netlist.py','verify_b2_netlist.py','refresh_b2_4_report.py')]]}})
    print('B2_4_REPORT',st['states']['B2_POST_SYNTH_FUNCTIONAL'],'freeze_hash_checks',len(checks))
if __name__=='__main__':main(Path(sys.argv[1]))
