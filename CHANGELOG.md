# 变更记录

## 2026-10-14：Stage F正式工作区启用

- 正式根目录切换为`D:\FPGA\captain_integration`，dev为日常开发分支，main保持`9d5b85dd`。
- 正式路径完整315场景RTL Golden回归、13份冻结核心/8项Golden哈希、新路径16份eLinx源配置、真实GUI综合及VS Code Git识别PASS。GUI综合为2784 LUT/1069 FF/28 Memory/22 IO，0 Errors、25 Warnings。
- 原工作区17,261文件移动后哈希匹配；候选和两个E3克隆离线归档，逐项文件哈希与Git历史保护通过。
- 保留首次切换失败及自动回滚记录，修复Windows PowerShell 5.1路径/JSON数组兼容；修复隐藏目录导致的部分归档，以合集验哈希及原子重命名完成闭环。
- 增加AGENTS长期开发约定和Stage F最终报告。没有修改冻结RTL，没有更新main或创建新稳定标签；完整新VO时钟回归NOT RUN，官方接口和性能、时序、EQ6原生等价与物理fit仍NOT VERIFIED。

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
- 报告记录提交`d2c9b947ac89da4701d4ae668aa951ca085c66da`也已由独立克隆快进恢复，自检与72个跟踪文件的SHA-256比较再次通过。
- 修正Windows PowerShell路径解析和Golden清单属性计数；三个Stage F辅助脚本语法检查通过，切换与辅助归档计划均只读演练，没有移动目录。
- 本次只改文档与校验脚本，没有修改RTL、Testbench、Golden或eLinx模板；故未重复运行315场景ModelSim回归。
# 阶段2开发中

- 16VL共享帧构建器接真实B0 MAC：4097帧独立Golden PASS，保持每VL真实1ms BAG，发送端持续Payload实测188.74 Mbps；系统性能尚未验收。
- 新增125MHz NTP Q32.32 RTC时基和四时间戳运算，14个独立有理数Golden检查点PASS；网络SNTP仍待集成。

- 核对2026官方指南及FAQ；确认八端口ready可不参与握手，帧边界范围保留工程约定。
- 正式路径真实VO已导出，315场景完整网表回归运行中，未提前标PASS。
- 新增16VL独立SN门控及4293帧独立Golden验证；原315场景RTL回归PASS。尚未集成多VL系统。
- V1 eLinx输入固定为原16份canonical文件，避免新发展模块改变V1构建清单。

