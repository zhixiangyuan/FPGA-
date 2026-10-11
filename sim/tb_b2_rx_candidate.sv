`timescale 1ns/1ps
module tb_b2_rx_candidate;
    localparam integer CASES=17, MAX_BYTES=16384;
    reg clk=0; always #4 clk=~clk;
    reg reset=1;
    reg [7:0] in_data=0;
    reg in_valid=0,in_sop=0,in_eop=0;
    reg [15:0] in_length=0;
    wire in_ready;
    wire [7:0] payload_data;
    wire payload_valid,payload_sop,payload_eop;
    reg payload_ready=1;
    wire [10:0] payload_length;
    wire [15:0] payload_vlid;
    wire [7:0] payload_sn_unchecked;
    wire candidate_accepted,candidate_rejected;
    wire [3:0] reject_reason;
    wire [31:0] accepted_count,rejected_count;
    wire [1:0] banks_busy;
    reg [7:0] client_mem[0:MAX_BYTES-1],payload_mem[0:MAX_BYTES-1];
    reg [255:0] meta_mem[0:CASES-1];
    integer cycle=0, active_case=-1, out_index=0, delivered=0;
    integer accepted_seen=0,rejected_seen=0;
    integer app_fd;

    afdx_single_vl_rx_candidate dut(
        .clk(clk),.reset(reset),.in_data(in_data),.in_valid(in_valid),
        .in_ready(in_ready),.in_sop(in_sop),.in_eop(in_eop),.in_length(in_length),
        .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),
        .cfg_src_mac(48'h020000000009),.cfg_src_ip(32'h0a000001),
        .cfg_dst_ip(32'he0e0003c),.cfg_src_port(16'd24),.cfg_dst_port(16'd23),
        .payload_data(payload_data),.payload_valid(payload_valid),
        .payload_ready(payload_ready),.payload_sop(payload_sop),
        .payload_eop(payload_eop),.payload_length(payload_length),
        .payload_vlid(payload_vlid),.payload_sn_unchecked(payload_sn_unchecked),
        .candidate_accepted(candidate_accepted),.candidate_rejected(candidate_rejected),
        .reject_reason(reject_reason),.accepted_count(accepted_count),
        .rejected_count(rejected_count),.banks_busy(banks_busy)
    );
    initial begin
        $readmemh("golden/client.mem",client_mem);
        $readmemh("golden/payload.mem",payload_mem);
        $readmemh("golden/meta.mem",meta_mem);
        app_fd=$fopen("actual_payload.csv","w");
        if(app_fd==0)$fatal(1,"cannot open app CSV");
        $fdisplay(app_fd,"cycle,case_id,byte_index,data,sop,eop,length,sn");
    end
    always @(posedge clk) begin
        cycle=cycle+1;
        if(!reset)begin
            if(candidate_accepted) accepted_seen=accepted_seen+1;
            if(candidate_rejected) rejected_seen=rejected_seen+1;
            if(payload_valid&&payload_ready)begin
                if(active_case<0)$fatal(1,"payload without expected case");
                if(payload_data!==payload_mem[meta_mem[active_case][127:96]+out_index])
                    $fatal(1,"payload mismatch case=%0d index=%0d",active_case,out_index);
                if(payload_length!==meta_mem[active_case][95:64] ||
                   payload_vlid!==16'h1234 ||
                   payload_sn_unchecked!==meta_mem[active_case][63:32])
                    $fatal(1,"metadata mismatch case=%0d",active_case);
                if(payload_sop!==(out_index==0) ||
                   payload_eop!==(out_index+1==meta_mem[active_case][95:64]))
                    $fatal(1,"payload boundary mismatch case=%0d index=%0d",active_case,out_index);
                $fdisplay(app_fd,"%0d,%0d,%0d,%02X,%0d,%0d,%0d,%0d",cycle,active_case,
                          out_index,payload_data,payload_sop,payload_eop,payload_length,payload_sn_unchecked);
                out_index=out_index+1;
                if(payload_eop) begin delivered=delivered+1;out_index=0;active_case=-1;end
            end
        end
    end
    task automatic send_case(input integer c);
        integer j,t,base,len;
        begin
            base=meta_mem[c][255:224];len=meta_mem[c][223:192];
            if(meta_mem[c][31:0]==0)active_case=c;
            for(j=0;j<len;j=j+1)begin
                @(negedge clk);
                in_data=client_mem[base+j];in_valid=1;
                in_sop=(j==0);in_eop=(j==len-1);in_length=len;
                t=0;
                do begin @(posedge clk);t=t+1;if(t>10000)$fatal(1,"input stall case=%0d",c);end while(!in_ready);
            end
            @(negedge clk);in_valid=0;in_sop=0;in_eop=0;
            t=0;
            if(meta_mem[c][31:0]==0)begin
                while(active_case>=0 && t<10000)begin @(posedge clk);t=t+1;end
                if(active_case>=0)$fatal(1,"payload timeout case=%0d",c);
            end else begin
                while(!candidate_rejected && t<10000)begin @(posedge clk);t=t+1;end
                if(!candidate_rejected || reject_reason!==meta_mem[c][31:0])
                    $fatal(1,"reject mismatch case=%0d got=%0d expected=%0d",c,reject_reason,meta_mem[c][31:0]);
                if(payload_valid)$fatal(1,"bad frame leaked payload case=%0d",c);
            end
            repeat(3)@(posedge clk);
        end
    endtask
    integer k;
    initial begin
        repeat(5)@(posedge clk);
        @(negedge clk);reset=0;
        for(k=0;k<15;k=k+1)send_case(k);
        send_case(16);
        if(accepted_seen!=7 || rejected_seen!=9 || delivered!=7 ||
           accepted_count!=7 || rejected_count!=9 || banks_busy!=0)
            $fatal(1,"unit counts accepted=%0d rejected=%0d delivered=%0d busy=%b",
                accepted_seen,rejected_seen,delivered,banks_busy);
        $fclose(app_fd);
        $display("B2_RX_PARSER_UNIT = PASS accepted=7 rejected=9 delivered=7 sn_policy=UNCHECKED");
        $finish;
    end
    initial begin #10000000;$fatal(1,"global timeout");end
endmodule
