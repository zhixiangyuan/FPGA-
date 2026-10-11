`timescale 1ns/1ps
module tb_b2_protocol_loop;
    localparam integer MAX_BYTES=16384;
    reg clk=0; always #4 clk=~clk;
    reg reset=1,msg_valid=0,payload_valid=0,payload_last=0,payload_abort=0;
    reg [10:0] msg_payload_length=0;
    reg [7:0] payload_data=0;
    wire msg_ready,payload_ready,msg_done,msg_error;
    wire [3:0] error_code;
    wire [31:0] late_count;
    wire [7:0] gmii_txd;
    wire gmii_tx_en,gmii_tx_er;
    reg [7:0] gmii_rxd=0;
    reg gmii_rx_dv=0,gmii_rx_er=0,inject=0;
    wire [7:0] app_data,app_sn_unchecked;
    wire app_valid,app_sop,app_eop;
    reg app_ready=1;
    wire [10:0] app_length;
    wire [15:0] app_vlid;
    wire candidate_accepted,candidate_rejected;
    wire [3:0] candidate_reject_reason;
    wire [31:0] candidate_accepted_count,candidate_rejected_count;
    wire [1:0] candidate_banks_busy;
    wire mac_rx_accepted,mac_rx_dropped;
    wire [4:0] mac_rx_drop_reason;
    wire [31:0] tx_sent,rx_seen,rx_good,rx_drop,rx_delivered;
    reg [7:0] wire_mem[0:MAX_BYTES-1],payload_mem[0:MAX_BYTES-1];
    reg [255:0] meta_mem[0:16];
    integer cycle=0, expected_tx=-1,tx_index=0,tx_frames=0,tx_bytes=0;
    integer expected_app=-1,app_index=0,app_frames=0,app_bytes=0;
    reg pressure_phase=0;
    integer last_start=0,have_start=0;
    reg tx_en_d=0;
    integer tx_fd,app_fd;

    afdx_protocol_candidate_top dut(
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
        .late_count(late_count),
        .app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
        .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),
        .app_vlid(app_vlid),.app_sn_unchecked(app_sn_unchecked),
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
    initial begin
        $readmemh("golden/wire.mem",wire_mem);
        $readmemh("golden/payload.mem",payload_mem);
        $readmemh("golden/meta.mem",meta_mem);
        tx_fd=$fopen("actual_tx_gmii.csv","w");
        app_fd=$fopen("actual_payload.csv","w");
        if(tx_fd==0||app_fd==0)$fatal(1,"cannot open CSV");
        $fdisplay(tx_fd,"cycle,case_id,byte_index,data");
        $fdisplay(app_fd,"cycle,case_id,byte_index,data,sop,eop,length,sn");
    end
    always @(posedge clk) begin
        cycle=cycle+1;
        if(reset)begin
            gmii_rxd<=0;gmii_rx_dv<=0;gmii_rx_er<=0;
            tx_en_d<=0;have_start=0;
        end else begin
            if(!inject)begin gmii_rxd<=gmii_txd;gmii_rx_dv<=gmii_tx_en;gmii_rx_er<=gmii_tx_er;end
            tx_en_d<=gmii_tx_en;
            if(gmii_tx_en && !tx_en_d)begin
                if(expected_tx<0)$fatal(1,"unexpected TX frame");
                if(have_start && cycle-last_start<125000)
                    $fatal(1,"real BAG violated gap=%0d",cycle-last_start);
                have_start=1;last_start=cycle;tx_index=0;tx_frames=tx_frames+1;
            end
            if(gmii_tx_en)begin
                if(expected_tx<0 || tx_index>=meta_mem[expected_tx][159:128] ||
                   gmii_txd!==wire_mem[meta_mem[expected_tx][191:160]+tx_index])
                    $fatal(1,"wire mismatch case=%0d byte=%0d",expected_tx,tx_index);
                $fdisplay(tx_fd,"%0d,%0d,%0d,%02X",cycle,expected_tx,tx_index,gmii_txd);
                tx_index=tx_index+1;tx_bytes=tx_bytes+1;
            end
            if(!gmii_tx_en && tx_en_d)begin
                if(tx_index!=meta_mem[expected_tx][159:128])
                    $fatal(1,"wire frame length mismatch case=%0d",expected_tx);
                expected_tx=-1;
            end
            if(msg_error)$fatal(1,"B1 sender reported error code=%0d",error_code);
            if(app_valid && app_ready)begin
                if(expected_app<0 ||
                   app_data!==payload_mem[meta_mem[expected_app][127:96]+app_index] ||
                   app_length!==meta_mem[expected_app][95:64] ||
                   app_sn_unchecked!==meta_mem[expected_app][63:32] ||
                   app_vlid!==16'h1234 ||
                   app_sop!==(app_index==0) ||
                   app_eop!==(app_index+1==meta_mem[expected_app][95:64]))
                    $fatal(1,"application mismatch case=%0d byte=%0d",expected_app,app_index);
                $fdisplay(app_fd,"%0d,%0d,%0d,%02X,%0d,%0d,%0d,%0d",cycle,expected_app,
                          app_index,app_data,app_sop,app_eop,app_length,app_sn_unchecked);
                app_index=app_index+1;app_bytes=app_bytes+1;
                if(app_eop)begin
                    app_frames=app_frames+1;app_index=0;
                    if(pressure_phase && expected_app>=0 && expected_app<3)
                        expected_app=expected_app+1;
                    else expected_app=-1;
                end
            end
        end
    end
    task automatic send_b1(input integer c);
        integer j,t,len,base,before_app;
        begin
            len=meta_mem[c][95:64];base=meta_mem[c][127:96];
            before_app=app_frames;
            @(negedge clk);expected_tx=c;expected_app=c;
            msg_payload_length=len;msg_valid=1;
            t=0;
            while(!msg_ready && t<10000)begin @(posedge clk);t=t+1;end
            if(!msg_ready)$fatal(1,"descriptor ready timeout");
            @(posedge clk);@(negedge clk);msg_valid=0;
            for(j=0;j<len;j=j+1)begin
                @(negedge clk);payload_valid=1;payload_data=payload_mem[base+j];
                payload_last=(j==len-1);t=0;
                do begin @(posedge clk);t=t+1;if(t>10000)$fatal(1,"payload ready timeout");end while(!payload_ready);
            end
            @(negedge clk);payload_valid=0;payload_last=0;
            t=0;while(!msg_done && t<150000)begin @(posedge clk);t=t+1;end
            if(!msg_done)$fatal(1,"B1 done timeout");
            t=0;while(app_frames==before_app && t<30000)begin @(posedge clk);t=t+1;end
            if(app_frames!=before_app+1)$fatal(1,"B2 app delivery timeout case=%0d",c);
            repeat(3)@(posedge clk);
        end
    endtask
    task automatic inject_valid_case(input integer c);
        integer j,len,base;
        begin
            len=meta_mem[c][159:128];base=meta_mem[c][191:160];
            @(negedge clk);inject=1;gmii_rx_dv=0;gmii_rxd=0;
            repeat(16)@(negedge clk);
            for(j=0;j<len;j=j+1)begin
                gmii_rxd=wire_mem[base+j];gmii_rx_dv=1;gmii_rx_er=0;
                @(negedge clk);
            end
            gmii_rx_dv=0;gmii_rxd=0;
            repeat(8)@(posedge clk);
        end
    endtask
    task automatic inject_case(input integer c);
        integer j,t,len,base,before_reject,before_drop;
        begin
            len=meta_mem[c][159:128];base=meta_mem[c][191:160];
            before_reject=candidate_rejected_count;before_drop=rx_drop;
            @(negedge clk);inject=1;gmii_rx_dv=0;gmii_rxd=0;
            repeat(16)@(negedge clk);
            for(j=0;j<len;j=j+1)begin
                gmii_rxd=wire_mem[base+j];gmii_rx_dv=1;gmii_rx_er=0;
                @(negedge clk);
            end
            gmii_rx_dv=0;gmii_rxd=0;
            t=0;
            if(c==15)begin
                while(rx_drop==before_drop && t<30000)begin @(posedge clk);t=t+1;end
                if(rx_drop!=before_drop+1 || candidate_rejected_count!=before_reject)
                    $fatal(1,"bad FCS was not isolated at MAC");
            end else begin
                while(candidate_rejected_count==before_reject && t<30000)begin @(posedge clk);t=t+1;end
                if(candidate_rejected_count!=before_reject+1 ||
                   candidate_reject_reason!==meta_mem[c][31:0] ||
                   rx_drop!=before_drop)
                    $fatal(1,"protocol reject mismatch case=%0d reason=%0d",c,candidate_reject_reason);
            end
            repeat(5)@(posedge clk);
        end
    endtask
    integer k,t;
    initial begin
        repeat(5)@(posedge clk);@(negedge clk);reset=0;
        for(k=0;k<6;k=k+1)begin
            if(k==4)app_ready=0;
            // A paused application is released after the complete candidate
            // is buffered; this is checked by the separate pressure suite.
            if(k==4)app_ready=1;
            send_b1(k);
        end
        for(k=6;k<=15;k=k+1)inject_case(k);
        @(negedge clk);inject=0;
        repeat(5)@(posedge clk);
        send_b1(16);
        @(negedge clk);
        if(tx_frames!=7 || tx_sent!=7 || app_frames!=7 ||
           candidate_accepted_count!=7 || candidate_rejected_count!=9 ||
           rx_seen!=17 || rx_good!=16 || rx_drop!=1 || rx_delivered!=16 ||
           late_count!=0 || candidate_banks_busy!=0)
            $fatal(1,"end-to-end counts tx=%0d app=%0d cand=%0d reject=%0d seen=%0d good=%0d drop=%0d delivered=%0d late=%0d",
                tx_frames,app_frames,candidate_accepted_count,candidate_rejected_count,
                rx_seen,rx_good,rx_drop,rx_delivered,late_count);
        // Reset the observation epoch. Pause the application while two B2
        // payload banks and both B0 MAC RX banks fill; the fifth wire frame
        // must be reported as a MAC no-space drop, then service resumes.
        @(negedge clk);reset=1;inject=0;app_ready=0;
        repeat(5)@(posedge clk);
        @(negedge clk);reset=0;pressure_phase=1;expected_app=0;
        inject_valid_case(0);inject_valid_case(1);
        t=0;while(candidate_accepted_count<2 && t<2000)begin @(posedge clk);t=t+1;end
        @(negedge clk);
        if(candidate_accepted_count!=2 || candidate_banks_busy!==2'b11)
            $fatal(1,"B2 two candidate banks not occupied");
        inject_valid_case(2);inject_valid_case(3);inject_valid_case(4);
        if(rx_seen!=5 || rx_good!=4 || rx_drop!=1 || candidate_accepted_count!=2 || app_frames!=7)
            $fatal(1,"pressure conservation before release seen=%0d good=%0d drop=%0d candidates=%0d",
                rx_seen,rx_good,rx_drop,candidate_accepted_count);
        @(negedge clk);app_ready=1;
        t=0;while(app_frames<11 && t<50000)begin @(posedge clk);t=t+1;end
        @(negedge clk);
        if(app_frames!=11 || candidate_accepted_count!=4 || candidate_banks_busy!=0 ||
           rx_delivered!=4)
            $fatal(1,"pressure drain/recovery failed app=%0d candidates=%0d mac_delivered=%0d",
                app_frames,candidate_accepted_count,rx_delivered);
        @(negedge clk);expected_app=16;
        inject_valid_case(16);
        t=0;while(app_frames<12 && t<30000)begin @(posedge clk);t=t+1;end
        if(app_frames!=12 || candidate_accepted_count!=5 || candidate_rejected_count!=0 ||
           rx_seen!=6 || rx_good!=5 || rx_drop!=1 || rx_delivered!=5)
            $fatal(1,"post-pressure recovery counts failed");
        $fclose(tx_fd);$fclose(app_fd);
        $display("B2_PROTOCOL_CANDIDATE_LOOP = PASS tx=7 app=7 protocol_reject=9 mac_fcs_drop=1 bag_cycles=125000 sn_policy=BLOCKED_SN_RULE");
        $display("B2_PROTOCOL_FIFO_PRESSURE = PASS b2_retained=2 mac_retained=2 mac_dropped=1 recovered=1 reset_epoch=1");
        $finish;
    end
    initial begin #30000000;$fatal(1,"global timeout");end
endmodule
