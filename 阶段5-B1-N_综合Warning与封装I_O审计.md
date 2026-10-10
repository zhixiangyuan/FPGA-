# 阶段5-B1-N 综合Warning与封装I/O审计

本次官方GUI综合成功，零Error、18条Warning。原始EPR、QPF/QSF、VQM、数据库、Pack产物、资源报告和截图共116份文件已按哈希归档至 [gui_success_001](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/gui_success_001/artifact_hashes.json)。生产RTL未修改。

## 目标与资源

GUI/EPR、Pack Tcl和cluster XML确认目标EQ6HL45/CSG225，顶层`afdx_network_tx_top`。Pack日志`AFDXNetwork.edi`标识eLinx 3.0.7并确认网表解析、Packer完成和ECP保存。时钟EDC为8 ns；clocklist包含`gmii_clk`及`clk`映射，队长人工日志确认Pack解析8 ns。本轮没有Setup/Hold报告，约束解析不等于125 MHz达标。

| 统计阶段 | 实际结果 | 使用边界 |
|---|---|---|
| 前级Analysis/Synthesis | 300输入、279输出、2490 logic cells、1304 registers、49152 memory bits、24 RAM segments | 前级兼容后端统计，不当作最终器件实现用量 |
| eLinx Pack综合资源报告 | 2491 LUT、1304 FF、369 CLB、12 Memory、579 Pins；DSP/PLL均0 | 综合映射统计；不是布局布线/引脚适配报告 |
| 逻辑帧存储 | TX bank、RX bank0、RX bank1，各2048×8，共49152 bit | 三份生产FIFO/RAM均保留 |
| 保留层级 | sender 1164 cells/625 FF；BAG 261 cells/133 FF；IPv4 checksum 124 cells；MAC 1325 cells/679 FF | 子层级统计包含子模块，不能把父子数字再次相加 |

前级和Pack的2490/2491、24 RAM segments/12 Memory属于不同统计口径，均保存原始报告；不混用成最终物理实现资源。

## 18条Warning分类

完整逐条原文见 [warnings.json](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/gui_success_001/warnings.json)。

| 类型 | 数量 | 具体位置 | 判断与验证需求 |
|---|---:|---|---|
| 10270 case没有default | 1 | `mac_gmii_tx.v:42`，组合输出`case(phase)` | `gmii_txd=0`在case前赋值，缺省路径已有确定输出，没有由此推断锁存器。MAC正常/错误/reset功能由网表测试验证；没有修改B0源码 |
| 10230 32位值截断 | 12 | TX:54、77、78、79、80、84、85、89、91、93；RX:36、80 | 10条TX、2条RX。多数为无尺寸状态常量赋给3位状态；值0～6可表示。TX Padding为受`blength<60`保护的`60-blength`，合法范围可由6位表示；RX长度零常量与成功帧`wire_count-4`在16位范围内。源码边界检查与网表字节/长度断言共同验证，不能仅凭警告文本忽略 |
| 276020 RAM read-during-write pass-through | 3 | TX bank及RX两个bank | 工具为保持原FIFO读写语义添加穿透逻辑，不能视为丢失RAM。检查FWFT、短/最大长帧、暂停、两bank排队、满bank丢弃与恢复；原2048深度FIFO的独立RTL回归保留 |
| 13024 常量输出汇总 | 1 | 输出pins stuck at VCC/GND | 下一条明细仅列`gmii_tx_er` |
| 13410 常量输出明细 | 1 | `gmii_tx_er` stuck at GND | B0生产RTL明确`assign gmii_tx_er=1'b0`，预期常量；没有出现TX数据、SN、BAG或RX整条路径被优化为常量的证据 |

18条中没有Critical Warning。状态机报告保留MAC RX phase和TX ingest，VQM/VO保留B1的SN、发送状态、BAG、checksum以及MAC CRC/RAM结构。寄存器移除清单包含等价合并及固定头字段/长度高位常量；是否影响可观察行为仍由真实VO自动断言验收。

此外，map报告的“Logic Cells Representing Combinational Loops”信息列出17个中间单元，并附注它们可能在后续优化中消失。checksum生产RTL本身是有限加法/折叠DAG；目前基础真实VO已正常推进时间并通过独立校验和Golden检查，没有将该信息直接判为运行失败，也没有据此宣称完成最终静态环路或原生EQ6等价证明。该项保留为后续工具映射/时序审计事项。

Pack日志的`VQM have NOT memory`位于`parse_mem_initial`上下文；它不覆盖map RAM Summary及Pack的12 Memory统计，也不能单独解释成RAM被删除。实际三份2048×8存储和网表收发行为作为主要证据。

## CSG225封装适配结论

当前诊断顶层共有300输入位和279输出位，总计579个外部I/O。CSG225总焊球数仅225，其中还包含电源和地；仅300输入就已超过总焊球数。因此这个诊断顶层无法直接适配CSG225。该结论无需运行Implementation即可成立。

```text
DIAGNOSTIC_TOP_IO_BITS = 579
CSG225_DIAGNOSTIC_TOP_IO_FIT = INCOMPATIBLE
PHYSICAL_PIN_ASSIGNMENT = NOT VERIFIED
HARDWARE_READY = NO
```

这个顶层为综合与功能观测暴露了描述符、IP/MAC配置、Payload、GMII、RX和32位统计计数，不能原样当作实物板卡顶层。后续应在另行批准的正式硬件集成阶段，制定内部配置寄存器/总线、诊断读取接口、真实PHY连接、复位/时钟及引脚分配方案；不是直接修改官方八端口AFDX_top。本轮只记录风险，不修改生产RTL、顶层或器件/封装。

## VO身份与时序边界

本次功能VO使用B0已实测的EDA Writer流程导出，模型顶层为`afdx_network_tx_top`，文件大小3827515字节。实际导出日志和VO头部选择EP1S80F1508C6，包含Stratix原语；GUI/Pack为EQ6HL45/CSG225。二者映射对应关系仍待官方确认。

```text
FUNCTIONAL_VO_EXPORT = PASS
POST_SYNTH_TIMING = NOT VERIFIED
EQ6_NATIVE_NETLIST_EQUIVALENCE = NOT VERIFIED
POST_ROUTE_TIMING = NOT RUN
IMPLEMENTATION = NOT RUN
BITSTREAM = NOT RUN
```

综合成功、网表功能成功、封装适配和Setup/Hold为四个独立结论。诊断I/O不兼容及未验证时序不能被功能PASS覆盖。
