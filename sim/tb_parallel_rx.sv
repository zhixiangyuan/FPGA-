`timescale 1ns/1ps
module tb_parallel_rx;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] gmii_rxd=0;reg gmii_rx_dv=0;
 wire [7:0] in_data,cand_data,cand_sn,app_data,app_sn;
 wire in_valid,in_ready,in_sop,in_eop,cand_valid,cand_ready,cand_sop,cand_eop;
 wire [15:0] in_length,cand_vlid,app_vlid,src_port,dst_port;
 wire [10:0] cand_length,app_length;
 wire app_valid,app_sop,app_eop;reg app_ready=1;
 wire mac_accepted,mac_dropped,candidate_accepted,candidate_rejected;
 wire [4:0] mac_reason;wire [3:0] reject_reason;
 wire accepted,rejected,reset_control,delivered;
 wire [31:0] accepted_count,rejected_count,control_count,missing_count,delivered_count;
 wire tested_app_ready=app_ready;
 wire frame_done,frame_good;
 afdx_mac_rx_checked mac(.clk(clk),.reset(reset),.gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(1'b0),
  .stream_data(in_data),.stream_valid(in_valid),.stream_ready(in_ready),.stream_sop(in_sop),.stream_eop(in_eop),
  .frame_done(frame_done),.frame_good(frame_good),.frame_length(in_length),.drop_frames());
 assign mac_accepted=frame_done&&frame_good;assign mac_dropped=frame_done&&!frame_good;assign mac_reason=5'd2;
 afdx_multi_vl_rx_parser #(.CHECK_PORTS(0),.BANKS(8),.PARALLEL_MAC_CHECK(1)) parser(.clk(clk),.reset(reset),
  .in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),.in_sop(in_sop),.in_eop(in_eop),.in_length(in_length),
  .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),.cfg_src_mac(48'h020000000009),
  .cfg_src_ip(32'h0a000001),.cfg_dst_ip(32'he0e0003c),.cfg_src_port(16'd24),.cfg_dst_port(16'd23),
  .payload_data(cand_data),.payload_valid(cand_valid),.payload_ready(cand_ready),.payload_sop(cand_sop),.payload_eop(cand_eop),
  .payload_length(cand_length),.payload_vlid(cand_vlid),.payload_sn_unchecked(cand_sn),
  .payload_src_port(src_port),.payload_dst_port(dst_port),.candidate_accepted(candidate_accepted),
  .candidate_rejected(candidate_rejected),.reject_reason(reject_reason),.accepted_count(),.rejected_count(),.banks_busy(),.payload_discard(1'b0),.frame_done(frame_done),.frame_good(frame_good),.wire_frame_length(in_length));
 afdx_multi_vl_sn_gate gate(.clk(clk),.reset(reset),.cfg_integrity_enable(16'hffff),
  .in_data(cand_data),.in_valid(cand_valid),.in_ready(cand_ready),.in_sop(cand_sop),.in_eop(cand_eop),.in_length(cand_length),
  .in_vlid(cand_vlid),.in_sn(cand_sn),.app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
  .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),.app_vlid(app_vlid),.app_sn(app_sn),
  .accepted(accepted),.rejected(rejected),.reset_control(reset_control),.delivered(delivered),
  .accepted_count(accepted_count),.rejected_count(rejected_count),.control_count(control_count),
  .missing_count(missing_count),.delivered_count(delivered_count));
 wire [7:0] psns[0:15];genvar pv;
 generate for(pv=0;pv<16;pv=pv+1)begin:observe_psn assign psns[pv]=gate.psn[pv];end endgenerate
 `include "golden/constants.vh"
 reg [255:0] meta[0:CASE_COUNT-1];reg [31:0] ports[0:CASE_COUNT-1];
 reg [7:0] wire_bytes[0:WIRE_BYTES-1],payload_bytes[0:APP_BYTES-1];
 integer current=0,cycle=0,app_index=0,app_count=0,app_total=0,action=0,reason=0,fd,bytefd,i,j,waits;
 integer last_start[0:16],previous_injection_start=0;reg [16:0] have_start=0;
 always @(posedge clk)begin
  cycle=cycle+1;
  if(!reset)begin
   if(candidate_rejected)begin action=4;reason=reject_reason;end
   if(mac_dropped)begin action=5;reason=mac_reason;end
   if(accepted)action=1;if(rejected)action=2;if(reset_control)action=3;
   if(app_valid&&tested_app_ready)begin
    if(meta[current][63:32]!=1||app_data!==payload_bytes[meta[current][191:160]+app_index]||
       app_sn!=meta[current][95:64]||app_vlid!=meta[current][127:96]||app_length!=meta[current][159:128]||
       {src_port,dst_port}!=ports[current]||app_sop!=(app_index==0)||app_eop!=(app_index+1==app_length))
     $fatal(1,"Application Golden mismatch case=%0d byte=%0d",current,app_index);
    $fwrite(bytefd,"%02x\n",app_data);app_index=app_index+1;app_total=app_total+1;
    if(app_eop)app_count=app_count+1;
   end
  end
 end
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/ports.mem",ports);
  $readmemh("golden/wire.mem",wire_bytes);$readmemh("golden/payload.mem",payload_bytes);
  fd=$fopen("decisions.csv","w");bytefd=$fopen("actual_app.mem","w");$fwrite(fd,"case_id,vlid,sn,action,reason,psn,app_bytes\n");
  repeat(4)@(negedge clk);reset=0;
  for(i=0;i<CASE_COUNT;i=i+1)begin
   current=i;action=0;reason=0;app_index=0;j=meta[i][127:96]-16'h1234;
   while(have_start[j]&&cycle-last_start[j]<125000)@(negedge clk);
   previous_injection_start=cycle;
   have_start[j]=1;last_start[j]=cycle;
   for(j=0;j<meta[i][223:192];j=j+1)begin
    gmii_rx_dv=1;gmii_rxd=wire_bytes[meta[i][255:224]+j];@(negedge clk);
   end
   gmii_rx_dv=0;gmii_rxd=0;waits=0;
   do begin
    app_ready=(cycle%7!=0);@(negedge clk);waits=waits+1;
    if(waits>10000)$fatal(1,"RX timeout case=%0d",i);
   end while(action==0||(action==1&&app_index!=meta[i][159:128]));
   repeat(5)@(negedge clk);
   if(action!=meta[i][63:32]||(action==4&&reason!=meta[i][31:0]))$fatal(1,"Reject reason case=%0d got=%0d/%0d expected=%0d/%0d",i,action,reason,meta[i][63:32],meta[i][31:0]);
   j=meta[i][127:96]-16'h1234;
   $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",i,meta[i][127:96],meta[i][95:64],action,reason,
     j<16?$signed({24'd0,psns[j]}):-1,app_index);
   if(i%256==255)$display("MULTI_VL_RX_PROGRESS %0d",i+1);
  end
  $fclose(fd);$fclose(bytefd);$display("PARALLEL_RX = PASS cases=%0d app_frames=%0d app_bytes=%0d",CASE_COUNT,app_count,app_total);$finish;
 end
 initial begin #800000000;$fatal(1,"Timeout");end
endmodule
