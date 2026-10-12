# 统一工作区迁移计划与权限状态

目标工作区：`D:\FPGA\captain_integration`
隔离候选：`D:\FPGA\captain_integration_migration_candidate_20261012`
最终归档：`D:\FPGA\AFDX_archive`

## 已完成

| 阶段 | 状态 | 结果 |
|---|---|---|
| A：目录/Git/依赖审计 | 完成 | V1.0、B1、B2历史与远端初始提交均已核对 |
| B：迁移方案与风险评估 | 完成 | 按队长补充的冻结、离线归档和授权边界更新 |
| C：隔离迁移 | 完成 | 完整工作区副本、三个Git bundle、独立候选和README历史合并已建立 |
| D：候选验证 | 完成 | 315场景RTL回归、GUI综合、VO导出和真实库0 ns加载均按报告记录；完整候选VO时钟套件标记NOT RUN |
| E1：GitHub dev同步 | 完成 | `dev`及6个原有标签已推送；独立克隆与核心哈希核验通过 |

详细证据见[`WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md`](WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md)与[`OFFLINE_ARCHIVE_CATALOG.json`](OFFLINE_ARCHIVE_CATALOG.json)。

## 当前状态

Stage E2 正在准备 `dev` 到 `main` 的 Pull Request。远端 `main` 当前仍为`a631d0dbaf5515b47077f16cbf02292a6b7be176`；候选`dev`包含该提交、V1.0冻结提交`668094d8d4bcb5e4f2a447274b61a88129c991ec`及后续准备提交`5cf6e2e9d511252663e0fa2cf75f41cee53b3901`。合并必须使用普通 Merge Commit，并等待队长批准。

Stage E3 只能在队长批准并完成`main`合并后执行，内容为远端独立恢复验证及本地分支同步。

Stage F 切换前检查和回滚方案可先准备；任何目录移动或重命名都必须取得队长对最终方案的单独确认。原工作区、旧阶段工程、Git bundle和原始证据在确认切换成功前不得删除或覆盖。

## 长期分支约定

长期分支为`main`与`dev`。`dev`用于日常开发与验证；`main`仅保存队长批准的稳定版本。V1.0原提交和标签保持不变。统一工程尚未合并到`main`，不代表官方接口、100 Mbps、最坏时延、时序或器件原生等价性已通过。
