# FPGA-

基于以太网 MAC 总线实现 AFDX

## 当前稳定版本

V1.0 阶段1候选工程已完成团队单VL工程profile的 RTL、真实功能网表、独立Golden和历史回归验收。真实VO网表测试为315个Golden场景、295个外部TX帧、22840个字节、296次实际应用bank提交和308条PSN决策，125 MHz、125000周期BAG与256帧SN回绕均已验证。

稳定源码点：`afdx-v1.0-stage1-system-verified-2026-10-12`。该标签固定在验收提交 `668094d8d4bcb5e4f2a447274b61a88129c991ec`。完整结果见[正式验收报告](阶段1_V1.0正式系统验收与交付报告.md)。

**范围限制：**八端口目前采用团队批准的GMII线字节约定，未确认官方接口兼容。100 Mbps、官方端到端最坏时延/抖动、Setup/Hold、EQ6原生网表等价性和物理I/O适配均未验证。不得把综合资源或功能VO通过解读成这些项目PASS。

## 目录

- `rtl/`：候选顶层、GMII边界和应用回送队列。
- `vendor/frozen/`：13份冻结B0/B1/B2核心快照；校验信息见`FROZEN_CORE_MANIFEST.json`。
- `sim/`、`scripts/`：Testbench、独立Golden生成器、编译/仿真/核验和历史回归脚本。
- `golden/V1.0_full_vo_315/`：真实VO验收使用的315场景Golden输入、元数据及SHA-256。
- `elinx/AFDXV1/`：可迁移的eLinx工程文件、16个源文件和8 ns时钟约束。
- `README_SYSTEM.md`、`GIT_WORKFLOW.md`：复现说明与后续Git流程。
- `RESTORE_POINT.json`：验收标签、提交和离线交付包哈希。

原始仿真波形、综合数据库、真实VO、厂商器件模型、完整日志及打包交付物保留在独立离线证据目录/归档中，不纳入GitHub源码历史。离线交付包内的Altera模型受其许可约束，不在此仓库再分发。

## 本地RTL复现

需要Python 3.10+、ModelSim 2020.4及有效仿真许可。`MODELSIM_BIN`可指定ModelSim可执行文件目录，`MGLS_LICENSE_FILE`可指定许可位置。

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py runs/rtl_001
```

runner会自动选择新的`rtl_NNN`目录；核验命令中的目录应替换为runner实际打印的路径。Golden由独立Python参考模型生成，测试覆盖真实业务来源、SN门控、协议错误、双缓存压力、FCS、reset和恢复。

## eLinx综合工程

打开`elinx/AFDXV1/AFDXV1.epr`。工程目标为EQ6HL45/CSG225，顶层`AFDX_top`，使用`clock_125mhz.edc`中的125 MHz/8 ns约束。阶段1实际GUI综合资源为2784 LUT、1069 FF、28 Memory、22 IO，0 Errors、25 Warnings。综合通过不代表时序或物理封装适配通过。

Git恢复步骤和`main`/`dev`约定见[Git工作流](GIT_WORKFLOW.md)。
