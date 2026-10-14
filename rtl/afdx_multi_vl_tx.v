// Stage2 development fork: independent per-VL SN and BAG, shared frame builder.
// Derived from frozen B1 SHA256 dcf165241bebae6c481ead513ebd8c7c72a689d312996a52914c6a36112afd8a.
// Single-VL AFDX IPv4/UDP frame builder for the unchanged stage5B0 MAC TX
// client contract. This module emits DA..SN only; the MAC emits FCS/GMII.
module afdx_multi_vl_tx #(
    parameter integer VL_COUNT = 16,
    parameter [15:0] VL_BASE = 16'h1234,
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

    output reg  [7:0] mac_tx_data,
    output reg        mac_tx_valid,
    input  wire       mac_tx_ready,
    output reg        mac_tx_sop,
    output reg        mac_tx_eop,
    output reg  [15:0] mac_tx_length,
    output wire       mac_tx_afdx,
    input  wire       mac_tx_done,
    input  wire       mac_tx_reject,
    input  wire       gmii_tx_en,

    output reg        msg_done,
    output reg        msg_error,
    output reg  [3:0] error_code,
    output wire [31:0] late_count
);
    localparam [3:0] ST_IDLE       = 4'd0;
    localparam [3:0] ST_ETH        = 4'd1;
    localparam [3:0] ST_IPV4       = 4'd2;
    localparam [3:0] ST_UDP        = 4'd3;
    localparam [3:0] ST_PAYLOAD    = 4'd4;
    localparam [3:0] ST_PADDING    = 4'd5;
    localparam [3:0] ST_SN         = 4'd6;
    localparam [3:0] ST_WAIT_DONE  = 4'd7;
    localparam [3:0] ST_ABORT      = 4'd8;
    localparam [3:0] ST_WAIT_REJ   = 4'd9;
    localparam [3:0] ST_DRAIN      = 4'd10;

    localparam [3:0] ERR_BAD_LENGTH = 4'd1;
    localparam [3:0] ERR_BAD_DA     = 4'd2;
    localparam [3:0] ERR_BAD_SA     = 4'd3;
    localparam [3:0] ERR_BAD_TTL    = 4'd4;
    localparam [3:0] ERR_BAD_BAG    = 4'd5;
    localparam [3:0] ERR_PAYLOAD_EARLY = 4'd6;
    localparam [3:0] ERR_PAYLOAD_LATE  = 4'd7;
    localparam [3:0] ERR_PAYLOAD_ABORT = 4'd8;
    localparam [3:0] ERR_MAC_REJECT    = 4'd9;

    reg [3:0] state;
    reg [7:0] next_sn [0:VL_COUNT-1];
    reg [15:0] active_vl;
    wire [16:0] descriptor_vl = {1'b0,msg_vlid}-{1'b0,VL_BASE};
    wire vl_legal = msg_vlid >= VL_BASE && descriptor_vl < VL_COUNT;
    wire [15:0] descriptor_index = vl_legal ? descriptor_vl[15:0] : 16'd0;
    integer init_vl;
    reg [7:0] active_sn;
    reg [10:0] payload_length_q;
    reg [10:0] payload_remaining;
    reg [4:0] pad_remaining;
    reg [3:0] eth_index;
    reg [4:0] ipv4_index;
    reg [2:0] udp_index;
    reg [111:0] eth_shift;
    reg [159:0] ipv4_shift;
    reg [63:0] udp_shift;
    reg [31:0] src_ip_q;
    reg [31:0] dst_ip_q;
    reg [15:0] src_port_q;
    reg [15:0] dst_port_q;
    reg [7:0] ttl_q;
    reg [3:0] pending_error_code;
    reg need_drain;
    reg drain_done;
    reg mac_reject_seen;

    wire [10:0] desc_padding = (msg_payload_length < 11'd17) ?
                               (11'd17 - msg_payload_length) : 11'd0;
    wire [15:0] desc_mac_length = 16'd43 + {5'd0, msg_payload_length} + {5'd0, desc_padding};
    wire [15:0] ipv4_total_q = 16'd28 + {5'd0, payload_length_q};
    wire [15:0] udp_length_q = 16'd8 + {5'd0, payload_length_q};
    wire [159:0] ipv4_base_q = {
        8'h45, 8'h00, ipv4_total_q, 16'h0000, 16'h4000,
        ttl_q, 8'h11, 16'h0000, src_ip_q, dst_ip_q
    };
    wire [15:0] ipv4_checksum_q;
    afdx_ipv4_checksum checksum_q (
        .header_zero_checksum(ipv4_base_q),
        .checksum(ipv4_checksum_q)
    );
    wire [159:0] ipv4_header_q = {
        8'h45, 8'h00, ipv4_total_q, 16'h0000, 16'h4000,
        ttl_q, 8'h11, ipv4_checksum_q, src_ip_q, dst_ip_q
    };

    wire desc_bad_length = (msg_payload_length < 11'd1) || (msg_payload_length > 11'd1471);
    wire desc_bad_da = (msg_da_const[25:24] != 2'b11) || !vl_legal;
    wire desc_bad_sa = msg_src_mac[40];
    wire desc_bad_ttl = (msg_ttl == 8'd0);
    localparam [31:0] BAG_1MS_CYCLES = CLK_HZ / 32'd1000;
    wire desc_bag_valid = (CLK_HZ >= 32'd1000) &&
                          ((CLK_HZ % 32'd1000) == 0) &&
                          (msg_bag_cycles == (BAG_1MS_CYCLES << 0) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 1) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 2) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 3) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 4) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 5) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 6) ||
                           msg_bag_cycles == (BAG_1MS_CYCLES << 7));
    wire desc_bad_bag = !desc_bag_valid;
    wire desc_legal = !desc_bad_length && !desc_bad_da && !desc_bad_sa && !desc_bad_ttl && !desc_bad_bag;
    wire desc_fire = msg_valid && msg_ready;
    wire legal_desc_fire = desc_fire && desc_legal;
    wire tx_fire = mac_tx_valid && mac_tx_ready;

    wire state_building = (state >= ST_ETH) && (state <= ST_SN);
    wire payload_early = (state == ST_PAYLOAD) && payload_valid && payload_ready &&
                         payload_last && (payload_remaining != 11'd1);
    wire payload_late = (state == ST_PAYLOAD) && payload_valid && payload_ready &&
                        !payload_last && (payload_remaining == 11'd1);
    wire cancel_event = (state_building && payload_abort) || payload_early || payload_late ||
                        ((state == ST_WAIT_DONE) && mac_tx_reject);
    wire frame_pending = (state == ST_SN);
    wire sn_release;
    wire late_pulse;
    wire frame_eop_fire = (state == ST_SN) && tx_fire && mac_tx_eop;

    assign msg_ready = !reset && (state == ST_IDLE) && mac_tx_ready;
    assign payload_ready = !reset &&
                           (((state == ST_PAYLOAD) && mac_tx_ready && !payload_abort) ||
                            ((state == ST_DRAIN) && !payload_abort));
    assign mac_tx_afdx = 1'b1;

    wire [VL_COUNT-1:0] releases,late_pulses;
    wire [31:0] late_counts [0:VL_COUNT-1];
    assign sn_release = releases[active_vl];
    assign late_pulse = late_pulses[active_vl];
    // Sum is diagnostic only; per-VL gates own the actual BAG state.
    reg [31:0] late_total;
    integer sum_vl;
    always @* begin
        late_total=0;
        for(sum_vl=0;sum_vl<VL_COUNT;sum_vl=sum_vl+1)
            late_total=late_total+late_counts[sum_vl];
    end
    assign late_count=late_total;
    genvar vl;
    generate for(vl=0;vl<VL_COUNT;vl=vl+1)begin: vl_bag
        afdx_bag_gate gate(
            .clk(clk),.reset(reset),
            .gmii_tx_en(gmii_tx_en && active_vl==vl),
            .frame_arm(legal_desc_fire && descriptor_index==vl),
            .frame_cancel(cancel_event && active_vl==vl),
            .frame_pending(frame_pending && active_vl==vl),
            .frame_eop_fire(frame_eop_fire && active_vl==vl),
            .bag_cycles(msg_bag_cycles),.jitter_cycles(msg_jitter_cycles),
            .release_final_byte(releases[vl]),.late_pulse(late_pulses[vl]),
            .late_count(late_counts[vl]));
    end endgenerate

    always @* begin
        mac_tx_data = 8'h00;
        mac_tx_valid = 1'b0;
        mac_tx_sop = 1'b0;
        mac_tx_eop = 1'b0;

        if (!(state_building && payload_abort)) begin
            case (state)
                ST_ETH: begin
                    mac_tx_data = eth_shift[111:104];
                    mac_tx_valid = 1'b1;
                    mac_tx_sop = (eth_index == 4'd0);
                end
                ST_IPV4: begin
                    mac_tx_data = ipv4_shift[159:152];
                    mac_tx_valid = 1'b1;
                end
                ST_UDP: begin
                    mac_tx_data = udp_shift[63:56];
                    mac_tx_valid = 1'b1;
                end
                ST_PAYLOAD: begin
                    mac_tx_data = payload_data;
                    mac_tx_valid = payload_valid && !payload_abort;
                end
                ST_PADDING: begin
                    mac_tx_data = 8'h00;
                    mac_tx_valid = 1'b1;
                end
                ST_SN: begin
                    mac_tx_data = active_sn;
                    mac_tx_valid = sn_release;
                    mac_tx_eop = sn_release;
                end
                ST_ABORT: begin
                    // B0 abort contract: repeated SOP in an in-progress frame
                    // causes finish_bad/flush, independent of remaining length.
                    mac_tx_data = 8'h00;
                    mac_tx_valid = 1'b1;
                    mac_tx_sop = 1'b1;
                    mac_tx_eop = 1'b1;
                end
                default: begin end
            endcase
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            state <= ST_IDLE;
            active_vl <= 0;
            for(init_vl=0;init_vl<VL_COUNT;init_vl=init_vl+1) next_sn[init_vl] <= RESET_SN;
            active_sn <= RESET_SN;
            payload_length_q <= 11'd0;
            payload_remaining <= 11'd0;
            pad_remaining <= 5'd0;
            eth_index <= 4'd0;
            ipv4_index <= 5'd0;
            udp_index <= 3'd0;
            eth_shift <= 112'd0;
            ipv4_shift <= 160'd0;
            udp_shift <= 64'd0;
            src_ip_q <= 32'd0;
            dst_ip_q <= 32'd0;
            src_port_q <= 16'd0;
            dst_port_q <= 16'd0;
            ttl_q <= 8'd0;
            mac_tx_length <= 16'd0;
            pending_error_code <= 4'd0;
            need_drain <= 1'b0;
            drain_done <= 1'b0;
            mac_reject_seen <= 1'b0;
            msg_done <= 1'b0;
            msg_error <= 1'b0;
            error_code <= 4'd0;
        end else begin
            msg_done <= 1'b0;
            msg_error <= 1'b0;

            if (desc_fire && !desc_legal) begin
                msg_error <= 1'b1;
                if (desc_bad_length) error_code <= ERR_BAD_LENGTH;
                else if (desc_bad_da) error_code <= ERR_BAD_DA;
                else if (desc_bad_sa) error_code <= ERR_BAD_SA;
                else if (desc_bad_ttl) error_code <= ERR_BAD_TTL;
                else error_code <= ERR_BAD_BAG;
            end else if (legal_desc_fire) begin
                state <= ST_ETH;
                active_vl <= descriptor_index;
                active_sn <= next_sn[descriptor_index];
                payload_length_q <= msg_payload_length;
                payload_remaining <= msg_payload_length;
                pad_remaining <= desc_padding[4:0];
                eth_index <= 4'd0;
                ipv4_index <= 5'd0;
                udp_index <= 3'd0;
                eth_shift <= {msg_da_const, msg_vlid, msg_src_mac, 16'h0800};
                src_ip_q <= msg_src_ip;
                dst_ip_q <= msg_dst_ip;
                src_port_q <= msg_src_port;
                dst_port_q <= msg_dst_port;
                ttl_q <= msg_ttl;
                mac_tx_length <= desc_mac_length;
                pending_error_code <= 4'd0;
                need_drain <= 1'b0;
                drain_done <= 1'b0;
                mac_reject_seen <= 1'b0;
            end else if (state_building && payload_abort) begin
                pending_error_code <= ERR_PAYLOAD_ABORT;
                need_drain <= 1'b0;
                state <= ST_ABORT;
            end else begin
                case (state)
                    ST_IDLE: begin end

                    ST_ETH: if (tx_fire) begin
                        if (eth_index == 4'd13) begin
                            eth_index <= 4'd0;
                            ipv4_index <= 5'd0;
                            ipv4_shift <= ipv4_header_q;
                            state <= ST_IPV4;
                        end else begin
                            eth_shift <= {eth_shift[103:0], 8'h00};
                            eth_index <= eth_index + 1'b1;
                        end
                    end

                    ST_IPV4: if (tx_fire) begin
                        if (ipv4_index == 5'd19) begin
                            ipv4_index <= 5'd0;
                            udp_index <= 3'd0;
                            udp_shift <= {src_port_q, dst_port_q, udp_length_q, 16'h0000};
                            state <= ST_UDP;
                        end else begin
                            ipv4_shift <= {ipv4_shift[151:0], 8'h00};
                            ipv4_index <= ipv4_index + 1'b1;
                        end
                    end

                    ST_UDP: if (tx_fire) begin
                        if (udp_index == 3'd7) begin
                            udp_index <= 3'd0;
                            state <= ST_PAYLOAD;
                        end else begin
                            udp_shift <= {udp_shift[55:0], 8'h00};
                            udp_index <= udp_index + 1'b1;
                        end
                    end

                    ST_PAYLOAD: if (payload_valid && payload_ready) begin
                        if (payload_last && (payload_remaining != 11'd1)) begin
                            pending_error_code <= ERR_PAYLOAD_EARLY;
                            need_drain <= 1'b0;
                            state <= ST_ABORT;
                        end else if (!payload_last && (payload_remaining == 11'd1)) begin
                            pending_error_code <= ERR_PAYLOAD_LATE;
                            need_drain <= 1'b1;
                            state <= ST_ABORT;
                        end else begin
                            payload_remaining <= payload_remaining - 1'b1;
                            if (payload_remaining == 11'd1) begin
                                if (pad_remaining != 5'd0) state <= ST_PADDING;
                                else state <= ST_SN;
                            end
                        end
                    end

                    ST_PADDING: if (tx_fire) begin
                        if (pad_remaining == 5'd1) begin
                            pad_remaining <= 5'd0;
                            state <= ST_SN;
                        end else begin
                            pad_remaining <= pad_remaining - 1'b1;
                        end
                    end

                    ST_SN: if (tx_fire) begin
                        state <= ST_WAIT_DONE;
                    end

                    ST_WAIT_DONE: begin
                        if (mac_tx_reject) begin
                            msg_error <= 1'b1;
                            error_code <= ERR_MAC_REJECT;
                            state <= ST_IDLE;
                        end else if (mac_tx_done) begin
                            msg_done <= 1'b1;
                            if (active_sn == 8'd255) next_sn[active_vl] <= 8'd1;
                            else next_sn[active_vl] <= active_sn + 1'b1;
                            state <= ST_IDLE;
                        end
                    end

                    ST_ABORT: if (tx_fire) begin
                        mac_reject_seen <= 1'b0;
                        if (need_drain) begin
                            drain_done <= 1'b0;
                            state <= ST_DRAIN;
                        end else begin
                            state <= ST_WAIT_REJ;
                        end
                    end

                    ST_WAIT_REJ: if (mac_tx_reject) begin
                        msg_error <= 1'b1;
                        error_code <= pending_error_code;
                        state <= ST_IDLE;
                    end

                    ST_DRAIN: begin
                        if (mac_tx_reject) mac_reject_seen <= 1'b1;
                        if (payload_abort || (payload_valid && payload_ready && payload_last))
                            drain_done <= 1'b1;
                        if ((mac_reject_seen || mac_tx_reject) &&
                            (drain_done || payload_abort || (payload_valid && payload_ready && payload_last))) begin
                            msg_error <= 1'b1;
                            error_code <= pending_error_code;
                            state <= ST_IDLE;
                        end
                    end

                    default: state <= ST_IDLE;
                endcase
            end
        end
    end
endmodule
