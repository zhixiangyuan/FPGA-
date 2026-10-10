`timescale 1ns/1ps

module tb_b1_ready_stall;
    localparam integer FRAME_COUNT = 268;
    localparam integer MAX_BYTES = 65536;
    reg clk = 0;
    always #4 clk = ~clk;
    reg reset = 1;
    reg msg_valid = 0;
    wire msg_ready;
    reg [10:0] msg_payload_length = 0;
    reg [7:0] payload_data = 0;
    reg payload_valid = 0;
    wire payload_ready;
    reg payload_last = 0;
    reg payload_abort = 0;
    wire [7:0] mac_tx_data;
    wire mac_tx_valid, mac_tx_sop, mac_tx_eop, mac_tx_afdx;
    wire [15:0] mac_tx_length;
    reg mac_tx_done = 0;
    reg mac_tx_reject = 0;
    wire msg_done, msg_error;
    wire [3:0] error_code;
    wire [31:0] late_count;
    reg gmii_tx_en = 0;
    reg [31:0] cycle_count = 0;
    wire mac_tx_ready = ((cycle_count % 11) >= 4);

    reg [7:0] payload_mem [0:MAX_BYTES-1];
    reg [7:0] client_mem [0:MAX_BYTES-1];
    reg [215:0] meta_mem [0:FRAME_COUNT-1];
    integer expected_frame = -1;
    integer accepted_bytes = 0;
    integer stall_cycles = 0;
    integer stall_checks = 0;
    integer frame_count = 0;
    reg prev_stall = 0;
    reg [7:0] held_data = 0;
    reg held_valid = 0, held_sop = 0, held_eop = 0;
    reg [15:0] held_length = 0;

    afdx_single_vl_tx #(.RESET_SN(8'd1), .CLK_HZ(32'd1000000)) dut (
        .clk(clk), .reset(reset), .msg_valid(msg_valid), .msg_ready(msg_ready),
        .msg_payload_length(msg_payload_length), .msg_da_const(32'h03000000),
        .msg_vlid(16'h1234), .msg_src_mac(48'h020000000009),
        .msg_src_ip(32'h0a000001), .msg_dst_ip(32'he0e0003c),
        .msg_src_port(16'd24), .msg_dst_port(16'd23), .msg_ttl(8'd1),
        .msg_bag_cycles(32'd1000), .msg_jitter_cycles(32'd5000),
        .payload_data(payload_data), .payload_valid(payload_valid),
        .payload_ready(payload_ready), .payload_last(payload_last),
        .payload_abort(payload_abort), .mac_tx_data(mac_tx_data),
        .mac_tx_valid(mac_tx_valid), .mac_tx_ready(mac_tx_ready),
        .mac_tx_sop(mac_tx_sop), .mac_tx_eop(mac_tx_eop),
        .mac_tx_length(mac_tx_length), .mac_tx_afdx(mac_tx_afdx),
        .mac_tx_done(mac_tx_done), .mac_tx_reject(mac_tx_reject),
        .gmii_tx_en(gmii_tx_en), .msg_done(msg_done), .msg_error(msg_error),
        .error_code(error_code), .late_count(late_count)
    );

    initial begin
        $readmemh("golden/golden_payload.mem", payload_mem);
        $readmemh("golden/golden_client.mem", client_mem);
        $readmemh("golden/golden_meta.mem", meta_mem);
    end

    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
        if (reset) begin
            prev_stall <= 0;
            accepted_bytes <= 0;
        end else begin
            if (prev_stall) begin
                if (mac_tx_valid !== held_valid || mac_tx_data !== held_data ||
                    mac_tx_sop !== held_sop || mac_tx_eop !== held_eop ||
                    mac_tx_length !== held_length)
                    $fatal(1, "MAC ready stall changed data/control: expected data=%02x sop=%b eop=%b length=%0d got data=%02x sop=%b eop=%b length=%0d",
                        held_data, held_sop, held_eop, held_length,
                        mac_tx_data, mac_tx_sop, mac_tx_eop, mac_tx_length);
                stall_checks <= stall_checks + 1;
            end
            prev_stall <= mac_tx_valid && !mac_tx_ready;
            if (mac_tx_valid && !mac_tx_ready) begin
                stall_cycles <= stall_cycles + 1;
                held_valid <= mac_tx_valid;
                held_data <= mac_tx_data;
                held_sop <= mac_tx_sop;
                held_eop <= mac_tx_eop;
                held_length <= mac_tx_length;
            end
            if (mac_tx_valid && mac_tx_ready) begin
                if (expected_frame < 0) $fatal(1, "Unexpected MAC byte");
                if (accepted_bytes >= meta_mem[expected_frame][135:120])
                    $fatal(1, "MAC emitted too many bytes");
                if (mac_tx_data !== client_mem[meta_mem[expected_frame][167:136]+accepted_bytes])
                    $fatal(1, "MAC client byte mismatch frame=%0d index=%0d got=%02x expected=%02x",
                        expected_frame, accepted_bytes, mac_tx_data,
                        client_mem[meta_mem[expected_frame][167:136]+accepted_bytes]);
                if (mac_tx_sop !== (accepted_bytes == 0)) $fatal(1, "MAC SOP mismatch");
                if (mac_tx_eop !== (accepted_bytes + 1 == meta_mem[expected_frame][135:120]))
                    $fatal(1, "MAC EOP mismatch index=%0d length=%0d", accepted_bytes, meta_mem[expected_frame][135:120]);
                if (mac_tx_length !== meta_mem[expected_frame][135:120])
                    $fatal(1, "MAC length changed or incorrect");
                if (!mac_tx_afdx) $fatal(1, "B1 MAC client AFDX flag is not asserted");
                accepted_bytes <= accepted_bytes + 1;
            end
        end
    end

    task automatic send_frame(input integer frame_idx);
        integer payload_len, payload_offset, k, timeout;
        begin
            payload_len = meta_mem[frame_idx][183:168];
            payload_offset = meta_mem[frame_idx][215:184];
            @(negedge clk); expected_frame=frame_idx; accepted_bytes=0;
            msg_payload_length=payload_len[10:0]; msg_valid=1;
            timeout=0;
            while (!msg_ready && timeout<10000) begin @(posedge clk); timeout=timeout+1; end
            if (!msg_ready) $fatal(1, "Descriptor ready timeout");
            @(posedge clk);
            @(negedge clk); msg_valid=0;
            for (k=0; k<payload_len; k=k+1) begin
                @(negedge clk); payload_data=payload_mem[payload_offset+k];
                payload_valid=1; payload_last=(k==payload_len-1);
                timeout=0;
                do begin @(posedge clk); timeout=timeout+1; if(timeout>20000)$fatal(1,"Payload ready timeout"); end while(!payload_ready);
            end
            @(negedge clk); payload_valid=0; payload_last=0;
            timeout=0;
            while (accepted_bytes < meta_mem[frame_idx][135:120] && timeout<30000) begin @(posedge clk); timeout=timeout+1; end
            if (accepted_bytes != meta_mem[frame_idx][135:120]) $fatal(1,"Client byte count timeout");
            // Signal the real MAC completion contract only after the final
            // client byte is accepted. The one-cycle GMII edge also starts BAG.
            @(negedge clk); gmii_tx_en=1; mac_tx_done=1;
            @(negedge clk); gmii_tx_en=0; mac_tx_done=0;
            timeout=0;
            while (!msg_done && timeout<10000) begin @(posedge clk); timeout=timeout+1; end
            if (!msg_done) $fatal(1,"Message completion timeout");
            frame_count=frame_count+1;
        end
    endtask

    integer i;
    initial begin
        repeat (5) @(posedge clk);
        @(negedge clk); reset=0;
        for (i=0; i<5; i=i+1) send_frame(i);
        if (stall_cycles < 100 || stall_checks < 100)
            $fatal(1, "Insufficient ready backpressure observed stalls=%0d checks=%0d", stall_cycles, stall_checks);
        if (frame_count != 5 || msg_error || late_count != 0)
            $fatal(1, "Unexpected B1 ready-stall end state");
        $display("B1_READY_STALL = PASS frames=%0d checked_bytes=%0d stalled_cycles=%0d hold_checks=%0d",
            frame_count, accepted_bytes, stall_cycles, stall_checks);
        $finish;
    end

    initial begin
        #100000000;
        $fatal(1,"Ready-stall test timeout");
    end
endmodule
