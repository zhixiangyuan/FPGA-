// Management-service variant of the eight-port stage2 top. The business path is
// the unchanged 16-VL echo profile; the management path adds one dedicated VL
// carrying real SNMPv1 agent traffic through the same frozen MAC and frame
// builder. Business and management messages alternate on the single TX port.
// rx_ready stays unused and tx_ready stays low, matching the documented FAQ
// valid-only contract for the official eight ports.
module afdx_stage2_mgmt_top #(
 parameter [31:0] ES_IP=32'h0a000001,
 parameter [31:0] GROUP_IP=32'he0e0003c,
 parameter [47:0] ES_MAC=48'h020000000009,
 parameter [31:0] GROUP_DA_PREFIX=32'h03000000,
 parameter [47:0] MANAGER_MAC=48'h02000000000a,
 parameter [31:0] MANAGER_IP=32'h0a000009,
 parameter [15:0] MGMT_VLID=16'h1244,
 parameter [15:0] SNMP_PORT=16'd161,
 parameter [31:0] BAG_CYCLES=32'd125000,
 parameter [31:0] JITTER_CYCLES=32'd12500,
 // Legal AFDX bag values are 1,2,4,...,128 ms, and the shared frame builder
 // rejects any other descriptor. The management VL therefore uses the smallest
 // legal bag (1 ms) with 10 percent jitter, not a sub-millisecond interval.
 parameter [31:0] MGMT_BAG_CYCLES=32'd125000,
 parameter [31:0] MGMT_JITTER_CYCLES=32'd12500,
 parameter [31:0] TICK_DIVIDER=32'd1250000
)(
 input wire clk,reset,input wire [7:0] rx_data,input wire rx_valid,rx_ready,
 output wire [7:0] tx_data,output wire tx_valid,tx_ready,
 // Integration-test control for sysUpTime: the system test replays the same
 // tick vectors the SNMP unit vectors assume. Tied off, the agent uses the
 // real 10 ms TimeTicks counter below. This is not the official eight-port
 // delivery top.
 input wire [31:0] uptime_override,input wire uptime_override_en
);
 assign tx_ready=1'b0;
 wire [7:0] mac_tx_data,mac_rx_data,biz_data,biz_sn,app_data,app_sn;
 wire mac_tx_valid,mac_tx_ready,mac_tx_sop,mac_tx_eop,mac_tx_afdx,mac_tx_done,mac_tx_reject;
 wire mac_rx_valid,mac_rx_ready,mac_rx_sop,mac_rx_eop;
 wire [15:0] mac_tx_length,mac_rx_length,biz_vlid,app_vlid,biz_src_port,biz_dst_port;
 // The receive parser and the echo queue must not share one net: both drive it
 // as an output, and two different driven values resolve to X, which makes the
 // frame builder drop the descriptor as an unknown (not illegal) reference.
 wire [15:0] biz_rx_vlid;
 wire [10:0] biz_length,app_length,biz_msg_length;
 wire biz_valid,biz_ready,biz_sop,biz_eop,app_valid,app_ready,app_sop,app_eop;
 wire biz_msg_valid,biz_msg_ready,biz_payload_valid,biz_payload_ready,biz_payload_last,biz_msg_error,biz_msg_done;
 wire [7:0] biz_payload_data;
 wire [15:0] biz_msg_src_port,biz_msg_dst_port;
 wire [3:0] error_code,reject_reason;wire [31:0] late_count,stored_count,sent_count,queue_error_count;
 wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count,sn_missing_count,app_delivered_count;
 wire accepted,rejected,reset_control,delivered,candidate_accepted,candidate_rejected,mac_accepted,mac_dropped;
 wire [4:0] mac_drop_reason;
 wire business_in_ready,mgmt_in_ready;
 wire [7:0] mgmt_data,mgmt_sn,mgmt_app_data,mgmt_app_sn;
 wire mgmt_valid,mgmt_ready,mgmt_sop,mgmt_eop,mgmt_app_valid,mgmt_app_ready,mgmt_app_sop,mgmt_app_eop;
 wire [15:0] mgmt_vlid,mgmt_src_port,mgmt_dst_port,mgmt_app_vlid;
 wire [10:0] mgmt_length,mgmt_app_length;
 wire mgmt_candidate_accepted,mgmt_candidate_rejected,mgmt_accepted,mgmt_rejected,mgmt_reset_control,mgmt_delivered;
 wire [3:0] mgmt_reject_reason;
 wire [31:0] mgmt_sn_accepted_count,mgmt_sn_rejected_count,mgmt_sn_control_count,mgmt_sn_missing_count,mgmt_sn_delivered_count;
 wire [7:0] demux_snmp_data;
 wire demux_snmp_valid,demux_snmp_sop,demux_snmp_eop;
 wire [10:0] demux_snmp_length;wire [15:0] demux_snmp_src_port;
 wire snmp_in_ready,snmp_out_valid,snmp_out_sop,snmp_out_eop,trap_ready,fifo_in_ready;
 wire [7:0] snmp_out_data;wire [10:0] snmp_out_length;wire [15:0] snmp_out_src_port,snmp_out_dst_port;
 wire svc_msg_valid,svc_msg_ready,svc_payload_valid,svc_payload_ready,svc_payload_last;
 wire [10:0] svc_msg_length;wire [15:0] svc_msg_src_port,svc_msg_dst_port;wire [7:0] svc_payload_data;
 wire tx_msg_valid,tx_msg_ready,tx_payload_valid,tx_payload_ready,tx_payload_last;
 wire [10:0] tx_msg_length;wire [15:0] tx_msg_vlid,tx_msg_src_port,tx_msg_dst_port;
 wire [7:0] tx_msg_data;wire service_active;
 reg [31:0] uptime_ticks;
 // Named observability nets: the testbench reads these instead of relying on
 // optimizer-dependent internal names.
 wire [31:0] mgmt_parser_accepted_count,mgmt_parser_rejected_count;
 wire [31:0] business_parser_accepted_count,business_parser_rejected_count;
 wire [31:0] demux_routed_count,demux_dropped_count;wire [15:0] demux_last_dropped_port;
 wire [31:0] snmp_request_count,snmp_response_count,snmp_error_count,snmp_trap_count;
 wire [5:0] snmp_sys_name_length;
 wire [31:0] fifo_captured_count,fifo_overflow_count,fifo_sent_count;
 wire [31:0] arbiter_service_sent_count,arbiter_service_error_count;
 // Both receive parsers see every wire frame through one shared ready gate, so
 // the MAC bank owner is never asked to hold a byte that one path rejected.
 assign mac_rx_ready=business_in_ready&&mgmt_in_ready;
 // Business application path: identical to afdx_stage2_top.
 afdx_multi_vl_echo_queue application(.clk(clk),.reset(reset),.app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
  .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),.app_sn(app_sn),.app_vlid(app_vlid),
  .app_src_port(biz_src_port),.app_dst_port(biz_dst_port),
  .msg_valid(biz_msg_valid),.msg_ready(biz_msg_ready),.msg_length(biz_msg_length),.msg_vlid(biz_vlid),
  .msg_src_port(biz_msg_src_port),.msg_dst_port(biz_msg_dst_port),
  .payload_data(biz_payload_data),.payload_valid(biz_payload_valid),.payload_ready(biz_payload_ready),.payload_last(biz_payload_last),
  .msg_done(biz_msg_done),.msg_error(biz_msg_error),.gmii_tx_en(tx_valid),.cfg_bag_cycles(BAG_CYCLES),
  .stored_count(stored_count),.sent_count(sent_count),.error_count(queue_error_count),.banks_busy());
 afdx_multi_vl_rx_parser #(.CHECK_PORTS(0)) parser(.clk(clk),.reset(reset),
  .in_data(mac_rx_data),.in_valid(mac_rx_valid),.in_ready(business_in_ready),.in_sop(mac_rx_sop),.in_eop(mac_rx_eop),.in_length(mac_rx_length),
  .cfg_da_prefix(GROUP_DA_PREFIX),.cfg_vlid(16'h1234),.cfg_src_mac(ES_MAC),.cfg_src_ip(ES_IP),.cfg_dst_ip(GROUP_IP),
  .cfg_src_port(16'd24),.cfg_dst_port(16'd23),.payload_data(biz_data),.payload_valid(biz_valid),.payload_ready(biz_ready),
  .payload_sop(biz_sop),.payload_eop(biz_eop),.payload_length(biz_length),.payload_vlid(biz_rx_vlid),.payload_sn_unchecked(biz_sn),
  .payload_src_port(biz_src_port),.payload_dst_port(biz_dst_port),.candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),
  .reject_reason(reject_reason),.accepted_count(business_parser_accepted_count),.rejected_count(business_parser_rejected_count),.banks_busy());
 afdx_multi_vl_sn_gate gate(.clk(clk),.reset(reset),.cfg_integrity_enable(16'hffff),
  .in_data(biz_data),.in_valid(biz_valid),.in_ready(biz_ready),.in_sop(biz_sop),.in_eop(biz_eop),.in_length(biz_length),
  .in_vlid(biz_rx_vlid),.in_sn(biz_sn),.app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),.app_sop(app_sop),.app_eop(app_eop),
  .app_length(app_length),.app_vlid(app_vlid),.app_sn(app_sn),.accepted(accepted),.rejected(rejected),.reset_control(reset_control),.delivered(delivered),
  .accepted_count(sn_accepted_count),.rejected_count(sn_rejected_count),.control_count(sn_control_count),
  .missing_count(sn_missing_count),.delivered_count(app_delivered_count));
 // Management VL: same parser profile, configured for the management peer.
 afdx_multi_vl_rx_parser #(.VL_COUNT(1),.CHECK_PORTS(0)) mgmt_parser(.clk(clk),.reset(reset),
  .in_data(mac_rx_data),.in_valid(mac_rx_valid),.in_ready(mgmt_in_ready),.in_sop(mac_rx_sop),.in_eop(mac_rx_eop),.in_length(mac_rx_length),
  .cfg_da_prefix(GROUP_DA_PREFIX),.cfg_vlid(MGMT_VLID),.cfg_src_mac(MANAGER_MAC),.cfg_src_ip(MANAGER_IP),.cfg_dst_ip(ES_IP),
  .cfg_src_port(SNMP_PORT),.cfg_dst_port(SNMP_PORT),.payload_data(mgmt_data),.payload_valid(mgmt_valid),.payload_ready(mgmt_ready),
  .payload_sop(mgmt_sop),.payload_eop(mgmt_eop),.payload_length(mgmt_length),.payload_vlid(mgmt_vlid),.payload_sn_unchecked(mgmt_sn),
  .payload_src_port(mgmt_src_port),.payload_dst_port(mgmt_dst_port),.candidate_accepted(mgmt_candidate_accepted),
  .candidate_rejected(mgmt_candidate_rejected),.reject_reason(mgmt_reject_reason),.accepted_count(mgmt_parser_accepted_count),.rejected_count(mgmt_parser_rejected_count),.banks_busy());
 afdx_multi_vl_sn_gate #(.VL_COUNT(1),.VL_BASE(MGMT_VLID)) mgmt_gate(.clk(clk),.reset(reset),.cfg_integrity_enable(1'b1),
  .in_data(mgmt_data),.in_valid(mgmt_valid),.in_ready(mgmt_ready),.in_sop(mgmt_sop),.in_eop(mgmt_eop),.in_length(mgmt_length),
  .in_vlid(mgmt_vlid),.in_sn(mgmt_sn),.app_data(mgmt_app_data),.app_valid(mgmt_app_valid),.app_ready(mgmt_app_ready),
  .app_sop(mgmt_app_sop),.app_eop(mgmt_app_eop),.app_length(mgmt_app_length),.app_vlid(mgmt_app_vlid),.app_sn(mgmt_app_sn),
  .accepted(mgmt_accepted),.rejected(mgmt_rejected),.reset_control(mgmt_reset_control),.delivered(mgmt_delivered),
  .accepted_count(mgmt_sn_accepted_count),.rejected_count(mgmt_sn_rejected_count),.control_count(mgmt_sn_control_count),
  .missing_count(mgmt_sn_missing_count),.delivered_count(mgmt_sn_delivered_count));
 afdx_management_rx_demux #(.SNMP_PORT(SNMP_PORT)) demux(.clk(clk),.reset(reset),
  .in_data(mgmt_app_data),.in_valid(mgmt_app_valid),.in_ready(mgmt_app_ready),.in_sop(mgmt_app_sop),.in_eop(mgmt_app_eop),
  .in_length(mgmt_app_length),.in_src_port(mgmt_src_port),.in_dst_port(mgmt_dst_port),
  .snmp_data(demux_snmp_data),.snmp_valid(demux_snmp_valid),.snmp_ready(snmp_in_ready),.snmp_sop(demux_snmp_sop),
  .snmp_eop(demux_snmp_eop),.snmp_length(demux_snmp_length),.snmp_src_port(demux_snmp_src_port),
  .routed_count(demux_routed_count),.dropped_count(demux_dropped_count),.last_dropped_port(demux_last_dropped_port));
 wire [31:0] uptime_value=uptime_override_en?uptime_override:uptime_ticks;
 afdx_snmp_agent #(.LOCAL_IP(ES_IP)) snmp(.clk(clk),.reset(reset),
  .in_data(demux_snmp_data),.in_valid(demux_snmp_valid),.in_ready(snmp_in_ready),.in_sop(demux_snmp_sop),.in_eop(demux_snmp_eop),
  .in_length(demux_snmp_length),.in_src_port(demux_snmp_src_port),.uptime_ticks(uptime_value),
  .trap_start(1'b0),.trap_ready(trap_ready),
  .out_data(snmp_out_data),.out_valid(snmp_out_valid),.out_ready(fifo_in_ready),.out_sop(snmp_out_sop),.out_eop(snmp_out_eop),
  .out_length(snmp_out_length),.out_src_port(snmp_out_src_port),.out_dst_port(snmp_out_dst_port),
  .request_count(snmp_request_count),.response_count(snmp_response_count),.error_count(snmp_error_count),
  .trap_count(snmp_trap_count),.sys_name_length(snmp_sys_name_length));
 afdx_service_message_fifo service(.clk(clk),.reset(reset),
  .in_data(snmp_out_data),.in_valid(snmp_out_valid),.in_ready(fifo_in_ready),.in_sop(snmp_out_sop),.in_eop(snmp_out_eop),
  .in_src_port(snmp_out_src_port),.in_dst_port(snmp_out_dst_port),
  .msg_valid(svc_msg_valid),.msg_ready(svc_msg_ready),.msg_length(svc_msg_length),
  .msg_src_port(svc_msg_src_port),.msg_dst_port(svc_msg_dst_port),
  .out_data(svc_payload_data),.out_valid(svc_payload_valid),.out_ready(svc_payload_ready),.out_last(svc_payload_last),
  .captured_count(fifo_captured_count),.overflow_count(fifo_overflow_count),.sent_count(fifo_sent_count));
 afdx_service_tx_arbiter arbiter(.clk(clk),.reset(reset),
  .biz_msg_length(biz_msg_length),.biz_msg_vlid(biz_vlid),.biz_msg_src_port(biz_msg_src_port),.biz_msg_dst_port(biz_msg_dst_port),
  .biz_msg_valid(biz_msg_valid),.biz_msg_ready(biz_msg_ready),
  .biz_payload_data(biz_payload_data),.biz_payload_valid(biz_payload_valid),.biz_payload_ready(biz_payload_ready),.biz_payload_last(biz_payload_last),
  .svc_msg_length(svc_msg_length),.svc_msg_src_port(svc_msg_src_port),.svc_msg_dst_port(svc_msg_dst_port),
  .svc_msg_valid(svc_msg_valid),.svc_msg_ready(svc_msg_ready),
  .svc_payload_data(svc_payload_data),.svc_payload_valid(svc_payload_valid),.svc_payload_ready(svc_payload_ready),.svc_payload_last(svc_payload_last),
  .svc_msg_vlid(MGMT_VLID),.tx_msg_done(mac_tx_done),.tx_msg_error(mac_tx_reject),
  .tx_msg_valid(tx_msg_valid),.tx_msg_ready(tx_msg_ready),.tx_msg_length(tx_msg_length),
  .tx_msg_vlid(tx_msg_vlid),.tx_msg_src_port(tx_msg_src_port),.tx_msg_dst_port(tx_msg_dst_port),
  .tx_payload_data(tx_msg_data),.tx_payload_valid(tx_payload_valid),.tx_payload_ready(tx_payload_ready),.tx_payload_last(tx_payload_last),
  .service_active(service_active),.service_sent_count(arbiter_service_sent_count),.service_error_count(arbiter_service_error_count));
 // sysUpTime.0 in RFC1213 TimeTicks units at 125 MHz (10 ms per tick).
 reg [31:0] tick_counter;
 always @(posedge clk)begin
  if(reset)begin tick_counter<=0;uptime_ticks<=0;end
  else if(tick_counter+1'b1==TICK_DIVIDER)begin tick_counter<=0;uptime_ticks<=uptime_ticks+1'b1;end
  else tick_counter<=tick_counter+1'b1;
 end
 afdx_multi_vl_tx #(.VL_COUNT(17)) sender(.clk(clk),.reset(reset),
  .msg_valid(tx_msg_valid),.msg_ready(tx_msg_ready),.msg_payload_length(tx_msg_length),
  .msg_da_const(GROUP_DA_PREFIX),.msg_vlid(tx_msg_vlid),.msg_src_mac(ES_MAC),.msg_src_ip(ES_IP),
  .msg_dst_ip(service_active?MANAGER_IP:GROUP_IP),.msg_src_port(tx_msg_src_port),.msg_dst_port(tx_msg_dst_port),
  .msg_ttl(8'd1),.msg_bag_cycles(service_active?MGMT_BAG_CYCLES:BAG_CYCLES),
  .msg_jitter_cycles(service_active?MGMT_JITTER_CYCLES:JITTER_CYCLES),
  .payload_data(tx_msg_data),.payload_valid(tx_payload_valid),.payload_ready(tx_payload_ready),.payload_last(tx_payload_last),.payload_abort(1'b0),
  .mac_tx_data(mac_tx_data),.mac_tx_valid(mac_tx_valid),.mac_tx_ready(mac_tx_ready),.mac_tx_sop(mac_tx_sop),.mac_tx_eop(mac_tx_eop),
  .mac_tx_length(mac_tx_length),.mac_tx_afdx(mac_tx_afdx),.mac_tx_done(mac_tx_done),.mac_tx_reject(mac_tx_reject),.gmii_tx_en(tx_valid),
  .msg_done(biz_msg_done),.msg_error(biz_msg_error),.error_code(error_code),.late_count(late_count));
 mac_gmii_core mac(.clk(clk),.reset(reset),.tx_data(mac_tx_data),.tx_valid(mac_tx_valid),.tx_sop(mac_tx_sop),.tx_eop(mac_tx_eop),
  .tx_length(mac_tx_length),.tx_afdx(mac_tx_afdx),.tx_ready(mac_tx_ready),.gmii_txd(tx_data),.gmii_tx_en(tx_valid),.gmii_tx_er(),
  .gmii_rxd(rx_data),.gmii_rx_dv(rx_valid),.gmii_rx_er(1'b0),
  .rx_data(mac_rx_data),.rx_valid(mac_rx_valid),.rx_sop(mac_rx_sop),.rx_eop(mac_rx_eop),.rx_ready(mac_rx_ready),.rx_length(mac_rx_length),
  .tx_done(mac_tx_done),.tx_reject(mac_tx_reject),.rx_accepted(mac_accepted),.rx_dropped(mac_dropped),.rx_drop_reason(mac_drop_reason),
  .tx_sent(),.tx_rejected(),.rx_seen(),.rx_good(),.rx_drop(),.rx_delivered(),.rx_banks_busy(),.counter_saturated());
endmodule
