# 阶段2 多 VL SN 模块验收

范围：`rtl/afdx_multi_vl_sn_gate.v` 单模块验证，尚未集成正式收发链路。结论：模块 RTL 和独立 SN Golden 比较 PASS；多 VL 系统、综合资源和 VO 验收 NOT RUN。

16 个连续配置 VL 各自保存完整性 PSN；首次普通帧建立基线，接受 +1/+2，支持255→1，+2计缺号；其他普通SN拒绝业务但更新PSN，SN0控制清零且不交付。未配置VL拒绝且不推进配置VL状态。每VL可配置完整性检查使能，配置只应在业务开始前加载。输入必须已经完整合法并预留在上游bank，门控不负责协议解析或容量预留。

## 实际运行

命令：`python scripts/run_multi_vl_sn.py`。

最终证据：`build/logs/multi_vl_sn_004/summary.json`、`transcript.log`、`actual_sn.csv`、`waves.wlf`、`golden/manifest.json`。ModelSim2020.4，125 MHz/8 ns，退出码0、Errors0、Warnings0。4294向量（含reset事件），4293帧SN决策被独立Python模型逐项核对；每VL256帧完整回绕，另覆盖+2、重复、旧号、异常跳号、异常后恢复、SN0、未知VL、逐字节背压、局部检查关闭和半帧reset。Testbench检查42061个实际应用字节及元数据。

失败证据保留：`multi_vl_sn_001` 是RTL数字字面量词法编译失败；`multi_vl_sn_002` 仿真通过但CSV将无效VL的-1打印为无符号值，独立核验失败，不能作为整体验收PASS。修复Testbench明确有符号输出后，003/004真实重测通过；未放宽Golden。

原315场景回归在 `build/logs/rtl_002` 实际PASS，独立 `verification.json` PASS：295TX/22840线字节、296应用帧/2520应用字节、308PSN决策、256回绕、最小BAG125003周期，缓存/reset/错误恢复要求保持。13份冻结核心未修改。

V1工程生成脚本已改用明确的16份V1输入清单；新增发展模块不会被错误纳入V1源码快照。实际生成 `build/elinx/AFDXV1_004`，16份源码及8ns检查通过；该新构建工程未运行综合，不能写综合PASS。

## 剩余验证

需要接入MAC/协议Parser、按VL应用缓存和发送调度，确认容量预留、协议错误不推进PSN和真实输出。模块测试不能代表双网冗余、128TX/4096RX容量或完整ARINC664P7合规。
