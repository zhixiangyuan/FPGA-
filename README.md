# FPGA-

基于以太网 MAC 总线实现 AFDX

正式开发工作区：`D:\FPGA\captain_integration`。日常开发使用`dev`；`main`仅接受队长批准的稳定版本。源码、测试、Golden和配置在同一工程持续维护，常规阶段不复制日期命名的完整工程。

## 当前开发状态

TFTP 与配置型 615A-2（A3、UDP 59）端点已完成模块验证。当前支持一个 665-2 LSAP、一个 0～4096 字节偶数长度的 `config.bin`，包括 LUI/LUR/LUS 上传、LND/LNR/LNS 媒体定义下载、独立状态会话、WAIT/ABORT、有限重试以及双 bank 原子提交。`a615a_008` 的 30 个 RTL/独立 Golden 用例、684 个输出包通过；坏数据 CRC、坏总 Load CRC、头部错误、中止及复位不会错误提交。`AFDX615_002` EQ6 综合及打包 PASS：7678 LUT、2602 FF、968 CLB、24 Memory；原生 Fmax 152.114 MHz、8 ns setup +1426 ps，预布线 hold −68 ps、32 个端点。该数据库导出的真实兼容功能 VO 在 `a615a_vo_001` 完成 7 个模块场景、85 包的完整时钟与独立 Golden 核验，无 RTL DUT 或 force。原生 EQ6 网表等价性、完整保持时序及 I/O 时序仍未签核。

底层 `tftp_013` 的 19 组定向用例、64 包、1898 字节通过；`atomic_store_002` 的 10 组原子 RAM 用例通过。原始文件端点 `tftp_endpoint_vo_002` 是上一检查点的真实 RAM 功能 VO 证据，不替代当前 615A 或正式八端口集成验收。正式 GMII 集成已完成 RTL 回归，固定候选功能 VO 尚未完成。该配置不包含通用多文件/支持文件、FIND/INFORMATION、操作员定义下载或非易失存储，也尚未与外部装载器互操作。

正式入口已接入 `afdx_stage3_mgmt_top`，使用第三管理 VL 0x1246。新增 516 字节同步 RAM 报文队列，并修复装载包提前占用共享发送器等待 BAG、造成业务拥塞的问题；BAG 到期后才参与仲裁，帧构建器继续独立校验 BAG。`submission_615a_010` 的 9 个上传/下载/失败恢复场景、640 个输出帧、795541 字节通过独立 Golden，期间 512 个 1471 字节业务帧无丢失，业务 Payload 速率 163.496 Mbps、最大输入首字节至输出末字节延时 60456 ns。双方所有 VL 均检查至少 125000 周期 BAG；对端帧间隔为 2048 周期，本结果不代表任意短帧突发无损，原两 bank MAC 容量边界仍保留。

当前核心 `mgmt_load_002` 的 57 用例、47 帧、6484 字节通过；`mgmt_load_mixed_003` 使用与原基线相同的 interval=4000、service interval=160000，4141 帧、6255335 字节通过，业务速率 184.2148 Mbps、最大延时 60448 ns 与原基线一致。V1.0 `rtl_011` 的 315 场景及原源码/Golden 哈希通过。`AFDXSUB_003` EQ6 后端打包 PASS：24261 LUT、9256 FF、3059 CLB、152 Memory、22 位 I/O，0 Errors、104 Warnings；比接入前增加 7890 LUT、2691 FF、26 Memory。并发修复本身比 `_002` 增加 30 LUT、35 FF，RAM 不变。当前 Fmax 119.861 MHz，满足 100 MHz，但 8 ns setup 为 −343 ps、1 个失败端点，正在定位状态 ROM 寻址路径；hold 为 −68 ps、64 个端点，包含 MAC 接收和装载 RAM 路径。当前候选不能标记为 125 MHz 或最终 VO 验收通过。

接入 615A 前的八端口基线：`rtl/submission/AFDX_top.v`。内部使用真实 sysUpTime，复位后自动发起 SNTP，默认每 16 秒轮询，无外部测试控制输入。`submission_002` 定向 RTL 验证通过：9 帧、956 字节匹配独立 Golden，覆盖自动同步、业务回送、SET/GET、真实 10 ms 计时、重复 SN、错误 community 和复位恢复。`AFDXSUB_001` EQ6 综合及后端打包 PASS：16370 LE、16371 LUT、6565 FF、2075 CLB、126 Memory、22 位 I/O、0 Errors、80 Warnings；相较管理测试顶层增加 45 LUT、32 FF，RAM 不变。两条新增 Warning 是轮询定时器的 32 位正整数常量赋给 31 位计数器，默认常量均在范围内。原生 Fmax 127.372 MHz、8 ns setup +149 ps，原有 32 个 hold 端点仍为 −68 ps，I/O 延迟未完整约束。新入口的完整 VO 留至 615A 集成后的固定候选集中验收。历史 V1.0 的 `rtl/AFDX_top.v` 使用独立源码清单，两份同名模块不能同时编译。

阶段2仍在 `dev` 开发。最新同载验证 `mgmt_mixed_010` 在同一有时钟系统仿真中运行 16 个业务 VL、4096 个业务帧、45 个 SNMP/SNTP 服务输出和完整管理向量。4141 个输出帧、6,255,335 字节逐帧匹配独立 Golden；整个业务窗口 Payload 速率为 184.21 Mbps，首字节到末字节的最大延时为 60.448 µs，各业务 VL 的最小 BAG 为 128000 周期。该结果仅覆盖已测负载，不代表任意竞争下的最坏时延。

SNMP 的 BER 字段、community 和 request ID 使用串行同步读取；TLV 边界解析结果已寄存。接收解析器在合法 SN 末字节直接检查提交条件，避免错误分类编码进入关键提交路径；错误原因仍保留。管理族 `mgmt_036` 的 57 用例、接收路径 `multi_vl_rx_005` 的 4404 场景、混合负载及原 V1.0 `rtl_010` 的 315 场景独立 Golden 核验均通过。EQ6 `AFDXS2M_022` 综合为 16325 个逻辑单元、497152 个存储位、200 个 RAM 段、78 条 Warning，后端打包 PASS；后端利用率为 16326 LUT、6533 FF、2067 CLB、126 Memory。相较 `AFDXS2M_021` 减少 14 个逻辑单元，存储资源和 Warning 数不变。EQ6 原生综合时序 Fmax 为 127.372 MHz，8 ns setup 裕量 +0.149 ns、失败端点 0；预布线 hold 裕量仍为 −0.068 ns，32 个失败端点全部位于冻结 MAC 接收写 RAM 路径。未运行布局布线，I/O 延迟未完整约束，不能宣称完整时序签核。`mgmt_vo_010` 已完成综合数据库导出的 Stratix 兼容功能 VO 完整时钟回归：57 用例、47 帧、6484 字节逐字节匹配独立 Golden，8 ns 时钟，0 Errors、0 Warnings；EQ6 原生网表等价性尚未验证。

V1.0 阶段1候选工程已完成团队单VL工程profile的 RTL、真实功能网表、独立Golden和历史回归验收。真实VO网表测试为315个Golden场景、295个外部TX帧、22840个字节、296次实际应用bank提交和308条PSN决策，125 MHz、125000周期BAG与256帧SN回绕均已验证。

稳定源码恢复点：`afdx-v1.0-stage1-system-verified-2026-10-12`。该标签固定在验收提交 `668094d8d4bcb5e4f2a447274b61a88129c991ec`。它表示团队单VL工程profile的功能验收基线，不代表所有全国赛指标已通过。完整结果见[正式验收报告](阶段1_V1.0正式系统验收与交付报告.md)。

**交付缺口：**官方 100 Mbps 吞吐目标在上述有界混合负载中通过；官方抖动统计口径尚未量化，测试中的 50 µs 只是工程检查值。正式八端口生产入口已通过定向 RTL 与综合，完整候选 VO 待最终集中验收；当前配置型 615A 的原子装卸载与失败恢复已通过 RTL；8 ns 建立时序、保持时序、I/O 约束、固定候选 VO 与外部装载器互操作仍待完成。官方 FAQ 允许以综合功能仿真验收，不要求实体硬件下载；综合功能 PASS 不等于 EQ6 放置布线时序签核。

## GitHub 发布状态

Stage E2 Pull Request [#1](https://github.com/zhixiangyuan/FPGA-/pull/1) 已于2026-10-12通过普通 Merge Commit 合并。统一工程提交为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；远端`main`与`dev`在E3同步点均指向该提交。远程独立克隆、17个可达提交、6个历史标签、67个跟踪文件及逐文件哈希核验通过。原V1.0稳定标签仍指向冻结提交`668094d8d4bcb5e4f2a447274b61a88129c991ec`。随后E3/F准备报告和校验脚本只更新`dev`，`main`保持上述审核提交。

Stage F已按队长批准完成正式路径切换、315场景ModelSim RTL/Golden回归、实际eLinx GUI综合和VS Code Git识别。旧工作区、候选仓库和E3克隆已离线归档并验哈希；结果见[Stage F最终验收报告](reports/Stage%20F统一工作区最终验收报告.md)。本轮未更新main或创建新稳定标签。新路径完整VO时钟回归为NOT RUN；POST_SYNTH_TIMING、EQ6原生网表等价、官方八端口兼容、100 Mbps、最坏时延/抖动与物理I/O适配仍未验证。

## 目录

- `rtl/`：候选顶层、GMII边界和应用回送队列。
- `vendor/frozen/`：13份冻结B0/B1/B2核心快照；校验信息见`FROZEN_CORE_MANIFEST.json`。
- `sim/`、`scripts/`：Testbench、独立Golden生成器、编译/仿真/核验和历史回归脚本。
- `golden/V1.0_full_vo_315/`：真实VO验收使用的315场景Golden输入、元数据及SHA-256。
- `elinx/AFDXV1/`：eLinx EPR/EDC模板。RTL唯一canonical副本位于`rtl/`和`vendor/frozen/`；运行准备脚本后，在被忽略的`build/elinx/`中生成可打开工程和逐项哈希清单。
- `build/logs/`：ModelSim、Golden、真实VO导出等临时构建证据；默认由Git忽略。完整历史日志及波形离线归档。
- `README_SYSTEM.md`、`GIT_WORKFLOW.md`：复现说明与后续Git流程。
- `RESTORE_POINT.json`、`OFFLINE_ARCHIVE_CATALOG.json`：验收标签、提交、离线交付包以及整套旧工作区和Git bundle恢复位置与哈希。

原始仿真波形、综合数据库、真实VO、厂商器件模型、完整日志及打包交付物保留在独立离线证据目录/归档中，不纳入GitHub源码历史。离线交付包内的Altera模型受其许可约束，不在此仓库再分发。

## 本地RTL复现

需要Python 3.10+、ModelSim 2020.4及有效仿真许可。`MODELSIM_BIN`可指定ModelSim可执行文件目录，`MGLS_LICENSE_FILE`可指定许可位置。

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py build/logs/rtl_001
```

runner会自动选择新的`build/logs/rtl_NNN`目录；核验命令中的目录应替换为runner实际打印的路径。Golden由独立Python参考模型生成，测试覆盖真实业务来源、SN门控、协议错误、双缓存压力、FCS、reset和恢复。`AFDX_BUILD_ROOT`可指定其他本地生成目录。

## eLinx综合工程

先运行`python scripts/prepare_v1_elinx.py`，它会从`rtl/`和`vendor/frozen/`的canonical源码生成`build/elinx/AFDXV1_NNN/AFDXV1.epr`，并逐文件核对哈希。打开生成的工程。目标为EQ6HL45/CSG225，顶层`AFDX_top`，使用`clock_125mhz.edc`中的125 MHz/8 ns约束。阶段1原GUI综合资源为2784 LUT、1069 FF、28 Memory、22 IO，0 Errors、25 Warnings。综合通过不代表时序或物理封装适配通过。

真实VO及原厂器件模型不在Git源码树中。将V1.0离线交付包解压到本地归档后，设置`AFDX_V1_EVIDENCE_ROOT`指向其`evidence`目录，再按`README_SYSTEM.md`运行真实VO复验脚本。厂商模型仅用于本机已许可的仿真环境。

Git恢复步骤和`main`/`dev`约定见[Git工作流](GIT_WORKFLOW.md)。
