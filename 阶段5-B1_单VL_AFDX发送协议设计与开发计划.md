# 阶段5-B1：单 VL AFDX 发送协议设计与开发计划

日期：2026-10-10  
范围：架构审计、字段/接口冻结建议、实施与验收计划。**本文件不批准也不包含正式 RTL 开发。**

## 1. 结论与本阶段边界

建议在独立的 `afdx_single_vl_tx` 发送层中完成「Payload → UDP/IPv4 → Ethernet/VLID → AFDX Padding → SN → 已验收自研 MAC」。发送层输出一条完整、连续的 Ethernet 客户帧字节流，让阶段5-B0 MAC 负责 GMII 前导码、SFD、FCS 和 IFG。

本阶段只冻结候选协议和接口，不改阶段5-B0源码、冻结的八端口 `AFDX_top`、器件/工程，也不运行综合、Implementation、Bitstream 或硬件下载。单 VL 发送闭环不能代表完整 ARINC 664 Part 7 端系统。

## 2. 依据和证据等级

| 资料 | 能确认的内容 | 限制 |
|---|---|---|
| 本地官方《2026 FPGA赛道选题指南-中科亿海微.pdf》，PDF第4–6页 | 选题一要求围绕 Ethernet MAC 实现 AFDX；列出 UDP/IP、缓冲、发送调度、接收管理和 MAC 等；指南列出100 Mbps、VLID、SN 1–255、有效载荷通常不超过1471字节、总帧长不超过1518字节；给出八端口模板 | 指南没有冻结本项目的 DA/SA、IP/UDP 地址端口、校验和配置、SN=0复位处理、输入Payload边界或八端口帧边界。它是本项目选题依据，不等于完整标准条文 |
| 已批准的《阶段5-A_自研MAC与GMII架构修订.md》第4.2节 | AFDX Padding 位于 Payload 后、SN 前；Padding 与 SN 不计入 IP/UDP 长度；MAC 设为预填充模式，不再在 SN 后补零 | 这是已审核的项目架构决策；仍需在 B1 的独立 Golden 与真实 MAC 中逐字节验收 |
| 阶段5-B0实际生产 RTL 与验收证据 | MAC 客户接口为字节 `tx_data/tx_valid/tx_ready/tx_sop/tx_eop/tx_length/tx_afdx`；真实 TX 缓存一帧、检查长度与 SOP/EOP，完成后生成 GMII 帧；已有独立 CRC、MAC/RX/FIFO仿真及综合证据 | B0 尚无 UDP/IP 构帧逻辑；`POST_SYNTH_TIMING` 和 `EQ6_NATIVE_NETLIST_EQUIVALENCE` 继续为 `NOT VERIFIED` |
| AMD/Xilinx XAPP1130 | 技术参考展示了目的 MAC 由32位常量字段和16位 VLID 组成、帧尾 Padding/SN/FCS次序、SN=0复位语义和 BAG 调度 | 厂商技术说明不是比赛指南，也不能代替当前授权版 ARINC 664 Part 7。其 SN 起始描述与本地比赛指南的1–255表述不完全一致，必须按下文冻结建议处理。[XAPP1130](https://docs.amd.com/api/khub/documents/wnNwXuguJhbeWhCBnpF7pQ/content) |
| RFC 791 / RFC 768；AIM AFDX Programmer's Guide | RFC 791规定 IPv4 首部校验和；RFC 768定义 UDP 长度和校验和，IPv4 下0表示未生成 UDP 校验和；AIM示例帧把 UDP 校验和字段设为0 | RFC描述通用 IP/UDP；AIM 是厂商实现手册，不是 ARINC 规范。UDP checksum=0 是本计划建议的 AFDX profile，比赛指南没有明文冻结。 [RFC 791](https://www.rfc-editor.org/rfc/rfc791.html), [RFC 768](https://www.rfc-editor.org/rfc/rfc768.html), [AIM AFDX Programmer's Guide](https://www.aim-online.com/wp-content/uploads/2023/01/Arinc664_Programmers_Guide.pdf) |

因此，下面的协议字段分为「比赛指南明确」「已有项目架构」「B1工程建议」三类。需要 ARINC 精确条款的内容不能只凭厂商应用说明宣称标准合规；标准正式版本可从 [SAE ARINC 664 Part 7 产品页](https://saemobilus.sae.org/standards/arinc664p7-1-664p7-1-aircraft-data-network-part-7-avionics-full-duplex-switched-ethernet-network)核对。

本地官方选题指南路径为 `D:\FPGA\全国大学生嵌入式芯片与系统设计竞赛'2026FPGA赛道选题指南-中科亿海微.pdf`，本次核对文件 SHA-256：`73E44600D609799A373EB84669BCAA75BBA1F070E84FC2212ACCBA37ED849AFB`。阶段5-A已审核架构路径为 `D:\FPGA\captain_integration\stage5_selfmac_design_20261010\阶段5-A_自研MAC与GMII架构修订.md`。

阶段5-B0真实源码位于 `D:\FPGA\captain_integration\stage5B0_selfmac_20261010\rtl`，FIFO依赖位于同目录 `deps`；ModelSim 2020.4全回归和实际 GUI 综合/网表证据的 SHA-256 记录见该工程的 `evidence\final_manifest.json`。本计划以这些生产RTL接口为准，不用交接文档假设替代当前源码。

## 3. 发送链路和职责

```mermaid
flowchart LR
  APP[业务消息描述符与Payload] --> SCHED[单VL BAG门控]
  SCHED --> TX[afdx_single_vl_tx\nMAC帧字节生成]
  TX -->|DA..SN\n预填充完整帧| MAC[阶段5-B0 mac_gmii_core TX]
  MAC -->|Preamble/SFD + FCS + IFG| GMII[GMII TX]
  GMII --> PHY[仿真PHY环回/抓帧]
  PHY --> RX[阶段5-B0 MAC RX]
  RX --> SB[独立Golden与记分板]
```

| 层 | 负责内容 | 明确不负责 |
|---|---|---|
| 单 VL 发送协议层 | 配置锁存、帧长度计算、Ethernet/IP/UDP首部、IPv4 checksum、Padding、SN、BAG门控、Payload握手和协议错误报告 | GMII时序、FCS、Preamble/SFD、IFG |
| 阶段5-B0 MAC | 完整客户帧缓冲；由 `tx_valid && tx_ready` 接收字节；按 SOP/EOP/长度提交；在预填充模式下保持帧字节；计算并发送FCS、Preamble/SFD和IFG | VLID、IP/UDP、SN、Payload含义、AFDX调度 |
| 独立Golden/TB | 独立生成字段、IP checksum与整帧期望；观察MAC客户字节和GMII线帧 | 不用生产 RTL 函数计算期望，不 force MAC 内部状态 |

### 建议新增模块和文件

| 独立B1文件 | 职责 | 复用/边界 |
|---|---|---|
| `rtl/afdx_ipv4_checksum.v` | 对固定20字节 IPv4 头计算独立可综合的16位反码校验和 | 只负责IPv4头，不处理UDP/FCS |
| `rtl/afdx_single_vl_tx.v` | 描述符锁存、Payload握手、Ethernet/IP/UDP字段发出、Padding/SN追加、MAC帧长度、序号与错误状态 | 直接连接B0的MAC客户接口，不复制2048字节帧FIFO |
| `rtl/afdx_bag_gate.v` | 以实际 `gmii_tx_en` 上升沿为帧开始事件，管理单VL最小发送间隔及jitter诊断 | 与MAC IFG分工；不做多VL仲裁 |
| `rtl/afdx_network_tx_top.v` | 独立可综合/仿真组合顶层，连接新发送层、真实 `mac_gmii_core` 和PHY环回接口 | 不是官方八端口 `AFDX_top`，不自动发测试帧 |
| `sim/tb_afdx_single_vl_tx.sv` | 协议字段、Payload/ready、SN、BAG及错误用例 | 可用可控sink验证模块接口暂停 |
| `sim/tb_afdx_single_vl_mac_loopback.sv` | 新协议发送层经阶段5-B0真实MAC及PHY模型的端到端验证 | DUT包含真实B0 MAC生产RTL |
| `sim/golden/generate_single_vl.py` | 独立生成Ethernet/IP/UDP/Padding/SN/FCS字节向量 | Golden不调用RTL函数 |
| `scripts/run_stage5b1.ps1` | 一键编译、运行新测试、保存日志/WLF/哈希并调用历史回归 | 独立于B0验收入口，使用新运行编号，不覆写历史证据 |

首版保持小而清晰：checksum作为一个纯组合辅助模块；BAG计时器可作为独立模块或与发送状态机合并，不再为每个头字段建立重复FIFO或复杂层间总线。

B1 不再复制帧 FIFO。现有 MAC 的 2048×8 TX 帧存储可容纳最大1514字节客户帧。协议层按 ready/valid 字节流将完整客户帧送入 MAC；MAC 只有接收到合法 EOP 后才开始发送线上帧。这样 Payload 暂停只会暂停装帧，不会让 GMII 帧中途停顿。

## 4. 候选帧格式和字段定义

### 4.1 线上字节布局

```text
7×55 | D5 | DA(6) | SA(6) | EtherType 0800(2)
     | IPv4(20) | UDP(8) | Payload(P) | Padding(Q) | SN(1) | FCS(4) | IFG(至少12 byte-times)
```

前导码、SFD、FCS、IFG由已有 MAC 生成。协议层只提交 `DA` 到 `SN` 的客户字节；不提交 FCS，也不提交 Ethernet 前导码或 IFG。

### 4.2 以太网、VLID和配置

| 字段 | B1建议定义 | 来源/状态 |
|---|---|---|
| DA | `{da_const[31:0], vlid[15:0]}`，所有多字节字段按网络字节序、最高字节先发；32位常量字段由系统配置。技术参考要求目的地址的首字节为组播且本地管理地址，VLID占末16位 | XAPP1130技术参考；比赛指南只列VLID，没有给完整位布局 |
| VLID | 16位配置值，发为 `vlid[15:8]`、`vlid[7:0]`；不从 IP 地址或 UDP 端口推导 | 项目配置，不在RTL写死 |
| SA | 48位配置的单播发送接口地址 | 具体编码由队伍/系统集成配置提供；不由本模块自动猜测 |
| EtherType | 固定 `16'h0800`，随后是 IPv4 | B1子集不含 VLAN |
| 源/目的 IPv4 | 32位配置，按高字节先发；目的 IP 与 VLID分别配置，不假定两者编码相同 | 配置值由测试/上层提供 |
| UDP源/目的端口 | 16位配置，网络字节序 | 不硬编码常量到业务逻辑 |

### 4.3 IPv4和UDP头

| 字段 | B1候选值/算法 | 长度口径 |
|---|---|---|
| IPv4版本/IHL | `8'h45`（IPv4、20字节无选项） | 固定20字节 |
| DSCP/ECN | `8'h00` | 固定建议值，需配置时再扩展 |
| Total Length | `28 + P` | 20字节IPv4头 + 8字节UDP头 + Payload；不包含 Padding、SN、FCS |
| Identification | `16'h0000` | B1禁止分片的候选配置；是否要逐帧递增属于待确认工程策略 |
| Flags/Fragment Offset | `16'h4000`（DF=1，偏移0） | B1不实现分片/重组 |
| TTL | 8位配置，测试基线候选值为1 | AIM示例中有 TTL=1，但本地比赛指南没有指定，不能写成官方要求 |
| Protocol | `8'h11`（UDP） | 固定 |
| IPv4 Header Checksum | 每帧实际计算 | 先把checksum字段置0，对20字节首部按16位大端反码和折叠进位后取反；仅保护 IPv4 首部 |
| UDP Length | `8 + P` | 8字节UDP头 + Payload；不包含 Padding、SN |
| UDP Checksum | `16'h0000` | B1建议采用 AFDX IPv4无UDP校验和profile；RFC768允许IPv4用0表示未生成，AIM示例也使用0。本地比赛指南未明示此profile，正式写RTL前应在队长批准时冻结 |

IPv4和UDP头长度、校验和按网络字节序写入。Golden必须独立重算IPv4头校验和；校验规则为首部完整16位字之和（含已填checksum）折叠后为 `16'hFFFF`。UDP checksum为0时不做“与Payload匹配的UDP校验和”检查，但要断言字段确实为0。

### 4.4 Payload、Padding、SN和MAC长度

比赛指南给出的典型 AFDX Payload 范围为1–1471字节。令 `P=Payload字节数`：

```text
P合法范围       = 1..1471
Q               = max(0, 17 - P)
MAC客户帧长度    = 14 + 20 + 8 + P + Q + 1 = 43 + P + Q
DA到FCS帧长度    = MAC客户帧长度 + 4
```

`Q`个零字节跟在UDP Payload后，`SN`紧接Padding，`FCS`紧接SN。Padding和SN不属于IPv4 Total Length或UDP Length。短业务Payload时，AFDX层负责补齐；MAC在 `tx_afdx=1` 预填充模式下不再补零。这样不会出现 MAC 把零补在SN后面的错误。

| P | Q | IPv4 Total Length | UDP Length | 提交给MAC的 DA..SN 字节数 | DA..FCS字节数 |
|---:|---:|---:|---:|---:|---:|
| 1 | 16 | 29 | 9 | 60 | 64 |
| 16 | 1 | 44 | 24 | 60 | 64 |
| 17 | 0 | 45 | 25 | 60 | 64 |
| 18 | 0 | 46 | 26 | 61 | 65 |
| 1471 | 0 | 1499 | 1479 | 1514 | 1518 |

`P=0`和`P=1472`在B1入口拒绝。线缆计数如需显示GMII字节，包括8字节前导码/SFD；IFG作为帧间时间单独记录。比赛指南的总帧长口径按Ethernet DA到FCS理解，报告中不得把前导码或IFG混入1518字节上限。

### 4.5 SN状态建议与资料差异

比赛指南写明序号范围为1–255；AMD/XAPP1130另说明SN=0用于发送端复位状态，普通序号在255后回到1。为服从比赛指南给出的正常业务范围，建议B1先采用：

1. `next_sn` 复位值为1，业务帧只使用1..255；
2. 接收一个合法发送描述符时锁存 `active_sn=next_sn`，将它作为Padding后的最后一个 MAC 客户字节；
3. 只有 MAC `tx_done`（FCS最后一字节已发出）后推进状态：`255 → 1`，否则 `next_sn = active_sn + 1`；
4. 入参错误或 MAC `tx_reject` 不推进 SN；共享 reset取消当前帧并把序号恢复到1；
5. B1不自动发送SN=0复位通知帧。是否需要单独的SN=0通知帧，须由正式指南答疑/标准依据另行冻结。

这个建议避免测试期待的正常SN越出指南所列的1–255范围，但不能宣称它已经解决了标准对发送端复位通知的全部要求。独立Golden必须覆盖 `1,2,...,254,255,1` 和reset后首个业务帧；测试发送256个最短Payload即可真实覆盖回绕，无需 force 内部计数器。

### 4.6 FCS和帧长度职责

协议层向MAC提交的 `tx_length` 是DA到SN的字节数，范围60–1514。`tx_afdx=1`表示已经完成AFDX Padding；`tx_sop`只随DA字节，`tx_eop`只随SN字节。MAC为客户帧计算FCS，并负责Preamble/SFD、GMII连续发送与IFG。FCS覆盖DA到SN，包括AFDX Padding和SN；不覆盖Preamble、SFD或IFG。这个职责分工复用B0已验证实现，禁止协议层重复补零或添加自己的FCS。

## 5. 与真实阶段5-B0 MAC的接口契约

`mac_gmii_core` 的真实 TX 客户接口为：

| 信号 | B1连接/语义 |
|---|---|
| `tx_data[7:0]` | 依次提交DA、SA、EtherType、IPv4、UDP、Payload、Padding、SN |
| `tx_valid` / `tx_ready` | 同拍为1才接受当前字节；阻塞时当前数据和全部帧元数据保持稳定 |
| `tx_sop` | 仅在DA字节的有效握手拍置1 |
| `tx_eop` | 仅在SN字节的有效握手拍置1 |
| `tx_length[15:0]` | 本帧DA..SN总字节数，在SOP时被MAC锁存；B1仍保持整帧稳定 |
| `tx_afdx` | 整帧固定为1，告诉MAC不要在SN之后再添加Padding |
| `tx_done` / `tx_reject` | `tx_done`表示MAC已发出FCS末字节；`tx_reject`表示帧未被接受/因契约错误被拒绝 |

建议的新模块接口分成两段：

| 接口组 | 候选信号 | 契约 |
|---|---|---|
| 消息描述符 | `msg_valid`, `msg_ready`, `payload_length`, `VLID`, `src/dst MAC`, `src/dst IP`, `src/dst UDP port`, `TTL`, `BAG`配置 | `msg_valid && msg_ready`时一次性锁存本帧配置；Payload长度按1..1471字节解释 |
| Payload字节流 | `payload_data[7:0]`, `payload_valid`, `payload_ready`, `payload_last` | 只在描述符握手后传Payload；最后一字节同时置`payload_last`；暂停期间源端保持数据 |
| MAC客户流 | B0原生TX接口信号 | 不改MAC接口；由`afdx_single_vl_tx`生成；ready=0时数据、SOP/EOP、长度和AFDX模式逐拍保持 |
| 状态 | `msg_done`, `msg_error`, `error_code`, `late_count`（如启用调度诊断） | 每个描述符只有一个最终状态；错误帧不发送，不推进SN |

B0 MAC只有一个TX帧存储bank，所以B1 v1一次只处理一个消息描述符。`msg_ready=0`期间上游必须保留下一条描述符及Payload，不允许假定MAC能缓存多帧。协议层直接把生成字节写入B0 FIFO，不新建第二个整帧缓存。Payload途中出现不匹配的`payload_last`、实际长度不足或超出声明长度时，协议层报告错误并让MAC按既有短帧/长度检查拒绝；任何情况下都不得把部分帧提交到GMII。

`tx_done`之后推进SN；`tx_reject`、描述符无效、Payload长度错误或未完成帧reset都不推进。B0 MAC完成和拒绝信号已在真实RTL中实现，B1只复用它们，不修改B0源码。

## 6. BAG调度

单 VL 仍需限制带宽。技术参考将BAG定义为同一VL连续帧开始时间之间的最小间隔，并给出常见配置1、2、4、8、16、32、64、128 ms；系统集成配置决定具体值。B1建议增加单VL门控：

- 测量`gmii_tx_en`上升沿作为实际帧开始事件，不从Payload描述符时间或`tx_done`猜测帧间间隔；
- 下一次GMII帧开始不得早于 `last_start + BAG`；B0 MAC自己完成至少12 byte-times IFG；
- 一个VL没有待发消息时不发空帧；等待期间上游保留消息描述符；
- 测试使用1 ms BAG、125 MHz仿真时钟（125,000个时钟），仅证明计数和调度逻辑正确，不代表100 Mbps或板级时延达标；
- 记录请求到达、允许发送槽和实际GMII开始时间，检查不早发及配置的最大jitter。完整BAG/jitter限值仍需依据具体VL配置和正式标准。

若Payload未能及时供给，B1可以晚于允许槽发送或报告过期；不会通过追赶方式连续突发补发。计划中的第一版选择“晚发并计数，不丢业务消息”，但需要队长确认过期策略。XAPP1130的BAG/jitter说明仅作为技术参考，不替代比赛指南或当前授权版ARINC条款。[XAPP1130 BAG/jitter章节](https://docs.amd.com/api/khub/documents/wnNwXuguJhbeWhCBnpF7pQ/content)

## 7. 正式八端口 `AFDX_top` 的帧约定风险

本地比赛指南模板包含 `tx_data/rx_data`、`tx_valid/rx_valid`、`tx_ready/rx_ready`，但没有 `tx_sop/eop`、帧长度、消息请求、VL配置或Payload长度。模板端口注释没有定义 `tx_data` 是应用Payload、IP包、Ethernet客户帧还是GMII线上字节；也没有定义帧间valid低电平是否为边界。因此，仅靠八端口不能可靠地确定变长帧的起点、终点和长度。

B1执行建议：

1. 保持正式八端口名称、方向和位宽原样，不为单 VL 测试添加端口，也不自动发送固定测试帧；继续沿用已冻结的 `tx_ready=0`、`rx_ready`不参与内部收发判定。ready约定不会补出缺失的帧边界；
2. 新建独立 `afdx_network_tx_top`/`tb_afdx_single_vl_tx`，使用上节的描述符和Payload流，实例化真实B0 MAC进行协议验证；
3. 将`afdx_single_vl_tx`作为可复用子模块，暂不接入正式`AFDX_top`；
4. 进入正式系统集成前，先冻结官方八端口每个valid字节表示的层次、帧边界规则、接收方向数据来源和测试方法。没有这些定义时，正式八端口接口测试不能证明完整AFDX发送可达。

独立验证顶层的 PASS 只证明协议子模块+MAC测试链路，不等于正式 `AFDX_top` 已接入或选题一通过。

## 8. ModelSim自动化验收计划

### 8.1 Golden生成

新增独立 `sim/golden/generate_single_vl.py`：用标准Python整数运算独立生成IPv4 16位反码checksum，UDP校验和按B1 profile写0，按配置写MAC/IP/端口，补 `Q=max(0,17-P)` 后追加SN。Golden不import RTL、不调用`mac_crc32_byte`；FCS用独立`zlib.crc32`按Ethernet字节序生成，并检查已有固定向量。每个运行记录Golden文件、配置、来源哈希和ModelSim版本。

### 8.2 自动测试矩阵

| 类别 | 测试 | 必须自动断言 |
|---|---|---|
| 长度边界 | P=1、16、17、18、1471；拒绝P=0、1472；另加随机长度 | Q、IP Total Length、UDP Length、MAC `tx_length`、DA..FCS大小均与独立公式一致 |
| 地址/字段 | VLID如`16'h1234`、DA常量、SA、IP地址/UDP端口、多组TTL | 目的MAC末两字节为`12 34`；字节序、组播/本地位和源单播规则准确；配置变化不串帧 |
| IP校验和 | 静态向量、随机源/目的地址及P | 与独立Golden匹配，含checksum字段反码和为`FFFF`；只改IP字段会导致测试失败 |
| UDP字段 | 所有P边界与随机Payload | UDP长度准确；checksum字段恒为`0000`；Padding/SN不进入UDP长度 |
| Padding/SN | P=1、16、17、18、1471 | 字节顺序严格为Payload→Q个0→SN→FCS；SN后不出现新Padding |
| SN | 发出1..255后再发1；reset后首个业务帧 | 仅在`tx_done`后递增，255回1；reject、输入错误不消耗SN；reset按冻结策略返回1 |
| Payload握手 | 字节流首/中/末拍暂停、valid空拍、ready=0多拍 | valid未握手时payload和MAC输出稳定；不重字节、不丢字节、不乱序；有效帧内GMII连续 |
| BAG/连续请求 | 连续保持下一消息请求，配置BAG；payload供给及时与延迟两组 | 实际GMII开始间隔不小于BAG；不发空帧、不追赶突发；统计迟到但只按批准策略处理 |
| 错误与reset | 无效长度、早/晚`payload_last`、MAC reject、reset在装帧/线上发送时 | 错帧不以完整合法帧出现在GMII/RX；状态可恢复；序号与错误计数符合策略 |
| 真实B0 MAC闭环 | 新协议TX→原B0自研MAC→PHY模型环回→原B0 MAC RX | `rx_data/rx_length/rx_sop/rx_eop`与客户帧Golden逐字节一致；实际GMII抓帧与完整wire Golden（含FCS）一致 |

单元层可以用可控ready接收器检查协议生成器的暂停行为；**系统级闭环必须实例化实际B0 MAC RTL**。单元sink PASS不能替代真实MAC闭环。TB不force内部状态，不伪造GMII输出，不通过删除断言通过。

### 8.3 一键回归与产物

新增独立B1入口，在新运行编号目录中依次运行Golden生成、协议单元测试、真实B0 MAC闭环和历史回归。ModelSim使用SE-64 2020.4及独立work库。每次保存：

- 命令、工具版本、全部RTL/Testbench/Golden SHA-256；
- 原始Transcript、PASS/FAIL摘要、真实WLF和GMII TX/RX字节转储；
- 每次失败、修复和修复后全量回归，不覆盖旧运行目录；
- `STAGE1_REGRESSION`、`STAGE2_REGRESSION`、`STAGE3B2_RESULT`与`STAGE5B0_MAC_REGRESSION`分别报告。

阶段5-B0既有源码与报告只读复用；不得为B1修改B0 MAC来绕开接口问题。

## 9. eLinx与综合网表后续验证

只有B1 RTL自动测试和真实B0 MAC闭环全部PASS后，才建议启动独立N阶段：

1. 在新工程中实例化B1发送层和阶段5-B0 MAC，综合顶层暴露真实协议配置、Payload和GMII接口；不加入空逻辑或`keep`制造资源；
2. 仍使用EQ6HL45/CSG225并核对GUI源文件哈希、top、约束和RAM资源；
3. 报告 eLinx synthesis 的资源、警告、实际数据库和网表；
4. 如果官方功能网表导出可用，ModelSim DUT只编译导出的真实网表与原语库，再跑边界帧、校验和、SN回绕、BAG、reset和数据一致性用例；RTL仿真与网表仿真分开判定；
5. `EQ6_NATIVE_NETLIST_EQUIVALENCE` 和 `POST_SYNTH_TIMING`继续作为独立状态。B0报告中的EP1S80内部EDA映射差异、无Setup/Hold端点报告问题不阻止B1协议模块RTL设计，但在新结果中仍需如实标记；不得据功能网表PASS宣称EQ6原生等价或时序达标；
6. 不运行Implementation、Bitstream或硬件下载。若需要这些操作，必须另行批准。

## 10. 风险、未实现范围和新手解释

| 风险 | 影响 | 计划措施 |
|---|---|---|
| 八端口缺少帧边界/长度 | 正式顶层无法独立确定变长Ethernet/IP帧范围 | 独立协议验证顶层；正式接入前冻结官方帧语义 |
| SN=0复位语义差异 | 比赛指南1–255与技术参考reset=0之间可能有适用范围差别 | B1普通业务帧用1–255，reset不发0；获得官方确认后再修改/扩展 |
| UDP checksum profile | 通用UDP可计算校验和，AFDX示例使用0；比赛指南未写字段值 | B1先按0做候选Golden，实际RTL开始前由队长冻结 |
| 单TX bank + 流式Payload | 上游长暂停会拖晚帧启动 | 描述符和Payload保持valid；测试延迟/jitter，实际容量边界不承诺无限缓存 |
| BAG/jitter与125MHz仿真 | 周期正确不等于比赛100Mbps时序通过 | 用显式时钟频率参数；验证整数周期关系，结果只称RTL功能测试 |
| B0器件模型/时序缺口 | 新协议逻辑可功能通过但器件等价/Setup-Hold仍未知 | 作为独立证据项继续追踪，不把其结果混入RTL PASS |

本B1单 VL 发送范围不包含多 VL仲裁/队列、双网络A/B冗余、接收端完整IPv4/UDP解析、SNMP、615A、RTC或完整性能认证。官方指南的高完整性、发送调度及端系统要求仍有后续任务。

给新手的直观理解：Payload是要寄出的内容；UDP/IP头是地址和长度标签；Ethernet目的地址里的VLID像“这封信走哪条虚拟线路”；Padding只在短信后补齐，SN是帧号；最后由已经验证的MAC包上FCS、前导码并从GMII发出去。测试会先把预期信件独立打印出来，再逐字节比较真实MAC发出和收到的内容。

**本文件只提交架构与开发计划。等待队长审核；未修改任何RTL、阶段5-B0报告或冻结的 `AFDX_top`，未开始阶段5-B1实际实现。**
