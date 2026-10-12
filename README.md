# AFDX V1.0 校赛阶段1保底工程

这是独立分支 `candidate/gmii-v1` 上的团队候选八端口实现，未替换冻结生产AFDX_top，不宣称官方评测兼容或完整全国赛功能已完成。

## 运行与演示

需Python 3.10+、ModelSim 2020.4及可用仿真许可。默认ModelSim位置为 `D:\FPGA\Modlesim20.4\ModelSim20.4\win64`；其他安装位置通过环境变量 `MODELSIM_BIN` 指定，许可位置可用 `MGLS_LICENSE_FILE` 指定。

在工程目录执行：

```powershell
python scripts/run_v1.py
python scripts/verify_v1.py runs/rtl_001
```

`run_v1.py`自动选择下一个空闲rtl_NNN运行目录；第二条命令应换成第一条打印的目录。它使用本目录 `vendor/frozen` 的13份核心源码，不依赖上游工程作为编译输入；原路径只作存在时的可选完整性核查。新日志不会覆盖已有证据。ModelSim中的 `sim/tb_v1_echo.sv` 是完整演示入口，Golden与WLF/CSV自动生成。

示例：第一帧外部RX SN=77，实际应用交付SN=77，本端发送SN=1；随后回送原Payload并生成新的协议帧及FCS。由此证明真实业务来源、SN检查、应用缓存和独立发送序号链路，而不是固定ROM发送或MAC层回环。

## 候选线字节契约

- clk=125MHz，reset高有效、同步；保留八端口原名/方向/位宽（22位I/O）。
- rx_valid持续为1期间每周期一个新线上字节，包含7字节55、SFD d5、客户帧和4字节小端FCS。rx_valid=0结束帧，帧内不允许用低valid暂停字节；测试给至少12周期IFG。
- tx_valid为真实B0 GMII TX EN，tx_data包含上述完整线帧；IFG不是有效数据。
- tx_ready固定0，rx_ready不影响输入或回送；测试会主动翻转它验证这一约定。
- 八端口没有PHY_ER，边界层将gmii_rx_er置0，不能从此接口证明PHY错误输入能力。坏FCS及合法FCS的协议错误分别测试；B0独立回归保留其原PHY错误覆盖。
- 固定单VL工程profile与B2-4相同，Payload为1..1471字节，Padding和SN规则沿用已批准核心；SN0不交付普通业务，不回送。

路径为：八端口RX→B0 MAC→B2 Parser/SN门控→应用双bank原子队列→B1独立SN发送器→B0 MAC→八端口TX。应用队列每bank1471字节，最后字节提交，收到msg_done后释放；BAG等待期间产生真实缓存背压。应用/Parser/MAC各双bank，总压力场景保留6帧、丢弃第7个压力帧，然后恢复。

## 范围和限制

此阶段验证125MHz/125000周期真实BAG、256帧SN回绕及外部输出Golden；125MHz每周期8位的线节拍不等于已验证100Mbps。多VL、冗余、SNMP、615A、RTC、100Mbps/最坏时延/抖动留待后续完整任务包。时序、EQ6原生等价性、物理引脚fit仍未验证。不得将资源余量或综合冒烟成功视为上述指标PASS。

阶段1只进行RTL验收与一次GUI综合冒烟，没有执行候选V1真实VO完整测试、Implementation、Bitstream或下载。冻结B2-4网表PASS不能替代候选V1网表验收。官方数据层次、帧边界、节拍及扩展仍待答复；本契约是队长批准的独立分支实验约定。

## 文件

- `rtl/`：新边界、应用事务队列、候选AFDX_top。
- `vendor/frozen/`：冻结B0/B1/B2及FIFO原样快照。
- `sim/`、`scripts/`：ModelSim完整TB、独立Python Golden、运行/核验/综合审计脚本。
- `FROZEN_CORE_MANIFEST.json`：上游与本地快照哈希。
- `runs/`：每次原始证据，保留初次未连接诊断告警记录和清理后的PASS。
- `delivery/V1.0/`：独立可复验包；`delivery/V1.0.zip`：相同包的压缩归档。

综合工程中只使用Run Synthesis；保存的EPR明确目标EQ6HL45/CSG225、8ns约束。包内`elinx/AFDXV1`用于独立重建工程，`evidence/`保存实际GUI与仿真证据，二者分开以避免旧绝对路径数据库被误当作迁移后的新结果。
