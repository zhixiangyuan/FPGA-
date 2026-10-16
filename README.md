# FPGA-

基于以太网 MAC 总线实现 AFDX

正式开发工作区：`D:\FPGA\captain_integration`。日常开发使用`dev`；`main`仅接受队长批准的稳定版本。源码、测试、Golden和配置在同一工程持续维护，常规阶段不复制日期命名的完整工程。

## 当前开发状态

阶段2仍在 `dev` 开发。最新同载验证 `mgmt_mixed_010` 在同一有时钟系统仿真中运行 16 个业务 VL、4096 个业务帧、45 个 SNMP/SNTP 服务输出和完整管理向量。4141 个输出帧、6,255,335 字节逐帧匹配独立 Golden；整个业务窗口 Payload 速率为 184.21 Mbps，首字节到末字节的最大延时为 60.448 µs，各业务 VL 的最小 BAG 为 128000 周期。该结果仅覆盖已测负载，不代表任意竞争下的最坏时延。

SNMP 的 BER 字段、community 和 request ID 使用串行同步读取；TLV 边界解析结果已寄存。接收解析器在合法 SN 末字节直接检查提交条件，避免错误分类编码进入关键提交路径；错误原因仍保留。管理族 `mgmt_036` 的 57 用例、接收路径 `multi_vl_rx_005` 的 4404 场景、混合负载及原 V1.0 `rtl_010` 的 315 场景独立 Golden 核验均通过。EQ6 `AFDXS2M_022` 综合为 16325 个逻辑单元、497152 个存储位、200 个 RAM 段、78 条 Warning，后端打包 PASS；后端利用率为 16326 LUT、6533 FF、2067 CLB、126 Memory。相较 `AFDXS2M_021` 减少 14 个逻辑单元，存储资源和 Warning 数不变。EQ6 原生综合时序 Fmax 为 127.372 MHz，8 ns setup 裕量 +0.149 ns、失败端点 0；预布线 hold 裕量仍为 −0.068 ns，32 个失败端点全部位于冻结 MAC 接收写 RAM 路径。未运行布局布线，I/O 延迟未完整约束，不能宣称完整时序签核。`mgmt_vo_010` 已完成综合数据库导出的 Stratix 兼容功能 VO 完整时钟回归：57 用例、47 帧、6484 字节逐字节匹配独立 Golden，8 ns 时钟，0 Errors、0 Warnings；EQ6 原生网表等价性尚未验证。

V1.0 阶段1候选工程已完成团队单VL工程profile的 RTL、真实功能网表、独立Golden和历史回归验收。真实VO网表测试为315个Golden场景、295个外部TX帧、22840个字节、296次实际应用bank提交和308条PSN决策，125 MHz、125000周期BAG与256帧SN回绕均已验证。

稳定源码恢复点：`afdx-v1.0-stage1-system-verified-2026-10-12`。该标签固定在验收提交 `668094d8d4bcb5e4f2a447274b61a88129c991ec`。它表示团队单VL工程profile的功能验收基线，不代表所有全国赛指标已通过。完整结果见[正式验收报告](阶段1_V1.0正式系统验收与交付报告.md)。

**交付缺口：**官方 100 Mbps 吞吐目标在上述有界混合负载中通过；官方抖动统计口径尚未量化，测试中的 50 µs 只是工程检查值。`afdx_stage2_mgmt_top` 仍有测试控制输入，官方八端口生产顶层尚未完成；615A/TFTP 原子装载与失败恢复、保持时序及 I/O 约束、最终独立 Golden 恢复仍待完成。官方 FAQ 允许以综合功能仿真验收，不要求实体硬件下载；综合功能 PASS 不等于 EQ6 放置布线时序签核。

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
