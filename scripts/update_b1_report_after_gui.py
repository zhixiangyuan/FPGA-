from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / '阶段5-B1_单VL_AFDX发送协议完整开发与验收报告.md'
t = p.read_text(encoding='utf-8')
start = t.index('## 当前结论')
end = t.index('## 实现结构')
t = t[:start] + '''## 当前结论（本轮验收仍在运行）

官方GUI综合、真实功能VO导出、基础网表复验，以及全部B1 RTL和阶段1/2/3-B2/5-B0历史回归已通过。完整网表测试尚未结束，不能将B1总结果记为PASS。

2026-10-10 21:04核对时，`runs/netlist_004`实际完成23帧，其中reset后SN回绕序列完成11帧。进度由每帧关闭写入的`frame_progress.csv`提供；ModelSim进程仍存在。该运行保留真实125 MHz、125000周期BAG和全部断言，未使用force、修改综合网表或降低SN回绕要求。它还需完成完整256帧回绕及末尾FIFO压力/恢复断言。

| 项目 | 状态 | 证据/边界 |
|---|---|---|
| B1协议RTL、真实B0 MAC/GMII、BAG/SN、异常恢复 | PASS | 本轮`acceptance_003`及其引用的实际仿真 |
| 阶段1/2/3-B2/5-B0历史回归 | PASS | 本轮阶段3-B2 `run_014`、B0 `acceptance_005` |
| B1官方GUI综合 | PASS | 实际0 errors、18 warnings，VQM/数据库/Pack及资源报告均归档 |
| 功能VO导出 | PASS | 真实3,827,515字节VO；EP1S80/Stratix兼容模型身份如实记录 |
| 基础真实网表功能测试 | PASS | `netlist_002`、`005`、`006`、`007`均逐字节通过；7帧、1959个GMII字节 |
| 完整真实网表功能测试 | RUNNING | `netlist_004`；完整SN回绕和最后FIFO压力尚未取得最终PASS |
| CSG225诊断顶层I/O适配 | INCOMPATIBLE | 300输入+279输出=579，超过CSG225总焊球数 |
| `POST_SYNTH_TIMING` | NOT VERIFIED | 没有Setup/Hold证据，8 ns解析不等于时序通过 |
| `EQ6_NATIVE_NETLIST_EQUIVALENCE` | NOT VERIFIED | GUI/Pack为EQ6，EDA功能VO为EP1S80/Stratix；待官方确认 |
| Implementation / Bitstream / 下载 | NOT RUN | 本轮未执行 |
| `STAGE5B1_RESULT` | IN_PROGRESS | 完整网表必要测试未结束，不能判定通过 |

机器可读当前状态见 [current_status.json](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/current_status.json)。此文件与本报告是当前进度记录，不是完整网表已经完成的证明。原GUI综合前版本已保存在`evidence/pre_gui_report_001.md`。

''' + t[end:]
for old,new in [('stall_002','stall_003'),('gmii_010','gmii_011'),('clk125_004','clk125_006'),('abort_002','abort_003'),('run_013','run_014'),('rtl_010','rtl_011'),('netlist_008','netlist_009'),('acceptance_004','acceptance_005')]:
    t=t.replace(old,new)
t=t.replace('[acceptance_002 summary](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/acceptance_002/summary.json)', '[acceptance_003 summary](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/acceptance_003/summary.json)')
start=t.index('## eLinx工程与待执行验收')
end=t.index('## 范围外与遗留事项')
t=t[:start]+'''## 官方GUI综合、资源和Warning审计

真实工程为 [AFDXNetwork.epr](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/elinx_001/AFDXNetwork/AFDXNetwork.epr)。综合成功后共116份实际工程、VQM、数据库、Pack、约束和报告文件已按原文件与归档文件哈希一致性保存至 [gui_success_001](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/gui_success_001/artifact_hashes.json)，同时保存队长截图。项目清单中的全部原源码和综合快照哈希仍一致。

| 阶段 | 实际资源 | 含义 |
|---|---|---|
| 前级综合 | 2490 logic cells、1304 registers、49152 memory bits、24 RAM segments、579 I/O | 前级统计，不当作最终物理资源 |
| eLinx Pack综合映射 | 2491 LUT、1304 FF、369 CLB、12 Memory、579 Pins；DSP/PLL=0 | 真实综合映射报告，未经布局布线 |
| 帧存储 | TX bank、RX bank0、RX bank1，各2048×8 | 三份实际生产FIFO/RAM保留 |

sender、BAG、IPv4 checksum、MAC TX/RX、CRC及帧存储均保留；父子层级统计不重复相加。18条Warning分为：case缺default 1条、位宽截断12条、RAM读写穿透3条、常量输出汇总和明细2条。唯一明确列出的常量输出`gmii_tx_er=0`符合生产设计。具体源码范围、RAM验证要求和信息级环路提示见 [综合Warning与封装I/O审计](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/阶段5-B1-N_综合Warning与封装I_O审计.md)。没有据警告擅自修改B0生产RTL，也没有宣称最终静态环路已验证。

实际EPR、cluster XML和Pack Tcl分别确认顶层、EQ6HL45和CSG225。EDC为`create_clock -name gmii_clk -period 8.000 -waveform {0.000 4.000} [get_ports clk]`；Pack解析与clocklist有实际记录。没有编造外部input/output delay，没有取得有效Setup/Hold报告。

579个外部I/O无法直接适配CSG225；当前诊断顶层仅用于综合和可观察的功能验收。后续正式硬件集成应另行批准内部配置、诊断总线、PHY及引脚方案，本轮不改生产接口。

## 真实功能网表导出与ModelSim复验

在独立工程副本调用安装内EDA Writer，只执行功能网表导出：

```text
quartus_eda.exe --read_settings_files=on --write_settings_files=off --simulation=on --functional=on --tool=modelsim --format=verilog AFDXNetwork
```

实际产物 [afdx_network_tx_top.vo](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/eda_export_001/afdx_network_tx_top.vo)，导出日志和命令见同目录`export.log`及`provenance.json`。

```text
bytes = 3827515
SHA-256 = 76de54156426080cf3a9a70ceaa7eb7e4244e55765fd0cc2eaa6882f3b945cb5
```

VO头部与导出日志选择EP1S80F1508C6/Stratix；不能冒充EQ6器件原生功能模型。没有SDF，没有运行Implementation。

ModelSim SE-64 2020.4只编译真实VO、官方未修改的`altera_primitives.v`、`220model.v`、`stratix_atoms.v`及网表TB；不编译B0/B1 RTL作为DUT。每个目录独立编译库并保存输入快照、哈希、命令、transcript、WLF及字节CSV。

| 实际运行 | 结果 | 覆盖或修复 |
|---|---|---|
| `netlist_001` | FAIL | 波形日志命令访问优化掉的TB信号，测试未开始；保留失败 |
| `netlist_002` | PASS | 原语默认行为，P=1/16/17/18/1471、Padding/SN/FCS、IP checksum、真实BAG、取消后恢复、RX暂停、reset；7帧1959字节 |
| `netlist_003` | FAIL | Tcl优化参数引用错误，未进入功能测试；改为显式vopt后重测 |
| `netlist_004` | RUNNING | 全套边界、6个无效描述符、3种异常Payload、256帧SN回绕、迟到计数、双RX bank压力及恢复 |
| `netlist_005` | PASS | 同一VO使用ModelSim官方零延迟功能选项；与002的GMII/RX CSV逐字节及周期完全一致，仅功能对比 |
| `netlist_006` | PASS | 正常原语模式，调整可见性和优化选项；保留真实波形 |
| `netlist_007` | PASS | 去除信号保留的性能诊断；全部基础断言/CSV仍执行，但该运行没有完整信号WLF，不充当波形证据 |

`netlist_004`末尾FIFO压力测试预期：暂停消费时两帧保留、第三帧明确丢弃且计数+1，恢复消费后再次正常收发。尚未运行至最终判定，不能提前记PASS。故意溢出检测通过也不表示通信无损。

完整测试设计的最终断言要求：271个TX Golden帧、22771个GMII字节、273个RX已比较帧、完整256帧SN回绕、迟到计数2及明确丢弃1帧。这些数字是待执行完成的验收期望，当前不能描述为已取得的结果。

附加性能诊断`netlist_probe_001`因Tcl查询命令无效而停止，已保留，不计入功能PASS。零延迟功能模式另外触发官方原语库的vopt赋值调度Warning；没有修改原语库，不作为时序或原生器件等价证据。

## 自动化与亲自复验

新手指南见 [阶段5-B1-N_队长功能网表复验指南](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/阶段5-B1-N_队长功能网表复验指南.md)。

```powershell
Set-Location -LiteralPath 'D:\\FPGA\\captain_integration\\stage5B1_single_vl_20261010'
.\\run_stage5b1.ps1
# 已有GUI综合预检通过后，单独重新跑完整功能网表：
$taskPython = Join-Path $env:USERPROFILE '.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe'
& $taskPython -B .\\scripts\\run_b1_netlist.py .\\runs\\eda_export_001\\afdx_network_tx_top.vo --suite full
& $taskPython -B .\\scripts\\write_current_status.py
```

完整网表SN回绕按125000周期BAG实际运行数千万个时钟周期，当前机器可能需要数小时。进度见`frame_progress.csv`；已有完整运行未结束时不要重复启动另一份。

`run_stage5b1_n.ps1`将历史回归、GUI成功预检、功能导出、完整网表复验和状态汇总串联起来，不会运行Synthesis或Implementation。当前各子步骤已按上述实际记录执行，包装入口仅完成语法检查，不能描述为另一次完整一键运行。任何关键FAIL均阻止总PASS；当前完整网表RUNNING也阻止总PASS。

''' + t[end:]
start=t.index('## 2026-10-10 官方VO教程补充复审')
t=t[:start]+'''## 官方VO教程补充复审及操作边界

2023-06-05官方教程已只读审查，适用性结论见 [官方VO教程适用性与B1接续审查](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/阶段5_官方VO教程适用性与B1接续审查.md)。其中包含Implementation/SDF的分支本轮未执行；本次使用已经实际验证的综合数据库→功能EDA网表导出分支，保留自研MAC路线。

本轮只修复新增Testbench、网表运行脚本、汇总脚本及文档。B0 MAC、原五份冻结RTL、队友源码、正式AFDX_top和历史验收证据均未修改。GUI工程产物归档后不回写，EDA导出使用独立副本。未调用厂商MAC IP，未执行Implementation、Bitstream或下载，未进入5-B2。

## 尚需完成

等待本次完整真实网表运行结束，核对最终PASS标记、计数、SN回绕、FIFO压力与输入哈希后再更新最终报告。基础网表PASS及综合PASS不能代替这项必要验证；当前阶段5-B1仍为IN_PROGRESS。
'''
p.write_text(t, encoding='utf-8')
print('B1_REPORT_UPDATED_CURRENT_PROGRESS_ONLY', p)
