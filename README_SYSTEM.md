# V1.0正式系统候选工程：完整阶段1

官方八端口语义仍待答复；本工程保留团队GMII候选契约，不替换原生产AFDX_top。125MHz、真实125000周期BAG、独立本端SN及256帧回绕不变。协议限制与缓存结构见原README和新的《阶段1_V1.0正式系统验收与交付报告.md》。原阶段1综合冒烟报告保留为历史快照。

## 复现

需Python 3.10+、ModelSim 2020.4及可用仿真许可。通过MODELSIM_BIN配置安装位置，通过MGLS_LICENSE_FILE配置许可。源码编译只使用本包冻结核心，不需要上游工程。

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py runs/rtl_001
```

rtl_NNN由runner自动选新编号，核验命令换成实际打印目录。该模式验证内部实际app逐字节事务以及八端口外部Golden。

真实综合网表复现使用包内`evidence/netlist_001`的原VO、原语库、只读观测映射、TB和完整Golden，编译清单不含生产RTL：

```powershell
python scripts/replay_v1_netlist.py --load-only
python scripts/replay_v1_netlist.py
```

第一条只核查迁移后的本地编译/加载，不冒称完整时钟仿真。第二条执行完整315用例，可能耗时数小时；确保没有另一份验收正在运行再执行。内部计数部分被综合优化，真实网表以实际应用RAM提交、保存的长度/原接收SN、实际PSN及外部完整帧Golden验收；不伪造被优化的计数。最终外部Payload也来自真实SN门控后的应用缓存。

## 演示

打开实际完整网表运行的WLF，查看rx_valid/rx_data、tx_valid/tx_data、obs_psn、obs_committed及缓存busy。第一业务输入SN77，本端发送SN1，Payload相同且FCS重新生成。坏协议/坏FCS/异常SN无业务回应，恢复帧产生正确回送；压力保留六帧、容量丢弃一帧并恢复。reset取消待发业务，之后建立新的SN基线。

包内elinx/AFDXV1是可迁移的EPR/源码；evidence/elinx_001及eda_export_001保存实际GUI数据库、25条Warning审计和真实VO来源。日志、CSV、Golden、WLF、性能样本和SHA-256都保留。Git bundle提供字节保持的恢复点。

## 独立状态

综合功能、原语模型功能、时序、器件原生等价性和引脚适配分别验收。功能VO使用Stratix兼容模型，不证明EQ6原生等价性。33个组合环报告项未作最终STA证明；POST_SYNTH_TIMING、EQ6_NATIVE_NETLIST_EQUIVALENCE及物理fit仍未验证。八端口rx_ready按团队契约忽略、tx_ready固定0，只有这两个ready存在相应未用/常量告警；真实rx_data/rx_valid及tx_data/tx_valid有协议收发能力。

100Mbps、最坏1–2ms时延、抖动及多VL/SNMP/615A/RTC不能从本单VL数据集推导为PASS。性能JSON只记录实际功能仿真样本与端点，保留压力排队风险。未执行Implementation、Bitstream或下载；阶段1结束后等待队长审批，不自动进入阶段2。
