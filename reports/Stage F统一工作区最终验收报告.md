# Stage F 统一工作区最终验收报告

日期：2026-10-14。范围：统一工作区切换、Git/GitHub 配置管理、工程复现和历史归档。结论：本地 Stage F 切换与工程验证 PASS；报告发布后以远端读回记录确认 GitHub 同步。该结论不代表全部全国赛功能及性能要求达标。

## 1. 正式工作区与 Git 基线

正式根目录为 `D:\FPGA\captain_integration`，`git rev-parse --show-toplevel` 返回该目录。活动分支为 `dev`，本地长期分支仅有 `main` 和 `dev`，origin 为 `https://github.com/zhixiangyuan/FPGA-.git`。

| 对象 | 提交或状态 |
|---|---|
| 已批准 main | `9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`，本轮未更新 |
| 切换及功能验证输入 dev | `63b19657d968fd7421b8ab8b700834d6904ae59c` |
| 最终 dev 报告发布提交 | 本报告及归档脚本修复以普通提交发布；实际最终 ID 记录于下述 `publication_verification.json`，并可用 `git rev-parse HEAD` 与远端读回核对 |
| 原 V1.0 冻结提交 | `668094d8d4bcb5e4f2a447274b61a88129c991ec` |
| V1.0 后续准备提交 | `5cf6e2e9d511252663e0fa2cf75f41cee53b3901`，仍可从 dev 到达 |
| GitHub Initial commit | `a631d0dbaf5515b47077f16cbf02292a6b7be176`，仍可从 dev 到达 |

GitHub：[main](https://github.com/zhixiangyuan/FPGA-/tree/main)、[dev](https://github.com/zhixiangyuan/FPGA-/tree/dev)、[原 PR #1](https://github.com/zhixiangyuan/FPGA-/pull/1)。发布核验文件位置：`D:\FPGA\AFDX_archive\stageF_evidence_20261014\publication_verification.json`。报告提交自身的哈希不预写进自身内容，以实际推送及读回结果为准。

6 个历史标签的名称、标签对象和目标保持一致：V1.0 candidate/system-verified 两标签、`stage5b1-approved-2026-10-11`、`stage5b2-b2-1-2-approved-2026-10-11`、`stage5b2-b2-4-approved-2026-10-11`、`archive/stage5b2-head-2026-10-12`。原 V1.0 system-verified 标签仍解析至 `668094d8`。B1/B2 独立历史保留在标签和原 Git bundle 中。本轮未创建新稳定标签。

## 2. 实际工程结构

```text
captain_integration/
  .git/                 唯一长期活动仓库
  rtl/                  顶层、边界适配和应用队列
  vendor/frozen/        13 份冻结 B0/B1/B2 核心
  sim/                  ModelSim Testbench
  golden/               独立 Golden 与 SHA-256
  scripts/              编译、运行、核验及工程生成
  elinx/                EPR/8 ns EDC 模板
  reports/              阶段报告与重要结果
  build/                被 Git 忽略的工具工程、缓存、日志和波形
  AGENTS.md             Codex 后续开发约定
  README.md / GIT_WORKFLOW.md / CHANGELOG.md
```

ModelSim runner 的全部生产输入来自本地 `rtl/`、`vendor/frozen/`。实际运行记录显示旧上游源码路径存在数为 0，仍完整通过验收，证明正式工程不依赖旧阶段目录提供生产源码。eLinx 的16份工具源码副本从上述 canonical 源码生成并逐项验哈希。

## 3. 正式路径实际验证

| 核验项 | 状态 | 证据 |
|---|---|---|
| Git 根、origin、main/dev、上游关系、历史标签 | PASS | `switch_002.log`、`final_verification.json` 与最终发布读回 |
| 13 份冻结核心 / 8 项 Golden 清单 | PASS | `verify_unified_workspace.ps1` 与最终逐项 SHA-256 |
| ModelSim 完整 RTL 回归 | PASS | `build/logs/rtl_001`，退出码0，Errors 0，Warnings 0 |
| 独立 Python Golden 核验 | PASS | `rtl_001/verification.json` |
| eLinx 工程生成、16份源码哈希、Top/器件/约束 | PASS | `build/elinx/AFDXV1_001/project_manifest.json` |
| 官方 GUI Run Synthesis | PASS | 新路径 GUI `Synthesis Complete`、真实综合报告和 `synthesis_audit.json` |
| VS Code Git 识别 | PASS | 用户手动完成工作区信任后，GUI显示 `Git: D:\FPGA\captain_integration` 和 dev分支 |
| 新路径完整 VO 时钟回归 | NOT RUN | 本轮未导出或重复运行完整网表套件；原 V1.0 VO 验收记录保留 |
| Implementation / Bitstream / 硬件下载 / 阶段2开发 | NOT RUN | 本轮授权边界 |

RTL 运行和核验命令为 `python scripts/run_v1.py`、`python scripts/verify_v1.py build/logs/rtl_001`。实际结果：315个Golden用例；295个TX帧、22,840个线字节；296次应用bank提交、2,520个Payload字节；308条PSN决策；256帧SN回绕；289个BAG间隔，最小125,003周期，门限125,000周期。协议拒绝11、SN拒绝4、SN0控制1、坏FCS拒绝1；压力保留6帧、容量丢弃1帧且PSN不推进；reset取消和半帧恢复通过。时钟保持125 MHz/8 ns。

本次WLF SHA-256为 `612d92a054521f9ad8ecf3a0ed60691c24c9fcc9ecf32c20dd2d67f18914c001`；TX CSV为 `8e67da741680254e488c023ce05a5324b064da4805a0a311ba642c48efc2f6d0`；应用CSV为 `1dc58e31e10cd4a1b9c77036b0540cda989e1fff4a848332db2f0a21d6cd27e6`。波形和原始日志离线保存，不提交GitHub。

eLinx GUI实际打开 `D:\FPGA\captain_integration\build\elinx\AFDXV1_001\AFDXV1.epr`，Top=`AFDX_top`，目标=`EQ6HL45/CSG225`，8 ns约束。真实综合：0 Errors、25 Warnings、2784 LUT、1069 FF、404 CLB、28 Memory、22 IO，逻辑RAM为96,224 bit。应用队列、B1发送器、MAC、接收Parser和SN门控均保留，未被优化为空。25条Warning按既有分类逐条审计通过；原始Warning、层级和资源哈希在`synthesis_audit.json`。33项组合环、`tx_ready`常量、`rx_ready`未参与输出仍属于独立风险。22/160仅表示IO数量余量。

## 4. 历史与辅助工程归档

原工作区在切换前及移动后均按17,261文件、2,573,320,124字节清单逐项SHA-256核验通过。3个历史Git bundle、V1.0 ZIP和原Git bundle复核通过；原有完整副本、原始清单及厂商模型未删除或覆盖。

| 内容 | 保留位置 |
|---|---|
| 本次移动的旧工作区 | `D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration_pre_stageF_20261012` |
| 既有完整旧工作区副本 | `D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration` |
| 原历史Git bundle | `D:\FPGA\AFDX_archive\git_bundles_20261012` |
| 迁移候选 | `D:\FPGA\AFDX_archive\workspace_transition_20261013\migration_candidate_20261012`，920文件/107,835,273字节 |
| 保存E3 RTL证据的克隆 | `D:\FPGA\AFDX_archive\workspace_transition_20261013\e3_ascii_clone_20261012`，193文件/4,488,060字节 |
| 最新E3 dev恢复克隆 | `D:\FPGA\AFDX_archive\workspace_transition_20261013\e3_latest_dev_clone_20261013`，240文件/1,569,518字节 |
| Stage F真实日志、WLF、综合数据库和GUI证据 | `D:\FPGA\AFDX_archive\stageF_evidence_20261014` |

辅助工程移动前后逐文件哈希匹配；3个归档仓库通过`git fsck --full`，未发现损坏。已有dangling对象原样保留。修复后的归档核验以`archive_manifest_recovery_20261014.json`为准，首次PARTIAL清单保留。辅助原路径均不存在；归档中的Git仓库仅用于历史恢复，不作为开发入口。

## 5. 本次修复与回滚

首次切换已把旧根移动并克隆新根，但Windows PowerShell 5.1在参数默认值阶段无法读取`$PSScriptRoot`。切换脚本自动把失败克隆保留在`captain_integration_stageF_failed_20261012`并恢复旧根。随后修复路径默认值求值时机、显式传入根目录，以及PowerShell 5.1的JSON数组形状差异；dev普通修复提交为`c0135c0`和`63b1965`。实际Windows PowerShell复测PASS，第二次切换成功。

辅助归档的PowerShell `Move-Item`处理隐藏目录时发生部分移动。先使用原移动前清单校验源与目标的文件合集，无重复文件、无缺失、无哈希变化；随后以同卷原子重命名完成归档并再次逐项验哈希。首个候选目录留下的空目录树也保留于`candidate_empty_residual_20261014`。没有删除任何原文件、Git历史或证据。归档脚本现使用`[IO.Directory]::Move`避免递归部分移动；使用隐藏`.git`目录的受控移动探针实测文件哈希与隐藏属性均保留，结果PASS，见`atomic_move_probe.json`。

故障日志：`switch.log`、`switch_002.log`、`auxiliary_archive.log`、`auxiliary_recovery.log`；恢复脚本和真实操作记录均在Stage F证据目录。正式工程没有修改冻结RTL、Testbench、Golden或eLinx模板。

## 6. 日常使用与恢复

VS Code使用「文件→打开文件夹」选择`D:\FPGA\captain_integration`。用户已手动完成该工作区信任；Source Control实际识别正式仓库。此后PowerShell应在正式根打开：

```powershell
Set-Location D:\FPGA\captain_integration
git status
git branch --show-current
git pull --ff-only origin dev
# 修改、测试并核对实际变更文件后：
git add <已核对的文件>
git commit -m "说明本次已验证的变更"
git push origin dev
```

每个正式阶段：完整回归→验收报告→PR→队长批准→普通Merge Commit发布main→队长批准稳定Tag。未经审批不得把本次报告自动合并main或创建新稳定标签。

查看历史及指定版本：

```powershell
git fetch origin --tags
git log --graph --oneline --decorate --all
git show --stat afdx-v1.0-stage1-system-verified-2026-10-12
```

恢复时先保护所有未提交修改。需要原V1.0源码查看时，使用独立恢复目录或干净工作树的detached tag；不要破坏活动dev。灾难恢复可从GitHub私有仓库克隆到一个不存在的检查目录，再签出dev或原标签；也可从归档bundle克隆恢复。旧目录结构快照由原V1.0标签恢复，统一目录结构由main/dev恢复，不能混淆。完整VO、原语库和数据库需从离线归档恢复，具体路径和哈希见原`OFFLINE_ARCHIVE_CATALOG.json`及本次证据。

目录级回滚只用于故障恢复：先关闭相关工具并保留新工程修改，然后使用已保留旧根和切换脚本的Rollback流程；使用新的失败归档后缀防止覆盖首次失败现场。不得把回滚脚本当作日常版本管理操作。

## 7. 跨磁盘备份与剩余风险

实测D盘与E盘均为物理Disk 0的不同分区。D盘两个副本、或复制到E盘，都不能抵御Disk 0损坏。建议将`AFDX_archive`完整备份到另一块物理磁盘或外置硬盘，尤其保留Git bundles、V1.0 ZIP、VO、WLF、EDA数据库、许可受限原语库、原始报告及SHA清单；复制后重新核对哈希，并保留一份离线副本。本轮只提出建议，未自动跨磁盘复制。GitHub仅恢复已上传源码和配置，不能替代离线大证据备份。

`POST_SYNTH_TIMING=NOT VERIFIED`、`EQ6_NATIVE_NETLIST_EQUIVALENCE=NOT VERIFIED`、物理I/O适配=NOT VERIFIED；原579位诊断IO仍为INCOMPATIBLE，旧诊断地址1仍为UNSUPPORTED。官方八端口语义、100 Mbps、官方最坏端到端时延/抖动及2 ms指标尚未验证。团队单VL GMII工程profile的功能PASS不表示完整ARINC 664 Part 7合规或全国赛全部指标PASS。

正式工作区具备后续开发与配置管理条件；AFDX下一阶段功能仍须队长另行分配和批准。本轮完成后停止，不开始阶段2。
