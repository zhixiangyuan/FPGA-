// Independent B1 integration top. It is not the frozen eight-port AFDX_top.
// A real AFDX payload descriptor and payload stream drive the protocol layer;
// the unchanged B0 production MAC provides the GMII and loopback RX path.
module afdx_network_tx_top #(
    parameter [7:0] RESET_SN = 8'd1,
    parameter [31:0] CLK_HZ = 32'd125000000
) (
    input  wire        clk,
    input  wire        reset,

    input  wire        msg_valid,
    output wire        msg_ready,
    input  wire [10:0] msg_payload_length,
    input  wire [31:0] msg_da_const,
    input  wire [15:0] msg_vlid,
    input  wire [47:0] msg_src_mac,
    input  wire [31:0] msg_src_ip,
    input  wire [31:0] msg_dst_ip,
    input  wire [15:0] msg_src_port,
    input  wire [15:0] msg_dst_port,
    input  wire [7:0]  msg_ttl,
    input  wire [31:0] msg_bag_cycles,
    input  wire [31:0] msg_jitter_cycles,

    input  wire [7:0] payload_data,
    input  wire       payload_valid,
    output wire       payload_ready,
    input  wire       payload_last,
    input  wire       payload_abort,

    output wire [7:0] gmii_txd,
    output wire       gmii_tx_en,
    output wire       gmii_tx_er,
    input  wire [7:0] gmii_rxd,
    input  wire       gmii_rx_dv,
    input  wire       gmii_rx_er,

    output wire        msg_done,
    output wire        msg_error,
    output wire [3:0]  error_code,
    output wire [31:0] late_count,
    output wire [7:0]  rx_data,
    output wire        rx_valid,
    output wire        rx_sop,
    output wire        rx_eop,
    output wire [15:0] rx_length,
    input  wire        rx_ready,
    output wire        rx_accepted,
    output wire        rx_dropped,
    output wire [4:0]  rx_drop_reason,
    output wire [1:0]  rx_banks_busy,
    output wire        counter_saturated,
    output wire [31:0] tx_sent,
    output wire [31:0] tx_rejected,
    output wire [31:0] rx_seen,
    output wire [31:0] rx_good,
    output wire [31:0] rx_drop,
    output wire [31:0] rx_delivered
);
    wire [7:0] mac_tx_data;
    wire mac_tx_valid;
    wire mac_tx_ready;
    wire mac_tx_sop;
    wire mac_tx_eop;
    wire [15:0] mac_tx_length;
    wire mac_tx_afdx;
    wire mac_tx_done;
    wire mac_tx_reject;

    afdx_single_vl_tx #(.RESET_SN(RESET_SN), .CLK_HZ(CLK_HZ)) sender (
        .clk(clk), .reset(reset),
        .msg_valid(msg_valid), .msg_ready(msg_ready),
        .msg_payload_length(msg_payload_length), .msg_da_const(msg_da_const),
        .msg_vlid(msg_vlid), .msg_src_mac(msg_src_mac),
        .msg_src_ip(msg_src_ip), .msg_dst_ip(msg_dst_ip),
        .msg_src_port(msg_src_port), .msg_dst_port(msg_dst_port),
        .msg_ttl(msg_ttl), .msg_bag_cycles(msg_bag_cycles),
        .msg_jitter_cycles(msg_jitter_cycles),
        .payload_data(payload_data), .payload_valid(payload_valid),
        .payload_ready(payload_ready), .payload_last(payload_last),
        .payload_abort(payload_abort),
        .mac_tx_data(mac_tx_data), .mac_tx_valid(mac_tx_valid),
        .mac_tx_ready(mac_tx_ready), .mac_tx_sop(mac_tx_sop),
        .mac_tx_eop(mac_tx_eop), .mac_tx_length(mac_tx_length),
        .mac_tx_afdx(mac_tx_afdx), .mac_tx_done(mac_tx_done),
        .mac_tx_reject(mac_tx_reject), .gmii_tx_en(gmii_tx_en),
        .msg_done(msg_done), .msg_error(msg_error),
        .error_code(error_code), .late_count(late_count)
    );

    mac_gmii_core mac (
        .clk(clk), .reset(reset),
        .tx_data(mac_tx_data), .tx_valid(mac_tx_valid),
        .tx_sop(mac_tx_sop), .tx_eop(mac_tx_eop),
        .tx_length(mac_tx_length), .tx_afdx(mac_tx_afdx),
        .tx_ready(mac_tx_ready),
        .gmii_txd(gmii_txd), .gmii_tx_en(gmii_tx_en), .gmii_tx_er(gmii_tx_er),
        .gmii_rxd(gmii_rxd), .gmii_rx_dv(gmii_rx_dv), .gmii_rx_er(gmii_rx_er),
        .rx_data(rx_data), .rx_valid(rx_valid), .rx_sop(rx_sop), .rx_eop(rx_eop),
        .rx_ready(rx_ready), .rx_length(rx_length),
        .tx_done(mac_tx_done), .tx_reject(mac_tx_reject),
        .rx_accepted(rx_accepted), .rx_dropped(rx_dropped),
        .rx_drop_reason(rx_drop_reason), .tx_sent(tx_sent),
        .tx_rejected(tx_rejected), .rx_seen(rx_seen), .rx_good(rx_good),
        .rx_drop(rx_drop), .rx_delivered(rx_delivered),
        .rx_banks_busy(rx_banks_busy), .counter_saturated(counter_saturated)
    );
endmodule
