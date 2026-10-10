`timescale 1ns/1ps
module tb_b0_tx_abort_contract;
    reg clk = 1'b0;
    always #4 clk = ~clk;

    reg reset = 1'b1;
    reg [7:0] tx_data = 8'h00;
    reg tx_valid = 1'b0;
    reg tx_sop = 1'b0;
    reg tx_eop = 1'b0;
    reg [15:0] tx_length = 16'd60;
    reg tx_afdx = 1'b1;
    wire tx_ready;
    wire [7:0] gmii_txd;
    wire gmii_tx_en;
    wire gmii_tx_er;
    wire [7:0] rx_data;
    wire rx_valid;
    wire rx_sop;
    wire rx_eop;
    wire [15:0] rx_length;
    wire tx_done;
    wire tx_reject;
    wire rx_accepted;
    wire rx_dropped;
    wire [4:0] rx_drop_reason;
    wire [31:0] tx_sent;
    wire [31:0] tx_rejected;
    wire [31:0] rx_seen;
    wire [31:0] rx_good;
    wire [31:0] rx_drop;
    wire [31:0] rx_delivered;
    wire [1:0] rx_banks_busy;
    wire counter_saturated;

    mac_gmii_core dut (
        .clk(clk), .reset(reset),
        .tx_data(tx_data), .tx_valid(tx_valid), .tx_sop(tx_sop), .tx_eop(tx_eop),
        .tx_length(tx_length), .tx_afdx(tx_afdx), .tx_ready(tx_ready),
        .gmii_txd(gmii_txd), .gmii_tx_en(gmii_tx_en), .gmii_tx_er(gmii_tx_er),
        .gmii_rxd(8'h00), .gmii_rx_dv(1'b0), .gmii_rx_er(1'b0),
        .rx_data(rx_data), .rx_valid(rx_valid), .rx_sop(rx_sop), .rx_eop(rx_eop),
        .rx_ready(1'b1), .rx_length(rx_length), .tx_done(tx_done), .tx_reject(tx_reject),
        .rx_accepted(rx_accepted), .rx_dropped(rx_dropped), .rx_drop_reason(rx_drop_reason),
        .tx_sent(tx_sent), .tx_rejected(tx_rejected), .rx_seen(rx_seen), .rx_good(rx_good),
        .rx_drop(rx_drop), .rx_delivered(rx_delivered), .rx_banks_busy(rx_banks_busy),
        .counter_saturated(counter_saturated)
    );

    integer line_bytes = 0;
    integer reject_events = 0;
    integer done_events = 0;
    integer abort_line_bytes = 0;
    integer legal_line_bytes = 0;
    integer mode = 0;
    integer i;
    integer timeout;
    reg previous_done = 1'b0;

    always @(posedge clk) begin
        if (reset) begin
            previous_done <= 1'b0;
        end else begin
            if (gmii_tx_en) begin
                line_bytes <= line_bytes + 1;
                if (mode == 1) abort_line_bytes <= abort_line_bytes + 1;
                if (mode == 2) legal_line_bytes <= legal_line_bytes + 1;
            end
            if (tx_reject) reject_events <= reject_events + 1;
            if (tx_done) begin
                done_events <= done_events + 1;
                if (previous_done) $fatal(1, "tx_done exceeded one clock");
            end
            previous_done <= tx_done;
        end
    end

    task send_beat;
        input [7:0] value;
        input sop;
        input eop;
        integer accepted;
        begin
            @(negedge clk);
            tx_data = value;
            tx_sop = sop;
            tx_eop = eop;
            tx_length = 16'd60;
            tx_afdx = 1'b1;
            tx_valid = 1'b1;
            accepted = 0;
            while (!accepted) begin
                @(posedge clk);
                if (tx_ready) accepted = 1;
            end
            @(negedge clk);
            tx_valid = 1'b0;
            tx_sop = 1'b0;
            tx_eop = 1'b0;
        end
    endtask

    task wait_for_reject_count;
        input integer expected;
        begin
            timeout = 0;
            while (reject_events < expected && timeout < 20) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (reject_events != expected)
                $fatal(1, "reject count mismatch expected=%0d actual=%0d", expected, reject_events);
        end
    endtask

    task wait_for_tx_ready;
        begin
            timeout = 0;
            while (!tx_ready && timeout < 20) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            if (!tx_ready) $fatal(1, "TX did not return ready without reset");
        end
    endtask

    initial begin
        repeat (5) @(posedge clk);
        @(negedge clk); reset = 1'b0;
        wait_for_tx_ready();

        // Abort a partially filled 60-byte frame. The repeated SOP + EOP
        // is the production mac_gmii_tx malformed-frame abort contract.
        mode = 1;
        for (i = 0; i < 8; i = i + 1) send_beat(8'h10 + i, i == 0, 1'b0);
        send_beat(8'hE7, 1'b1, 1'b1);
        wait_for_reject_count(1);
        repeat (4) @(posedge clk);
        if (abort_line_bytes != 0 || done_events != 0)
            $fatal(1, "aborted partial frame leaked to GMII or completed");
        wait_for_tx_ready();

        // Abort with exactly one declared byte remaining. The repeated SOP
        // must still win over the otherwise length-correct EOP condition.
        for (i = 0; i < 59; i = i + 1) send_beat(8'h40 + i, i == 0, 1'b0);
        send_beat(8'hE8, 1'b1, 1'b1);
        wait_for_reject_count(2);
        repeat (4) @(posedge clk);
        if (abort_line_bytes != 0 || done_events != 0)
            $fatal(1, "one-byte-left abort leaked to GMII or completed");
        wait_for_tx_ready();

        // No reset between aborts and recovery: a fresh legal frame must send.
        mode = 2;
        send_beat(8'hDA, 1'b1, 1'b0);
        for (i = 1; i < 60; i = i + 1) send_beat(i[7:0], 1'b0, i == 59);
        timeout = 0;
        while (done_events < 1 && timeout < 200) begin
            @(posedge clk);
            timeout = timeout + 1;
        end
        repeat (4) @(posedge clk);
        if (done_events != 1) $fatal(1, "legal recovery frame did not complete");
        if (legal_line_bytes != 72) $fatal(1, "recovery GMII byte count=%0d expected=72", legal_line_bytes);
        if (tx_sent != 1 || tx_rejected != 2) $fatal(1, "MAC counters sent=%0d rejected=%0d", tx_sent, tx_rejected);
        if (reset !== 1'b0) $fatal(1, "unexpected reset used during recovery");

        $display("B0_MAC_ABORT_CONTRACT = PASS aborts=%0d tx_frames=%0d tx_rejects=%0d gmii_bytes=%0d resets_after_start=0",
                 reject_events, done_events, tx_rejected, line_bytes);
        $finish;
    end
endmodule
