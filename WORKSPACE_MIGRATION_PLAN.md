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

详细证据见[`WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md`](WORKSPACE_MIGRATION_STAGE_C_D_REPORT.md)与[`OFFLINE_ARCHIVE_CATALOG.json`](OFFLINE_ARCHIVE_CATALOG.json)。

## 待单独批准

### Stage E：GitHub发布

开始前重新读取私有GitHub仓库的`main`、标签和远端权限。最近一次只读确认的远端`main`为`a631d0dbaf5515b47077f16cbf02292a6b7be176`，只有初始化README。若它已变化，先停止写入并重新审核历史关系。

获得Stage E批准后，重新配置候选`origin`为目标GitHub仓库，再读取远端提交并在隔离候选中完成历史整合，保留`a631d0d`、V1.0全部提交和标签；核对最终树、README、源码哈希和测试，再推送`dev`及获批的`main`/标签。禁止强制推送。推送后从新目录克隆远端，核验提交、标签、源码、Golden和必需配置。Stage E未批准前不配置remote或执行任何远端写入。

### Stage F：正式工作区切换

只有Stage E推送和独立克隆均通过、且队长另行批准后，才可将统一工程安置为`D:\FPGA\captain_integration`正式活动工作区。切换前保留原目录及嵌套Git仓库的可恢复副本；用清单复核文件和哈希；确认新EPR在最终路径仍可打开、ModelSim脚本仍可运行。未获Stage F批准前不移动、改名或删除任何原工作区目录。

长期分支约定为`main`与`dev`。在阶段审核批准前，迁移修改只留在隔离候选`dev`；V1.0原标签和提交不改写，候选不被描述为全国赛全指标通过版本。
