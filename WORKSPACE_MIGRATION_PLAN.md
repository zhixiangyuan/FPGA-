# 统一工作区迁移计划与权限状态

目标工作区：`D:\FPGA\captain_integration`
隔离候选归档：`D:\FPGA\AFDX_archive\workspace_transition_20261013\migration_candidate_20261012`
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
| F：正式切换与收尾 | 完成 | 正式路径Git/哈希/315场景RTL Golden/GUI综合/VS Code识别PASS；历史和辅助工程离线归档PASS，报告只发布dev |

详细证据见[`WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md`](WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md)与[`OFFLINE_ARCHIVE_CATALOG.json`](OFFLINE_ARCHIVE_CATALOG.json)。

## 当前状态

PR #1已合并。远端`main`与`dev`同步点均为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；随后产生的E3/F准备记录只进入`dev`。E3实际结果及NOT RUN项见[`reports/STAGE_E3_RECOVERY_REPORT.md`](reports/STAGE_E3_RECOVERY_REPORT.md)。

队长已批准Stage F，正式工作区现为`D:\FPGA\captain_integration`。实际验证、第一次自动回滚及第二次成功切换、隐藏目录归档问题闭环、所有归档位置见[最终报告](reports/Stage%20F统一工作区最终验收报告.md)。原准备报告与历史清单作为当时快照保留，未回写原始冻结证据。

## 长期分支约定

长期分支为`main`与`dev`。dev用于日常开发与验证；main仅保存队长批准的稳定版本。统一工程已通过E2合并main，本次Stage F报告和脚本修复只进入dev。V1.0原提交和标签保持不变；官方接口、100 Mbps、最坏时延、时序和器件原生等价性仍未验证。
