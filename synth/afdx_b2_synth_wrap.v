// Low-I/O B2 synthesis wrapper. This is a test/package shell only; it does
// not replace or modify the frozen official eight-port AFDX_top.
module afdx_b2_synth_wrap(
    input wire clk,
    input wire reset,
    input wire msg_valid,
    output wire msg_ready,
    input wire [10:0] msg_payload_length,
    input wire [7:0] payload_data,
    input wire payload_valid,
    output wire payload_ready,
    input wire payload_last,
    input wire payload_abort,
    output wire msg_done,
    output wire msg_error,
    output wire [3:0] error_code,
    output wire [7:0] gmii_txd,
    output wire gmii_tx_en,
    output wire gmii_tx_er,
    input wire gmii_rx_override,
    input wire [7:0] gmii_rxd_ext,
    input wire gmii_rx_dv_ext,
    input wire gmii_rx_er_ext,
    output wire [7:0] app_data,
    output wire app_valid,
    input wire app_ready,
    output wire app_sop,
    output wire app_eop,
    output wire [10:0] app_length,
    output wire [15:0] app_vlid,
    output wire [7:0] app_sn,
    input wire diag_read,
    input wire [3:0] diag_addr,
    output reg [31:0] diag_data
);
    // The default receive path is a one-cycle GMII/PHY loop. The external
    // override permits the netlist TB to inject arbitrary full-wire frames,
    // including protocol mutations with independently recomputed FCS.
    reg [7:0] loop_rxd;
    reg loop_dv,loop_er;
    always @(posedge clk) begin
        if(reset)begin loop_rxd<=0;loop_dv<=0;loop_er<=0;end
        else begin loop_rxd<=gmii_txd;loop_dv<=gmii_tx_en;loop_er<=gmii_tx_er;end
    end
    wire [7:0] gmii_rxd=gmii_rx_override?gmii_rxd_ext:loop_rxd;
    wire gmii_rx_dv=gmii_rx_override?gmii_rx_dv_ext:loop_dv;
    wire gmii_rx_er=gmii_rx_override?gmii_rx_er_ext:loop_er;
    wire [31:0] late_count,tx_sent,rx_seen,rx_good,rx_drop,rx_delivered;
    wire [31:0] tx_rejected,candidate_accepted_count,candidate_rejected_count;
    wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count;
    wire [31:0] sn_missing_count,app_delivered_count;
    wire [7:0] psn;
    wire psn_valid,sn_accepted,sn_rejected,sn_reset_control,app_delivered;
    wire candidate_accepted,candidate_rejected,mac_rx_accepted,mac_rx_dropped;
    wire [3:0] candidate_reject_reason;
    wire [4:0] mac_rx_drop_reason;
    wire [1:0] candidate_banks_busy;

    afdx_protocol_rx_top protocol(
        .clk(clk),.reset(reset),.msg_valid(msg_valid),.msg_ready(msg_ready),
        .msg_payload_length(msg_payload_length),.msg_da_const(32'h03000000),
        .msg_vlid(16'h1234),.msg_src_mac(48'h020000000009),
        .msg_src_ip(32'h0a000001),.msg_dst_ip(32'he0e0003c),
        .msg_src_port(16'd24),.msg_dst_port(16'd23),.msg_ttl(8'd1),
        .msg_bag_cycles(32'd125000),.msg_jitter_cycles(32'd12500),
        .payload_data(payload_data),.payload_valid(payload_valid),
        .payload_ready(payload_ready),.payload_last(payload_last),
        .payload_abort(payload_abort),
        .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),
        .gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(gmii_rx_er),
        .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),
        .late_count(late_count),.app_data(app_data),.app_valid(app_valid),
        .app_ready(app_ready),.app_sop(app_sop),.app_eop(app_eop),
        .app_length(app_length),.app_vlid(app_vlid),.app_sn(app_sn),
        .psn_valid(psn_valid),.psn(psn),.sn_accepted(sn_accepted),
        .sn_rejected(sn_rejected),.sn_reset_control(sn_reset_control),
        .app_delivered(app_delivered),.sn_accepted_count(sn_accepted_count),
        .sn_rejected_count(sn_rejected_count),.sn_control_count(sn_control_count),
        .sn_missing_count(sn_missing_count),.app_delivered_count(app_delivered_count),
        .candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),
        .candidate_reject_reason(candidate_reject_reason),
        .candidate_accepted_count(candidate_accepted_count),
        .candidate_rejected_count(candidate_rejected_count),
        .candidate_banks_busy(candidate_banks_busy),
        .mac_rx_accepted(mac_rx_accepted),.mac_rx_dropped(mac_rx_dropped),
        .mac_rx_drop_reason(mac_rx_drop_reason),.tx_sent(tx_sent),
        .rx_seen(rx_seen),.rx_good(rx_good),.rx_drop(rx_drop),
        .rx_delivered(rx_delivered)
    );

    always @* begin
        diag_data=0;
        if(diag_read)case(diag_addr)
            4'd0:diag_data=tx_sent;
            4'd1:diag_data=tx_rejected;
            4'd2:diag_data=rx_seen;
            4'd3:diag_data=rx_good;
            4'd4:diag_data=rx_drop;
            4'd5:diag_data=rx_delivered;
            4'd6:diag_data=candidate_accepted_count;
            4'd7:diag_data=candidate_rejected_count;
            4'd8:diag_data={23'd0,psn_valid,psn};
            4'd9:diag_data=sn_accepted_count;
            4'd10:diag_data=sn_rejected_count;
            4'd11:diag_data=sn_control_count;
            4'd12:diag_data=sn_missing_count;
            4'd13:diag_data=app_delivered_count;
            4'd14:diag_data={30'd0,candidate_banks_busy};
            4'd15:diag_data={late_count[15:0],12'd0,mac_rx_dropped,candidate_rejected,sn_rejected,sn_reset_control};
        endcase
    end
endmodule
