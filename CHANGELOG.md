# 变更记录

## 2026-10-12：统一工作区迁移与 GitHub 发布准备（Stage C/D、E1）

- 保留V1.0稳定恢复点及完整旧 Git 历史；把 eLinx 源文件改为从 `rtl/` 和 `vendor/frozen/` 生成，避免维护两份活动 RTL。
- 将日常仿真和eLinx工程输出统一放入被Git忽略的 `build/`。
- 更新 ModelSim/eLinx 复现脚本，使其支持新构建根目录和离线证据路径。
- 在隔离候选工程完成315场景RTL Golden回归、候选eLinx GUI综合、真实功能VO导出及ModelSim 0 ns加载检查。
- 该候选仍是团队单VL功能工程；官方接口兼容、100 Mbps、最坏时延/抖动、Setup/Hold、EQ6原生等价性及物理封装适配均未标记PASS。
- Stage E1 已将迁移候选提交 `8e31c6414e93b56244f29ce1087ce216daffab04` 和全部 6 个历史标签推送到 GitHub；独立克隆核对了 14 个提交对象、67 个跟踪文件、13 份冻结核心及 8 项 Golden 数据。
- Stage E2 正在准备 `dev` 到 `main` 的 Pull Request。远端 `main` 仍为初始提交 `a631d0dbaf5515b47077f16cbf02292a6b7be176`；尚未合并。Stage F 正式工作区切换尚未执行。
