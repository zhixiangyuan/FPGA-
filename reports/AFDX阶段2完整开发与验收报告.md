# AFDX 阶段2完整开发与验收报告

当前状态：**IN PROGRESS**。本文持续记录已执行结果，尚不是阶段2完成声明。开发在统一工作区dev进行，main及原稳定标签未更新。

## 已执行及剩余任务

| 任务 | 当前实际状态 | 证据与限制 |
|---|---|---|
| 官方接口审计 | PASS：八端口及valid-only答疑核对 | 官方FAQ C62；前导码/FCS范围仍为工程契约 |
| 原正式路径V1完整VO | RUNNING | `build/logs/netlist_001`，唯一VO验收进程；未提前标PASS |
| 16VL SN状态表 | 模块PASS | `multi_vl_sn_004`，4293帧独立决策、每VL256回绕 |
| 16VL GMII接收/解析/SN/实际应用 | RTL PASS | `multi_vl_rx_004`，4404场景、4243实际应用帧、160992字节 |
| 16VL共享发送及真实MAC | RTL PASS | `multi_vl_tx_002`，4097帧/6250568线字节；单独发送端Payload188.74 Mbps |
| 16VL真实收发闭环 | RTL PASS：已测profile | `multi_vl_system_005`，4404场景、4243回送帧，实际应用及外部字节独立Golden |
| 持续吞吐及GMII时延 | 实测profile PASS | 下面的负载和统计定义；非所有负载最坏情况证明 |
| 16VL eLinx综合及资源 | GUI综合及审计PASS | `AFDXS2_004`，0Errors/29Warnings；时序等价独立保留 |
| 16VL真实VO导出 | PASS：导出 | `eda_stage2_export_001`，完整VO功能回归NOT RUN |
| SNMP网络管理 | 独立模块PASS，网络集成NOT RUN | `snmp_004`，52个BER/MIB/Trap场景；限定SNMPv1 MIB profile |
| RTC/SNTP | 独立模块PASS，系统集成NOT RUN | `rtc_002`、`sntp_002`；真实1秒超时测试，非完整系统同步误差证明 |
| 615A | NOT RUN | 规范资料及TFTP/DLP实现仍在推进；TFTP不能代替完整615A验收 |
| 多VL压力/接收隔离/冗余 | 部分未完成 | 当前接收Parser仍为共享双bank；需要压力与公平性强化，不能声称4096RX或双网冗余 |
| 原315场景回归 | PASS | `rtl_006/verification.json`，原时钟/BAG/Golden/断言不变 |
| GitHub最终独立恢复 | NOT RUN | 模块进度已正常提交dev，阶段末完整恢复仍待执行 |

## 实测吞吐和延时

`multi_vl_system_005` 的前4096帧构成绩能窗口：16VL、每VL256帧SN回绕、1471字节Payload、125MHz/8ns，外部发送负载的全局注入间隔8000周期。每VL最小BAG保持125000周期，未通过缩短BAG提高吞吐。

外部输出统计窗口262092208ns，包含BAG及空闲时间：Payload183.911336 Mbps，GMII线字节190.787694 Mbps，Ethernet帧189.787496 Mbps。该负载下三种GMII延时：输入首→输出首48240ns，输入末→输出首36040ns，输入首→输出末60440ns，样本极差均0ns。不能推广为任意过载、无限缓存排队或全部竞争场景的最坏情况。全部4404定向场景输入首→输出末最大72584ns。

数据来源：实际 `input_events.csv`、`tx_events.csv`、`actual_echo.mem`、`actual_app.mem`；每帧FCS及Payload由独立Python帧构建器逐字节比较，发送SN按每VL本端发送计数推导，与接收SN分离。

## 综合修复与真实证据

首个GUI工程 `AFDXS2_001` 因应用大RAM无法推断而FAIL，报告保留。002改为时钟读口但仍受复位/控制混合影响，真实综合FAIL。003将RAM读写端口与复位控制分离，综合前端0Errors/29Warnings、449264逻辑RAM bit、136前端RAM段；厂商独立VQM合成工具在MEMORY_COLLECT崩溃，失败日志保留。直接调用错误的Infrastructure工具不能完成打包，未当成PASS。

004重新执行真实GUI Run Synthesis，通过进程只读观测确认官方实际流程：quartus_map→quartus_cdb生成post-synthesis VQM→共享后端可执行文件运行仅 `AFDXS2_pack.tcl` 的run_pack。未点击或执行place/route的Implementation阶段。GUI实际Synthesis Complete，14677LUT、4354FF、1960CLB、112Memory、22IO；应用RAM376576bit，B0 MAC、Parser、16VL SN和独立BAG/发送状态保留。29Warning逐条记录于 `synthesis_audit.json`。

RAM双端口Warning276027不能忽略：RTL两端口使用同一clk，但同址读写行为仍须靠所有权、压力和真实VO测试验证。49个映射组合环报告单元作为新增风险保留，旧V1的33项原报告不改写。22/160仅为I/O数量余量。

真实VO导出SHA-256：`f3b7fd2a9060ecaa02ead623787764752674480956be037232c31edf28e55351`。目标顶层 `afdx_stage2_top`，来自004真实数据库；兼容功能模型为Stratix/EP1S80，不能扩大成EQ6原生网表等价性通过。

## 管理模块范围

SNMPv1根据RFC1157/1213实现真实BER处理、sysDescr.0/sysUpTime.0/sysName.0查询、GETNEXT、私有community下sysName写入、错误Response及coldStart Trap。单varbind能力上限明确，超限返回tooBig；Trap enterprise0.0是未分配工程身份，不冒用第三方企业号。该开发profile不表示完整SNMPv1通用实现或SNMPv3安全能力。

SNTPv4根据RFC4330实现真实48字节请求和应答字段校验，拒绝错误origin、LI/VN/mode/stratum/root-distance、错误来源IP/端口和截断；错误后合法应答恢复，1秒真实125MHz超时及reset通过。UTC Q32.32有理数时基和四时间戳偏移运算独立核验。请求时间戳当前定义为入队时刻，正式同步误差必须计入TX排队及网络延迟，不能凭模块通过宣称系统时间精度达标。

## 回归与保护

13份冻结核心未改，原V1.0标签和main未动。`rtl_005` 原始ModelSim输出PASS，但后续canonical输入哈希核验发现其曾把未使用的新发展模块纳入输入列表，期间该模块变更，核验FAIL；`verification_failure.json`保留。未放宽哈希检查，而是固定V1实际16份生产输入，在006完整重测及独立核验PASS。005不能作为完整验收PASS。

## 继续保持的状态

`POST_SYNTH_TIMING=NOT VERIFIED`；`EQ6_NATIVE_NETLIST_EQUIVALENCE=NOT VERIFIED`；物理I/O fit=NOT VERIFIED；历史579位诊断顶层 `DIAGNOSTIC_IO_FIT=INCOMPATIBLE`；历史诊断地址1 `UNSUPPORTED`。未执行Bitstream或硬件下载，未创建代表阶段2稳定验收的新标签。

剩余工作继续执行：管理协议网络集成、615A真实加卸载及恢复、多VL压力/隔离和资源验证、最终真实VO完整回归、GitHub独立复现及最终技术交付。本报告完成前保持IN PROGRESS。
