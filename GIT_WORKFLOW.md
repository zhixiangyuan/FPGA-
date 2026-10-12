# Git版本管理约定

当前统一工程仍处于本地隔离迁移候选目录，Stage C/D 已完成但尚未获准执行Stage E。候选本地仅保留`main`和`dev`两条分支，暂不配置任何Git remote，以免普通`git push`指向错误仓库。GitHub仓库最近一次只读读取到的`main`为`a631d0dbaf5515b47077f16cbf02292a6b7be176`；本地迁移`dev`、冻结标签和工程文件尚未推送。Stage E另行批准并完成前，从GitHub克隆不会得到本候选。

## 分支和阶段版本

- `main`：只保存队长审核通过的稳定阶段版本。
- `dev`：下一阶段唯一主开发支线；可将每个已验证的小任务作为独立提交保存。未完成阶段不得打正式稳定标签或合并进`main`。
- 阶段验收通过后，将最终报告、代码提交和恢复说明一起核对，再创建新的带注释稳定标签。不得移动或覆盖已有标签。
- V1.0已验收源码标签为`afdx-v1.0-stage1-system-verified-2026-10-12`，指向`668094d8d4bcb5e4f2a447274b61a88129c991ec`。
- 提交`5cf6e2e9d511252663e0fa2cf75f41cee53b3901`包含V1.0 GitHub准备资料、Golden和可迁移eLinx快照；它及GitHub原始README提交均保留在迁移`dev`历史中。统一工程的canonical RTL在`rtl/`与`vendor/frozen/`，综合源副本由脚本生成。

## 日常开发命令

首次获取私有仓库时，需要有GitHub访问权限：

```powershell
git clone https://github.com/zhixiangyuan/FPGA-.git
cd FPGA-
git switch dev
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

阶段完成后先在GitHub审查`dev`相对`main`的差异；仅在正式验收通过后合并。不要直接在`main`开发，不要使用强制推送、硬重置或清理未跟踪文件的命令。

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
