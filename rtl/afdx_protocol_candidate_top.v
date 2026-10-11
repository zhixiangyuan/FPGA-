// Independent B2 protocol diagnostic top. The official eight-port AFDX_top
// remains untouched. Frozen B1 and B0 are instantiated by reference.
module afdx_protocol_candidate_top (
    input wire clk,reset,
    input wire msg_valid,output wire msg_ready,
    input wire [10:0] msg_payload_length,
    input wire [31:0] msg_da_const,input wire [15:0] msg_vlid,
    input wire [47:0] msg_src_mac,input wire [31:0] msg_src_ip,msg_dst_ip,
    input wire [15:0] msg_src_port,msg_dst_port,
    input wire [7:0] msg_ttl,
    input wire [31:0] msg_bag_cycles,msg_jitter_cycles,
    input wire [7:0] payload_data,input wire payload_valid,
    output wire payload_ready,input wire payload_last,payload_abort,
    output wire [7:0] gmii_txd,output wire gmii_tx_en,gmii_tx_er,
    input wire [7:0] gmii_rxd,input wire gmii_rx_dv,gmii_rx_er,
    output wire msg_done,msg_error,output wire [3:0] error_code,
    output wire [31:0] late_count,
    output wire [7:0] app_data,output wire app_valid,
    input wire app_ready,output wire app_sop,app_eop,
    output wire [10:0] app_length,output wire [15:0] app_vlid,
    output wire [7:0] app_sn_unchecked,
    output wire candidate_accepted,candidate_rejected,
    output wire [3:0] candidate_reject_reason,
    output wire [31:0] candidate_accepted_count,candidate_rejected_count,
    output wire [1:0] candidate_banks_busy,
    output wire mac_rx_accepted,mac_rx_dropped,
    output wire [4:0] mac_rx_drop_reason,
    output wire [31:0] tx_sent,rx_seen,rx_good,rx_drop,rx_delivered
);
    wire [7:0] mac_client_data;
    wire mac_client_valid,mac_client_ready,mac_client_sop,mac_client_eop;
    wire [15:0] mac_client_length;
    wire [31:0] tx_rejected;
    wire [1:0] mac_rx_banks_busy;
    wire counter_saturated;
    afdx_network_tx_top #(.RESET_SN(8'd1),.CLK_HZ(32'd125000000)) tx_mac(
        .clk(clk),.reset(reset),.msg_valid(msg_valid),.msg_ready(msg_ready),
        .msg_payload_length(msg_payload_length),.msg_da_const(msg_da_const),
        .msg_vlid(msg_vlid),.msg_src_mac(msg_src_mac),
        .msg_src_ip(msg_src_ip),.msg_dst_ip(msg_dst_ip),
        .msg_src_port(msg_src_port),.msg_dst_port(msg_dst_port),
        .msg_ttl(msg_ttl),.msg_bag_cycles(msg_bag_cycles),
        .msg_jitter_cycles(msg_jitter_cycles),
        .payload_data(payload_data),.payload_valid(payload_valid),
        .payload_ready(payload_ready),.payload_last(payload_last),
        .payload_abort(payload_abort),
        .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),
        .gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(gmii_rx_er),
        .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),
        .late_count(late_count),
        .rx_data(mac_client_data),.rx_valid(mac_client_valid),
        .rx_sop(mac_client_sop),.rx_eop(mac_client_eop),
        .rx_length(mac_client_length),.rx_ready(mac_client_ready),
        .rx_accepted(mac_rx_accepted),.rx_dropped(mac_rx_dropped),
        .rx_drop_reason(mac_rx_drop_reason),
        .rx_banks_busy(mac_rx_banks_busy),.counter_saturated(counter_saturated),
        .tx_sent(tx_sent),.tx_rejected(tx_rejected),
        .rx_seen(rx_seen),.rx_good(rx_good),.rx_drop(rx_drop),
        .rx_delivered(rx_delivered)
    );
    afdx_single_vl_rx_candidate rx_protocol(
        .clk(clk),.reset(reset),
        .in_data(mac_client_data),.in_valid(mac_client_valid),
        .in_ready(mac_client_ready),.in_sop(mac_client_sop),
        .in_eop(mac_client_eop),.in_length(mac_client_length),
        .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),
        .cfg_src_mac(48'h020000000009),.cfg_src_ip(32'h0a000001),
        .cfg_dst_ip(32'he0e0003c),.cfg_src_port(16'd24),
        .cfg_dst_port(16'd23),
        .payload_data(app_data),.payload_valid(app_valid),
        .payload_ready(app_ready),.payload_sop(app_sop),.payload_eop(app_eop),
        .payload_length(app_length),.payload_vlid(app_vlid),
        .payload_sn_unchecked(app_sn_unchecked),
        .candidate_accepted(candidate_accepted),
        .candidate_rejected(candidate_rejected),
        .reject_reason(candidate_reject_reason),
        .accepted_count(candidate_accepted_count),
        .rejected_count(candidate_rejected_count),
        .banks_busy(candidate_banks_busy)
    );
endmodule
