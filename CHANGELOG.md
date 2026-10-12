# 变更记录

## 2026-10-12：统一工作区迁移候选（Stage C/D，等待审核）

- 保留V1.0稳定恢复点及完整旧 Git 历史；把 eLinx 源文件改为从 `rtl/` 和 `vendor/frozen/` 生成，避免维护两份活动 RTL。
- 将日常仿真和eLinx工程输出统一放入被Git忽略的 `build/`。
- 更新 ModelSim/eLinx 复现脚本，使其支持新构建根目录和离线证据路径。
- 在隔离候选工程完成315场景RTL Golden回归、候选eLinx GUI综合、真实功能VO导出及ModelSim 0 ns加载检查。
- 该候选仍是团队单VL功能工程；官方100 Mbps、最坏时延/抖动、Setup/Hold、EQ6原生等价性及物理封装适配没有据此标记PASS。
- 未执行GitHub推送或正式工作区切换；迁移提交仅位于 `dev`，待队长审核。
