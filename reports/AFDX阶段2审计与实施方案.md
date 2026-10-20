# AFDX 阶段2审计与实施方案

## 基线和授权

开发根目录 `D:\FPGA\captain_integration`，分支 `dev`。基线提交 `fbbfc72d5dcd7abb6ebf5cec480b63c232c02fd9`。原 main、V1.0 标签、13 份冻结核心和历史验收证据保持不变。阶段2可开发模块写入 `rtl/`，工具快照及原始输出写入 `build/`。本文件是执行计划，不能作为功能通过证据。

## 官方依据和接口契约

已实际读取用户提供的 8 页选题指南和问题汇总的 59 个非空行。源文件 SHA-256、逐页文本和带坐标的 FAQ 单元格记录于 `build/audit/stage2/official_sources.json`。附件中的工具获取、软件操作说明作为参考资料处理，不作为新增操作授权。

| 要求 | 实际依据 | 当前结论及后续验证 |
|---|---|---|
| 八端口、方向和位宽 | 指南物理页5–6 | 当前 RTL 一致；补 valid-only 定向测试 |
| GMII 为 MAC/PHY 接口 | FAQ C3、C61 | 复用 B0 自研 MAC；外部 valid 连续高表示线帧 |
| ready 不参与握手 | FAQ C50、C62 | rx_ready 可忽略、tx_ready 固定0符合该项明确答复 |
| 前导码、FCS、帧边界 | FAQ C49未给具体范围 | 使用前导码/SFD/DA..FCS、valid低结束帧；工程约定，不写成官方逐字段规定 |
| 仿真和工具 | FAQ C13、C46、C57、C80–81 | RTL与真实综合功能VO；不需要布局布线或实体硬件 |
| 100 Mbps | 指南物理页5、FAQ C58 | 需要持续负载实测；活跃字节速率不足以证明 |
| 时钟 | FAQ C59 | 当前125 MHz保持；新性能测试明确速率和负载定义 |
| GMII延时≤2 ms | FAQ C60 | 同时记录输入首/末至输出首/末，以及队列/BAG时间 |
| 抖动 | 指南物理页5；C60未量化补充 | 记录定义、分布及最大值；不自行声称统一官方判分口径 |
| 帧长、VLID、SN | 指南物理页5 | 当前单VL上限1471 Payload、1518含FCS；扩展定向测试 |
| ARINC664P7及高完整性 | 指南物理页4 | 单VL工程profile已验收；不等于完整标准合规 |
| 128 TX/4096 RX VL | 指南物理页5使用“典型” | 先16 VL功能、资源和吞吐实测，再容量评估；未测容量不标PASS |
| SNMP、615A、RTC | 指南物理页4；FAQ C12、C47–48 | 当前缺失，需要真实协议RTL和端到端验收 |

八端口没有 GMII RX_ER 引脚；valid-only profile不能表达所有物理错误，当前能表达截断、坏FCS、协议错误。新增模块内部保留错误能力，八端口测试不冒称覆盖外部RX_ER注入。

## 真实工程审计

当前链路为边界适配→B0 MAC→B2合法帧解析/双bank→SN门控→应用双bank→B1重封装→B0 GMII输出。发送SN由本端独立管理。生产源码仅来自 `rtl/` 与 `vendor/frozen/`，没有旧工作区生产源码依赖。

V1.0 RTL 315 场景、13核心和8Golden已有真实PASS；正式路径GUI综合实际PASS：2784 LUT、1069 FF、28 Memory、22 IO、8ns约束。25 Warning分类保留于 `reports/V1.0_migration_synthesis_warnings.json` 和真实 `build/elinx/AFDXV1_001/synthesis_audit.json`。分类包含有界截断、MAC不完整case、RAM读写旁路、未使用寄存器及ready常量/未用输入；ready两项现有官方答疑支持，历史报告不改写。

33组合环报告项仍需检查具体层级及RAM旁路/反馈依赖。综合功能PASS不能推出Setup/Hold通过；不得删除报告项或降低时钟以掩盖风险。`POST_SYNTH_TIMING=NOT VERIFIED`、`EQ6_NATIVE_NETLIST_EQUIVALENCE=NOT VERIFIED`、物理fit仍未验证。

本轮已从正式路径真实综合数据库导出 `build/logs/eda_export_001/AFDX_top.vo`；SHA-256 `b9710b645a1c1ee385d7d60ab187db58f886f60fc6143f65567f45955d9bb39f`。完整真实网表测试 `build/logs/netlist_001` 已于2026-10-14 03:58:24Z结束并通过 `scripts/verify_v1_netlist.py` 独立核验，保持125 MHz、125000周期BAG、256回绕、315Golden，未启动第二次重复验收。

## 实施次序

1. 补齐原正式路径完整VO；期间独立审计和模块开发不改测试输入快照。
2. valid-only边界、性能统计及原315回归持续保留。
3. 新多VL SN状态表、原子缓存及按帧调度；单VLprofile复用。先16VL独立状态、BAG、资源和压力测试，独立Golden覆盖全部回绕。
4. 接收协议发展版本支持VL表、UDP校验及管理服务分流；发送端支持独立VL/BAG/SN、共享MAC。MAC和冻结核心不重写。
5. SNMP采用RFC1157 BER/PDU实际处理；明确实现的MIB和操作子集。依据：[RFC1157](https://www.rfc-editor.org/rfc/rfc1157.html)。
6. 615A参考规范文件和TFTP传输；先完成RFC1350可靠块传输、文件原子提交、卸载及失败恢复，再核对615A控制文件流程。TFTP通过不能代替完整615A通过。依据：[RFC1350](https://www.rfc-editor.org/rfc/rfc1350.html)。
7. RTC采用明确时基及SNTPv4时间戳/同步运算、错误应答检查。依据：[RFC4330](https://www.rfc-editor.org/rfc/rfc4330.html)。
8. 串行集成服务、多VL、独立Golden与完整系统测试；官方eLinx综合、真实VO功能回归、资源和多口径性能验证。
9. dev普通提交/推送，GitHub独立恢复，最终完整验收报告。未经队长批准不合并main、不创建稳定标签。

SN依据仍使用 [AMD XAPP1130](https://docs.amd.com/api/khub/documents/wnNwXuguJhbeWhCBnpF7pQ/content) 的完整性参考及已批准工程profile；SN0控制不交付业务属于本项目约定。冗余需分通道完整性状态和独立消重，不能把普通重复SN过滤冒称双网冗余。

## 资源与性能风险

1471字节/1ms单VL Payload上限11.768 Mbps，需要至少9个满载VL才能在理论上超过100 Mbps，仍需计入MAC、调度、缓存和服务竞争。先16VL以保留余量。共享MAC和按VL状态表优于复制整个单VL端系统；必要缓存使用RAM、预留容量再推进SN。保护每VL1ms BAG，不缩短BAG来制造吞吐PASS。

协议资料的可获取深度、615A控制文件完整性、管理服务可变长BER解析、缓存压力最坏时延、组合环及原生模型是实际风险。每项必须保留未完成状态，继续可独立开发项。禁止Implementation、Bitstream和硬件下载。
