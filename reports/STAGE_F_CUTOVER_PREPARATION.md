# Stage F：统一工作区切换准备与回滚预案

更新日期：2026-10-14。状态：**准备工作完成；没有移动、重命名或删除任何旧工作区。正式切换等待队长批准。**

## 1. 当前工作区与历史目录

最终目标 `D:\FPGA\captain_integration` 当前不是 Git 根目录；目录下有 16 个阶段工程目录和 3 个嵌套 Git 仓库。3 个仓库（`school_v1_20261011`、`stage5B1_single_vl_20261010`、`stage5B2_rx_arch_20261011`）当前均干净。没有顶层 `.git`。

独立候选 Git 根目录为 `D:\FPGA\captain_integration_migration_candidate_20261012`。Stage E3同步点的本地`main`和`dev`均为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；两个分支均跟踪相应`origin`分支。后续E3/F报告与校验脚本保存在`dev`，`main`保持经批准的统一工程提交。

## 2. 归档、Git bundle 和磁盘空间

`D:\FPGA\AFDX_archive\workspaces_20261012\workspace_manifest.json` 列出 17,261 个文件、2,573,320,124 字节。2026-10-13对原工作区与归档副本逐文件重新计算 SHA-256，缺失、变化和多余文件均为 0；两边均与清单精确匹配。

3 个 Git bundle 均通过 SHA-256、大小和 `git bundle verify`：

| Bundle | 字节数 | SHA-256 | 验证 |
|---|---:|---|---|
| school_v1_20261011 | 113,075 | `04ca3dfee019e6cc913916f2467755a88a65dbef516d7e72bda43319685240f3` | PASS |
| stage5B1_single_vl_20261010 | 92,330 | `a1076f3cc98c9f7041a3ced1da3f33eafa396ac68c3eefe79037aa681a8c65c5` | PASS |
| stage5B2_rx_arch_20261011 | 106,206 | `e68883bd24ff46bca718754a2ed2803bcc0526394e0c9dcb51a8d75795562e60` | PASS |

本次重新核验3个 B0/B1/B2 Git bundle：大小与 SHA-256 和离线清单一致，且`git bundle verify`全部通过。V1.0 离线 ZIP 为 57,173,744 字节，SHA-256 为 `1015dc36af7c1bffc539a262b7e3ae9c4802fe67c201f7d9cb18242e560b0700`；V1.0 Git bundle 为 81,841 字节，SHA-256 为 `bfe4b27ca4305cf1029937c383252390555af1a7bbd6ee43ad24ac8982e4b679`，本次复核均通过。Stage C/D 证据归档412个内容文件，manifest SHA-256为`8b84bf1305bbbc7d0bc25259b7eba19e7a6fe2b6e7c76d320ac6971e6dc97326`；逐项SHA-256重核通过。

D 盘总容量约 150 GiB，2026-10-13复核剩余38.74 GiB。切换采用同卷目录移动，归档已在同卷，因此不需要额外复制2.57 GB旧工作区；克隆和构建有空间余量。获批执行前仍须重新读取实时剩余空间。

## 3. 工具路径与打开窗口

- ModelSim 未运行。Stage E3 在 `D:\FPGA\AFDX_E3_dev_clone_20261012` 的 ASCII 路径完成 315 场景 RTL Golden 回归，退出码 0、`Errors: 0`、`Warnings: 0`。
- GUI核验时 eLinx 项目标题确认路径为 ASCII 独立克隆 `D:\FPGA\AFDX_E3_dev_clone_20261012\build\elinx\AFDXV1_001\AFDXV1.epr`，项目 Summary 确认`AFDX_top`与`EQ6HL45/CSG225`。选中综合入口后状态仍为`Not started`，综合未启动；随后窗口自动化检测到最小化/新输入并停止。2026-10-14最新进程检查未发现 eLinx、ModelSim 或 VS Code 进程，也未发现命令行引用待切换根目录/克隆路径的应用进程。详见[Stage E3报告](STAGE_E3_RECOVERY_REPORT.md)。
- Git可执行文件已配置为`E:\git\Git\cmd\git.exe`。切换执行前仍须重新检查 VS Code 是否打开旧根或候选目录。
- eLinx EPR 使用项目内相对源路径；`prepare_v1_elinx.py` 以自身脚本位置确定工程根目录。`run_v1.py` 从仓库根目录读取 RTL，并支持 `MODELSIM_BIN` 指定本机 ModelSim。`run_history.ps1` 是一次性历史脚本，仍含 `D:\FPGA\captain_integration` 绝对路径；该路径将成为最终根目录，不作为常规开发入口。

## 4. 获批后的切换步骤

切换只在队长批准后执行。执行前重新确认原工作区与归档哈希、GitHub refs、远端权限、D 盘空间和应用占用；确认以下两个归档目标不存在：

- `D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration_pre_stageF_20261012`
- `D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration_stageF_failed_20261012`

获批后，先将旧 `D:\FPGA\captain_integration` 原样移动到第一个归档路径，再从 GitHub 克隆到 `D:\FPGA\captain_integration`。克隆默认签出 `main`，然后创建本地跟踪分支 `dev` 并切到 `dev`。原有归档副本和全部 Git bundle 保留，不覆盖、不删除。

更新后的`scripts/stagef_workspace_switch.ps1`在显式`-Execute`后执行切换、创建跟踪分支、运行`scripts/verify_unified_workspace.ps1`、运行 ModelSim RTL Golden 及独立核验。验证失败时尝试把失败克隆移入独立失败目录并恢复旧根；若文件占用阻止回滚，会保留旧根于备份位置并明确报错，不删除数据。切换后仍需在 eLinx GUI 打开生成的 EPR，并在 VS Code 打开最终根目录，在集成终端验证`git rev-parse --show-toplevel`与`git status`。不得把 GUI 综合或完整 VO 时钟回归当作脚本已完成的验证。

## 5. 回滚预案

回滚脚本为 `scripts/stagef_workspace_switch.ps1`。默认 `-Action Plan` 只显示路径，不改动文件。实际切换与回滚均要求显式 `-Execute`，且在获批后运行。

如果克隆或切换后验证失败，脚本将新工作区移动到 `D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration_stageF_failed_20261012`，再把旧工作区从 `captain_integration_pre_stageF_20261012` 移回 `D:\FPGA\captain_integration`。失败工作区保留供分析，不删除任何内容。

以下操作本轮均未执行：旧根目录移动/重命名、候选目录移动/删除、Git 历史改写、Implementation、Bitstream、硬件下载及 AFDX 阶段2开发。请队长审核本预案后，再批准正式目录切换。

## 6. 唯一长期活动工作区与辅助克隆归档

当前除旧根和候选根外，还存在两个 E3 验证克隆：`D:\FPGA\AFDX_E3_dev_clone_20261012`保存ModelSim回归证据，`D:\FPGA\AFDX_E3_dev_clone_20261013`用于最新远程dev恢复核验。为在正式切换后实现单一长期开发入口，建议在新根通过Git、ModelSim和eLinx验收后，将迁移候选和两个E3克隆原样移动到新的离线归档子目录：

- `D:\FPGA\captain_integration_migration_candidate_20261012` → `D:\FPGA\AFDX_archive\workspace_transition_20261013\migration_candidate_20261012`
- `D:\FPGA\AFDX_E3_dev_clone_20261012` → `D:\FPGA\AFDX_archive\workspace_transition_20261013\e3_ascii_clone_20261012`
- `D:\FPGA\AFDX_E3_dev_clone_20261013` → `D:\FPGA\AFDX_archive\workspace_transition_20261013\e3_latest_dev_clone_20261013`

移动步骤由`scripts/archive_stagef_aux_workspaces.ps1`提供，仅在最终根通过验收并显式传入`-Execute`时执行；脚本会先复核最终根，再对移动前后的文件生成逐项SHA-256清单。若 eLinx 仍加载 E3 克隆中的工程，先在 GUI 确认无未保存修改并关闭 eLinx，再运行归档脚本。已有`D:\FPGA\AFDX_archive\workspaces_20261012`清单不追加或重写，迁移归档使用新的子目录。

这三个目录在最终工作区验收前继续保留在原路径作为回滚和复现来源；本轮未移动它们。AppData下的临时main/dev克隆不作为开发入口，也不删除。
