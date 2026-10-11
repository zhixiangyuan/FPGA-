# 阶段5-B2 AFDX接收协议开发与闭环验收报告

报告日期：2026-10-11（Asia/Shanghai）。范围：已批准的B2-1/B2-2首版单VL工程profile。正式AFDX_top集成、B2综合/网表和物理实现不在本次范围。

**B2-1和B2-2在已批准的单VL工程profile范围内通过。阶段5-B2完整系统集成与综合尚未完成。** 2026-10-11队长已明确批准SN规则；最终应用输出位于生产SN门控之后，原`payload_sn_unchecked`只作为Parser与SN模块之间的内部元数据，不作为最终交付证据。此前候选阶段报告保存在`evidence/pre_sn_report_001.md`，原始失败和通过运行目录均保留。

## 1. 本次状态与验收范围

| 项目 | 状态 | 证据 |
|---|---|---|
| Ethernet/VLID、IPv4/UDP、Padding、长度解析 | PASS | 原Parser保持复用；`unit_002`、`pressure_001`和最新完整闭环 |
| 已批准SN生产门控 | PASS | `afdx_single_vl_sn_gate.v`，首次普通帧、+1/+2、回绕、异常更新PSN、零SN控制 |
| 完整256帧真实SN回绕 | PASS | `full_003`由冻结B1真实发送1..255、1；125 MHz、8 ns、125000周期BAG |
| 重复、旧号、异常跳号及后续恢复 | PASS | 4个SN拒绝均更新PSN，后续合法帧恢复；另验证254→1的+2回绕 |
| SN=0控制及协议/MAC错误不更新PSN | PASS | 零SN置PSN=0、无普通Payload；10个协议错误和1个坏FCS不更新PSN |
| 原子应用交付、容量压力、reset取消与恢复 | PASS | 预留Parser bank；B2保留2帧、B0保留2帧，第5帧明确丢弃；未检查容量丢帧不推进PSN；已接受但未交付的reset取消单列 |
| 真正的B1发送→GMII→B0接收→B2 Parser→SN门控→应用 | PASS | `full_003`、独立CSV和SN决策复核 |
| 阶段1/2/3-B2/5-B0/5-B1必要历史回归 | PASS | 本轮`history_002`：B1 `acceptance_005`、B0 `acceptance_007`、3-B2 `run_016`（含阶段1/2）全部通过 |
| `B2_1_FUNCTIONAL_RESULT` | PASS | 协议解析、缓存、错误处理和reset |
| `B2_2_PROTOCOL_LOOP_RESULT` | PASS | 冻结B1→B0真实GMII→B2 SN门控→应用交付 |
| `STAGE5B2_RESULT` | IN_PROGRESS_B2_3_B2_4 | B2-1/B2-2已审核通过；完整集成与综合待做 |
| B2-3正式AFDX_top集成 | NOT RUN | 八端口字节层次与帧边界仍待官方答复 |
| B2-4综合与综合网表 | NOT RUN | 本轮未执行 |
| `POST_SYNTH_TIMING` | NOT VERIFIED | 没有新增有效Setup/Hold证据 |
| `EQ6_NATIVE_NETLIST_EQUIVALENCE` | NOT VERIFIED | 未取得EQ6原生等价证据 |
| `DIAGNOSTIC_IO_FIT` | INCOMPATIBLE | 原579个诊断I/O无法适配CSG225的结论保留 |

Implementation、Bitstream和硬件下载均未执行。B0/B1生产RTL、队友原源码与冻结AFDX_top接口均未修改。本结果不扩展到多VL、冗余、SNMP、615A、RTC或完整ARINC 664 Part 7合规。

## 2. 生产实现与原子提交

原[候选Parser](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/rtl/afdx_single_vl_rx_candidate.v)完整保留。它从冻结B0 MAC客户帧接口接收DA..SN，校验Ethernet/VLID、固定IPv4/UDP profile、反码头校验和、长度、Padding和EOP，并将完整合法Payload存入两个1471字节bank之一。协议失败帧不进入SN门控。

新增[单VL SN门控](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/rtl/afdx_single_vl_sn_gate.v)与[完整协议顶层](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/rtl/afdx_protocol_rx_top.v)。门控在Parser完整候选可见时进行一次SN决策，PASS由应用ready控制原bank的消费，拒绝/控制事件由内部DRAIN释放bank。PSN推进时Payload已经保留在预留bank中；应用暂停不需要临时或额外未验证缓存，不存在“SN已接受但Payload无处保存”的路径。

完整性PSN、Parser bank占用、SN接受计数、SN拒绝计数、零SN控制计数、+2缺号计数和应用实际交付计数相互独立。应用计数只在最后一字节真实握手时递增。reset清除PSN有效位和在途缓存，进入新统计epoch；已接受但未完成交付的Payload按reset取消处理，不记为交付。

冻结规则见[SN规则与状态转换表](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/阶段5-B2_SN规则冻结与状态转换表.md)。`next(255)=1`、`next(0)=1`；首次完整普通帧1..255建立基线，+1/+2放行，+2缺号计数加1，其他普通SN拒绝但更新PSN，SN=0仅作控制事件。协议失败、MAC未交付以及未到SN检查点的容量丢帧不更新PSN。这是队长批准的工程profile；B1发送器仍保持不发SN=0。

## 3. 真实测试与独立Golden

最终运行为[full_003](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/summary.json)。DUT直接编译冻结B1发送器与B0自研MAC、原字节FIFO、新B2 Parser/SN门控/独立顶层；没有mock MAC、force SN、缩短BAG或RTL替换实际模块。仿真时钟8 ns，B1配置`CLK_HZ=125000000`、BAG=125000周期。所有263个真实B1帧的GMII起点间隔由TB断言，含256帧回绕组；仿真时间261077304 ns。

[独立Golden生成器](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/scripts/generate_b2_full_golden.py)以Python整数状态模型实现获批SN转移，独立反码和与zlib CRC生成实际线上字节。309个Golden帧覆盖：P=1/16/17/18/1471/64/33、首帧任意普通SN、256帧1..255→1、+2与跨回绕+2、重复、旧号、异常跳号、错误后合法恢复、SN=0后+1/+2、协议错误SN与坏FCS SN不影响基线、容量丢帧和reset恢复。协议字段错误帧全部按修改后内容重算FCS；专门的坏FCS用例独立隔离MAC层错误。

原始[transcript](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/transcript.log)有两个最终标记：

```text
B2_SN_CAPACITY_RESET = PASS retained=4 mac_drop=1 psn_not_advanced_on_unchecked_drop=1 reset_cancel=1
B2_FULL_SN_PROTOCOL = PASS sn_wrap=256 real_b1_tx=263 tx_bytes=20454 app_frames=291 app_bytes=2431 clk_hz=125000000 bag_cycles=125000
Errors: 0, Warnings: 0
```

退出码0。263个真实B1发送帧、20454个GMII字节逐字节对照Golden；最终291个应用帧、2431个Payload字节及全部元数据均由SN门控后输出比较。这些累计数量跨多个reset epoch，不能直接与某一个硬件计数末态相等。303条普通场景SN决策逐条对照PSN、有效位、接受/拒绝/控制/缺号和交付计数；容量压力阶段另以明确守恒断言核对。

[文件级独立复核](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/verification.json)从原始CSV重做逐字节比较、逐条SN决定比较、FCS检查、真实源码/快照/Golden哈希与原始PASS检查，结果PASS。实测4个SN拒绝、1个零SN控制、10个协议拒绝、1个故意坏FCS、1个容量丢帧和1个reset取消；均没有错误Payload泄漏到应用端。

证据包括[GMII CSV](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/actual_tx_gmii.csv)、[最终应用Payload CSV](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/actual_payload.csv)、[SN决策CSV](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/sn_decisions.csv)、[WLF](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/full_003/waves.wlf)、Golden及源码快照。WLF SHA-256为`2a161a6b4b8eac88e78ea073605f34a13865d2c7b3dbb172d5dfb4a0be821e7a`。

## 4. 容量压力与异常恢复的实际结果

应用ready=0时，首帧SN=10在门控作出接受决定，Payload仍保留；第二帧SN=11已存入Parser另一bank但尚未经过SN检查。B0另缓存SN=12、13，第5帧SN=14因B0无空间明确丢弃。此时断言PSN仍为10、SN接受数为1、应用交付数为0，证明未检查的帧和容量丢帧均未提前推进状态。

恢复ready后，10..13依次通过SN门控并真正交付，PSN为13、接受数=交付数=4。随后SN=15按+2接受并记录单帧缺号。SN=16接受后再次暂停应用，验证Payload依然占有bank、接受数6/交付数5；reset取消它，清空PSN/计数/缓存，下一完整合法SN=200重新建立基线并交付。应用暂停期间逐拍断言数据、长度、VLID、SN及SOP/EOP保持稳定。

重复、旧号和异常跳号的拒绝帧仍更新PSN；紧随其后的合法+1帧通过，证明不会永久失步。所有10个协议失败帧以及坏FCS帧均不更新PSN，紧随恢复帧按之前的正确PSN判断。零SN控制事件置PSN0、内部释放Payload、不向应用交付普通业务。

## 5. 失败记录、回归与源码保护

`full_001`因新增SN模块的Verilog数字字面量紧贴三目运算符而编译失败；原始日志保留。修复语法后`full_002`完整通过；补充跨回绕+2、背压稳定断言与Golden epoch信息后`full_003`通过。没有降低期望、删除错误检查或修改冻结B0/B1。旧`unit_001`、`loop_002/003`等候选阶段失败记录仍保留，旧报告已归档。

本轮[history_002](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/runs/history_002/summary.json)使用既有历史入口实际运行阶段1/2/3-B2/5-B0/5-B1回归，退出码0；[B1 acceptance_005](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/acceptance_005/summary.json)、[B0 acceptance_007](D:/FPGA/captain_integration/stage5B0_selfmac_20261010/runs/acceptance_007/summary.json)、[3-B2 run_016](D:/FPGA/captain_integration/stage3B2_20261008/runs/run_016/summary.json)全部通过。历史脚本更新的汇总快照已恢复，原运行目录保留。B1冻结清单复算不匹配数为0，Git冻结工作区无修改。没有重新运行B1耗时完整网表SN套件，也没有执行B2综合或网表测试。

完整源文件、报告与证据SHA-256由[B2证据清单](D:/FPGA/captain_integration/stage5B2_rx_arch_20261011/B2_EVIDENCE_MANIFEST.json)保存；源码来源与运行副本哈希同时列于`full_003/summary.json`。复验入口为`scripts/run_b2_full.py`，随后执行`verify_b2_full.py <运行目录>`；它们仅运行RTL ModelSim仿真和证据核验。

## 6. 剩余风险与停止点

本次证明已批准的单VL收发工程profile在RTL/真实MAC/GMII路径上的功能与错误恢复。正式八端口AFDX_top业务可达性和边界、100 Mbps吞吐统计、2 ms官方时延口径、Setup/Hold、EQ6原生模型等价、579个诊断I/O与CSG225集成，以及B2综合后行为均未因此获得PASS。

队长已审核通过B2-1/B2-2。本报告用于冻结功能范围与证据；下一阶段B2-4在本轮只完成审计计划，综合尚未启动。正式八端口集成及接口扩展仍未进行；Implementation、Bitstream和硬件下载不在授权内。
