# 变更记录

## 2026-10-14：时务与RTC系统集成闭环（SNTP over 真实MAC）

- `build/logs/mgmt_016` PASS：16 VL业务回环、SNMP管理VL（`0x1244`）与SNTP时务VL（`0x1245`）共用真实冻结MAC及共享帧构建器，57个Golden用例中56个GMII输入帧（6894线字节）产生47个输出帧（6484线字节）逐字节匹配独立Golden；管理VL BAG最小139969周期、业务VL 145747周期（要求125000）；GMII输入首字节至输出首字节2.880至48.256 µs。
- 实测时务交换：请求起点为RTC复位初值，服务器时间戳由Golden给定，接受/拒绝/超时1/0/0，往返延迟8250392 NTP单位（约1.921 ms，限值1秒），`synchronized=1`、`error_count=0`；偏移与延迟由独立脚本按NTP模运算重算核对，不复用仿真器结果。
- 发射侧改为三路仲裁（业务回环、SNMP应答、时务请求），两个服务源各自独占不背压的消息缓冲并在彼此间轮转；管理接收改为单解析器覆盖两条管理VL加按端口分流，避免服务端点的停顿经解析链传导到共享MAC接收路径。
- 集成中修复两个新增真实缺陷：给客户端的接收时刻取自寄存输出，比应答首字节晚一拍致T4恒为0、RTC判据失败；共享构建器17个VL槽位容纳不下时务VL。
- 校验脚本修正三处期望：服务计数按"实际产生应答的用例"而非全部用例计算（50个SNMP向量中6个异常请求按协议静默）；时务请求用例不带GMII输入，注入帧数与用例数相差1；十六进制观测值加前缀以便独立解析。
- 原315场景RTL回归 `build/logs/rtl_008` PASS；13份冻结核心、main及原稳定标签未改动。管理族eLinx综合与VO复验仍NOT RUN。

## 2026-10-14：管理服务系统集成闭环（SNMP over 真实MAC）

- `build/logs/mgmt_012` PASS：16 VL业务回环与专用管理VL共用真实冻结MAC及共享帧构建器，46个输出帧、6381线字节逐字节匹配独立Golden；管理VL BAG最小139969周期、业务VL 145747周期（要求125000）；GMII输入首字节至输出首字节2.880至48.256 µs。
- 新增 `rtl/afdx_service_message_fifo.v`、`rtl/afdx_service_tx_arbiter.v`、`rtl/afdx_management_rx_demux.v`、`rtl/afdx_stage2_mgmt_top.v`，以及对应的独立Golden生成器、运行与校验脚本。
- 集成中修复三个真实缺陷：服务FIFO仅在空闲状态接受字节，首字节后死锁并背压整条接收链（55帧中49帧被MAC丢弃）；管理BAG原设100 µs属非法AFDX BAG被构建器拒绝，改用最小合法1 ms；集成顶层 `biz_vlid` 被接收解析器与回环队列双重驱动产生未知值，使构建器 `desc_legal` 未知、业务描述符被静默丢弃。
- 校验脚本修正两处期望：线帧VLID改为取DA低两字节；解析器拒绝计数按Golden推导（共享MAC上两个解析器均观察全部线帧）。
- 原315场景RTL回归 `build/logs/rtl_007` PASS；13份冻结核心、main及原稳定标签未改动。

## 2026-10-14：正式路径完整VO网表回归闭环

- 正式路径真实GUI综合数据库导出的功能VO完成315场景完整网表回归：`build/logs/netlist_001` 退出码0、Errors 0、Warnings 0，295个外部TX帧/22840字节、296次应用bank提交、308条PSN决策、289个BAG间隔（最小最大均125003周期）和256帧SN回绕全部由独立脚本从冻结Golden重建比对。
- 新导出VO（`b9710b64…`）与归档V1.0 VO（`7c0a4e00…`）仅`// DATE`横幅不同，规范化SHA-256一致；两次运行的五份外部行为CSV与Golden清单哈希完全相同。
- `scripts/verify_v1_netlist.py` 扩展支持当前runner schema，新增导出链、输入快照、Golden清单、归档参考运行哈希校验及行为等价交叉检查。
- 原始证据归档`D:\FPGA\AFDX_archive\stage2_evidence_20261014`（36个文件及SHA-256清单）。未修改冻结核心，未更新main或创建稳定标签，`POST_SYNTH_TIMING`与`EQ6_NATIVE_NETLIST_EQUIVALENCE`保持NOT VERIFIED。

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

- 16VL完整GMII收发RTL闭环及独立Golden通过；已测负载Payload183.91Mbps，GMII首入至末出60.44us，未推广为任意负载最坏情况。
- 真实GUI综合0Errors/29Warnings：14677LUT、4354FF、112Memory、22IO；VO已导出，完整新VO回归尚未执行。
- SNMPv1单varbind MIB模块52场景PASS，SNTPv4客户端19场景及真实1秒超时PASS；网络系统集成继续开发。
- V1 RTL回归源码清单固定为实际16份基线输入，防止未使用的发展模块在长期测试期间造成provenance混淆；006完整315回归和独立核验PASS。

- 16VL共享帧构建器接真实B0 MAC：4097帧独立Golden PASS，保持每VL真实1ms BAG，发送端持续Payload实测188.74 Mbps；系统性能尚未验收。
- 新增125MHz NTP Q32.32 RTC时基和四时间戳运算，14个独立有理数Golden检查点PASS；网络SNTP仍待集成。

- 核对2026官方指南及FAQ；确认八端口ready可不参与握手，帧边界范围保留工程约定。
- 正式路径真实VO已导出，315场景完整网表回归运行中，未提前标PASS。
- 新增16VL独立SN门控及4293帧独立Golden验证；原315场景RTL回归PASS。尚未集成多VL系统。
- V1 eLinx输入固定为原16份canonical文件，避免新发展模块改变V1构建清单。

