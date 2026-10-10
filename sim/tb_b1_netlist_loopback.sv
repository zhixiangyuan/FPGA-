`timescale 1ns/1ps

// Functional test for the eLinx-exported afdx_network_tx_top .vo.
// This test compiles no B1 or B0 RTL; only the actual netlist and eLinx models.
module tb_b1_netlist_loopback;
    localparam integer FRAME_COUNT = 268;
    localparam integer MAX_BYTES = 65536;
    reg clk=0;
    always #4 clk=~clk;
    reg reset=1;
    reg msg_valid=0;
    wire msg_ready;
    reg [10:0] msg_payload_length=0;
    reg [31:0] msg_da_const=32'h03000000;
    reg [15:0] msg_vlid=16'h1234;
    reg [47:0] msg_src_mac=48'h020000000009;
    reg [31:0] msg_src_ip=32'h0a000001;
    reg [31:0] msg_dst_ip=32'he0e0003c;
    reg [15:0] msg_src_port=24, msg_dst_port=23;
    reg [7:0] msg_ttl=1;
    reg [31:0] msg_bag_cycles=125000;
    reg [31:0] msg_jitter_cycles=12500;
    reg [7:0] payload_data=0;
    reg payload_valid=0;
    wire payload_ready;
    reg payload_last=0, payload_abort=0;
    wire [7:0] gmii_txd;
    wire gmii_tx_en, gmii_tx_er;
    reg [7:0] gmii_rxd=0;
    reg gmii_rx_dv=0, gmii_rx_er=0;
    wire msg_done, msg_error;
    wire [3:0] error_code;
    wire [31:0] late_count;
    wire [7:0] rx_data;
    wire rx_valid, rx_sop, rx_eop;
    wire [15:0] rx_length;
    reg rx_ready=1;
    wire rx_accepted, rx_dropped;
    wire [4:0] rx_drop_reason;
    wire [1:0] rx_banks_busy;
    wire counter_saturated;
    wire [31:0] tx_sent, tx_rejected, rx_seen, rx_good, rx_drop, rx_delivered;

    reg [7:0] payload_mem[0:MAX_BYTES-1];
    reg [7:0] client_mem[0:MAX_BYTES-1];
    reg [7:0] wire_mem[0:MAX_BYTES-1];
    reg [215:0] meta_mem[0:FRAME_COUNT-1];
    integer cycle_count=0;
    integer expected_frame=-1, expected_rx_frame=-1;
    integer tx_frames=0, tx_bytes=0, wire_index=0;
    integer rx_frames=0, rx_index=0;
    integer errors_seen=0;
    integer have_start=0, last_start_cycle=0;
    reg gmii_tx_en_d=0;
    integer gmii_dump_fd;
    integer rx_dump_fd;

    // The synthesized DUT is the actual eLinx .vo module. No RTL shadow is present.
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
        $readmemh("golden/golden_payload.mem",payload_mem);
        $readmemh("golden/golden_client.mem",client_mem);
        $readmemh("golden/golden_wire.mem",wire_mem);
        $readmemh("golden/golden_meta.mem",meta_mem);
        gmii_dump_fd=$fopen("actual_tx_gmii.csv","w");
        rx_dump_fd=$fopen("actual_rx_client.csv","w");
        if(gmii_dump_fd==0||rx_dump_fd==0)$fatal(1,"Cannot open synthesized-netlist byte dumps");
        $fdisplay(gmii_dump_fd,"cycle,frame_index,wire_byte_index,gmii_txd");
        $fdisplay(rx_dump_fd,"cycle,frame_index,client_byte_index,rx_data,rx_sop,rx_eop,rx_length");
    end

    always @(posedge clk) begin
        cycle_count<=cycle_count+1;
        if (reset) begin
            gmii_rxd<=0; gmii_rx_dv<=0; gmii_rx_er<=0; gmii_tx_en_d<=0;
            have_start<=0; last_start_cycle<=0;
        end else begin
            gmii_rxd<=gmii_txd; gmii_rx_dv<=gmii_tx_en; gmii_rx_er<=gmii_tx_er;
            gmii_tx_en_d<=gmii_tx_en;
            if (msg_error) errors_seen<=errors_seen+1;
            if (gmii_tx_en&&!gmii_tx_en_d) begin
                if (expected_frame<0) $fatal(1,"Unexpected synthesized GMII frame");
                if (have_start&&(cycle_count-last_start_cycle)<125000)
                    $fatal(1,"Synthesized BAG start interval violation");
                if (gmii_txd!==wire_mem[meta_mem[expected_frame][119:88]])
                    $fatal(1,"Synthesized GMII preamble byte mismatch frame=%0d",expected_frame);
                $fdisplay(gmii_dump_fd,"%0d,%0d,0,%02X",cycle_count,expected_frame,gmii_txd);
                last_start_cycle<=cycle_count; have_start<=1; wire_index<=1; tx_bytes<=tx_bytes+1;
            end else if (gmii_tx_en) begin
                if (expected_frame<0 || wire_index>=meta_mem[expected_frame][87:72])
                    $fatal(1,"Synthesized GMII frame too long");
                if (gmii_txd!==wire_mem[meta_mem[expected_frame][119:88]+wire_index])
                    $fatal(1,"Synthesized GMII mismatch frame=%0d byte=%0d",expected_frame,wire_index);
                $fdisplay(gmii_dump_fd,"%0d,%0d,%0d,%02X",cycle_count,expected_frame,wire_index,gmii_txd);
                wire_index<=wire_index+1; tx_bytes<=tx_bytes+1;
            end
            if (!gmii_tx_en&&gmii_tx_en_d) begin
                if (expected_frame<0 || wire_index!=meta_mem[expected_frame][87:72])
                    $fatal(1,"Synthesized wire length mismatch frame=%0d",expected_frame);
                tx_frames<=tx_frames+1; expected_frame<=-1;
            end
            if (rx_valid&&rx_ready) begin
                if (expected_rx_frame<0 || rx_index>=meta_mem[expected_rx_frame][135:120])
                    $fatal(1,"Unexpected synthesized RX byte");
                if (rx_data!==client_mem[meta_mem[expected_rx_frame][167:136]+rx_index])
                    $fatal(1,"Synthesized RX data mismatch frame=%0d byte=%0d",expected_rx_frame,rx_index);
                if (rx_sop!==(rx_index==0) || rx_eop!==(rx_index+1==meta_mem[expected_rx_frame][135:120]))
                    $fatal(1,"Synthesized RX boundary mismatch frame=%0d byte=%0d",expected_rx_frame,rx_index);
                if (rx_length!==meta_mem[expected_rx_frame][135:120])
                    $fatal(1,"Synthesized RX length mismatch");
                $fdisplay(rx_dump_fd,"%0d,%0d,%0d,%02X,%0d,%0d,%0d",cycle_count,expected_rx_frame,rx_index,rx_data,rx_sop,rx_eop,rx_length);
                if (rx_eop) begin rx_frames<=rx_frames+1; rx_index<=0; expected_rx_frame<=-1; end
                else rx_index<=rx_index+1;
            end
        end
    end

    task automatic submit(input integer idx,input integer length);
        integer timeout;
        begin
            @(negedge clk); expected_frame=idx; expected_rx_frame=idx; rx_index=0;
            msg_payload_length=length[10:0]; msg_valid=1;
            timeout=0;
            while(!msg_ready&&timeout<20000)begin @(posedge clk);timeout=timeout+1;end
            if(!msg_ready)$fatal(1,"Synthesized descriptor ready timeout");
            @(posedge clk); @(negedge clk); msg_valid=0;
        end
    endtask

    task automatic payload_from_golden(input integer idx,input integer length);
        integer k,offset,timeout;
        begin
            offset=meta_mem[idx][215:184];
            for(k=0;k<length;k=k+1)begin
                @(negedge clk);payload_data=payload_mem[offset+k];payload_valid=1;payload_last=(k==length-1);
                timeout=0;
                do begin @(posedge clk);timeout=timeout+1;if(timeout>30000)$fatal(1,"Synthesized payload-ready timeout");end while(!payload_ready);
            end
            @(negedge clk);payload_valid=0;payload_last=0;payload_data=0;
        end
    endtask

    task automatic wait_done;
        integer timeout;
        begin timeout=0;while(!msg_done&&timeout<200000)begin @(posedge clk);timeout=timeout+1;end
            if(!msg_done)$fatal(1,"Synthesized message completion timeout");end
    endtask

    task automatic wait_rx(input integer desired);
        integer timeout;
        begin timeout=0;while(rx_frames<desired&&timeout<40000)begin @(posedge clk);timeout=timeout+1;end
            if(rx_frames!=desired)$fatal(1,"Synthesized RX timeout desired=%0d got=%0d",desired,rx_frames);end
    endtask

    task automatic send_frame(input integer idx,input integer wait_for_rx);
        integer len, desired;
        begin len=meta_mem[idx][183:168];desired=rx_frames+1;submit(idx,len);payload_from_golden(idx,len);wait_done();if(wait_for_rx!=0)wait_rx(desired);repeat(2)@(posedge clk);end
    endtask

    task automatic wait_error(input [3:0] code);
        integer timeout;reg found;
        begin timeout=0;found=0;while(!found&&timeout<40000)begin @(posedge clk);if(msg_error)begin found=1;if(error_code!==code)$fatal(1,"Synthesized error code mismatch");end timeout=timeout+1;end
            if(!found)$fatal(1,"Synthesized error timeout code=%0d",code);end
    endtask

    integer i;
    initial begin
        repeat(6)@(posedge clk);@(negedge clk);reset=0;
        // Five lengths include the 1/16/17/18-byte padding boundary and maximum 1471-byte payload.
        rx_ready=0;send_frame(0,0);
        i=0;while(!rx_valid&&i<30000)begin @(posedge clk);i=i+1;end
        if(!rx_valid)$fatal(1,"Synthesized RX pause did not present a buffered frame");
        repeat(10)@(posedge clk);
        if(!rx_valid||rx_frames!=0)$fatal(1,"Synthesized RX did not hold while paused");
        @(negedge clk);rx_ready=1;wait_rx(1);
        for(i=1;i<5;i=i+1)send_frame(i,1);

        // Malformed payload must abort at the real MAC and a valid next frame must still pass.
        submit(5,10);
        for(i=0;i<3;i=i+1)begin @(negedge clk);payload_data=8'hb0+i;payload_valid=1;payload_last=(i==2);do @(posedge clk);while(!payload_ready);end
        @(negedge clk);payload_valid=0;payload_last=0;wait_error(4'd6);
        if(gmii_tx_en)$fatal(1,"Synthesized malformed frame leaked to GMII");
        send_frame(5,1);

        // Reset the actual netlist, then prove it can transmit and receive again.
        @(negedge clk);reset=1;msg_valid=0;payload_valid=0;rx_ready=1;
        repeat(5)@(posedge clk);@(negedge clk);reset=0;
        send_frame(0,1);
        if(tx_frames!=7||rx_frames!=7||tx_sent!=1||rx_good!=1||rx_drop!=0||tx_rejected!=0)
            $fatal(1,"Synthesized final counters incorrect tx_frames=%0d rx_frames=%0d",tx_frames,rx_frames);
        if(errors_seen!=1||late_count!=0||counter_saturated)
            $fatal(1,"Synthesized final diagnostics incorrect errors=%0d late=%0d",errors_seen,late_count);
        $fclose(gmii_dump_fd);$fclose(rx_dump_fd);
`ifdef DUT_IS_NETLIST
        $display("B1_POST_SYNTH_NETLIST_FUNCTIONAL = PASS lengths=1,16,17,18,1471 abort_recovery=1 reset_recovery=1 wire_bytes=%0d rx_frames=%0d",
            tx_bytes,rx_frames);
`else
        $display("B1_125M_RTL_GMII_FUNCTIONAL = PASS lengths=1,16,17,18,1471 abort_recovery=1 reset_recovery=1 wire_bytes=%0d rx_frames=%0d",
            tx_bytes,rx_frames);
`endif
        $finish;
    end

    initial begin #1000000000;$fatal(1,"Simulation timeout");end
endmodule
