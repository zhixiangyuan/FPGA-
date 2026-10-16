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
| 运行管理服务系统集成（16 VL业务回环 + SNMP/SNTP over 真实MAC） | `python scripts/run_stage2_mgmt.py` |
| 运行 16 VL 持续业务与完整管理向量共存测试 | `python scripts/run_stage2_mixed.py` |
| 运行 VL 突发与更密集管理请求共存测试 | `python scripts/run_stage2_mixed.py --interval 4000 --service-interval 160000` |
| 运行系统级时务连续交换、重复 SN、真实 1 秒超时及复位恢复 | `python scripts/run_stage2_time_recovery.py` |
| 生成管理族 eLinx 综合工程副本（含SNMP/SNTP/RTC的顶层） | `python scripts/prepare_stage2_mgmt_elinx.py` |
| 运行管理族真实综合与数据库映射打包 | `python scripts/run_stage2_synthesis.py --project-dir build/elinx/AFDXS2M_NNN --settings-reference build/elinx/AFDXS2_005` |
| 运行 EQ6 原生综合时序分析并核对 100 MHz 与工程时钟裕量（不运行布局布线） | `python scripts/run_stage2_native_timing.py --project-dir build/elinx/AFDXS2M_NNN` |
| 静态检查顶层多驱动网冲突 | `python scripts/check_top_drivers.py [顶层文件...]` |

混合负载默认每 VL 256 帧、1471 字节负载，覆盖 SN 回绕。`--interval` 指一轮内不同 VL 的注入间隔；相邻轮次至少间隔 128000 周期，输入和输出仍独立检查每 VL 至少 125000 周期 BAG。吞吐窗口从首个业务输入到最后业务输出，包含空闲、启动和服务竞争；同时保存输出窗口口径和三种 GMII 时延。50 µs 时延极差是工程检查目标，不能当作官方已确认的抖动统计口径。SNTP 的 T1 是入队时间，T4 是路由后首负载字节时间，测试报告会量化它们与 GMII 首字节的差值。

`MODELSIM_BIN`、`MGLS_LICENSE_FILE`、`ELINX_HOME`、`AFDX_BUILD_ROOT`、`AFDX_V1_EVIDENCE_ROOT` 可用于指定本机工具、构建和离线证据目录。离线证据默认位置与恢复哈希见仓库根目录的 `OFFLINE_ARCHIVE_CATALOG.json`。

## 历史归档脚本

Stage F已完成。`stagef_workspace_switch.ps1`和`archive_stagef_aux_workspaces.ps1`保留用于审计和获批故障恢复，不作为日常入口；不要重复执行已完成的切换或归档。后续工作始终在正式根目录dev中开发。

`archive_v1_system.py`、`finish_v1_system.py`、`finalize_v1.py`、`package_v1.py`、`complete_v1_on_exit.py` 和 `run_history.ps1` 是原阶段目录的一次性收尾或跨阶段历史回归工具。它们保留在提交历史中用于追溯，不作为统一工程的日常入口；其原始输入、日志和结果保存在离线工作区归档中。不要在统一工程中用这些脚本覆盖已冻结的 V1.0 交付证据。
