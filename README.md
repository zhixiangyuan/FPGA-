# FPGA-

基于以太网 MAC 总线实现 AFDX

正式开发工作区：`D:\FPGA\captain_integration`。日常开发使用`dev`；`main`仅接受队长批准的稳定版本。源码、测试、Golden和配置在同一工程持续维护，常规阶段不复制日期命名的完整工程。

## 比赛要求补齐候选（2026-10-27）

新增比赛应用入口 `rtl/competition/AFDX_top.v`。该入口接收 VLID + 应用有效载荷，包含独立 A/B MAC、每网完整性检查、跨网消重、128 个业务发送 VL、4096 个业务接收 VL，以及共用发送器的 SNMP、SNTP/RTC 和原配置型 615A 服务。旧 `rtl/submission/AFDX_top.v` 保留为历史管理入口；两份 `AFDX_top` 定义不可同时编译。

应用格式、状态口、配置范围、当前验证结果及限制见 [比赛要求补齐说明](reports/比赛要求补齐_20261027.md)。新源码不会沿用 `a792a18` 或导入前候选的整机 VO PASS。

```powershell
python scripts/run_redundant_rx.py
python scripts/run_competition_mgmt.py
python scripts/run_competition.py
python scripts/run_competition_smoke.py
python scripts/prepare_competition_elinx.py
```

以上入口使用同一组 canonical RTL 和独立 Python Golden。默认真实 125 MHz、1 ms BAG；4096 接收状态的初始化需要 4096 个周期。`initialized` 与 `tx_ready` 有效后才开始应用注入。

当前候选 RTL、EQ6HL130 综合、原生 8 ns setup 及真实综合网表短链路均已通过。应用有效载荷交付 183.8886 Mbps，已测最大应用时延 62.096 μs；128 条发送 VL 全部实际发送，4096 条接收 VL 状态通过 17954 条独立向量。最终综合为 50861 LUT、16551 FF、356 Memory、102 Pins；Fmax 125.8495 MHz，8 ns setup +54 ps。真实 VO 短链路覆盖最小/最大负载、最后 TX/RX VL、双网消重与自动 SNTP，111.344 μs 连续仿真约用时 4 分 12 秒。完整物理时序、新封装完整 615A 会话及 EQ6 原生映射等价仍未签核，不把短测扩大为这些项目的 PASS。机器可读证据见 `reports/COMPETITION_CANDIDATE_20261027.json`，范围见本次比赛补齐报告。以下保留导入和旧候选记录，供历史对照。

## 导入时开发状态（历史对照）

2026-10-27 已按用户要求导入 `FPGA-Final-Project.zip` 的增强版，来源提交为 `b478fa4e9fa1cd8af9ac379224beeabe4fd9cbc2`。保留原始 Git 历史并通过普通 Merge Commit 合入 `dev`；导入前版本 `a792a18` 保存在 `backup/before-final-import-20261027`。压缩包 `source/` 的 173 个文件与导入提交逐项比对一致（统一换行符后）；13 份冻结核心未修改。

本版增加 SNMP 的 sysObjectID、sysContact、sysLocation，对 contact/name/location 支持 SET，并增加 SNMPv2c 请求支持；接收侧新增可选 BAG 检查与可配置长度上限，生产入口默认关闭 BAG 检查。其余改动包括综合前端兼容、位宽处理以及综合/VO 辅助脚本。

本机导入后验证：SNMP 63 用例、SN 完整性 4293 次独立判定、615A 模块 30 用例/684 帧、管理集成 58 帧、正式入口 9 帧，以及接收 BAG/长度边界检查均为 PASS。运行目录、摘要哈希和输入指纹见 [导入验证记录](reports/FPGA_FINAL_IMPORT_20261027.json)。

当前新源码的完整 615A 整机 RTL、重新综合及完整整机 VO 均为 NOT RUN；包内综合数据为外部交付报告，本次未复验。随包 615A 日志的 111 帧与随包脚本要求的 512 个背景业务帧存在对应关系疑点，未作为本次验收证据。下文 30733 LUT、640 帧整机 VO PASS 等结果仅属于导入前候选，不能沿用为当前增强版的验收结论。

## 导入前候选验收记录（a792a18）

正式八端口入口为 `rtl/submission/AFDX_top.v`，内部接入 16 个业务 VL、SNMP、自动 SNTP 和配置型 615A-2（A3、UDP 59）。615A 支持一个 665-2 LSAP、一个 0～4096 字节偶数长度的 `config.bin`，覆盖 LUI/LUR/LUS 上传、LND/LNR/LNS 媒体定义下载、独立状态会话、WAIT/ABORT、有限重试及双 bank 原子提交。存储为易失 RAM；不包含通用多文件/支持文件、FIND/INFORMATION、操作员定义下载、压缩或加密，外部装载器互操作尚未验证。

当前候选 RTL 与独立 Golden 已通过：

- `a615a_009`：615A 模块 30 用例、684 包，覆盖头部/数据/总 Load CRC、错误身份、WAIT/ABORT、丢包与错误 TID、复位、空文件及 4 KiB 边界；故障计时器在模块测试中按声明缩放。
- `submission_615a_013`：正式 GMII 的 9 个装卸载/失败恢复场景，640 个输出帧、795541 字节逐帧核验；装载期间 512 个完整业务帧无丢失，Payload 速率 163.496 Mbps，最大输入首字节至输出末字节延时 60448 ns，已测每 VL 时延极差为 0。真实 8 ns 时钟，双方最小 BAG 均不少于 125000 周期，对端帧间隔至少 2048 周期；未缩短整机协议定时器，也未使用内部状态检查或 force。
- `mgmt_load_003`：当前管理核心 57 用例、47 帧、6484 字节通过。`submission_006`：正式入口的自动 SNTP、真实 10 ms sysUpTime、SNMP SET/GET、重复 SN 与复位恢复，9 帧、956 字节通过。
- `mgmt_load_mixed_004`：与原基线相同的 interval=4000、service interval=160000，16 个业务 VL、4096 个业务帧及完整管理向量同载；4141 帧、6255335 字节通过，业务速率 184.2148 Mbps、最大延时 60448 ns，与原基线一致。
- 原 V1.0 `rtl_011`：315 场景通过独立 Golden，295 个 TX 帧、22840 字节、296 次应用提交、308 条 SN 决策及 256 帧 SN 回绕通过；13 份冻结源码和 8 份原 Golden 哈希保持一致。

已修复装载包提前占用共享发送器等待 BAG 的拥塞：装载 BAG 到期后才参与仲裁，帧构建器继续独立检查 BAG。在相同 Testbench 和数据的对照中，修复前已送达业务帧的最大延迟约 4.77 ms，修复后约 60.45 µs。上述结果仅覆盖声明的有界负载；原两 bank MAC 对连续短帧突发的容量边界仍保留，不承诺任意突发无损。

当前固定综合候选为 `AFDXSUB_005`，使用 SPEED 综合目标。真实 EQ6 后端打包 PASS：30733 LUT、9239 FF、3846 CLB、152 Memory、22 位 I/O，0 Errors、104 Warnings。接入前八端口基线为 16371 LUT、6565 FF、126 Memory；新增功能及当前综合目标合计增加 14362 LUT、2674 FF、26 Memory。相同 RTL 的 BALANCED 候选 `_004` 为 24204 LUT、9256 FF、152 Memory，8 ns setup −598 ps；SPEED 增加 6529 LUT，以原生综合估算 Fmax 125.849 MHz、8 ns setup +54 ps、失败端点 0 满足建立约束。当前裕量较小，预布线 hold 仍为 −68 ps、64 个端点，I/O 延迟未完整约束；未运行布局布线，不宣称完整时序签核。

**最终整机功能 VO：PASS。** `build/logs/submission_615a_vo_checkpoint_002` 使用 `eda_stage2_export_011/AFDX_top.vo`、原厂原语、真实 8 ns 时钟与 125000 周期 BAG，在同一状态链完成 15 段会话及 9 个场景；最终 ModelSim 进程退出 0、无 Error/Fatal，完整独立 Golden 和同候选 RTL 的双向逐 VL wire bytes 比较通过。共 640 个 TX 帧、643 个 RX 帧、795541 个 TX 字节；512 个完整同载业务帧的 Payload 速率为 163.4956 Mbps，已测 GMII 最大延时 60448 ns，每 VL 时延极差为 0。原始摘要、各段日志、检查点和输入指纹保留在该目录。实际仿真模型为 eLinx 工具导出的 EP1S80/Stratix 兼容模型，EQ6 原生映射等价性仍为 NOT VERIFIED；历史模块 VO 与 V1.0 证据均不替代本次整机结果。

比赛正式提交材料尚未整理。外部装载器互操作、更大 VL 容量及完整物理时序仍未验证；赛题 V2.1 和答疑要求 eLinx 编译及综合后仿真，无需硬件平台或布局布线，不把这些未验证能力冒称赛题验收 PASS，也不宣称完整 ARINC 标准合规。

## 队友从 GitHub 接手

仓库默认分支为 `main`。队友克隆后先记录 `git rev-parse HEAD`，阅读本页，再从 `rtl/submission/AFDX_top.v` 和 `scripts/submission_sources.py` 确认生产入口与源码清单；`sim/tb_submission_615a.sv`、`scripts/run_submission_615a.py`、`scripts/generate_615a_golden.py` 提供仿真激励、Golden 生成及验收逻辑。完整交接稿位于用户另行打包的 `D:\FPGA\交接内容`，包含设计文档、测试报告和交接手册。

Git 跟踪源码、Testbench、脚本和模板约束，**不跟踪 `build/`**。因此仅有 GitHub 仓库不能直接查看本次完整 VO、15 段原始日志、ModelSim 编译库或厂商仿真模型，也不能据此声称复核了原始 PASS。原始证据在本机 `build/logs/submission_615a_vo_checkpoint_002`，同候选 RTL 参考在 `build/logs/submission_615a_013`；需要复核时由持有者按许可和文件哈希单独交接，不把厂商模型或完整构建目录推送到公开仓库。

## GitHub 发布状态

Stage E2 Pull Request [#1](https://github.com/zhixiangyuan/FPGA-/pull/1) 已于2026-10-12通过普通 Merge Commit 合并。统一工程提交为`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`；远端`main`与`dev`在E3同步点均指向该提交。远程独立克隆、17个可达提交、6个历史标签、67个跟踪文件及逐文件哈希核验通过。原V1.0稳定标签仍指向冻结提交`668094d8d4bcb5e4f2a447274b61a88129c991ec`。随后E3/F准备报告和校验脚本只更新`dev`，`main`保持上述审核提交。

Stage F已按队长批准完成正式路径切换、315场景ModelSim RTL/Golden回归、实际eLinx GUI综合和VS Code Git识别。旧工作区、候选仓库和E3克隆已离线归档并验哈希；结果见[Stage F最终验收报告](reports/Stage%20F统一工作区最终验收报告.md)。该阶段未更新main或创建新稳定标签；当时新路径完整VO时钟回归为NOT RUN，POST_SYNTH_TIMING、EQ6原生网表等价、官方八端口兼容、100 Mbps、最坏时延/抖动与物理I/O适配均未验证。后续最新结果以本页“当前开发状态”为准。

## 目录

- `rtl/`：候选顶层、GMII边界和应用回送队列。
- `vendor/frozen/`：13份冻结B0/B1/B2核心快照；校验信息见`FROZEN_CORE_MANIFEST.json`。
- `sim/`、`scripts/`：Testbench、独立Golden生成器、编译/仿真/核验和历史回归脚本。
- `golden/V1.0_full_vo_315/`：真实VO验收使用的315场景Golden输入、元数据及SHA-256。
- `elinx/AFDXV1/`：eLinx EPR/EDC模板。RTL唯一canonical副本位于`rtl/`和`vendor/frozen/`；运行准备脚本后，在被忽略的`build/elinx/`中生成可打开工程和逐项哈希清单。
- `build/logs/`：ModelSim、Golden、真实VO导出等临时构建证据；默认由Git忽略。完整历史日志及波形离线归档。
- `README_SYSTEM.md`、`GIT_WORKFLOW.md`：复现说明与后续Git流程。
- `RESTORE_POINT.json`、`OFFLINE_ARCHIVE_CATALOG.json`：验收标签、提交、离线交付包以及整套旧工作区和Git bundle恢复位置与哈希。

原始仿真波形、综合数据库、真实VO、厂商器件模型、完整日志及打包交付物保留在独立离线证据目录/归档中，不纳入GitHub源码历史。离线交付包内的Altera模型受其许可约束，不在此仓库再分发。

## 本地RTL复现

需要Python 3.10+、ModelSim 2020.4及有效仿真许可。`MODELSIM_BIN`可指定ModelSim可执行文件目录，`MGLS_LICENSE_FILE`可指定许可位置。

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py build/logs/rtl_001
```

runner会自动选择新的`build/logs/rtl_NNN`目录；核验命令中的目录应替换为runner实际打印的路径。Golden由独立Python参考模型生成，测试覆盖真实业务来源、SN门控、协议错误、双缓存压力、FCS、reset和恢复。`AFDX_BUILD_ROOT`可指定其他本地生成目录。

## 当前管理与装载候选复现

```powershell
python scripts/run_615a.py
python scripts/run_submission_615a.py
python scripts/run_stage2_mgmt.py --load-core
python scripts/run_stage2_mixed.py --load-core --interval 4000 --service-interval 160000
```

生产源码清单由 `scripts/submission_sources.py` 给出；`rtl/AFDX_top.v` 是独立 V1.0 入口，不能与生产入口同时编译。重新综合须先用 `prepare_submission_elinx.py` 生成新编号目录，再通过 `run_stage2_synthesis.py` 指定该目录、已验证的 settings reference 以及 `--optimization-technique SPEED`；默认 BALANCED 结果不能代替当前候选。真实 VO 验收入口 `run_submission_615a.py` 还需指定 `--vo`、`--provenance` 和同源码通过的 `--rtl-reference`。

完整 VO 运行期间可执行 `python scripts/check_live_submission_vo.py --run build/logs/submission_615a_vo_checkpoint_002 --rtl-reference build/logs/submission_615a_013`，只读核对已落盘完整帧的 FCS、BAG、帧长及逐 VL 的 RTL 字节前缀，并校验参考与 Golden 指纹。`PREFIX_MATCH_ONLY` 不代表最终 PASS；本次最终结果以原 runner 的完整验收及 `summary.json` 为准。

本次断点验收曾使用 `run_submission_vo_checkpoint.py --run build/logs/submission_615a_vo_checkpoint_002 --session-minutes 100` 在同一目录冷恢复，复用相同真实 VO 的 O5 编译缓存，保持 8 ns 时钟、真实 BAG、全部场景和原 Golden 核验。每次恢复前校验输入、Golden、参考、检查点、编译库及已输出 CSV；`PAUSED` 不计为 PASS。该目录现已为 `PASS`，不应再调用续跑命令。

原非检查点运行 `submission_615a_vo_002` 已获用户批准停止，原始输出和取消说明保留，未计为验收通过。本次整机 PASS 仅来自连续接续的 `submission_615a_vo_checkpoint_002`；原两段 10 μs 冷恢复短测只作为续跑机制证据。

两路短段试验 `submission_vo_parallel_001` 使用相同 VO、Testbench、Golden 和原断言，各测 200 μs 的两个真实状态区间：串行合计 213.203 秒，并行 165.906 秒，加速 1.285 倍、节省 22.2%；对应五份 CSV 哈希一致，收发帧通过 RTL 逐 VL 字节前缀、FCS 和 BAG 检查。生成第二个真实前置状态另耗时 1450.547 秒，不包含在上述采样比值中。两路峰值工作集 1495.35 MiB、私有内存 1651.54 MiB，系统最低可用 1464.00 MiB；试验期间正式 VO 同时运行。入口为 `scripts/benchmark_submission_vo_parallel.py --stop-at <带时区截止时间>`，每次执行会建立新试验，勿作为状态查询命令重复运行。该结果为 `BENCHMARK_MATCH_ONLY`：尚未验证长时间高负载或超过两路的扩展效率，原连续 9 场景尚未拆分。按两路效率不下降的假设，13 小时至 4 小时约需 6 路，18 小时至 3 小时约需 10 路；当前可用内存不足以据此直接扩路，也不能保证完整验收在该时间内结束。

## eLinx综合工程

2026-10-18 在封存的 10.12 ms 真实 VO 检查点上完成 `vo_resume_optimization_001`：两个相邻 100 μs 区间、默认调度/指定独立物理核心/重复采样/两路并行共 10 个样本，Golden、原断言及真实时钟/BAG 不变。对应五份 CSV 哈希及终点一致，原 67 份根目录产物、检查点、25 份缓存和 5 份 CSV 均未改变。相同 A 区间默认两次纯运行 65.981/54.858 秒，CPU2 绑定两次 65.092/57.803 秒，未证实稳定的单路绑核收益；默认/绑核两路墙钟 97.813/92.328 秒，相对对应串行样本吞吐为 1.455/1.535 倍。区间 B 的真实起点由区间 A 顺序计算取得，不能用这些吞吐比值缩短原连续 9 场景的关键路径。场景共享文件 bank、SN、协议状态与连续背景流，独立完整场景分组尚未建立。续跑采用已有 O5 镜像、默认调度及原检查点控制器，避免并发重复 VO；原数据保留。剩余 109.179368 ms 按默认 A 样本外推约 16.6～20.0 小时，均值约 18.3 小时，仅为短段估计，后续实际活跃度仍会影响耗时；不承诺 5～7 小时完成。短测入口 `benchmark_loaded_vo_resume.py --stop-at <带时区截止时间>` 会启动新试验，不用于查询进度；`LOADED_BENCHMARK_MATCH_ONLY` 不计为完整 VO 通过。

先运行`python scripts/prepare_v1_elinx.py`，它会从`rtl/`和`vendor/frozen/`的canonical源码生成`build/elinx/AFDXV1_NNN/AFDXV1.epr`，并逐文件核对哈希。打开生成的工程。目标为EQ6HL45/CSG225，顶层`AFDX_top`，使用`clock_125mhz.edc`中的125 MHz/8 ns约束。阶段1原GUI综合资源为2784 LUT、1069 FF、28 Memory、22 IO，0 Errors、25 Warnings。综合通过不代表时序或物理封装适配通过。

真实VO及原厂器件模型不在Git源码树中。将V1.0离线交付包解压到本地归档后，设置`AFDX_V1_EVIDENCE_ROOT`指向其`evidence`目录，再按`README_SYSTEM.md`运行真实VO复验脚本。厂商模型仅用于本机已许可的仿真环境。

Git恢复步骤和`main`/`dev`约定见[Git工作流](GIT_WORKFLOW.md)。
