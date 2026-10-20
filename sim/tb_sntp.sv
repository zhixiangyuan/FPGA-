`timescale 1ns/1ps
module tb_sntp;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,request_start=0;reg [63:0] utc_time=0;
 wire request_ready;wire [7:0] tx_data;wire tx_valid,tx_sop,tx_eop;reg tx_ready=0;
 wire [10:0] tx_length;wire [15:0] tx_src_port,tx_dst_port;
 reg [7:0] rx_data=0;reg rx_valid=0,rx_sop=0,rx_eop=0;
 wire rx_ready;reg [10:0] rx_length=0;reg [31:0] rx_src_ip=0;
 reg [15:0] rx_src_port=0,rx_dst_port=49152;reg [63:0] rx_timestamp=0;
 wire sync_valid,response_accepted,response_rejected,timeout;
 wire [63:0] sync_t1,sync_t2,sync_t3,sync_t4,request_timestamp;
 wire [31:0] accepted_count,rejected_count,timeout_count;
 afdx_sntp_client dut(.*);
 `include "golden/constants.vh"
 reg [223:0] meta[0:CASE_COUNT-1];reg [255:0] times[0:CASE_COUNT-1];
 reg [7:0] responses[0:RX_BYTES-1],requests[0:TX_BYTES-1];
 integer fd,txfd,cycle=0,current=0,tx_index=0,group=0,i,j,waits;
 always @(posedge clk)begin
  cycle=cycle+1;
  if(!reset&&tx_valid&&tx_ready&&group>=0)begin
   if(tx_data!==requests[group*48+tx_index]||tx_sop!=(tx_index==0)||tx_eop!=(tx_index==47)||
      tx_length!=48||tx_src_port!=49152||tx_dst_port!=123)$fatal(1,"SNTP request mismatch");
   $fwrite(txfd,"%0d,%0d,%02x\n",group,tx_index,tx_data);tx_index=tx_index+1;
  end
 end
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/times.mem",times);
  $readmemh("golden/responses.mem",responses);$readmemh("golden/requests.mem",requests);
  fd=$fopen("sync.csv","w");txfd=$fopen("requests.csv","w");
  $fwrite(fd,"case_id,accepted,rejected,t1,t2,t3,t4\n");$fwrite(txfd,"group,byte_index,data\n");
  repeat(4)@(negedge clk);reset=0;#1;
  for(i=0;i<CASE_COUNT;i=i+1)begin
   current=i;
   if(meta[i][223:192])begin
    if(!request_ready)$fatal(1,"Request not ready");
    group=meta[i][95:64];tx_index=0;utc_time=times[i][255:192];request_start=1;
    @(negedge clk);request_start=0;waits=0;
    while(tx_index<48)begin
     tx_ready=(cycle%5!=0);@(negedge clk);waits=waits+1;if(waits>200)$fatal(1,"TX timeout");
    end
   end
   rx_length=meta[i][159:128];rx_src_ip=meta[i][63:32];rx_src_port=meta[i][31:0];rx_timestamp=times[i][63:0];
   for(j=0;j<rx_length;j=j+1)begin
    rx_data=responses[meta[i][191:160]+j];rx_valid=1;rx_sop=(j==0);rx_eop=(j+1==rx_length);
    @(negedge clk);
   end
   rx_valid=0;rx_sop=0;rx_eop=0;
   @(negedge clk);
   if(response_accepted!=meta[i][127:96]||response_rejected==meta[i][127:96]||sync_valid!=meta[i][127:96])
    $fatal(1,"Response decision case=%0d",i);
   if(sync_valid&&{sync_t1,sync_t2,sync_t3,sync_t4}!==times[i])$fatal(1,"Timestamp extraction");
   $fwrite(fd,"%0d,%0d,%0d,%016x,%016x,%016x,%016x\n",i,response_accepted,response_rejected,sync_t1,sync_t2,sync_t3,sync_t4);
   repeat(3)@(negedge clk);
  end
  // Real 125MHz, default one-second timeout, not a reduced-clock shortcut.
  // Do not compare this separate timeout request against previous Golden groups.
  group=-1;reset=1;tx_ready=0;utc_time=64'he900010000000000;
  @(negedge clk);reset=0;request_start=1;
  @(negedge clk);request_start=0;
  // Consume timeout request independently without the regular monitor.
  tx_index=0;tx_ready=1;
  wait(timeout);@(negedge clk);
  if(timeout_count!=1||!request_ready)$fatal(1,"Timeout recovery");
  reset=1;@(negedge clk);
  if(accepted_count||rejected_count||timeout_count||sync_valid||tx_valid)$fatal(1,"Reset recovery");
  $fclose(fd);$fclose(txfd);$display("SNTP_CLIENT = PASS cases=%0d",CASE_COUNT);$finish;
 end
 initial begin #1100000000;$fatal(1,"Simulation timeout");end
endmodule
