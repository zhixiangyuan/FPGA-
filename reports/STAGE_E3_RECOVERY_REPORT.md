# Stage E3：GitHub 独立恢复与工程验收报告

更新日期：2026-10-14。远端 GitHub 私有仓库：`zhixiangyuan/FPGA-`。本报告记录 Stage E2 合并后的远端恢复、源码哈希、ModelSim RTL 回归与 eLinx 工程恢复检查。

## 1. GitHub 发布与分支恢复

PR [#1](https://github.com/zhixiangyuan/FPGA-/pull/1) 于 2026-10-12 以普通 Merge Commit 合并。实际 Merge Commit 为 `9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`。原 V1.0 稳定标签仍指向 `668094d8d4bcb5e4f2a447274b61a88129c991ec`，另外 5 个 V1.0/B1/B2 标签均保留原名称和目标。

在 Stage E3 同步点，GitHub `main` 与 `dev` 均指向 `9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`。本地候选 `main` 从 `668094d8` 通过 fast-forward 更新；本地候选 `dev` 从 PR head `f2c0af8` fast-forward 到合并提交；随后用普通 push 将同一提交同步至远端 `dev`。没有使用 force push、rebase 或 squash。本报告和 Stage F 预案的后续记录只提交到`dev`，不改变`main`。

## 2. GitHub 独立克隆与哈希

从 GitHub 分别克隆 `main` 和 `dev`，然后执行 `git fetch origin --tags`。两个克隆在同步后均能读取 `main`、`dev` 和 6 个标签；两个分支树相同，合并关系满足 `dev` 是 `main` 祖先。候选仓库和两个克隆的所有可达提交集合一致，共 17 个提交。

候选仓库、main 克隆和 dev 克隆各有 67 个跟踪文件，文件列表及逐文件 SHA-256 完全一致。13 份冻结核心、Golden 清单中的 8 项数据哈希通过。V1.0 原证据清单中的 41 个源码哈希均与冻结提交 `668094d8` 一致。`RESTORE_POINT.json`、原验收报告、冻结清单和原 V1.0 标签未修改。

克隆验证目录：

- main：`C:\Users\袁志祥\AppData\Local\Temp\afdx-stageE3-main-20261012`
- dev：`C:\Users\袁志祥\AppData\Local\Temp\afdx-stageE3-dev-20261012`
- ModelSim 用的 ASCII 路径克隆：`D:\FPGA\AFDX_E3_dev_clone_20261012`

## 3. ModelSim RTL 回归

在 ASCII 路径克隆执行 `python scripts/run_v1.py`，并执行 `python scripts/verify_v1.py build/logs/rtl_001` 独立核验。ModelSim SE-64 2020.4 返回退出码 0，`Errors: 0`、`Warnings: 0`，Golden 结果为 PASS。

| 核验项 | 结果 |
|---|---:|
| Golden 用例 | 315 |
| B1 TX 帧 / 线字节 | 295 / 22,840 |
| 实际应用 bank 提交 / Payload 字节 | 296 / 2,520 |
| SN 决策 / 完整回绕 | 308 / 256 帧 |
| BAG 间隔 | 检查 289 个；最小 125,003 周期，门限 125,000 |
| 压力与恢复 | 保留 6 帧、容量丢弃 1 帧，PSN 未推进；reset 取消和半帧恢复通过 |
| 协议错误 | 协议拒绝 11、SN 拒绝 4、SN=0 控制 1、坏 FCS 拒绝 1 |

原始运行证据保存在 `D:\FPGA\AFDX_E3_dev_clone_20261012\build\logs\rtl_001`，包括 transcript、console、WLF、Golden CSV、summary 和 verification。`waves.wlf` SHA-256 为 `9e1b04eab6db7469596f8b2c53f50e0b7c8ff44750b96d1a5ebb33b36db39aff`；`actual_tx.csv` SHA-256 为 `8e67da741680254e488c023ce05a5324b064da4805a0a311ba642c48efc2f6d0`；`actual_app.csv` SHA-256 为 `1dc58e31e10cd4a1b9c77036b0540cda989e1fff4a848332db2f0a21d6cd27e6`。

第一次从含中文用户名的临时克隆路径运行时，ModelSim 将路径字符替换为问号，报源文件无法打开。该次失败记录保留在 `C:\Users\袁志祥\AppData\Local\Temp\afdx-stageE3-dev-20261012\build\logs\rtl_001`。随后从 ASCII 路径重新克隆并运行，PASS 结果如上；没有修改 RTL、Golden 或断言。

## 4. eLinx 工程恢复

在 main 克隆、dev 克隆和 ASCII 路径克隆分别执行 `python scripts/prepare_v1_elinx.py`，均成功生成工程副本。顶层为 `AFDX_top`，器件/封装为 `EQ6HL45/CSG225`，约束为 8 ns，16 份源文件副本哈希与 canonical 源码一致。

已在 eLinx GUI 打开 ASCII 路径克隆的 `build/elinx/AFDXV1_001/AFDXV1.epr`。GUI 项目标题、Project Summary 和 Sources 树确认工程路径、`AFDX_top`、`EQ6HL45/CSG225`及真实候选协议模块。选中 Run Synthesis 项后界面仍显示`Status: Not started`，综合任务未启动；因此本次没有可核验的克隆综合结果。未启动 Implementation、Bitstream 或下载。随后 UI 自动化报告窗口最小化并检测到新的窗口输入，按安全规则停止继续点击。

**eLinx 克隆工程 GUI 加载：PASS；克隆工程 GUI 综合：NOT RUN。** 既有候选综合结果不作为克隆工程综合结果。

## 5. 保持为未验证的项目

- 克隆工程的 eLinx GUI Run Synthesis：NOT RUN；需在 eLinx 可观察、可操作时从已打开的 ASCII 克隆工程执行一次。
- Stage E3 克隆工程完整综合网表时钟回归：NOT RUN。
- `POST_SYNTH_TIMING`、`EQ6_NATIVE_NETLIST_EQUIVALENCE`、100 Mbps、官方端到端最坏时延/抖动、官方八端口兼容和物理 I/O 适配：NOT VERIFIED。
- Implementation、Bitstream、硬件下载及 AFDX 阶段2功能开发：NOT RUN。

本报告的 ModelSim PASS 仅适用于已运行的 RTL Golden 回归。eLinx 生成器 PASS 不代表 GUI 综合 PASS；0 ns 网表加载记录也不代表新的完整 VO 时钟回归。

## 6. 2026-10-14 后续远程恢复复核

- E3/F文档与校验脚本按普通提交保存在`dev`；切换脚本的PowerShell路径兼容和Golden清单计数问题已修复。远程`main=9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`，远程`dev=eb85750ced844f14a1bda7f26bda666545b738bd`；`main`未改动，原V1.0稳定标签仍解析至`668094d8d4bcb5e4f2a447274b61a88129c991ec`。
- 从最新远端`dev`独立克隆到`D:\FPGA\AFDX_E3_dev_clone_20261013`。克隆为20个可达提交、6个标签、72个跟踪文件，包含本地`main`和`dev`，活动分支为`dev`。候选与独立克隆72个跟踪文件的逐文件SHA-256匹配；`verify_unified_workspace.ps1`在候选和克隆中均输出`UNIFIED_WORKSPACE_CHECK=PASS`，核对13份冻结核心、8项Golden输入、远端分支、原V1.0标签及新路径eLinx配置。
- 此次E3记录和脚本修订没有更改RTL、Testbench、Golden或eLinx模板，因此不重复耗时315场景ModelSim回归。此前ASCII克隆的315场景PASS仍由`rtl_001`原始日志、WLF、CSV和核验文件支持。
- Stage F切换和辅助克隆归档脚本均通过PowerShell语法检查及只读Plan；正式根目录、候选目录、E3验证克隆、原有归档和bundle均未移动或删除。当前D盘剩余38.74 GiB；最新进程检查未发现eLinx、ModelSim或VS Code进程。
