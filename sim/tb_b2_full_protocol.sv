`timescale 1ns/1ps
module tb_b2_full_protocol;
    localparam integer MAX_BYTES=65536;
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
    wire [7:0] app_data,app_sn;
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
    `include "golden/constants.vh"
    reg [255:0] meta_mem[0:CASE_COUNT-1];
    reg [127:0] expect_mem[0:CASE_COUNT-1];
    integer cycle=0, expected_tx=-1,tx_index=0,tx_frames=0,tx_bytes=0;
    integer expected_app=-1,app_index=0,app_frames=0,app_bytes=0;
    reg pressure_phase=0;
    integer pressure_slot=0;
    wire psn_valid,sn_accepted,sn_rejected,sn_reset_control,app_delivered;
    wire [7:0] psn;
    wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count,sn_missing_count,app_delivered_count;
    integer decision_fd;
    integer last_start=0,have_start=0;
    reg tx_en_d=0;
    reg stalled_d=0;
    reg [44:0] held_app=0;
    integer tx_fd,app_fd;

    afdx_protocol_rx_top dut(
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
        .app_vlid(app_vlid),.app_sn(app_sn),
        .psn_valid(psn_valid),.psn(psn),.sn_accepted(sn_accepted),.sn_rejected(sn_rejected),
        .sn_reset_control(sn_reset_control),.app_delivered(app_delivered),
        .sn_accepted_count(sn_accepted_count),.sn_rejected_count(sn_rejected_count),
        .sn_control_count(sn_control_count),.sn_missing_count(sn_missing_count),
        .app_delivered_count(app_delivered_count),
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
        $readmemh("golden/expect.mem",expect_mem);
        decision_fd=$fopen("sn_decisions.csv","w");
        $fdisplay(decision_fd,"cycle,case_id,action,psn,psn_valid,accepted,rejected,control,missing,delivered");
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
            stalled_d<=0;
        end else begin
            if(stalled_d && (!app_valid ||
                {app_data,app_sop,app_eop,app_length,app_vlid,app_sn}!==held_app))
                $fatal(1,"SN-approved application beat changed during backpressure");
            stalled_d<=app_valid&&!app_ready;
            if(app_valid&&!app_ready)held_app<={app_data,app_sop,app_eop,app_length,app_vlid,app_sn};
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
                   app_sn!==meta_mem[expected_app][63:32] ||
                   app_vlid!==16'h1234 ||
                   app_sop!==(app_index==0) ||
                   app_eop!==(app_index+1==meta_mem[expected_app][95:64]))
                    $fatal(1,"application mismatch case=%0d byte=%0d",expected_app,app_index);
                $fdisplay(app_fd,"%0d,%0d,%0d,%02X,%0d,%0d,%0d,%0d",cycle,expected_app,
                          app_index,app_data,app_sop,app_eop,app_length,app_sn);
                app_index=app_index+1;app_bytes=app_bytes+1;
                if(app_eop)begin
                    app_frames=app_frames+1;app_index=0;
                    if(pressure_phase && pressure_slot<3)begin
                        pressure_slot=pressure_slot+1;expected_app=PRESSURE_0+pressure_slot;end
                    else expected_app=-1;
                end
            end
        end
    end
    task automatic reset_epoch;
        begin
            @(negedge clk);reset=1;inject=0;app_ready=1;
            msg_valid=0;payload_valid=0;payload_last=0;
            expected_tx=-1;expected_app=-1;app_index=0;pressure_phase=0;
            repeat(5)@(posedge clk);
            @(negedge clk);
            if(psn_valid || psn!=0 || sn_accepted_count!=0 || sn_rejected_count!=0 ||
               sn_control_count!=0 || app_delivered_count!=0 || candidate_banks_busy!=0)
                $fatal(1,"reset epoch failed");
            reset=0;
        end
    endtask
    task automatic inject_raw(input integer c);
        integer j,len,base;
        begin
            len=meta_mem[c][159:128];base=meta_mem[c][191:160];
            @(negedge clk);inject=1;gmii_rx_dv=0;gmii_rx_er=0;
            repeat(16)@(negedge clk);
            for(j=0;j<len;j=j+1)begin
                gmii_rxd=wire_mem[base+j];gmii_rx_dv=1;
                @(negedge clk);
            end
            gmii_rx_dv=0;gmii_rxd=0;
        end
    endtask
    task automatic transmit_b1(input integer c);
        integer j,t,len,base;
        begin
            @(negedge clk);inject=0;
            len=meta_mem[c][95:64];base=meta_mem[c][127:96];
            expected_tx=c;msg_payload_length=len;msg_valid=1;
            t=0;while(!msg_ready&&t<10000)begin @(posedge clk);t=t+1;end
            if(!msg_ready)$fatal(1,"descriptor timeout");
            @(posedge clk);@(negedge clk);msg_valid=0;
            for(j=0;j<len;j=j+1)begin
                @(negedge clk);payload_valid=1;payload_data=payload_mem[base+j];
                payload_last=(j==len-1);t=0;
                do begin @(posedge clk);t=t+1;if(t>10000)$fatal(1,"payload timeout");end while(!payload_ready);
            end
            @(negedge clk);payload_valid=0;payload_last=0;
            t=0;while(!msg_done&&t<150000)begin @(posedge clk);t=t+1;end
            if(!msg_done)$fatal(1,"real BAG/done timeout");
        end
    endtask
    task automatic exercise(input integer c,input integer source);
        integer action,t,before_app,before_sn,before_control,before_proto,before_mac;
        integer progress_fd;
        begin
            action=expect_mem[c][127:96];before_app=app_frames;
            before_sn=sn_rejected_count;before_control=sn_control_count;
            before_proto=candidate_rejected_count;before_mac=rx_drop;
            expected_app=action==0?c:-1;
            if(source==1)transmit_b1(c);else inject_raw(c);
            t=0;
            case(action)
                0: while(app_frames==before_app&&t<30000)begin @(posedge clk);t=t+1;end
                1: while(sn_rejected_count==before_sn&&t<30000)begin @(posedge clk);t=t+1;end
                2: while(sn_control_count==before_control&&t<30000)begin @(posedge clk);t=t+1;end
                3: while(candidate_rejected_count==before_proto&&t<30000)begin @(posedge clk);t=t+1;end
                4: while(rx_drop==before_mac&&t<30000)begin @(posedge clk);t=t+1;end
                default:$fatal(1,"unknown scenario action");
            endcase
            if(t>=30000)$fatal(1,"scenario timeout case=%0d action=%0d",c,action);
            t=0;while(candidate_banks_busy!=0&&t<30000)begin @(posedge clk);t=t+1;end
            @(negedge clk);
            if(t>=30000 || psn!==expect_mem[c][95:64] ||
               psn_valid!==expect_mem[c][63:32] || sn_missing_count!==expect_mem[c][31:0])
                $fatal(1,"SN state mismatch case=%0d got_psn=%0d expected=%0d missing=%0d expected=%0d",
                    c,psn,expect_mem[c][95:64],sn_missing_count,expect_mem[c][31:0]);
            if(app_frames!=before_app+(action==0) || sn_rejected_count!=before_sn+(action==1) ||
               sn_control_count!=before_control+(action==2) ||
               candidate_rejected_count!=before_proto+(action==3) || rx_drop!=before_mac+(action==4) ||
               sn_accepted_count!=app_delivered_count)
                $fatal(1,"decision/application conservation case=%0d",c);
            $fdisplay(decision_fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                cycle,c,action,psn,psn_valid,sn_accepted_count,sn_rejected_count,
                sn_control_count,sn_missing_count,app_delivered_count);
            progress_fd=$fopen("frame_progress.csv","a");
            $fdisplay(progress_fd,"%0d,%0d,%0d,%0d",cycle,c,tx_frames,app_frames);$fclose(progress_fd);
        end
    endtask
    task automatic pressure_reset_phase;
        integer t,before_app;
        begin
            before_app=app_frames;app_ready=0;pressure_phase=1;pressure_slot=0;
            expected_app=PRESSURE_0;
            inject_raw(PRESSURE_0);inject_raw(PRESSURE_1);
            t=0;while(candidate_accepted_count<2&&t<2000)begin @(posedge clk);t=t+1;end
            @(negedge clk);
            if(candidate_banks_busy!==2'b11 || psn!=10 || sn_accepted_count!=1 || app_delivered_count!=0)
                $fatal(1,"reserved-bank SN/backpressure state failed");
            inject_raw(PRESSURE_2);inject_raw(PRESSURE_3);inject_raw(CAPACITY_DROP);
            repeat(8)@(posedge clk);@(negedge clk);
            if(rx_seen!=5 || rx_good!=4 || rx_drop!=1 || psn!=10 || sn_accepted_count!=1)
                $fatal(1,"capacity drop advanced unchecked SN or lost reserved bank");
            app_ready=1;t=0;
            while(app_frames<before_app+4&&t<30000)begin @(posedge clk);t=t+1;end
            @(negedge clk);pressure_phase=0;
            if(app_frames!=before_app+4 || psn!=13 || sn_accepted_count!=4 ||
               app_delivered_count!=4 || sn_missing_count!=0 || candidate_banks_busy!=0)
                $fatal(1,"pressure delivery conservation failed");
            exercise(CAPACITY_RECOVERY,0);
            app_ready=0;expected_app=-1;inject_raw(RESET_CANCEL);
            t=0;while(sn_accepted_count<6&&t<2000)begin @(posedge clk);t=t+1;end
            @(negedge clk);
            if(sn_accepted_count!=6 || app_delivered_count!=5 || psn!=16 || candidate_banks_busy==0)
                $fatal(1,"reset-cancel setup failed");
            $display("B2_SN_CAPACITY_RESET = PASS retained=4 mac_drop=1 psn_not_advanced_on_unchecked_drop=1 reset_cancel=1");
        end
    endtask
    initial begin
        repeat(5)@(posedge clk);
        `include "golden/scenario.vh"
        @(negedge clk);
        if(tx_frames!=263 || late_count!=0)$fatal(1,"B1 wrap TX total/late mismatch");
        $fclose(tx_fd);$fclose(app_fd);$fclose(decision_fd);
        $display("B2_FULL_SN_PROTOCOL = PASS sn_wrap=256 real_b1_tx=263 tx_bytes=%0d app_frames=%0d app_bytes=%0d clk_hz=125000000 bag_cycles=125000",tx_bytes,app_frames,app_bytes);
        $finish;
    end
    initial begin #400000000;$fatal(1,"full simulation timeout");end
endmodule
