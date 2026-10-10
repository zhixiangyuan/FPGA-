# 阶段5 官方VO教程适用性与B1接续审查

审查日期：2026-10-10。结论：保留自研MAC；B0已经取得的RTL、eLinx综合和功能网表PASS仍有效。B1继续采用已实测成功的综合后功能网表路径；本轮不运行Implementation、不生成Bitstream、不下载硬件。

## 资料与版本

- 管理员提供的文档（官方来源由队长确认）：`C:\Users\袁志祥\Downloads\.vqm文件和.vo文件生成与使用20230605.docx`。内部版本V0.0.2，日期2023-06-05，变更说明“根据2.1.7新版本实测修改”。SHA-256：`2998e4437d297a9c55c7b669283cb907c4efdd732b959e1c86943a8fcf110ea8`。
- 文档副本、正文、截图、关系索引和哈希保存在 [official_vo_20230605](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/official_vo_20230605/source.json)。原DOCX未修改。
- 本机eLinx可执行文件FileVersion/ProductVersion为3.0.7.0，`data/version.ini`标记3.0.7、Build 1/22/2025。
- 本机UG102为`UG102_eLinx_Design_Suite_User_Guide_ehiway_v2024.9.pdf`。相关页的文本记录见 [ug102_matching_pages.json](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/official_vo_20230605/ug102_matching_pages.json)。

教程截图使用NCO示例，项目器件显示EQ6HL130/CSG484；本项目为EQ6HL45/CSG225。3.0.7高于教程所述最低2.1.7版本，但不能据此断言文件目录、原语或器件映射完全相同。

## 官方教程说明的流程

| 对象 | 教程证据 | 能证明什么 | 本项目适用边界 |
|---|---|---|---|
| VQM | §1定义为可综合网表；§2.1先设顶层、运行综合，在`project.runs/synth_1/backup`寻找VQM | 综合网表可用于模块交付和重新综合 | B1先取得真实GUI综合VQM与资源报告；实际路径以3.0.7生成结果为准 |
| VQM替换源码 | §2.2移除需替换模块的源码，加入VQM；§3要求保留MIF/HEX初始化依赖 | 这是网表交付/复用方式 | 本轮不移除已验收RTL、不替换MAC，不为取得VO而改变生产代码 |
| VO生成 | §4.1添加`EDA_SIMULATION_TOOL "ModelSim (Verilog)"`，勾选Generate SDF File，运行Implementation布线，VO位于`imple_*` | 教程明确描述布线后VO生成路径 | 涉及布局布线，超出当前授权；不执行此分支 |
| 关闭SDF回注 | §4.1注释`initial $sdf_annotate(...)` | 可以使用该结构网表做不加载该SDF的功能检查 | 不能因此声称Setup/Hold或布线后时序达标；保留原始产物，若以后采用则仅修改仿真副本并记录差异 |
| 保留SDF回注 | §5说明保留annotation并提供延迟文件 | 可进行含延迟模型的仿真，前提是实际注释文件正确加载 | 文中示例是`.sdo`，末段却写`.vdo`；扩展名表述不一致。必须检查实际文件是否为SDF格式、作用实例与回注日志，不盲目套用文件名 |
| ModelSim使用 | §4.2编译TB和VO、选择TB、ps分辨率、添加eLinx库 | VO需要正确原语库和仿真入口 | B1脚本使用独立work库、1 ps分辨率；只编译实际VO、原语库和TB，保留日志/WLF/哈希 |

UG102的印刷第42页（PDF第50页）明确提供`Flow → Run Synthesis`；印刷第45～47页（PDF第53～55页）区分Synthesis、Implementation、Generate Bitstream，并说明启动后级流程会自动运行前级。印刷第100页（PDF第108页）把Generate SDF File列在Implementation设置中。因此本轮只启动Synthesis；不点击Run Post-Implementation Simulation或任何后级流程。

## 与B0已通过流程的对比

| 路径 | 实际产物和验证 | 适用场景 | 不能证明 |
|---|---|---|---|
| B0：GUI综合→EDA Writer `--functional=on`→ModelSim | GUI目标EQ6HL45/CSG225；资源1475 LUT、682 FF、12 memories；功能VO无SDF回注；B0真实网表回归PASS | 验证综合后结构功能、CRC、FIFO、GMII和错误恢复；无需运行Implementation | 原生EQ6模型等价性、Setup/Hold、布线后时序、硬件性能 |
| 2023教程：综合→Implementation→VO/SDF→ModelSim | 布线后VO；按是否保留annotation决定加载SDF | 在另行获批后取得布线后模型，并核查延迟回注 | 仅有VO文件或仅注释SDF后PASS，仍不能证明时序达标或完整AFDX合规 |

B0导出命令和工具结果见 [functional_export.log](D:/FPGA/captain_integration/stage5B0_selfmac_20261010/evidence/gui_success_001/functional_export.log)。它使用本机eLinx安装目录附带的Quartus兼容EDA Writer，实际日志选择`EP1S80F1508C6`，VO头部也标记该器件，且包含Stratix原语。教程没有给出这条综合后命令，也没有解释EP1S80与EQ6的等价映射；因此这条路径的依据是本机B0实测成功，不能升级表述为“官方已确认EQ6原生模型等价”。

B0 [acceptance_004](D:/FPGA/captain_integration/stage5B0_selfmac_20261010/runs/acceptance_004/summary.json) 的PASS保留，其范围仍是功能里程碑。`POST_SYNTH_TIMING`与`EQ6_NATIVE_NETLIST_EQUIVALENCE`继续`NOT VERIFIED`。此教程不要求改用TripleSpeedEthernet IP；本轮没有生成或调用厂商MAC IP。

## B1本轮接续准备

生产RTL未修改，B0/B1项目源码哈希与已冻结清单一致。当前独立工程只有EPR和源码/约束目录，尚无GUI综合QPF/QSF、成功报告、数据库或VQM；B1的综合和网表验收仍未执行。

本轮只修复新增自动化脚本：

1. `run_b1_netlist.py`改用与TB一致的`DUT_IS_NETLIST`宏，防止网表运行输出错误的RTL结果标签；增加1 ps仿真分辨率，使用同一Python生成Golden。发现活动SDF annotation时停止，保留模型并报告范围。
2. `export_b1_functional_netlist.py`增加只读预检，导出前必须确认GUI综合成功、真实顶层/器件/封装、独立源码路径及哈希；不通过则不启动EDA Writer。
3. `write_current_status.py`改为读取最新真实运行summary、综合成功预检和网表运行结果，不再硬编码历史回归PASS或综合/网表NOT RUN；当前结果仍为等待GUI综合，未产生新的功能PASS。
4. 脚本修改前版本已归档。ModelSim对网表TB宏分支的**编译检查**PASS，未执行网表仿真，不作为B1功能网表PASS。记录见 [validation.json](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/official_vo_20230605/tb_compile_001/validation.json)。当前只读预检因缺少QPF/QSF而BLOCKED，见 [b1_preflight.txt](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/evidence/official_vo_20230605/b1_preflight.txt)。

## eLinx人工接力步骤

1. 在eLinx的 **Open Project** 对话框中选择 [AFDXNetwork.epr](D:/FPGA/captain_integration/stage5B1_single_vl_20261010/runs/elinx_001/AFDXNetwork/AFDXNetwork.epr)。UG102 §2.2（印刷第12页/PDF第20页）说明Open Project打开EPR文件；本轮不使用此前无法输入的Tcl Console。
2. 在 **Project Summary** 确认项目AFDXNetwork、Top module `afdx_network_tx_top`、器件EQ6HL45、封装CSG225。Sources应包含10个生产RTL快照；Constraints应包含`clock_125mhz.edc`，内容为8.000 ns内部时钟。若显示不一致，先返回实际信息，不直接更换器件或修改RTL。
3. 点击 **Flow → Run Synthesis**，等待结束。无需添加教程中的SDF选项，也不要运行Implementation。
4. 完成后查看 **Project Summary / Design Runs** 的Synthesis状态，并查看 **Log → Synthesis** 和 **Messages**。正确结果应为Synthesis Complete或Successful；记录errors/warnings。Implementation应仍为Not started或工程未创建该run。出错时保留生成目录和日志。
5. 回复“综合完成”或报出错误。无需移动工程或手动改QSF；Codex会直接读取本目录生成的真实产物，归档资源/VQM/数据库，执行已批准的功能VO导出和ModelSim网表验收，再更新B1完整报告。

如果3.0.7无法打开这个EPR，停止该操作并报告错误；不要新建到B0/原工程目录。当前没有执行Computer Use点击、综合、Implementation或下载。

## 最终边界

```text
SELF_MAC_ROUTE = RETAINED
STAGE5B0_RESULT = PASS (existing verified functional scope)
B1_PROTOCOL_RTL = PASS (existing evidence retained)
B1_REAL_MAC_GMII = PASS (existing evidence retained)
B1_ELINX_SYNTHESIS = NOT RUN
B1_POST_SYNTH_FUNCTIONAL_SIM = NOT RUN
POST_SYNTH_TIMING = NOT VERIFIED
EQ6_NATIVE_NETLIST_EQUIVALENCE = NOT VERIFIED
STAGE5B1_RESULT = BLOCKED_PENDING_ELINX_AND_NETLIST
```

若后续必须走教程的Implementation/SDF分支，将先提交独立工程、约束/I/O预算、资源和器件风险、回退与验证方案，等待队长批准。当前不需要为取得B0路径的功能VO扩大授权。
