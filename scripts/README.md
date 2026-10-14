# 脚本入口与输出约定

日常开发的输出统一写入 `build/`，该目录由 `.gitignore` 排除。提交源代码、可复现测试和阶段报告；完整运行日志、WLF、综合网表及 EDA 数据库放在本地归档。

## 日常入口

| 用途 | 命令 |
|---|---|
| 生成并运行完整 RTL Golden 回归 | `python scripts/run_v1.py` |
| 核验指定 RTL 运行 | `python scripts/verify_v1.py build/logs/rtl_NNN` |
| 生成 eLinx 工程副本 | `python scripts/prepare_v1_elinx.py` |
| 审计候选 GUI 综合 | `python scripts/audit_v1_synthesis.py --project-dir build/elinx/AFDXV1_NNN` |
| 从已通过的综合数据库导出功能 VO | `python scripts/export_v1_vo.py --project-dir build/elinx/AFDXV1_NNN` |
| 检查真实 VO 可编译并加载到 0 ns | `python scripts/replay_v1_netlist.py --reference <证据目录> --load-only` |
| 运行完整真实 VO 测试 | `python scripts/run_v1_netlist.py --reference <证据目录> [--dut-vo <候选VO> --dut-provenance <导出记录>]` |
| 独立核验完整 VO 测试 | `python scripts/verify_v1_netlist.py build/logs/netlist_NNN` |
| 从真实 VO 生成只读探针 | `python scripts/prepare_v1_netlist_observer.py --vo <AFDX_top.vo>` |
| 正式工作区Git/冻结哈希/Golden/工程配置自检 | `./scripts/verify_unified_workspace.ps1` |
| 运行管理服务系统集成（16 VL业务回环 + SNMP over 真实MAC） | `python scripts/run_stage2_mgmt.py` |
| 静态检查顶层多驱动网冲突 | `python scripts/check_top_drivers.py [顶层文件...]` |

`MODELSIM_BIN`、`MGLS_LICENSE_FILE`、`ELINX_HOME`、`AFDX_BUILD_ROOT`、`AFDX_V1_EVIDENCE_ROOT` 可用于指定本机工具、构建和离线证据目录。离线证据默认位置与恢复哈希见仓库根目录的 `OFFLINE_ARCHIVE_CATALOG.json`。

## 历史归档脚本

Stage F已完成。`stagef_workspace_switch.ps1`和`archive_stagef_aux_workspaces.ps1`保留用于审计和获批故障恢复，不作为日常入口；不要重复执行已完成的切换或归档。后续工作始终在正式根目录dev中开发。

`archive_v1_system.py`、`finish_v1_system.py`、`finalize_v1.py`、`package_v1.py`、`complete_v1_on_exit.py` 和 `run_history.ps1` 是原阶段目录的一次性收尾或跨阶段历史回归工具。它们保留在提交历史中用于追溯，不作为统一工程的日常入口；其原始输入、日志和结果保存在离线工作区归档中。不要在统一工程中用这些脚本覆盖已冻结的 V1.0 交付证据。
