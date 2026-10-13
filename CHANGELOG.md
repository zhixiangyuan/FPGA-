# 变更记录

## 2026-10-12：统一工作区迁移与 GitHub 发布准备（Stage C/D、E1）

- 保留V1.0稳定恢复点及完整旧 Git 历史；把 eLinx 源文件改为从 `rtl/` 和 `vendor/frozen/` 生成，避免维护两份活动 RTL。
- 将日常仿真和eLinx工程输出统一放入被Git忽略的 `build/`。
- 更新 ModelSim/eLinx 复现脚本，使其支持新构建根目录和离线证据路径。
- 在隔离候选工程完成315场景RTL Golden回归、候选eLinx GUI综合、真实功能VO导出及ModelSim 0 ns加载检查。
- 该候选仍是团队单VL功能工程；官方接口兼容、100 Mbps、最坏时延/抖动、Setup/Hold、EQ6原生等价性及物理封装适配均未标记PASS。
- Stage E1 已将迁移候选提交 `8e31c6414e93b56244f29ce1087ce216daffab04` 和全部 6 个历史标签推送到 GitHub；独立克隆核对了 14 个提交对象、67 个跟踪文件、13 份冻结核心及 8 项 Golden 数据。
- Stage E2 已创建 [`dev` 到 `main` 的 Pull Request #1](https://github.com/zhixiangyuan/FPGA-/pull/1)。其合并和后续验证状态见下方 Stage E2/E3 更新。

## 2026-10-13：Stage E2/E3与Stage F准备

- PR #1 已用普通 Merge Commit 合并；统一工程发布提交为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`。原V1.0标签及全部6个历史标签保持原目标。
- GitHub main/dev独立克隆、17个可达提交、67个跟踪文件逐项SHA-256、13份冻结核心和Golden输入核对通过；ASCII路径克隆的315场景ModelSim RTL Golden回归PASS。
- 独立克隆eLinx工程的配置生成、GUI加载与顶层/器件/8ns约束检查通过；该克隆的GUI综合为NOT RUN。完整VO时钟回归及官方性能/器件指标未据此标记PASS。
- 完成Stage F只读切换准备及回滚脚本；尚未移动、重命名或删除任何旧工作区，正式切换需队长另行批准。

## 2026-10-14：远程恢复复核与切换脚本修正

- 本次独立克隆核验基线的`dev`提交为`eb85750ced844f14a1bda7f26bda666545b738bd`；`main`保持`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`。克隆有72个跟踪文件，逐项SHA-256匹配，校验脚本PASS。
- 随后的文档收尾提交`7a8dceb7a92fd3332f253bcc3ffa81bcdae8f5be`已推送至`dev`，独立克隆快进并再次通过配置自检与逐文件SHA-256比较；`main`保持不变。
- 修正Windows PowerShell路径解析和Golden清单属性计数；三个Stage F辅助脚本语法检查通过，切换与辅助归档计划均只读演练，没有移动目录。
- 本次只改文档与校验脚本，没有修改RTL、Testbench、Golden或eLinx模板；故未重复运行315场景ModelSim回归。
