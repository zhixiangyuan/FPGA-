// Netlist suite: same approved protocol Golden, real 125MHz/BAG cycle counts.
// QUICK_PRESSURE_ONLY is used only for preliminary RTL TB validation; netlist runner never sets it.
`timescale 1ns/1ps

module tb_b1_netlist_full;
    localparam integer FRAME_COUNT = 268;
    localparam integer MAX_BYTES = 65536;
`ifdef QUICK_PRESSURE_ONLY
    localparam integer SN_WRAP_FRAMES = 1;
`else
    localparam integer SN_WRAP_FRAMES = 256;
`endif

    reg clk = 1'b0;
    always #4 clk = ~clk;

    reg reset = 1'b1;
    reg msg_valid = 1'b0;
    wire msg_ready;
    reg [10:0] msg_payload_length = 0;
    reg [31:0] msg_da_const = 32'h03000000;
    reg [15:0] msg_vlid = 16'h1234;
    reg [47:0] msg_src_mac = 48'h020000000009;
    reg [31:0] msg_src_ip = 32'h0a000001;
    reg [31:0] msg_dst_ip = 32'he0e0003c;
    reg [15:0] msg_src_port = 16'd24;
    reg [15:0] msg_dst_port = 16'd23;
    reg [7:0] msg_ttl = 8'd1;
    reg [31:0] msg_bag_cycles = 32'd125000;
    reg [31:0] msg_jitter_cycles = 32'd12500;

    reg [7:0] payload_data = 0;
    reg payload_valid = 0;
    wire payload_ready;
    reg payload_last = 0;
    reg payload_abort = 0;

    wire [7:0] gmii_txd;
    wire gmii_tx_en, gmii_tx_er;
    reg [7:0] gmii_rxd = 0;
    reg gmii_rx_dv = 0, gmii_rx_er = 0;

    wire msg_done, msg_error;
    wire [3:0] error_code;
    wire [31:0] late_count;
    wire [7:0] rx_data;
    wire rx_valid, rx_sop, rx_eop;
    wire [15:0] rx_length;
    reg rx_ready = 1;
    wire rx_accepted, rx_dropped;
    wire [4:0] rx_drop_reason;
    wire [1:0] rx_banks_busy;
    wire counter_saturated;
    wire [31:0] tx_sent, tx_rejected, rx_seen, rx_good, rx_drop, rx_delivered;

    reg [7:0] payload_mem [0:MAX_BYTES-1];
    reg [7:0] client_mem [0:MAX_BYTES-1];
    reg [7:0] wire_mem [0:MAX_BYTES-1];
    reg [215:0] meta_mem [0:FRAME_COUNT-1];

    integer cycle_count = 0;
    integer expected_frame = -1;
    integer expected_rx_frame = -1;
    integer tx_wire_frames = 0;
    integer tx_wire_bytes = 0;
    integer wire_index = 0;
    integer rx_frames_checked = 0;
    integer rx_byte_index = 0;
    integer error_pulses = 0;
    integer done_pulses = 0;
    integer last_start_cycle = 0;
    integer have_gmii_start = 0;
    integer expected_bag = 125000;
    reg gmii_tx_en_d = 0;
    reg msg_done_d = 0, msg_error_d = 0;
    reg inject_rx=0;
    reg [7:0] inject_rxd=0;
    reg inject_dv=0;
    reg pressure_phase=0;
    integer pressure_rx_before;
    integer pressure_seen_before, pressure_good_before, pressure_drop_before;
    integer gmii_dump_fd;
    integer rx_dump_fd;

    afdx_network_tx_top dut (
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
        .gmii_txd(gmii_txd), .gmii_tx_en(gmii_tx_en), .gmii_tx_er(gmii_tx_er),
        .gmii_rxd(gmii_rxd), .gmii_rx_dv(gmii_rx_dv), .gmii_rx_er(gmii_rx_er),
        .msg_done(msg_done), .msg_error(msg_error), .error_code(error_code),
        .late_count(late_count), .rx_data(rx_data), .rx_valid(rx_valid),
        .rx_sop(rx_sop), .rx_eop(rx_eop), .rx_length(rx_length),
        .rx_ready(rx_ready), .rx_accepted(rx_accepted), .rx_dropped(rx_dropped),
        .rx_drop_reason(rx_drop_reason), .rx_banks_busy(rx_banks_busy),
        .counter_saturated(counter_saturated), .tx_sent(tx_sent),
        .tx_rejected(tx_rejected), .rx_seen(rx_seen), .rx_good(rx_good),
        .rx_drop(rx_drop), .rx_delivered(rx_delivered)
    );

    initial begin
        $readmemh("golden/golden_payload.mem", payload_mem);
        $readmemh("golden/golden_client.mem", client_mem);
        $readmemh("golden/golden_wire.mem", wire_mem);
        $readmemh("golden/golden_meta.mem", meta_mem);
        gmii_dump_fd = $fopen("actual_tx_gmii.csv", "w");
        rx_dump_fd = $fopen("actual_rx_client.csv", "w");
        if (gmii_dump_fd == 0 || rx_dump_fd == 0) $fatal(1, "Cannot open actual byte dump files");
        $fdisplay(gmii_dump_fd, "cycle,frame_index,wire_byte_index,gmii_txd");
        $fdisplay(rx_dump_fd, "cycle,frame_index,client_byte_index,rx_data,rx_sop,rx_eop,rx_length");
    end

    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
        if (reset) begin
            // One registered GMII PHY loop. Reset also restarts the BAG
            // observation epoch, matching the sender's reset behavior.
            gmii_rxd <= 8'h00;
            gmii_rx_dv <= 1'b0;
            gmii_rx_er <= 1'b0;
            gmii_tx_en_d <= 1'b0;
            msg_done_d <= 1'b0;
            msg_error_d <= 1'b0;
            have_gmii_start <= 0;
            last_start_cycle <= 0;
        end else begin
            gmii_rxd <= inject_rx ? inject_rxd : gmii_txd;
            gmii_rx_dv <= inject_rx ? inject_dv : gmii_tx_en;
            gmii_rx_er <= inject_rx ? 1'b0 : gmii_tx_er;
            gmii_tx_en_d <= gmii_tx_en;
            msg_done_d <= msg_done;
            msg_error_d <= msg_error;
            if (msg_done && msg_done_d) $fatal(1, "msg_done was not a one-cycle pulse");
            if (msg_error && msg_error_d) $fatal(1, "msg_error was not a one-cycle pulse");
            if (msg_done) done_pulses <= done_pulses + 1;
            if (msg_error) error_pulses <= error_pulses + 1;

            if (gmii_tx_en && !gmii_tx_en_d) begin
                if (expected_frame < 0)
                    $fatal(1, "Unexpected GMII frame start while no valid frame is expected");
                if (have_gmii_start && (cycle_count - last_start_cycle) < expected_bag)
                    $fatal(1, "BAG violation: GMII start gap=%0d expected>=%0d", cycle_count-last_start_cycle, expected_bag);
                if (meta_mem[expected_frame][87:72] == 0)
                    $fatal(1, "Golden frame has zero wire length");
                if (gmii_txd !== wire_mem[meta_mem[expected_frame][119:88]])
                    $fatal(1, "GMII byte mismatch frame=%0d byte=0 got=%02x expected=%02x",
                        expected_frame, gmii_txd, wire_mem[meta_mem[expected_frame][119:88]]);
                last_start_cycle <= cycle_count;
                have_gmii_start <= 1;
                wire_index <= 1;
                tx_wire_bytes <= tx_wire_bytes + 1;
                $fdisplay(gmii_dump_fd, "%0d,%0d,0,%02X", cycle_count, expected_frame, gmii_txd);
            end
            else if (gmii_tx_en) begin
                if (expected_frame < 0)
                    $fatal(1, "GMII byte emitted without a Golden frame");
                if (wire_index >= meta_mem[expected_frame][87:72])
                    $fatal(1, "GMII frame too long at frame=%0d byte=%0d", expected_frame, wire_index);
                if (gmii_txd !== wire_mem[meta_mem[expected_frame][119:88] + wire_index])
                    $fatal(1, "GMII byte mismatch frame=%0d byte=%0d got=%02x expected=%02x",
                        expected_frame, wire_index, gmii_txd,
                        wire_mem[meta_mem[expected_frame][119:88] + wire_index]);
                wire_index <= wire_index + 1;
                tx_wire_bytes <= tx_wire_bytes + 1;
                $fdisplay(gmii_dump_fd, "%0d,%0d,%0d,%02X", cycle_count, expected_frame, wire_index, gmii_txd);
            end

            if (!gmii_tx_en && gmii_tx_en_d) begin
                if (expected_frame < 0 || wire_index != meta_mem[expected_frame][87:72])
                    $fatal(1, "GMII frame length mismatch frame=%0d got=%0d expected=%0d",
                        expected_frame, wire_index,
                        expected_frame < 0 ? -1 : meta_mem[expected_frame][87:72]);
                tx_wire_frames <= tx_wire_frames + 1;
                expected_frame <= -1;
            end

            if (rx_valid && rx_ready) begin
                if (expected_rx_frame < 0)
                    $fatal(1, "Unexpected RX data without Golden frame");
                if (rx_byte_index >= meta_mem[expected_rx_frame][135:120])
                    $fatal(1, "RX frame too long frame=%0d byte=%0d", expected_rx_frame, rx_byte_index);
                if (rx_data !== client_mem[meta_mem[expected_rx_frame][167:136] + rx_byte_index])
                    $fatal(1, "RX byte mismatch frame=%0d byte=%0d got=%02x expected=%02x",
                        expected_rx_frame, rx_byte_index, rx_data,
                        client_mem[meta_mem[expected_rx_frame][167:136] + rx_byte_index]);
                if (rx_sop !== (rx_byte_index == 0))
                    $fatal(1, "RX SOP mismatch frame=%0d byte=%0d", expected_rx_frame, rx_byte_index);
                if (rx_eop !== (rx_byte_index + 1 == meta_mem[expected_rx_frame][135:120]))
                    $fatal(1, "RX EOP mismatch frame=%0d byte=%0d", expected_rx_frame, rx_byte_index);
                if (rx_length !== meta_mem[expected_rx_frame][135:120])
                    $fatal(1, "RX length mismatch frame=%0d got=%0d expected=%0d",
                        expected_rx_frame, rx_length, meta_mem[expected_rx_frame][135:120]);
                $fdisplay(rx_dump_fd, "%0d,%0d,%0d,%02X,%0d,%0d,%0d", cycle_count, expected_rx_frame,
                    rx_byte_index, rx_data, rx_sop, rx_eop, rx_length);
                if (rx_eop) begin
                    rx_frames_checked <= rx_frames_checked + 1;
                    rx_byte_index <= 0;
                    if (pressure_phase && rx_frames_checked == pressure_rx_before)
                        expected_rx_frame <= 1;
                    else expected_rx_frame <= -1;
                end else begin
                    rx_byte_index <= rx_byte_index + 1;
                end
            end
        end
    end

    task automatic wait_msg_ready;
        integer timeout;
        begin
            timeout = 0;
            while (!msg_ready && timeout < 10000) begin @(posedge clk); timeout = timeout + 1; end
            if (!msg_ready) $fatal(1, "Timeout waiting for descriptor ready");
        end
    endtask

    task automatic submit_descriptor(input integer frame_idx, input integer payload_len);
        begin
            @(negedge clk);
            expected_frame = frame_idx;
            expected_rx_frame = frame_idx;
            rx_byte_index = 0;
            msg_payload_length = payload_len[10:0];
            msg_valid = 1'b1;
            wait_msg_ready();
            @(posedge clk);
            @(negedge clk);
            msg_valid = 1'b0;
        end
    endtask

    task automatic send_golden_payload(input integer frame_idx, input integer payload_len);
        integer k;
        integer offset;
        integer timeout;
        begin
            offset = meta_mem[frame_idx][215:184];
            for (k = 0; k < payload_len; k = k + 1) begin
                @(negedge clk);
                payload_data = payload_mem[offset + k];
                payload_valid = 1'b1;
                payload_last = (k == payload_len - 1);
                timeout = 0;
                do begin
                    @(posedge clk);
                    timeout = timeout + 1;
                    if (timeout > 10000) $fatal(1, "Timeout waiting for payload_ready");
                end while (!payload_ready);
            end
            @(negedge clk);
            payload_valid = 1'b0;
            payload_last = 1'b0;
            payload_data = 0;
        end
    endtask

    task automatic wait_rx_frame(input integer desired_count);
        integer timeout;
        begin
            timeout = 0;
            while (rx_frames_checked < desired_count && timeout < 20000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (rx_frames_checked != desired_count)
                $fatal(1, "Timeout waiting RX frame desired=%0d got=%0d", desired_count, rx_frames_checked);
        end
    endtask

    task automatic wait_msg_done;
        integer timeout;
        begin
            timeout = 0;
            while (!msg_done && timeout < 200000) begin @(posedge clk); timeout = timeout + 1; end
            if (!msg_done) $fatal(1, "Timeout waiting msg_done");
        end
    endtask

    task automatic send_valid_frame(input integer frame_idx, input integer wait_for_rx);
        integer payload_len;
        integer expected_rx_count;
        integer progress_fd;
        begin
            payload_len = meta_mem[frame_idx][183:168];
            expected_rx_count = rx_frames_checked + 1;
            submit_descriptor(frame_idx, payload_len);
            send_golden_payload(frame_idx, payload_len);
            wait_msg_done();
            if (wait_for_rx != 0) wait_rx_frame(expected_rx_count);
            repeat (2) @(posedge clk);
            progress_fd=$fopen("frame_progress.csv","a");
            if(progress_fd==0)$fatal(1,"Cannot save full-suite progress");
            $fdisplay(progress_fd,"%0d,%0d,%0d,%0d,%0d",cycle_count,frame_idx,tx_wire_frames,rx_frames_checked,tx_sent);
            $fclose(progress_fd);
        end
    endtask

    task automatic wait_msg_error(input [3:0] expected_code);
        integer timeout;
        reg found;
        begin
            timeout = 0;
            found = 0;
            while (!found && timeout < 200000) begin
                @(posedge clk);
                if (msg_error) begin
                    found = 1;
                    if (error_code !== expected_code)
                        $fatal(1, "Error code mismatch got=%0d expected=%0d", error_code, expected_code);
                end
                timeout = timeout + 1;
            end
            if (!found) $fatal(1, "Timeout waiting msg_error code=%0d", expected_code);
        end
    endtask

    task automatic send_bad_descriptor(input integer length, input [3:0] expected_code);
        begin
            @(negedge clk);
            expected_frame = -1;
            expected_rx_frame = -1;
            msg_payload_length = length[10:0];
            msg_valid = 1;
            wait_msg_ready();
            @(posedge clk);
            @(negedge clk);
            msg_valid = 0;
            wait_msg_error(expected_code);
            repeat (3) @(posedge clk);
            if (gmii_tx_en) $fatal(1, "Invalid descriptor emitted GMII data");
        end
    endtask

    task automatic send_bad_config(input integer which, input [3:0] expected_code);
        begin
            @(negedge clk);
            expected_frame=-1;
            expected_rx_frame=-1;
            msg_payload_length=11'd33;
            msg_da_const=32'h03000000;
            msg_src_mac=48'h020000000009;
            msg_ttl=8'd1;
            msg_bag_cycles=32'd125000;
            case (which)
                0: msg_da_const=32'h02000000;
                1: msg_src_mac=48'h010000000009;
                2: msg_ttl=8'd0;
                3: msg_bag_cycles=32'd125001;
                default: $fatal(1,"Invalid bad-config selector");
            endcase
            msg_valid=1;
            wait_msg_ready();
            @(posedge clk);
            @(negedge clk); msg_valid=0;
            wait_msg_error(expected_code);
            repeat (3) @(posedge clk);
            if (gmii_tx_en) $fatal(1,"Invalid descriptor configuration emitted GMII data");
            @(negedge clk);
            msg_da_const=32'h03000000;
            msg_src_mac=48'h020000000009;
            msg_ttl=8'd1;
            msg_bag_cycles=32'd125000;
        end
    endtask

    task automatic send_short_payload_error;
        integer k;
        begin
            submit_descriptor(11, 10);
            for (k=0; k<3; k=k+1) begin
                @(negedge clk); payload_data=8'hA0+k; payload_valid=1; payload_last=(k==2);
                do @(posedge clk); while (!payload_ready);
            end
            @(negedge clk); payload_valid=0; payload_last=0;
            wait_msg_error(4'd6);
            if (gmii_tx_en) $fatal(1, "Early payload mismatch leaked a GMII frame");
        end
    endtask

    task automatic send_long_payload_error;
        integer k;
        integer timeout;
        begin
            submit_descriptor(11, 3);
            for (k=0; k<3; k=k+1) begin
                @(negedge clk); payload_data=8'hB0+k; payload_valid=1; payload_last=0;
                do @(posedge clk); while (!payload_ready);
            end
            @(negedge clk); payload_valid=0; payload_last=0;
            // The sender aborts the MAC frame and drains the overlong message
            // until its real end marker before it accepts another descriptor.
            for (k=0; k<2; k=k+1) begin
                @(negedge clk); payload_data=8'hC0+k; payload_valid=1; payload_last=(k==1);
                timeout=0;
                do begin @(posedge clk); timeout=timeout+1; if(timeout>30000)$fatal(1,"Drain timeout"); end while(!payload_ready);
            end
            @(negedge clk); payload_valid=0; payload_last=0;
            wait_msg_error(4'd7);
            if (gmii_tx_en) $fatal(1, "Late payload mismatch leaked a GMII frame");
        end
    endtask

    task automatic send_explicit_abort;
        integer k;
        begin
            submit_descriptor(11, 10);
            for (k=0; k<3; k=k+1) begin
                @(negedge clk); payload_data=8'hD0+k; payload_valid=1; payload_last=0;
                do @(posedge clk); while (!payload_ready);
            end
            @(negedge clk); payload_valid=0; payload_last=0; payload_abort=1;
            @(posedge clk);
            @(negedge clk); payload_abort=0;
            wait_msg_error(4'd8);
            if (gmii_tx_en) $fatal(1, "Explicit abort leaked a GMII frame");
        end
    endtask

    task automatic inject_golden_wire(input integer frame_idx);
        integer k, offset, length;
        begin
            offset=meta_mem[frame_idx][119:88];
            length=meta_mem[frame_idx][87:72];
            for(k=0;k<length;k=k+1) begin
                @(negedge clk); inject_rxd=wire_mem[offset+k]; inject_dv=1;
            end
            @(negedge clk); inject_dv=0;
            repeat(16) @(posedge clk);
        end
    endtask

    integer i;
    integer saved_tx_frames;
    integer saved_rx_frames;
    initial begin
        repeat (6) @(posedge clk);
        @(negedge clk); reset=0;

        // Length boundary set: P=1,16,17,18,1471,2,7,64,255,512,1024.
        // The first frame is held at the real RX client's ready=0 to verify
        // that a committed frame remains intact until the consumer resumes.
        rx_ready=0;
        send_valid_frame(0, 0);
        if (!rx_valid || rx_byte_index != 0)
            $fatal(1, "RX did not retain the first frame while paused");
        repeat (12) @(posedge clk);
        if (rx_frames_checked != 0 || !rx_valid)
            $fatal(1, "RX frame changed or disappeared during pause");
        @(negedge clk); rx_ready=1;
        wait_rx_frame(1);

        for (i=1; i<11; i=i+1) send_valid_frame(i, 1);

        // Rejected descriptors and malformed payload lengths must not consume
        // SN or leak partial frames onto GMII. MAC rejection cleans the bank
        // without a global reset; the next Golden frame is expected to use SN=12.
        send_bad_descriptor(0, 4'd1);
        send_bad_descriptor(1472, 4'd1);
        send_bad_config(0, 4'd2);
        send_bad_config(1, 4'd3);
        send_bad_config(2, 4'd4);
        send_bad_config(3, 4'd5);
        send_short_payload_error();
        send_long_payload_error();
        send_explicit_abort();
        if (tx_wire_frames != 11 || tx_sent != 11 || rx_good != 11 || rx_delivered != 11)
            $fatal(1, "Invalid/malformed traffic altered successful frame counts");
        if (tx_rejected != 3)
            $fatal(1, "Expected three MAC-aborted malformed frames, got %0d", tx_rejected);
        repeat (2) @(posedge clk);
        if (error_pulses != 9)
            $fatal(1, "Expected nine protocol error pulses, got %0d", error_pulses);

        send_valid_frame(11, 1);
        if (tx_wire_frames != 12 || tx_sent != 12 || rx_good != 12 || rx_delivered != 12)
            $fatal(1, "Recovery frame did not complete after malformed input");

        // Reset starts a fresh SN domain. All ordinary SN values and the
        // 255->1 wrap are checked byte-for-byte on real GMII and RX.
        @(negedge clk); reset=1; msg_valid=0; payload_valid=0; payload_last=0;
        rx_ready=1; expected_frame=-1; expected_rx_frame=-1;
        repeat (5) @(posedge clk);
        @(negedge clk); reset=0;
        for (i=12; i<12+SN_WRAP_FRAMES; i=i+1) send_valid_frame(i, 1);
        if (tx_wire_frames != 12+SN_WRAP_FRAMES || tx_sent != SN_WRAP_FRAMES || tx_rejected != 0)
            $fatal(1, "SN wrap test TX counts incorrect frames=%0d sent=%0d rejected=%0d", tx_wire_frames, tx_sent, tx_rejected);
        if (rx_good != SN_WRAP_FRAMES || rx_delivered != SN_WRAP_FRAMES || rx_drop != 0)
            $fatal(1, "SN wrap test RX counts incorrect good=%0d delivered=%0d dropped=%0d", rx_good, rx_delivered, rx_drop);
        if (tx_wire_bytes != 4122+72*SN_WRAP_FRAMES)
            $fatal(1, "Unexpected wire byte count in SN wrap group: %0d", tx_wire_bytes);
        if (late_count != 0)
            $fatal(1, "Unexpected BAG late count=%0d", late_count);
        if (rx_seen != SN_WRAP_FRAMES || rx_frames_checked != 12+SN_WRAP_FRAMES)
            $fatal(1, "Unexpected total RX counts seen=%0d checked=%0d", rx_seen, rx_frames_checked);
        if (rx_drop != 0 || rx_dropped || counter_saturated)
            $fatal(1, "Unexpected MAC RX drop/error/saturation");

        // With zero permitted jitter, deliberately let the real MAC's
        // commit/start pipeline exceed the configured start interval. The
        // protocol must count late starts and continue sending without bursts.
        @(negedge clk); msg_jitter_cycles=0;
        send_valid_frame(1, 1);
        send_valid_frame(2, 1);
        if (late_count == 0)
            $fatal(1, "Late-start counter did not record zero-jitter MAC start latency");
        if (tx_wire_frames != 14+SN_WRAP_FRAMES || tx_sent != 2+SN_WRAP_FRAMES || rx_good != 2+SN_WRAP_FRAMES || rx_delivered != 2+SN_WRAP_FRAMES)
            $fatal(1, "Post-wrap BAG-late sends did not complete correctly");
        if (done_pulses != 14+SN_WRAP_FRAMES)
            $fatal(1, "Expected 270 single-cycle msg_done pulses, got %0d", done_pulses);
        if (tx_wire_bytes != 4266+72*SN_WRAP_FRAMES || rx_frames_checked != 14+SN_WRAP_FRAMES)
            $fatal(1, "Post-wrap BAG-late wire/RX totals incorrect");

        // Real top-level GMII input exercises both synthesized RX FIFO banks.
        // Three correct Golden frames enter while the consumer is paused;
        // exactly two are retained and the third is explicitly dropped.
        @(negedge clk);
        pressure_phase=1; pressure_rx_before=rx_frames_checked;
        pressure_seen_before=rx_seen; pressure_good_before=rx_good;
        pressure_drop_before=rx_drop;
        expected_rx_frame=0; rx_byte_index=0; rx_ready=0; inject_rx=1;
        inject_golden_wire(0); inject_golden_wire(1); inject_golden_wire(2);
        repeat(4) @(posedge clk);
        if(rx_seen!=pressure_seen_before+3 || rx_good!=pressure_good_before+2 || rx_drop!=pressure_drop_before+1)
            $fatal(1,"RX pressure conservation failed seen=%0d good=%0d drop=%0d",rx_seen,rx_good,rx_drop);
        if(rx_banks_busy!==2'b11 || !rx_drop_reason[4])
            $fatal(1,"RX pressure did not retain both banks/report no-space");
        @(negedge clk); rx_ready=1;
        wait_rx_frame(pressure_rx_before+2);
        @(negedge clk); inject_rx=0; pressure_phase=0; msg_jitter_cycles=32'd12500;
        send_valid_frame(3,1);
        if(tx_wire_frames!=SN_WRAP_FRAMES+15 || done_pulses!=SN_WRAP_FRAMES+15 || tx_sent!=SN_WRAP_FRAMES+3)
            $fatal(1,"TX recovery after RX pressure failed");
        if(rx_frames_checked!=SN_WRAP_FRAMES+17 || rx_good!=SN_WRAP_FRAMES+5 || rx_delivered!=SN_WRAP_FRAMES+5 || rx_seen!=SN_WRAP_FRAMES+6 || rx_drop!=1)
            $fatal(1,"RX pressure/recovery final counters failed");
        if(tx_wire_bytes!=4339+72*SN_WRAP_FRAMES || late_count!=2)
            $fatal(1,"Final wire count/BAG late count failed");
        $display("B1_NETLIST_FIFO_PRESSURE = PASS retained=2 dropped=1 recovery=1 (overflow is not lossless)");
        $fclose(gmii_dump_fd);
        $fclose(rx_dump_fd);
`ifdef DUT_IS_NETLIST
        $display("B1_POST_SYNTH_NETLIST_FULL = PASS boundaries=11 rejected_descriptors=6 malformed_payloads=3 sn_wrap_frames=%0d fifo_pressure=1 wire_bytes=%0d rx_checked=%0d late_count=%0d",
            SN_WRAP_FRAMES, tx_wire_bytes, rx_frames_checked, late_count);
`else
        $display("B1_FULL_TB_QUICK_RTL = PASS sn_frames=%0d fifo_pressure=1 wire_bytes=%0d rx_checked=%0d",
            SN_WRAP_FRAMES, tx_wire_bytes, rx_frames_checked);
`endif
        $display("B1_COUNTS tx_sent=%0d tx_rejected=%0d rx_seen=%0d rx_good=%0d rx_drop=%0d rx_delivered=%0d",
            tx_sent, tx_rejected, rx_seen, rx_good, rx_drop, rx_delivered);
        $finish;
    end

    initial begin
        #1000000000;
        $fatal(1, "Global simulation timeout");
    end
endmodule
