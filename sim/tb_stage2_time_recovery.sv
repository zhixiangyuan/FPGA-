`timescale 1ns/1ps
module tb_stage2_time_recovery;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] rx_data=0;reg rx_valid=0,start=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 afdx_stage2_mgmt_top dut(.clk(clk),.reset(reset),.rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(1'b0),
  .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),.uptime_override(32'd0),
  .uptime_override_en(1'b0),.sntp_request_start(start));
 reg [7:0] reply_template[0:102],frame[0:102];
 reg [63:0] observed_t1=0;
 reg prev_tx=0;integer tx_index=0,tx_count=0,cycle=0,epoch=0;
 integer txfd,rxfd,eventfd,countfd,group=0;
 always @(posedge clk)begin
  if(reset)cycle<=0;else begin
   cycle<=cycle+1;
   if(start&&dut.sntp_request_ready)$fwrite(eventfd,"trigger,%0d,%0d,%0d,0,0,0,0\n",epoch,group,cycle);
   if(dut.demux_sntp_valid&&dut.demux_sntp_sop)$fwrite(eventfd,"capture,%0d,%0d,%0d,0,0,0,0\n",epoch,group,cycle);
   if(dut.sntp_sync_valid)$fwrite(eventfd,"sync,%0d,%0d,%0d,%016x,%016x,%016x,%016x\n",epoch,group,cycle,dut.sntp_t1,dut.sntp_t2,dut.sntp_t3,dut.sntp_t4);
   if(dut.sntp_timeout)$fwrite(eventfd,"timeout,%0d,%0d,%0d,0,0,0,0\n",epoch,group,cycle);
   if(tx_valid&&!prev_tx)begin tx_index=0;observed_t1=0;end
   if(tx_valid)begin
    $fwrite(txfd,"%0d,%0d,%0d,%0d,%02x\n",epoch,group,cycle,tx_index,tx_data);
    if(tx_index>=90&&tx_index<=97)observed_t1={observed_t1[55:0],tx_data};
    tx_index=tx_index+1;
   end
   if(!tx_valid&&prev_tx)begin
    if(tx_index!=103)$fatal(1,"SNTP request frame size %0d",tx_index);
    tx_count=tx_count+1;
   end
   prev_tx<=tx_valid;
  end
 end
 task request;
  integer before_count;
  begin
   wait(dut.sntp_request_ready);@(negedge clk);
   before_count=tx_count;start=1;@(negedge clk);start=0;
   wait(tx_count>before_count);repeat(200)@(negedge clk);
  end
 endtask
 task reply;
  input integer wrong_origin;input [7:0] sn;
  integer k,b;reg [63:0] origin,t2,t3;reg [31:0] crc;
  begin
   origin=observed_t1^(wrong_origin?64'd1:64'd0);t2=observed_t1+64'h100000;t3=t2+64'd2748;
   for(k=0;k<103;k=k+1)frame[k]=reply_template[k];
   for(k=0;k<8;k=k+1)begin
    frame[74+k]=origin>>(8*(7-k));frame[82+k]=t2>>(8*(7-k));frame[90+k]=t3>>(8*(7-k));
   end
   frame[98]=sn;crc=32'hffffffff;
   for(k=8;k<=98;k=k+1)begin
    crc=crc^frame[k];for(b=0;b<8;b=b+1)crc=crc[0]?(crc>>1)^32'hedb88320:crc>>1;
   end
   crc=~crc;for(k=0;k<4;k=k+1)frame[99+k]=crc>>(8*k);
   @(negedge clk);
   for(k=0;k<103;k=k+1)begin
    $fwrite(rxfd,"%0d,%0d,%0d,%0d,%02x\n",epoch,group,cycle,k,frame[k]);
    rx_valid=1;rx_data=frame[k];@(negedge clk);
   end
   rx_valid=0;rx_data=0;
  end
 endtask
 initial begin #2200000000;$fatal(1,"time recovery system timeout");end
 initial begin
  $readmemh("reply_template.mem",reply_template);
  txfd=$fopen("tx_bytes.csv","w");rxfd=$fopen("rx_bytes.csv","w");eventfd=$fopen("time_events.csv","w");countfd=$fopen("counters.csv","w");
  $fwrite(txfd,"epoch,group,cycle,index,data\n");$fwrite(rxfd,"epoch,group,cycle,index,data\n");
  $fwrite(eventfd,"event,epoch,group,cycle,t1,t2,t3,t4\n");$fwrite(countfd,"key,value\n");
  repeat(4)@(negedge clk);
  if(dut.mgmt_gate.cfg_integrity_enable!==2'b11)$fatal(1,"unknown/incomplete service integrity configuration");
  reset=0;
  group=0;request;reply(0,1);wait(dut.sntp_accepted_count==1);wait(dut.rtc_sync_count==1);
  group=1;request;reply(1,3);wait(dut.sntp_rejected_count==1);repeat(200)@(negedge clk);
  // Skip SN 2 to exercise the missing-frame count. The malformed origin
  // consumed SN 3 at the integrity gate. Replaying a
  // corrected payload with that same SN must still be rejected before SNTP.
  reply(0,3);repeat(2000)@(negedge clk);
  if(dut.sntp_accepted_count!=1||dut.mgmt_sn_rejected_count!=1)$fatal(1,"SNTP VL duplicate SN bypass");
  reply(0,4);wait(dut.sntp_accepted_count==2);wait(dut.rtc_sync_count==2);
  group=2;request;wait(dut.sntp_timeout_count==1);wait(dut.sntp_request_ready);repeat(2)@(negedge clk);
  group=3;request;reply(0,5);wait(dut.sntp_accepted_count==3);wait(dut.rtc_sync_count==3);
  @(negedge clk);
  $fwrite(countfd,"accepted,%0d\nrejected,%0d\ntimeout,%0d\nsync,%0d\n",dut.sntp_accepted_count,dut.sntp_rejected_count,dut.sntp_timeout_count,dut.rtc_sync_count);
  $fwrite(countfd,"gate_duplicate,%0d\n",dut.mgmt_sn_rejected_count);
  $fwrite(countfd,"gate_missing,%0d\n",dut.mgmt_sn_missing_count);
  group=4;request;reset=1;@(negedge clk);epoch=1;reset=0;prev_tx=0;
  repeat(2000)@(negedge clk);
  if(dut.sntp_accepted_count||dut.sntp_rejected_count||dut.sntp_timeout_count||dut.rtc_sync_count||!dut.sntp_request_ready||tx_valid)$fatal(1,"system reset recovery");
  $fclose(txfd);$fclose(rxfd);$fclose(eventfd);$fclose(countfd);
  $display("TIME_SYSTEM_RECOVERY = PASS requests=%0d",tx_count);$finish;
 end
endmodule
