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
| E2：统一工程发布 | 完成 | PR #1普通Merge Commit为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；未改写历史或原V1.0标签 |
| E3：远程恢复验证 | 完成（限制项如实记录） | main/dev独立克隆、哈希与RTL Golden回归PASS；eLinx克隆GUI加载PASS，GUI综合NOT RUN；完整VO时钟回归NOT RUN |
| F：切换准备 | 等待批准 | 归档、bundle、空间、路径、应用占用和回滚方案已复核；未移动任何目录 |

详细证据见[`WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md`](WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md)与[`OFFLINE_ARCHIVE_CATALOG.json`](OFFLINE_ARCHIVE_CATALOG.json)。

## 当前状态

PR #1已合并。远端`main`与`dev`同步点均为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；随后产生的E3/F准备记录只进入`dev`。E3实际结果及NOT RUN项见[`reports/STAGE_E3_RECOVERY_REPORT.md`](reports/STAGE_E3_RECOVERY_REPORT.md)。

Stage F正式切换仍需队长对[`reports/STAGE_F_CUTOVER_PREPARATION.md`](reports/STAGE_F_CUTOVER_PREPARATION.md)单独批准。执行前重新检查实时磁盘空间和应用占用；目录移动或重命名前必须获得明确授权。旧工作区、旧阶段工程、Git bundle和原始证据不得删除或覆盖。

## 长期分支约定

长期分支为`main`与`dev`。`dev`用于日常开发与验证；`main`仅保存队长批准的稳定版本。V1.0原提交和标签保持不变。统一工程尚未合并到`main`，不代表官方接口、100 Mbps、最坏时延、时序或器件原生等价性已通过。
