`timescale 1ns/1ps
module tb_multi_vl_tx;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,msg_valid=0,payload_valid=0,payload_last=0,payload_abort=0;
 reg [10:0] msg_payload_length=0;
 reg [15:0] msg_vlid=16'h1234;
 reg [7:0] payload_data=0;
 wire msg_ready,payload_ready,msg_done,msg_error;wire [3:0] error_code;wire [31:0] late_count;
 wire [7:0] mac_tx_data,gmii_txd;wire mac_tx_valid,mac_tx_ready,mac_tx_sop,mac_tx_eop,mac_tx_afdx;
 wire [15:0] mac_tx_length;wire mac_tx_done,mac_tx_reject,gmii_tx_en,gmii_tx_er;
 wire [31:0] sent_frames,rejected_frames;wire counter_saturated;
 afdx_multi_vl_tx sender(.clk(clk),.reset(reset),.msg_valid(msg_valid),.msg_ready(msg_ready),
  .msg_payload_length(msg_payload_length),.msg_da_const(32'h03000000),.msg_vlid(msg_vlid),
  .msg_src_mac(48'h020000000009),.msg_src_ip(32'h0a000001),.msg_dst_ip(32'he0e0003c),
  .msg_src_port(16'd24),.msg_dst_port(16'd23),.msg_ttl(8'd1),
  .msg_bag_cycles(32'd125000),.msg_jitter_cycles(32'd12500),
  .payload_data(payload_data),.payload_valid(payload_valid),.payload_ready(payload_ready),
  .payload_last(payload_last),.payload_abort(payload_abort),
  .mac_tx_data(mac_tx_data),.mac_tx_valid(mac_tx_valid),.mac_tx_ready(mac_tx_ready),
  .mac_tx_sop(mac_tx_sop),.mac_tx_eop(mac_tx_eop),.mac_tx_length(mac_tx_length),.mac_tx_afdx(mac_tx_afdx),
  .mac_tx_done(mac_tx_done),.mac_tx_reject(mac_tx_reject),.gmii_tx_en(gmii_tx_en),
  .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),.late_count(late_count));
 mac_gmii_tx mac(.clk(clk),.reset(reset),.client_data(mac_tx_data),.client_valid(mac_tx_valid),
  .client_ready(mac_tx_ready),.client_sop(mac_tx_sop),.client_eop(mac_tx_eop),
  .client_length(mac_tx_length),.client_afdx_prepared(mac_tx_afdx),
  .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),.done(mac_tx_done),.reject(mac_tx_reject),
  .sent_frames(sent_frames),.rejected_frames(rejected_frames),.counter_saturated(counter_saturated));
 `include "golden/constants.vh"
 reg [191:0] meta[0:CASE_COUNT-1];reg [7:0] wire_gold[0:WIRE_BYTES-1],payload_gold[0:APP_BYTES-1];
 integer cycle=0,active_case=0,tx_case=0,tx_index=0,total_bytes=0;
 integer framefd,bytefd,i,j,waits,vl,starts[0:15];reg [15:0] have_start=0;
 reg tx_d=0;integer frame_start;
 always @(posedge clk)begin
  cycle=cycle+1;
  if(reset)begin tx_d<=0;have_start=0;end
  else begin
   if(msg_error||mac_tx_reject||gmii_tx_er)$fatal(1,"Unexpected error");
   tx_d<=gmii_tx_en;
   if(gmii_tx_en&&!tx_d)begin
    tx_case=active_case;tx_index=0;vl=meta[tx_case][191:160];
    if(have_start[vl]&&cycle-starts[vl]<125000)$fatal(1,"Independent VL BAG violation");
    have_start[vl]=1;starts[vl]=cycle;frame_start=cycle;
   end
   if(gmii_tx_en)begin
    if(tx_index>=meta[tx_case][31:0]||gmii_txd!==wire_gold[meta[tx_case][95:64]+tx_index])
     $fatal(1,"Golden case=%0d byte=%0d got=%02x",tx_case,tx_index,gmii_txd);
    $fwrite(bytefd,"%02x\n",gmii_txd);tx_index=tx_index+1;total_bytes=total_bytes+1;
   end
   if(!gmii_tx_en&&tx_d)begin
    if(tx_index!=meta[tx_case][31:0])$fatal(1,"Wire length");
    $fwrite(framefd,"%0d,%0d,%0d,%0d,%0d\n",tx_case,meta[tx_case][191:160],frame_start,cycle-1,tx_index);
   end
  end
 end
 task automatic offer(input integer cid,input integer count);
 begin
  @(negedge clk);active_case=cid;msg_vlid=16'h1234+meta[cid][191:160];
  msg_payload_length=meta[cid][127:96];msg_valid=1;
  waits=0;do begin @(posedge clk);waits=waits+1;if(waits>300000)$fatal(1,"Descriptor timeout");end while(!msg_ready);
  @(negedge clk);msg_valid=0;
  for(j=0;j<count;j=j+1)begin
   payload_valid=1;payload_data=payload_gold[meta[cid][63:32]+j];payload_last=(j+1==msg_payload_length);
   waits=0;do begin @(posedge clk);waits=waits+1;if(waits>300000)$fatal(1,"Payload timeout");end while(!payload_ready);
   @(negedge clk);
  end
  payload_valid=0;payload_last=0;
 end endtask
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/wire.mem",wire_gold);$readmemh("golden/payload.mem",payload_gold);
  framefd=$fopen("frames.csv","w");bytefd=$fopen("actual_wire.mem","w");
  $fwrite(framefd,"case_id,vl,start_cycle,end_cycle,wire_bytes\n");
  repeat(4)@(negedge clk);reset=0;
  for(i=0;i<4096;i=i+1)begin
   offer(i,1471);waits=0;
   do begin @(posedge clk);waits=waits+1;if(waits>300000)$fatal(1,"Completion timeout");end while(!msg_done);
   @(negedge clk);
   if(i%256==255)$display("MULTI_VL_TX_PROGRESS %0d",i+1);
  end
  // Cancel a partial, uncommitted payload, then verify independent TX SN reset.
  offer(4095,4);reset=1;payload_valid=0;repeat(4)@(negedge clk);reset=0;
  offer(4096,17);wait(msg_done);repeat(5)@(negedge clk);
  if(total_bytes!=WIRE_BYTES)$fatal(1,"Total wire bytes");
  $fclose(framefd);$fclose(bytefd);
  $display("MULTI_VL_TX = PASS cases=%0d bytes=%0d",CASE_COUNT,total_bytes);$finish;
 end
 initial begin #600000000;$fatal(1,"Simulation timeout");end
endmodule
