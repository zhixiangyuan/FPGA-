// Stage2 development fork: configured VL range, UDP checksum validation and port metadata.
// B2 candidate parser. It checks the approved B1 wire profile after the
// frozen B0 MAC has removed FCS. SN is reported, never filtered here: the
// receive SN state machine awaits the captain's separate decision.
module afdx_multi_vl_rx_parser #(
    parameter integer VL_COUNT=16,
    parameter integer CHECK_PORTS=1,
    parameter integer MAX_PAYLOAD = 1471
) (
    input  wire        clk,
    input  wire        reset,
    input  wire [7:0]  in_data,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire        in_sop,
    input  wire        in_eop,
    input  wire [15:0] in_length,
    input  wire [31:0] cfg_da_prefix,
    input  wire [15:0] cfg_vlid,
    input  wire [47:0] cfg_src_mac,
    input  wire [31:0] cfg_src_ip,
    input  wire [31:0] cfg_dst_ip,
    input  wire [15:0] cfg_src_port,
    input  wire [15:0] cfg_dst_port,
    output wire [7:0]  payload_data,
    output wire        payload_valid,
    input  wire        payload_ready,
    output wire        payload_sop,
    output wire        payload_eop,
    output wire [10:0] payload_length,
    output wire [15:0] payload_vlid,
    output wire [7:0]  payload_sn_unchecked,
    output wire [15:0] payload_src_port,payload_dst_port,
    output reg         candidate_accepted,
    output reg         candidate_rejected,
    output reg  [3:0]  reject_reason,
    output reg  [31:0] accepted_count,
    output reg  [31:0] rejected_count,
    output reg  [1:0]  banks_busy
);
    localparam [3:0] ERR_FRAMING=4'd1, ERR_ETHERNET=4'd2,
                     ERR_IPV4=4'd3, ERR_IP_CHECKSUM=4'd4,
                     ERR_UDP=4'd5, ERR_LENGTH=4'd6, ERR_PADDING=4'd7;
    reg [7:0] bank0 [0:MAX_PAYLOAD-1];
    reg [7:0] bank1 [0:MAX_PAYLOAD-1];
    reg [10:0] bank_length [0:1];
    reg [15:0] bank_vlid [0:1];
    reg [7:0] bank_sn [0:1];
    reg [15:0] bank_src_port[0:1],bank_dst_port[0:1];
    reg [15:0] wire_vlid,wire_src_port,wire_dst_port,udp_checksum;
    reg [31:0] udp_sum;
    reg [7:0] udp_hi;
    reg qbank [0:1];
    reg qhead, qtail;
    reg [1:0] qcount;
    reg [10:0] out_index;
    reg active, write_bank;
    reg [15:0] byte_index, declared_length, ip_total, udp_length;
    reg [7:0] ip_hi;
    reg [19:0] ip_sum;
    reg [3:0] first_error;
    reg [31:0] da_prefix_q, src_ip_q, dst_ip_q;
    reg [15:0] vlid_q, src_port_q, dst_port_q;
    reg [47:0] src_mac_q;

    wire any_free = !banks_busy[0] || !banks_busy[1];
    wire free_bank = banks_busy[0];
    assign in_ready = !reset && (active || any_free);
    wire in_fire = in_valid && in_ready;
    wire out_bank = qbank[qhead];
    assign payload_src_port=payload_valid?bank_src_port[out_bank]:16'd0;
    assign payload_dst_port=payload_valid?bank_dst_port[out_bank]:16'd0;
    assign payload_valid = !reset && qcount != 0;
    assign payload_data = !payload_valid ? 8'h00 :
                          (out_bank ? bank1[out_index] : bank0[out_index]);
    assign payload_length = !payload_valid ? 11'd0 : bank_length[out_bank];
    assign payload_vlid = !payload_valid ? 16'd0 : bank_vlid[out_bank];
    assign payload_sn_unchecked = !payload_valid ? 8'd0 : bank_sn[out_bank];
    assign payload_sop = payload_valid && out_index == 0;
    assign payload_eop = payload_valid && out_index + 11'd1 == payload_length;
    wire out_fire = payload_valid && payload_ready;
    wire out_done = out_fire && payload_eop;

    wire [15:0] p_length = ip_total - 16'd28;
    wire [15:0] padding_length = p_length < 16'd17 ? 16'd17 - p_length : 16'd0;
    wire [15:0] expected_length = 16'd43 + p_length + padding_length;
    wire [15:0] payload_end = 16'd42 + p_length;
    wire [15:0] sn_index = payload_end + padding_length;
    wire length_legal = ip_total >= 16'd29 && ip_total <= 16'd1499 &&
                        p_length <= MAX_PAYLOAD && udp_length == p_length + 16'd8 &&
                        declared_length == expected_length;

    function [15:0] folded_sum;
        input [19:0] sum;
        reg [16:0] first_fold;
        reg [16:0] second_fold;
        begin
            first_fold = {1'b0,sum[15:0]} + {13'd0,sum[19:16]};
            second_fold = {1'b0,first_fold[15:0]} + first_fold[16];
            folded_sum = second_fold[15:0];
        end
    endfunction
    function [31:0] sat_inc;
        input [31:0] value;
        begin sat_inc = value == 32'hffffffff ? value : value + 32'd1; end
    endfunction

    // The earliest failing category is retained. Structural errors cannot
    // leak candidate bytes because the bank is committed only at EOP.
    reg [3:0] beat_error;
    always @* begin
        beat_error = 0;
        if (active && (in_sop || in_length != declared_length)) beat_error = ERR_FRAMING;
        if (active && byte_index < 16'd42) begin
            case (byte_index)
                0: if (in_data != da_prefix_q[31:24]) beat_error=ERR_ETHERNET;
                1: if (in_data != da_prefix_q[23:16]) beat_error=ERR_ETHERNET;
                2: if (in_data != da_prefix_q[15:8]) beat_error=ERR_ETHERNET;
                3: if (in_data != da_prefix_q[7:0]) beat_error=ERR_ETHERNET;
                5: if ({wire_vlid[15:8],in_data}<vlid_q ||
                       ({1'b0,wire_vlid[15:8],in_data}-{1'b0,vlid_q})>=VL_COUNT)
                       beat_error=ERR_ETHERNET;
                6: if (in_data != src_mac_q[47:40]) beat_error=ERR_ETHERNET;
                7: if (in_data != src_mac_q[39:32]) beat_error=ERR_ETHERNET;
                8: if (in_data != src_mac_q[31:24]) beat_error=ERR_ETHERNET;
                9: if (in_data != src_mac_q[23:16]) beat_error=ERR_ETHERNET;
                10: if (in_data != src_mac_q[15:8]) beat_error=ERR_ETHERNET;
                11: if (in_data != src_mac_q[7:0]) beat_error=ERR_ETHERNET;
                12: if (in_data != 8'h08) beat_error=ERR_ETHERNET;
                13: if (in_data != 8'h00) beat_error=ERR_ETHERNET;
                14: if (in_data != 8'h45) beat_error=ERR_IPV4;
                15: if (in_data != 8'h00) beat_error=ERR_IPV4;
                18,19,21: if (in_data != 8'h00) beat_error=ERR_IPV4;
                20: if (in_data != 8'h40) beat_error=ERR_IPV4;
                22: if (in_data == 8'h00) beat_error=ERR_IPV4;
                23: if (in_data != 8'h11) beat_error=ERR_IPV4;
                26: if (in_data != src_ip_q[31:24]) beat_error=ERR_IPV4;
                27: if (in_data != src_ip_q[23:16]) beat_error=ERR_IPV4;
                28: if (in_data != src_ip_q[15:8]) beat_error=ERR_IPV4;
                29: if (in_data != src_ip_q[7:0]) beat_error=ERR_IPV4;
                30: if (in_data != dst_ip_q[31:24]) beat_error=ERR_IPV4;
                31: if (in_data != dst_ip_q[23:16]) beat_error=ERR_IPV4;
                32: if (in_data != dst_ip_q[15:8]) beat_error=ERR_IPV4;
                33: if (in_data != dst_ip_q[7:0]) beat_error=ERR_IPV4;
                34: if (CHECK_PORTS && in_data != src_port_q[15:8]) beat_error=ERR_UDP;
                35: if (CHECK_PORTS && in_data != src_port_q[7:0]) beat_error=ERR_UDP;
                36: if (CHECK_PORTS && in_data != dst_port_q[15:8]) beat_error=ERR_UDP;
                37: if (CHECK_PORTS && in_data != dst_port_q[7:0]) beat_error=ERR_UDP;
                40,41: begin end
                default: begin end
            endcase
        end
        if (active && byte_index >= payload_end && byte_index < sn_index &&
            in_data != 8'h00) beat_error = ERR_PADDING;
    end

    function [15:0] fold_udp;
        input [31:0] sum;
        reg [16:0] first,second;
        begin first={1'b0,sum[15:0]}+{1'b0,sum[31:16]};
              second={1'b0,first[15:0]}+first[16];
              fold_udp=second[15:0];end
    endfunction
    wire [31:0] udp_pseudo=udp_sum+{16'd0,src_ip_q[31:16]}+{16'd0,src_ip_q[15:0]}+
        {16'd0,dst_ip_q[31:16]}+{16'd0,dst_ip_q[15:0]}+32'd17+{16'd0,udp_length};
    wire udp_checksum_legal=udp_checksum==0 || fold_udp(udp_pseudo)==16'hffff;
    wire [3:0] final_error = first_error != 0 ? first_error :
                             beat_error != 0 ? beat_error :
                             !length_legal ? ERR_LENGTH :
                             folded_sum(ip_sum) != 16'hffff ? ERR_IP_CHECKSUM :
                             !udp_checksum_legal ? ERR_UDP :
                             byte_index != sn_index || byte_index + 16'd1 != in_length ? ERR_LENGTH :
                             4'd0;
    // A legal final beat is the SN byte, after every header/padding byte.
    // Their errors are already retained in first_error. Avoid routing the
    // current byte through the header error encoder just to commit the bank.
    wire frame_commit = in_fire && active && in_eop && first_error == 0 &&
                        !in_sop && in_length == declared_length && length_legal &&
                        folded_sum(ip_sum) == 16'hffff && udp_checksum_legal &&
                        byte_index == sn_index && byte_index + 16'd1 == in_length;
    wire frame_reject = in_fire && active && in_eop && !frame_commit;

    always @(posedge clk) begin
        if (reset) begin
            banks_busy<=0; qhead<=0; qtail<=0; qcount<=0; out_index<=0;
            active<=0; write_bank<=0; byte_index<=0; declared_length<=0;
            ip_total<=0; udp_length<=0; ip_hi<=0; ip_sum<=0; first_error<=0;
            da_prefix_q<=0; src_ip_q<=0; dst_ip_q<=0; vlid_q<=0;
            src_port_q<=0; dst_port_q<=0; src_mac_q<=0;
            bank_length[0]<=0; bank_length[1]<=0;
            bank_vlid[0]<=0; bank_vlid[1]<=0;
            bank_sn[0]<=0; bank_sn[1]<=0;
            bank_src_port[0]<=0;bank_src_port[1]<=0;bank_dst_port[0]<=0;bank_dst_port[1]<=0;
            wire_vlid<=0;wire_src_port<=0;wire_dst_port<=0;udp_checksum<=0;udp_sum<=0;udp_hi<=0;
            qbank[0]<=0; qbank[1]<=0;
            candidate_accepted<=0; candidate_rejected<=0; reject_reason<=0;
            accepted_count<=0; rejected_count<=0;
        end else begin
            candidate_accepted<=0; candidate_rejected<=0;
            if (out_fire) begin
                if (out_done) begin
                    out_index<=0; qhead<=!qhead; banks_busy[out_bank]<=0;
                end else out_index<=out_index+11'd1;
            end
            if (in_fire) begin
                if (!active) begin
                    active<=!in_eop; write_bank<=free_bank;
                    banks_busy[free_bank]<=!in_eop;
                    byte_index<=16'd1; declared_length<=in_length;
                    ip_total<=0; udp_length<=0; ip_sum<=0; ip_hi<=0;
                    wire_vlid<=0;wire_src_port<=0;wire_dst_port<=0;
                    udp_checksum<=0;udp_sum<=0;udp_hi<=0;
                    first_error<=!in_sop ? ERR_FRAMING :
                                 in_data!=cfg_da_prefix[31:24] ? ERR_ETHERNET : 4'd0;
                    da_prefix_q<=cfg_da_prefix; vlid_q<=cfg_vlid;
                    src_mac_q<=cfg_src_mac; src_ip_q<=cfg_src_ip;
                    dst_ip_q<=cfg_dst_ip; src_port_q<=cfg_src_port;
                    dst_port_q<=cfg_dst_port;
                    if(in_eop) begin
                        candidate_rejected<=1; reject_reason<=ERR_FRAMING;
                        rejected_count<=sat_inc(rejected_count);
                    end
                end else begin
                    byte_index<=byte_index+16'd1;
                    if(byte_index==4)wire_vlid[15:8]<=in_data;
                    if(byte_index==5)wire_vlid[7:0]<=in_data;
                    if(byte_index==34)wire_src_port[15:8]<=in_data;
                    if(byte_index==35)wire_src_port[7:0]<=in_data;
                    if(byte_index==36)wire_dst_port[15:8]<=in_data;
                    if(byte_index==37)wire_dst_port[7:0]<=in_data;
                    if(byte_index==40)udp_checksum[15:8]<=in_data;
                    if(byte_index==41)udp_checksum[7:0]<=in_data;
                    if(byte_index>=34 && byte_index<payload_end)begin
                        if(!byte_index[0])begin
                            udp_hi<=in_data;
                            if(byte_index+1==payload_end)udp_sum<=udp_sum+{16'd0,in_data,8'd0};
                        end else udp_sum<=udp_sum+{16'd0,udp_hi,in_data};
                    end
                    if (beat_error!=0 && first_error==0) first_error<=beat_error;
                    if (byte_index==16) ip_total[15:8]<=in_data;
                    if (byte_index==17) ip_total[7:0]<=in_data;
                    if (byte_index==38) udp_length[15:8]<=in_data;
                    if (byte_index==39) udp_length[7:0]<=in_data;
                    if (byte_index>=14 && byte_index<=33) begin
                        if (!byte_index[0]) ip_hi<=in_data;
                        else ip_sum<=ip_sum+{ip_hi,in_data};
                    end
                    if (byte_index>=42 && byte_index<payload_end &&
                        p_length>=1 && p_length<=MAX_PAYLOAD) begin
                        if(write_bank)bank1[byte_index-16'd42]<=in_data;
                        else bank0[byte_index-16'd42]<=in_data;
                    end
                    if (in_eop) begin
                        active<=0;
                        if (frame_commit) begin
                            bank_length[write_bank]<=p_length[10:0];
                            bank_vlid[write_bank]<=wire_vlid;
                            bank_src_port[write_bank]<=wire_src_port;
                            bank_dst_port[write_bank]<=wire_dst_port;
                            bank_sn[write_bank]<=in_data;
                            qbank[qtail]<=write_bank; qtail<=!qtail;
                            candidate_accepted<=1;
                            accepted_count<=sat_inc(accepted_count);
                        end else begin
                            banks_busy[write_bank]<=0;
                            candidate_rejected<=1; reject_reason<=final_error;
                            rejected_count<=sat_inc(rejected_count);
                        end
                    end
                end
            end
            case ({frame_commit,out_done})
                2'b10: qcount<=qcount+2'd1;
                2'b01: qcount<=qcount-2'd1;
                default: begin end
            endcase
        end
    end
endmodule
