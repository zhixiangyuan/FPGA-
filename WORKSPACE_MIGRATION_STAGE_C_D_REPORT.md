# 统一工作区迁移：Stage C/D 验证报告

日期：2026-10-12
候选目录：`D:\FPGA\captain_integration_migration_candidate_20261012`
状态：**Stage C/D 已完成。该报告记录迁移验证当时状态；后续 Stage E1 结果见第 6 节。**

## 1. 本轮结论

已在隔离候选目录完成统一工程整理和迁移验证。V1.0 的稳定恢复点、5cf6e2e 后续提交、GitHub 现有 Initial commit、B1/B2 原始 Git 历史及标签都保留。`main` 仍指向原 V1.0 冻结提交；迁移修改只落在候选 `dev`。

本轮没有修改原工作区、冻结生产 RTL、队友源码或官方 `AFDX_top` 接口；没有推送 GitHub、移动正式工作区、运行 Implementation 或生成 Bitstream。原始 `PENDING_CAPTAIN_REVIEW` 等状态和报告均未改写。V1.0 仍表示已验证的团队单VL功能候选，不表示全国赛全部指标通过。

## 2. 隔离迁移与历史保全

### 候选 Git 历史

- `main` 保持在提交 `668094d8d4bcb5e4f2a447274b61a88129c991ec`，标签 `afdx-v1.0-stage1-system-verified-2026-10-12` 未移动或重建。
- `dev` 从 V1.0 后续提交继续开发，并以合并提交 `649f3285ba5d529db5d2bf4417189be9bc6e4734` 接入 GitHub 已存在的 `a631d0dbaf5515b47077f16cbf02292a6b7be176` Initial commit。该提交保留了两段无共同祖先的历史并解决了 README 新增文件冲突。
- `5cf6e2e9d511252663e0fa2cf75f41cee53b3901` 可从 `dev` 到达，且仍在 school V1.0 bundle 中。它包含 V1.0 GitHub 准备资料、315场景 Golden 和可迁移 eLinx 文件；这些内容没有被回写到 668094d8。
- 候选本地仅保留`main`和`dev`两条分支；临时V1同步分支及其本地remote配置已在确认提交可从`dev`到达后移除。候选当前不配置remote；GitHub写入需等Stage E批准后再配置。
- 迁移前 V1.0 的两枚标签、B1 标签和 B2 两枚验收标签均保留；B2 最新历史提交另以 `archive/stage5b2-head-2026-10-12` 标明。未覆盖旧标签或改写旧提交哈希。
- 候选 `dev` 的 5cf6e2e 原始 eLinx RTL 副本已逐文件核对与 canonical 源码一致，然后从当前工作树移除；eLinx 项目副本现在由脚本从 `rtl/` 与 `vendor/frozen/` 生成。旧提交、旧目录和旧交付备份均未删除。

### 离线备份

`D:\FPGA\AFDX_archive\workspaces_20261012\captain_integration` 是完整历史工作区的独立复制。原目录与该复制按 `workspace_manifest.json` 的 17,261 个文件、2,573,320,124 字节逐项 SHA-256 比较通过；本轮结束时原工作区再核验仍全部匹配。

`D:\FPGA\AFDX_archive\git_bundles_20261012` 内的三个 bundle 均通过 `git bundle verify` 和恢复克隆核验：

| 仓库 | 提交数 | 标签数 | Bundle SHA-256 |
|---|---:|---:|---|
| school_v1_20261011 | 4 | 2 | `04ca3dfee019e6cc913916f2467755a88a65dbef516d7e72bda43319685240f3` |
| stage5B1_single_vl_20261010 | 1 | 1 | `a1076f3cc98c9f7041a3ced1da3f33eafa396ac68c3eefe79037aa681a8c65c5` |
| stage5B2_rx_arch_20261011 | 6 | 2 | `e68883bd24ff46bca718754a2ed2803bcc0526394e0c9dcb51a8d75795562e60` |

工作区、bundle、V1.0 ZIP、原 V1.0 Git bundle 和本轮候选运行证据的路径及哈希汇总于[OFFLINE_ARCHIVE_CATALOG.json](OFFLINE_ARCHIVE_CATALOG.json)。本轮新综合、仿真、导出和加载材料另归档到 `D:\FPGA\AFDX_archive\migration_candidate_C_D_20261012`，共412个文件、106,088,813字节；其文件清单和SHA-256在归档的 `archive_manifest.json`。

### Git 历史文件审计

候选所有可达历史共扫描139个Git blob；最大blob为126,335字节，没有超过10 MiB的blob，也没有命中GitHub token、云密钥或私钥头部模式。Altera/ModelSim厂商模型未进入Git历史；受许可限制的库仅保留在离线证据归档。此扫描是模式审计，不替代厂商许可审查。

## 3. 统一目录和路径验证

- 唯一活动 RTL 位置为 `rtl/` 与 `vendor/frozen/`；13份冻结 B0/B1/B2 核心的文件SHA与原冻结清单一致。现有历史清单原样保留。
- `golden/V1.0_full_vo_315/` 的8个数据成员与独立生成器输出的 SHA-256 完全一致。
- `elinx/AFDXV1/` 只保留 EPR 和 EDC 模板。`scripts/prepare_v1_elinx.py` 在被忽略的 `build/elinx/AFDXV1_NNN` 中生成16个源文件副本，并对每份副本与 canonical 文件逐项校验。
- 仿真日志、CSV、WLF、VO、eLinx数据库等本地生成物收敛到 `build/`，由 `.gitignore` 排除。日常入口、旧一次性归档脚本和输出位置记录于[`scripts/README.md`](scripts/README.md)。
- 新工程 EPR 内部引用相对项目路径。`run_v1.py`、综合审计/VO导出、ModelSim真实VO复现与完整VO runner已改用 `AFDX_BUILD_ROOT`、`AFDX_V1_EVIDENCE_ROOT` 等可配置路径。历史验收报告和冻结清单中的原绝对路径作为原始证据保留；旧阶段收尾脚本明确标为历史入口。

## 4. Stage D 实际验证

### 4.1 RTL 与 Golden：PASS

新候选目录的 ModelSim RTL 完整运行位于 `build/logs/rtl_001`，Golden独立核验通过：

- 315个Golden场景，`Errors: 0`、`Warnings: 0`。
- 295个 TX 帧、22,840个线上字节；296次应用bank提交、2,520个应用Payload字节；308条PSN决策逐项核对。
- 256帧SN回绕通过；125 MHz、125,000周期BAG按真实仿真运行。289个BAG间隔的最小值为125,003周期。
- 过滤、SN拒绝、SN=0控制、FCS错误、双缓存保留/容量丢弃、reset取消和恢复均由独立核验脚本检查。
- Golden清单SHA-256：`89c88953cf42ee44c5595c4b3f760ca954694bf25966f5be3ecfb768ebd57012`；WLF SHA-256：`3ea13710f1934e98021bac2ba9809edde054e0fe3f0aa4e0e0bfa34047c27d17`。

### 4.2 eLinx GUI 综合：PASS（综合范围）

`build/elinx/AFDXV1_002/AFDXV1.epr` 在 eLinx GUI 实际显示 Synthesis Complete；顶层 `AFDX_top`、器件 `EQ6HL45/CSG225`、`clock_125mhz.edc` 的8 ns约束均核对通过。综合结果：0 Errors、25 Warnings、2,784 LUT、1,069 FF、28 Memory、22 IO；可用I/O统计为160。

综合层级保留了应用回送队列、发送器、MAC、接收Parser和SN门控：应用队列250 LCs/92 FF/23,536 RAM bits；发送器680 LCs/312 FF；MAC 1,046 LCs/477 FF/49,152 RAM bits；接收Parser 691 LCs/176 FF/23,536 RAM bits；SN门控115 LCs/12 FF。共96,224个逻辑RAM位，未见真实协议链路被优化为空逻辑。

25条Warning逐条原文及分类见[综合Warning审计](reports/V1.0_migration_synthesis_warnings.json)：MAC不完整case 1条、MAC有界宽度截断12条、未读取的冻结Parser寄存器1条、读写旁路RAM推断7条、常量输出汇总1条、`tx_ready`固定为0一条、未使用输入汇总1条、`rx_ready`不影响任何输出一条。`tx_ready`和`rx_ready`两项揭示候选八端口边界与官方接口语义仍有风险；没有据此修改冻结核心或推断官方契约。

22/160仅表示综合端口数量小于器件可用I/O数量，不证明具体管脚分配、电气兼容或物理适配。综合报告中的33个组合环风险保留，未执行时序分析或布局布线。

### 4.3 功能 VO 导出与 ModelSim 加载：PASS（0 ns加载）

GUI综合成功后，已从该真实综合工程导出功能网表 `build/logs/eda_export_001/AFDX_top.vo`，导出日志报告无错误。新VO SHA-256为`0a5f30b1074e7ad4cd193c7e01dfc9a87b19b0a83093e1bd9dda39e1f5469227`。

新VO与原 V1.0完整验收所用VO的4,257,940字节逐字节比较仅有 `// DATE` 生成时间注释不同；统一该注释后两文件完全一致，规范化SHA-256均为`486ad1c5a4b10bad2fb895a20d91af1c29ac902fb821e6da99d1cbfd318399d7`。新VO使用归档的实际原语库和Testbench在ModelSim 2020.4完成编译与0 ns加载，退出码0、`Errors: 0`，且没有把RTL作为DUT编译。

**迁移候选完整时钟综合网表回归：NOT RUN。** 原 V1.0完整真实VO测试及Golden证据仍保存在离线归档并保持原PASS记录。本轮新导出物只有DATE注释差异，且新VO已经通过真实库编译/加载，因此没有重复耗时的315场景完整综合网表仿真。0 ns检查不代表重新通过完整网表Golden套件。

### 4.4 历史回归、性能与未验证项

- B1/B2历史仿真本轮未重跑；已有记录、标签、报告和bundle均保留。迁移未改动其冻结RTL。
- 从候选RTL样本得到的应用EOP至TX首字节区间为512 ns至1.999 ms，属于功能回归样本。100 Mbps合规、官方端到端延迟/抖动和最坏负载边界没有据此标PASS。
- `POST_SYNTH_TIMING=NOT VERIFIED`、`EQ6_NATIVE_NETLIST_EQUIVALENCE=NOT VERIFIED` 保持不变。旧579位诊断I/O适配仍为 `INCOMPATIBLE`；新V1顶层22位IO计数不改变该结论。
- Implementation、Bitstream、硬件下载、B2-3正式集成、阶段2开发及GitHub推送均未执行。

## 5. 后续权限边界（Stage C/D报告时点）

本报告所述候选在 `D:\FPGA\captain_integration_migration_candidate_20261012`。原 `D:\FPGA\captain_integration` 仍保持原路径、原仓库和逐文件哈希；旧阶段工程仍保存在原工作区及独立完整副本中。

当前 `main` 未接收迁移提交；`dev` 只保存隔离候选迁移。请先审核本报告和候选差异。Stage E GitHub推送和Stage F正式工作区切换均未获本轮授权，完成 Stage D 后在此停止。

## 6. 后续 Stage E1 状态更新

本节记录 Stage E1 完成时的远端状态；后续 Stage E2/E3 状态见第7节。

本节补记 Stage C/D 报告完成后的 GitHub 同步结果，不改变原 V1.0 验收报告、冻结提交或历史哈希清单。

- GitHub `dev` 已同步至提交`8e31c6414e93b56244f29ce1087ce216daffab04`。候选历史保留 GitHub 初始提交`a631d0dbaf5515b47077f16cbf02292a6b7be176`、V1.0冻结提交`668094d8d4bcb5e4f2a447274b61a88129c991ec`及后续准备提交`5cf6e2e9d511252663e0fa2cf75f41cee53b3901`。
- 6个原有标签均以原名称和原目标推送。V1.0稳定标签仍指向`668094d8d4bcb5e4f2a447274b61a88129c991ec`。B1/B2标签保存独立历史链，完整恢复克隆需执行`git fetch origin --tags`。
- 独立克隆核对通过：14个可达提交与候选仓库一致；67个跟踪文件SHA-256一致；13份冻结核心和8项Golden数据通过清单核验。原V1.0证据清单中的41个源码哈希与冻结提交`668094d8`一致。
- 在独立克隆目录执行`python scripts/prepare_v1_elinx.py`成功，生成工程副本的16个源文件哈希一致，顶层、器件、封装及8 ns约束核对通过。该步骤只生成综合工程，不代表新目录已运行综合或完整VO回归。
- 远端`main`仍指向原始 Initial commit；Stage E2 Pull Request [#1](https://github.com/zhixiangyuan/FPGA-/pull/1) 当前无冲突并可合并，但合并尚待队长批准。Stage E3和Stage F均未执行。

## 7. 后续 Stage E2/E3 与 Stage F 准备记录

本节为2026-10-13补充记录，不更改V1.0原始验收报告、冻结提交、历史标签或C/D阶段当时的测试状态。

- Stage E2 的 PR #1 已按普通 Merge Commit 合并，提交`9d5b85dd67bcf356bdc47c4aaf3336d2a863f832`。GitHub main/dev同步点、17个可达提交、6个历史标签及67个跟踪文件核对见[Stage E3报告](reports/STAGE_E3_RECOVERY_REPORT.md)。
- Stage E3 从独立克隆执行 ModelSim RTL Golden回归：315场景PASS、295 TX帧、22,840线字节、296次应用提交、256帧SN回绕、125,000周期BAG门限、Errors 0/Warnings 0。原始日志与WLF保存在`D:\FPGA\AFDX_E3_dev_clone_20261012\build\logs\rtl_001`。
- 独立克隆 eLinx EPR 的生成和 GUI 加载通过，GUI核对Top/器件/约束及源码层级；克隆工程GUI综合未运行，完整VO时钟回归也未运行。详细状态和原因见 Stage E3 报告。
- Stage F只读预检确认旧根目录仍完整、归档清单及bundle哈希通过、D盘可用空间约38.73 GiB。切换及回滚脚本经过语法与只读计划检查；没有移动、重命名或删除任何目录。
