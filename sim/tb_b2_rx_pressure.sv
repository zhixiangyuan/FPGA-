`timescale 1ns/1ps
module tb_b2_rx_pressure;
    localparam integer MAX_BYTES=16384;
    reg clk=0;always #4 clk=~clk;
    reg reset=1,in_valid=0,in_sop=0,in_eop=0,payload_ready=0;
    reg [7:0] in_data=0;
    reg [15:0] in_length=0;
    wire in_ready,payload_valid,payload_sop,payload_eop;
    wire [7:0] payload_data,payload_sn_unchecked;
    wire [10:0] payload_length;
    wire [15:0] payload_vlid;
    wire candidate_accepted,candidate_rejected;
    wire [3:0] reject_reason;
    wire [31:0] accepted_count,rejected_count;
    wire [1:0] banks_busy;
    reg [7:0] client_mem[0:MAX_BYTES-1],payload_mem[0:MAX_BYTES-1];
    reg [255:0] meta_mem[0:16];
    integer cycle=0,output_case=0,output_index=0,delivered=0;
    integer app_fd;
    afdx_single_vl_rx_candidate dut(
        .clk(clk),.reset(reset),.in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),
        .in_sop(in_sop),.in_eop(in_eop),.in_length(in_length),
        .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),
        .cfg_src_mac(48'h020000000009),.cfg_src_ip(32'h0a000001),
        .cfg_dst_ip(32'he0e0003c),.cfg_src_port(16'd24),.cfg_dst_port(16'd23),
        .payload_data(payload_data),.payload_valid(payload_valid),
        .payload_ready(payload_ready),.payload_sop(payload_sop),.payload_eop(payload_eop),
        .payload_length(payload_length),.payload_vlid(payload_vlid),
        .payload_sn_unchecked(payload_sn_unchecked),
        .candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),
        .reject_reason(reject_reason),.accepted_count(accepted_count),
        .rejected_count(rejected_count),.banks_busy(banks_busy)
    );
    initial begin
        $readmemh("golden/client.mem",client_mem);
        $readmemh("golden/payload.mem",payload_mem);
        $readmemh("golden/meta.mem",meta_mem);
        app_fd=$fopen("actual_payload.csv","w");
        if(app_fd==0)$fatal(1,"cannot open CSV");
        $fdisplay(app_fd,"cycle,case_id,byte_index,data,sop,eop");
    end
    always @(posedge clk) begin
        cycle=cycle+1;
        if(!reset && payload_valid && payload_ready) begin
            if(payload_data!==payload_mem[meta_mem[output_case][127:96]+output_index] ||
               payload_length!==meta_mem[output_case][95:64] ||
               payload_sn_unchecked!==meta_mem[output_case][63:32] ||
               payload_vlid!==16'h1234 ||
               payload_sop!==(output_index==0) ||
               payload_eop!==(output_index+1==meta_mem[output_case][95:64]))
               $fatal(1,"pressure payload mismatch case=%0d byte=%0d",output_case,output_index);
            $fdisplay(app_fd,"%0d,%0d,%0d,%02X,%0d,%0d",cycle,output_case,
                      output_index,payload_data,payload_sop,payload_eop);
            output_index=output_index+1;
            if(payload_eop)begin delivered=delivered+1;output_case=output_case+1;output_index=0;end
        end
    end
    task automatic send_frame(input integer c);
        integer j,t,base,len;
        begin
            base=meta_mem[c][255:224];len=meta_mem[c][223:192];
            for(j=0;j<len;j=j+1)begin
                @(negedge clk);in_valid=1;in_data=client_mem[base+j];
                in_sop=(j==0);in_eop=(j==len-1);in_length=len;
                t=0;
                do begin @(posedge clk);t=t+1;if(t>10000)$fatal(1,"input timeout");end while(!in_ready);
            end
            @(negedge clk);in_valid=0;in_sop=0;in_eop=0;
            repeat(2)@(posedge clk);
        end
    endtask
    integer t;
    initial begin
        repeat(5)@(posedge clk);@(negedge clk);reset=0;
        send_frame(0);send_frame(1);
        if(banks_busy!==2'b11 || in_ready!==1'b0 || accepted_count!==2 || payload_valid!==1)
            $fatal(1,"two-bank pressure not reached busy=%b ready=%b accepted=%0d",
                banks_busy,in_ready,accepted_count);
        repeat(20)begin @(posedge clk);if(!payload_valid || payload_data!==payload_mem[0])
            $fatal(1,"paused payload changed");end
        @(negedge clk);payload_ready=1;
        t=0;while(delivered<1 && t<10000)begin @(posedge clk);t=t+1;end
        if(delivered!=1)$fatal(1,"first frame did not drain");
        send_frame(2);
        t=0;while(delivered<3 && t<10000)begin @(posedge clk);t=t+1;end
        @(negedge clk);
        if(delivered!=3 || accepted_count!=3 || rejected_count!=0 || banks_busy!=0)
            $fatal(1,"pressure recovery failed delivered=%0d busy=%b",delivered,banks_busy);
        @(negedge clk);payload_ready=0;
        send_frame(0);
        if(banks_busy==0)$fatal(1,"reset setup missing buffered frame");
        @(negedge clk);reset=1;
        repeat(4)@(posedge clk);
        if(payload_valid || banks_busy!=0 || accepted_count!=0 || rejected_count!=0)
            $fatal(1,"reset did not discard candidate and clear counters");
        @(negedge clk);reset=0;payload_ready=1;output_case=16;output_index=0;
        send_frame(16);
        t=0;while(delivered<4 && t<10000)begin @(posedge clk);t=t+1;end
        @(negedge clk);
        if(delivered!=4 || accepted_count!=1 || banks_busy!=0)$fatal(1,"reset recovery failed");
        $fclose(app_fd);
        $display("B2_RX_PRESSURE_RESET = PASS retained=2 stalled=1 recovered=1 reset_cancel=1 sn_policy=UNCHECKED");
        $finish;
    end
    initial begin #10000000;$fatal(1,"global timeout");end
endmodule
