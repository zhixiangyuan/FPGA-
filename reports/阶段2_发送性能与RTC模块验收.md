# 阶段2 发送性能与 RTC 模块验收

以下是模块开发结果，不代表阶段2系统完整通过。

## 16 VL 共享发送构建器

`rtl/afdx_multi_vl_tx.v` 是冻结B1构建器的发展版本。原始SHA-256记录于文件及派生脚本，冻结文件未修改。共享帧构建FSM，16份独立SN及BAG状态；MAC采用真实冻结 `mac_gmii_tx`。目前定向测试按轮转提供事务，应用调度队列和完整多VL接收还未集成。

实际 `build/logs/multi_vl_tx_002` PASS：ModelSim退出码0、Errors0、Warnings0，4097个完整帧、6,250,568个GMII线字节逐字节匹配独立Python Golden。每个VL完整256回绕，BAG最小/最大均125003周期，要求125000周期；中途未提交Payload被reset取消，恢复后发送SN从1开始。失败运行001保留：观测信号被优化，vopt增加仅Testbench只读可见性后重测，无force或Mock。

持续性能窗口只包括reset前4096帧，时钟125 MHz、窗口255,384,928 ns：

| 口径 | 实测 |
|---|---:|
| AFDX Payload | 188.741475 Mbps |
| GMII线字节（前导码/SFD/DA..FCS） | 195.798430 Mbps |
| Ethernet帧（DA..FCS） | 194.771964 Mbps |

统计窗口包含真实每VL BAG及实际空闲时间，未使用仅活跃周期线速代替持续吞吐。证据：`performance.json`、`frames.csv`、`actual_wire.mem`、Golden、WLF和输入/输出哈希。当前仅发送端性能，系统RX→TX延时 NOT RUN；整系统100 Mbps、物理时序和综合资源 NOT VERIFIED。

## RTC 时基和同步运算

`afdx_rtc_timebase.v` 实现 NTP Q32.32 UTC、精确有理数分数累计和独立单调周期计数。根据RFC4330计算四时间戳offset和往返delay；合法应答才能步进UTC，单调计数不受步进影响。SNTP数据报生成与校验由 `afdx_sntp_client.v` 承担并经 `sntp_002` 单元验证；系统接入见 `build/logs/mgmt_016`（《阶段2_管理系统集成验收》），该次交换覆盖一次正常应答，不构成RTC端到端精度或多次交换稳定性证明。

`build/logs/rtc_002` 模块PASS：实际125 MHz、14个Golden检查点、1,375,145周期计时与同步事件，独立Python有理数模型核对UTC、正负offset、delay、非法/超时范围、跨NTP era、reset。量化误差小于1个NTP分数LSB。第一次001观测优化失败保留；002增加Testbench只读可见性后真实通过。

原315场景RTL回归 `build/logs/rtl_003` 及独立Golden `verification.json` PASS，原V1功能和冻结核心保持。

## 33项组合环补充审计

实际 `.map.rpt` 中33项为：1个MAC TX `fire~0`、16个仅名为 `rtl~0..15` 的中间单元、16个IPv4 checksum `fold_once[0..15]` 单元。不是33个独立已定位电路环。校验和RTL表达式是sum→fold_once→fold_twice的前馈；报告无法单凭名称证明最终映射没有环。MAC `fire` 的ready/writable依赖包含状态条件，需在发展版本综合及网表中继续核查。中间16项缺少层级，不能擅自归为RAM旁路或宣布误报。

原报告明确这些单元可能被后续综合优化移除；此提示也不能作为风险已解决证据。当前时序风险仍保留，Setup/Hold和EQ6原生模型等价性均NOT VERIFIED。
