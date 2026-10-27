`timescale 1ns/1ps
module tb_competition_smoke;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] tx_data=0,peer_data=0;reg tx_valid=0,peer_valid=0;
 wire [7:0] rx_data,a,b;wire ready,rv,rs,re,init,ae,be;
 reg [3:0] status_select=3;wire [31:0] status_data;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(ready),
  .rx_data(rx_data),.rx_valid(rv),.rx_ready(1'b1),.rx_sop(rs),.rx_eop(re),.initialized(init),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(),.gmii_b_tx_er(),
  .gmii_a_rxd(peer_valid?peer_data:a),.gmii_b_rxd(peer_valid?peer_data:b),
  .gmii_a_rx_dv(peer_valid||ae),.gmii_b_rx_dv(peer_valid||be),.gmii_a_rx_er(1'b0),.gmii_b_rx_er(1'b0),
  .status_select(status_select),.status_data(status_data),.time_synchronized());
 `include "golden/constants.vh"
 reg [7:0] apps[0:APP_BYTES-1],peer[0:PEER_BYTES-1];
 integer cycle=0,got=0,fd,wf;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(rv)begin $fwrite(fd,"%0d,%0d,%0d,%0d\n",cycle,rs,re,rx_data);if(re)got<=got+1;end
  if(ae)$fwrite(wf,"%0d,%02x\n",cycle,a);
  if(a!==b||ae!==be)$fatal(1,"dual-network TX mismatch");
  if(peer_valid&&ae)$fatal(1,"test network collision");
 end
 task offer(input integer offset,input integer size);
  begin
   @(negedge clk);while(!ready)@(negedge clk);
   for(integer p=0;p<size;p=p+1)begin tx_valid=1;tx_data=apps[offset+p];@(negedge clk);end
   tx_valid=0;
  end
 endtask
 initial begin
  fd=$fopen("smoke_app.csv","w");$fwrite(fd,"cycle,sop,eop,data\n");
  wf=$fopen("smoke_wire.csv","w");$fwrite(wf,"cycle,data\n");
  $readmemh("golden/apps.mem",apps);$readmemh("golden/peer.mem",peer);
  repeat(8)@(negedge clk);reset=0;wait(init);
  offer(0,3);@(negedge clk);offer(3,1473);
  wait(got==2);repeat(1000)@(negedge clk);
  for(integer p=0;p<PEER_BYTES;p=p+1)begin peer_valid=1;peer_data=peer[p];@(negedge clk);end
  peer_valid=0;wait(got==3);repeat(1000)@(negedge clk);
  if(status_data!=3)$fatal(1,"wrong delivery counter");
  status_select=4;@(negedge clk);
  if(status_data!=3)$fatal(1,"wrong duplicate counter");
  $display("COMPETITION_SMOKE_PASS deliveries=3 duplicates=3");
  $fclose(fd);$fclose(wf);$finish;
 end
 initial begin #1000000;$fatal(1,"smoke watchdog");end
endmodule
