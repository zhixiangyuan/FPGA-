# Git版本管理约定

Stage F已完成，唯一长期活动工程和Git根目录为`D:\FPGA\captain_integration`，默认活动分支为`dev`。Stage E2 PR [#1](https://github.com/zhixiangyuan/FPGA-/pull/1) 的普通Merge Commit `9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`仍是main。本次配置修复、最终报告和后续开发记录只进入dev，未经队长批准不合并main。6个历史标签不变；V1.0冻结提交`668094d8d4bcb5e4f2a447274b61a88129c991ec`仍由原标签保护，GitHub Initial commit和后续准备提交均可达。完整目录恢复说明见[Stage F最终报告](reports/Stage%20F统一工作区最终验收报告.md)。

## 分支和阶段版本

- `main`：只保存队长审核通过的稳定阶段版本。
- `dev`：下一阶段唯一主开发支线；可将每个已验证的小任务作为独立提交保存。未完成阶段不得打正式稳定标签或合并进`main`。
- 阶段验收通过后，将最终报告、代码提交和恢复说明一起核对，再创建新的带注释稳定标签。不得移动或覆盖已有标签。
- V1.0已验收源码标签为`afdx-v1.0-stage1-system-verified-2026-10-12`，指向`668094d8d4bcb5e4f2a447274b61a88129c991ec`。
- 提交`5cf6e2e9d511252663e0fa2cf75f41cee53b3901`包含V1.0 GitHub准备资料、Golden和可迁移eLinx快照；它及GitHub原始README提交均保留在迁移`dev`历史中。统一工程的canonical RTL在`rtl/`与`vendor/frozen/`，综合源副本由脚本生成。
- 原V1.0候选标签、稳定标签及B1/B2历史标签均已推送，未移动或重建。B1/B2标签指向独立历史提交链；执行恢复克隆后使用`git fetch origin --tags`获取全部标签历史。
- Stage E2 使用普通 Merge Commit。未来正式阶段仍须先通过验收、经队长批准并使用普通 Merge Commit；不得使用 Squash、Rebase 或强制推送。

## 日常开发命令

首次获取私有仓库时，需要有GitHub访问权限：

```powershell
git clone https://github.com/zhixiangyuan/FPGA-.git
cd FPGA-
git switch dev
git fetch origin --tags
```

完成一个小任务并验证后：

```powershell
git switch dev
git pull --ff-only origin dev
git status
# 修改并验证一个小任务后：
git add rtl/afdx_app_echo_queue.v
git commit -m "完善已验证的小任务"
git push origin dev
```

`git add`示例中的路径需替换成你本次实际修改并已核对的文件。

阶段完成后先在GitHub审查`dev`相对`main`的差异；仅在正式验收通过并经队长批准后，使用 Merge Commit 合并。不要直接在`main`开发，不要使用强制推送、硬重置或清理未跟踪文件的命令。

## 查看版本与恢复V1.0

```powershell
git fetch --tags origin
git log --oneline --decorate --graph --all
git show --stat afdx-v1.0-stage1-system-verified-2026-10-12
```

只查看稳定版本：

```powershell
git switch --detach afdx-v1.0-stage1-system-verified-2026-10-12
```

从稳定版本另开一个可继续工作的恢复分支：

```powershell
git switch -c restore/v1.0 afdx-v1.0-stage1-system-verified-2026-10-12
```

不要把测试恢复分支直接推到`main`。仓库提交哈希、标签、离线ZIP及Git bundle的SHA-256见`RESTORE_POINT.json`。离线包包含部分厂商仿真模型，其许可与再分发范围独立于本Git仓库；未经许可核实，不上传该包或模型文件。
