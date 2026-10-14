// Eight-port GMII engineering contract. Business profile: 16 consecutive VLs.
// Management service integration is developed separately; not enabled here yet.
module afdx_stage2_top(
 input wire clk,reset,input wire [7:0] rx_data,input wire rx_valid,rx_ready,
 output wire [7:0] tx_data,output wire tx_valid,tx_ready
);
 assign tx_ready=1'b0;
 wire [7:0] mac_tx_data,mac_rx_data,cand_data,cand_sn,app_data,app_sn,payload_data;
 wire mac_tx_valid,mac_tx_ready,mac_tx_sop,mac_tx_eop,mac_tx_afdx,mac_tx_done,mac_tx_reject;
 wire mac_rx_valid,mac_rx_ready,mac_rx_sop,mac_rx_eop;
 wire [15:0] mac_tx_length,mac_rx_length,cand_vlid,app_vlid,cand_src_port,cand_dst_port;
 wire [10:0] cand_length,app_length,msg_length;
 wire cand_valid,cand_ready,cand_sop,cand_eop,app_valid,app_ready,app_sop,app_eop;
 wire msg_valid,msg_ready,payload_valid,payload_ready,payload_last,msg_done,msg_error;
 wire [15:0] msg_vlid,msg_src_port,msg_dst_port;
 wire [3:0] error_code,reject_reason;wire [31:0] late_count,stored_count,sent_count,queue_error_count;
 wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count,sn_missing_count,app_delivered_count;
 wire accepted,rejected,reset_control,delivered,candidate_accepted,candidate_rejected,mac_accepted,mac_dropped;
 wire [4:0] mac_drop_reason;
 afdx_multi_vl_echo_queue application(.clk(clk),.reset(reset),.app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
  .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),.app_sn(app_sn),.app_vlid(app_vlid),
  .app_src_port(cand_src_port),.app_dst_port(cand_dst_port),
  .msg_valid(msg_valid),.msg_ready(msg_ready),.msg_length(msg_length),.msg_vlid(msg_vlid),.msg_src_port(msg_src_port),.msg_dst_port(msg_dst_port),
  .payload_data(payload_data),.payload_valid(payload_valid),.payload_ready(payload_ready),.payload_last(payload_last),
  .msg_done(msg_done),.msg_error(msg_error),.gmii_tx_en(tx_valid),.cfg_bag_cycles(32'd125000),
  .stored_count(stored_count),.sent_count(sent_count),.error_count(queue_error_count),.banks_busy());
 afdx_multi_vl_tx sender(.clk(clk),.reset(reset),.msg_valid(msg_valid),.msg_ready(msg_ready),
  .msg_payload_length(msg_length),.msg_da_const(32'h03000000),.msg_vlid(msg_vlid),.msg_src_mac(48'h020000000009),
  .msg_src_ip(32'h0a000001),.msg_dst_ip(32'he0e0003c),.msg_src_port(msg_src_port),.msg_dst_port(msg_dst_port),
  .msg_ttl(8'd1),.msg_bag_cycles(32'd125000),.msg_jitter_cycles(32'd12500),
  .payload_data(payload_data),.payload_valid(payload_valid),.payload_ready(payload_ready),.payload_last(payload_last),.payload_abort(1'b0),
  .mac_tx_data(mac_tx_data),.mac_tx_valid(mac_tx_valid),.mac_tx_ready(mac_tx_ready),.mac_tx_sop(mac_tx_sop),.mac_tx_eop(mac_tx_eop),
  .mac_tx_length(mac_tx_length),.mac_tx_afdx(mac_tx_afdx),.mac_tx_done(mac_tx_done),.mac_tx_reject(mac_tx_reject),.gmii_tx_en(tx_valid),
  .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),.late_count(late_count));
 mac_gmii_core mac(.clk(clk),.reset(reset),.tx_data(mac_tx_data),.tx_valid(mac_tx_valid),.tx_sop(mac_tx_sop),.tx_eop(mac_tx_eop),
  .tx_length(mac_tx_length),.tx_afdx(mac_tx_afdx),.tx_ready(mac_tx_ready),.gmii_txd(tx_data),.gmii_tx_en(tx_valid),.gmii_tx_er(),
  .gmii_rxd(rx_data),.gmii_rx_dv(rx_valid),.gmii_rx_er(1'b0),
  .rx_data(mac_rx_data),.rx_valid(mac_rx_valid),.rx_sop(mac_rx_sop),.rx_eop(mac_rx_eop),.rx_ready(mac_rx_ready),.rx_length(mac_rx_length),
  .tx_done(mac_tx_done),.tx_reject(mac_tx_reject),.rx_accepted(mac_accepted),.rx_dropped(mac_dropped),.rx_drop_reason(mac_drop_reason),
  .tx_sent(),.tx_rejected(),.rx_seen(),.rx_good(),.rx_drop(),.rx_delivered(),.rx_banks_busy(),.counter_saturated());
 afdx_multi_vl_rx_parser #(.CHECK_PORTS(0)) parser(.clk(clk),.reset(reset),
  .in_data(mac_rx_data),.in_valid(mac_rx_valid),.in_ready(mac_rx_ready),.in_sop(mac_rx_sop),.in_eop(mac_rx_eop),.in_length(mac_rx_length),
  .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),.cfg_src_mac(48'h020000000009),.cfg_src_ip(32'h0a000001),.cfg_dst_ip(32'he0e0003c),
  .cfg_src_port(16'd24),.cfg_dst_port(16'd23),.payload_data(cand_data),.payload_valid(cand_valid),.payload_ready(cand_ready),
  .payload_sop(cand_sop),.payload_eop(cand_eop),.payload_length(cand_length),.payload_vlid(cand_vlid),.payload_sn_unchecked(cand_sn),
  .payload_src_port(cand_src_port),.payload_dst_port(cand_dst_port),.candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),
  .reject_reason(reject_reason),.accepted_count(),.rejected_count(),.banks_busy());
 afdx_multi_vl_sn_gate gate(.clk(clk),.reset(reset),.cfg_integrity_enable(16'hffff),
  .in_data(cand_data),.in_valid(cand_valid),.in_ready(cand_ready),.in_sop(cand_sop),.in_eop(cand_eop),.in_length(cand_length),
  .in_vlid(cand_vlid),.in_sn(cand_sn),.app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),.app_sop(app_sop),.app_eop(app_eop),
  .app_length(app_length),.app_vlid(app_vlid),.app_sn(app_sn),.accepted(accepted),.rejected(rejected),.reset_control(reset_control),.delivered(delivered),
  .accepted_count(sn_accepted_count),.rejected_count(sn_rejected_count),.control_count(sn_control_count),
  .missing_count(sn_missing_count),.delivered_count(app_delivered_count));
endmodule
