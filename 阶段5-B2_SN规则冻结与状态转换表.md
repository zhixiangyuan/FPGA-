# 阶段5-B2 单VL SN规则冻结与状态转换表

批准日期：2026-10-11。依据为队长本轮明确审批；XAPP1130作为完整性检查参考。范围仅限本项目单VL工程profile，不宣称完整ARINC 664 Part 7合规。原待审核表保留为历史。

| 输入事件 | 完整性PSN更新 | Payload行为 | 计数与依据 |
|---|---|---|---|
| 接收端reset | 清除PSN有效位，PSN置0 | 取消候选、已接受但未交付完成的数据，开始新epoch | 队长批准的reset约定；reset取消不算应用交付 |
| 首个完整合法普通帧，SN=1..255 | 建立PSN基线为本帧SN | 放行原bank中的完整Payload | XAPP首帧例外及队长批准 |
| SN=next(PSN) | 更新为本帧SN | 放行 | XAPP +1 |
| SN=next(next(PSN)) | 更新为本帧SN | 放行；缺号计数+1 | XAPP +2，单帧缺号统计为工程计数 |
| 其他普通SN：重复、旧号、异常跳号 | **仍更新为本帧SN** | 拒绝Payload，内部耗尽并释放bank | XAPP完整性失败后的基线恢复；SN错误计数+1 |
| 完整合法SN=0 | PSN有效，PSN置0 | 控制事件，拒绝普通业务Payload，内部释放bank | XAPP零SN表示发送端reset；不交付Payload是本项目批准约定 |
| MAC错误或MAC容量丢帧，未交给Parser | 不更新 | 无应用交付 | 未执行SN检查；队长批准 |
| Ethernet/IP/UDP/长度/Padding错误 | 不更新 | Parser拒绝整帧，无候选数据进入SN门控 | 队长批准的分层规则 |
| Parser无空bank | 不更新尚未检查的帧；内部背压保持B0完整帧 | 容量恢复后继续，B0无法再缓存时明确丢帧 | 队长批准的预留与背压规则 |
| 合法帧已由SN门控接受，应用暂停 | 已作一次正确PSN更新，不再重复更新 | Payload持续保留在Parser原bank，保持数据/元数据，最终握手后释放 | 不另复制Payload；不存在状态已推进而Payload无处保存的路径 |
| Payload最后一字节与应用握手 | 不改变PSN | 应用实际交付计数+1，释放原bank | 完整性状态与应用交付计数独立 |

`next(255)=1`、`next(0)=1`；普通SN不经过0。`254 +2→1`、`255 +1→1`均已在真实RTL/GMII闭环验证。完整性PSN存于SN门控模块；缓存所有权存于Parser；应用交付只在末字节握手计数。

实现为`afdx_single_vl_sn_gate.v`，置于原已通过的候选Parser之后。门控在IDLE看见完整候选时先作一次决策，输入首字节暂不消费；PASS阶段由应用ready控制消费，DRAIN阶段内部耗尽被拒绝或控制帧。这样PSN决定发生时完整Payload已在预留bank中，应用背压不能造成隐性Payload丢失。

验收见正式报告与`runs/full_003`：独立Golden逐帧核对303条SN决策，完整真实256帧回绕、4个SN拒绝及恢复、1个SN=0控制事件、协议/MAC错误不更新PSN、容量丢帧与reset取消均通过。冻结B1发送器仍不发送SN=0；该控制事件由独立Golden生成的正确FCS线上帧验证。
