// INDEPENDENT TEAM CANDIDATE. Does not replace the frozen production AFDX_top.
module AFDX_top(
 input wire clk,input wire reset,
 output wire [7:0] tx_data,input wire [7:0] rx_data,
 output wire tx_valid,input wire rx_valid,
 output wire tx_ready,input wire rx_ready
);
 assign tx_ready=1'b0;
 wire [7:0] gmii_rxd,gmii_txd;wire gmii_rx_dv,gmii_rx_er,gmii_tx_en,gmii_tx_er;
 afdx_gmii_candidate_boundary boundary(.rx_data(rx_data),.rx_valid(rx_valid),
 .gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(gmii_rx_er),
 .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.tx_data(tx_data),.tx_valid(tx_valid));
 wire [7:0] app_data,app_sn,payload_data;wire app_valid,app_ready,app_sop,app_eop;
 wire [10:0] app_length,msg_length;wire [15:0] app_vlid;
 wire msg_valid,msg_ready,payload_valid,payload_ready,payload_last,msg_done,msg_error;
 wire [3:0] error_code;wire [31:0] late_count,stored_count,sent_count,queue_error_count;
 wire [1:0] echo_banks_busy,candidate_banks_busy;
 wire [7:0] psn;wire psn_valid;
 wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count,sn_missing_count,app_delivered_count;
 wire [31:0] candidate_accepted_count,candidate_rejected_count,tx_sent,rx_seen,rx_good,rx_drop,rx_delivered;
 wire sn_accepted,sn_rejected,sn_reset_control,app_delivered;
 wire candidate_accepted,candidate_rejected,mac_rx_accepted,mac_rx_dropped;
 wire [3:0] candidate_reject_reason;wire [4:0] mac_rx_drop_reason;
 afdx_app_echo_queue application(.clk(clk),.reset(reset),
 .app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
 .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),.app_sn(app_sn),.app_vlid(app_vlid),
 .msg_valid(msg_valid),.msg_ready(msg_ready),.msg_length(msg_length),
 .payload_data(payload_data),.payload_valid(payload_valid),.payload_ready(payload_ready),
 .payload_last(payload_last),.msg_done(msg_done),.msg_error(msg_error),
 .stored_count(stored_count),.sent_count(sent_count),.error_count(queue_error_count),.banks_busy(echo_banks_busy));
 afdx_protocol_rx_top protocol(.clk(clk),.reset(reset),
 .msg_valid(msg_valid),.msg_ready(msg_ready),.msg_payload_length(msg_length),
 .msg_da_const(32'h03000000),.msg_vlid(16'h1234),.msg_src_mac(48'h020000000009),
 .msg_src_ip(32'h0a000001),.msg_dst_ip(32'he0e0003c),.msg_src_port(16'd24),.msg_dst_port(16'd23),
 .msg_ttl(8'd1),.msg_bag_cycles(32'd125000),.msg_jitter_cycles(32'd12500),
 .payload_data(payload_data),.payload_valid(payload_valid),.payload_ready(payload_ready),
 .payload_last(payload_last),.payload_abort(1'b0),
 .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),
 .gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(gmii_rx_er),
 .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),.late_count(late_count),
 .app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),.app_sop(app_sop),.app_eop(app_eop),
 .app_length(app_length),.app_vlid(app_vlid),.app_sn(app_sn),
 .psn_valid(psn_valid),.psn(psn),.sn_accepted_count(sn_accepted_count),.sn_rejected_count(sn_rejected_count),
 .sn_accepted(sn_accepted),.sn_rejected(sn_rejected),.sn_reset_control(sn_reset_control),.app_delivered(app_delivered),
 .sn_control_count(sn_control_count),.sn_missing_count(sn_missing_count),.app_delivered_count(app_delivered_count),
 .candidate_accepted_count(candidate_accepted_count),.candidate_rejected_count(candidate_rejected_count),
 .candidate_banks_busy(candidate_banks_busy),.tx_sent(tx_sent),
 .candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),.candidate_reject_reason(candidate_reject_reason),
 .mac_rx_accepted(mac_rx_accepted),.mac_rx_dropped(mac_rx_dropped),.mac_rx_drop_reason(mac_rx_drop_reason),
 .rx_seen(rx_seen),.rx_good(rx_good),.rx_drop(rx_drop),.rx_delivered(rx_delivered));
endmodule
