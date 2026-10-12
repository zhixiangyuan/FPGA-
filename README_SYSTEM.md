# V1.0阶段1系统复现说明

本仓库保存V1.0候选工程源码、Testbench、独立Golden快照、eLinx工程配置、验收报告和恢复记录。完整真实VO验收包含厂商器件模型、综合网表、数据库、WLF和原始运行证据；因许可与体积原因，它作为独立离线归档保存，不在GitHub源码树中分发。归档路径和SHA-256见`RESTORE_POINT.json`。

## RTL功能复现

需Python 3.10+、ModelSim 2020.4及可用仿真许可。可用`MODELSIM_BIN`指定ModelSim安装位置，用`MGLS_LICENSE_FILE`指定许可位置。

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py runs/rtl_NNN
```

第一条命令会自动创建新的运行目录；第二条使用实际生成的目录名。完整RTL验收检查应用端事务和八端口输出Golden。`golden/V1.0_full_vo_315/`保留已验收真实VO测试的315场景向量和对应SHA-256；`scripts/generate_v1_golden.py`可以重新生成测试输入。

## eLinx工程

从`elinx/AFDXV1/AFDXV1.epr`打开候选工程。工程使用EQ6HL45/CSG225、AFDX_top和8 ns约束。重新综合会生成新的本地数据库；原阶段1实际综合的原始证据留在离线归档中，不应把新数据库冒充原验收结果。

## 真实功能VO验收复现

离线归档中包含已验收运行`netlist_001`的VO、Altera原语库、Stratix兼容器件模型、只读探针、Testbench、Golden、日志、CSV和WLF。将离线归档按原结构解压后，可运行：

```powershell
python scripts/replay_v1_netlist.py --load-only
python scripts/replay_v1_netlist.py
```

`--load-only`只编译并加载检查，不执行完整时钟仿真。无参数命令执行315个真实VO场景，会运行数小时。测试只编译真实`.vo`与随归档保存的原语库，不用RTL替代、不使用force。被综合优化的内部计数器不会伪造；验收观察真实应用bank提交、元数据、PSN和外部字节Golden。

## 验收边界

已验证的是125 MHz下团队单VL工程profile的功能链路，不代表官方八端口契约兼容。100 Mbps、官方端到端最坏时延/抖动、Setup/Hold、EQ6原生模型等价性、物理I/O适配和33项组合环风险仍未关闭。压力场景的排队时延不代表官方2 ms指标通过。阶段1未执行Implementation、Bitstream或硬件下载。
