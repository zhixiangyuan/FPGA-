`timescale 1ns/1ps
// Exercise every configured receive VL through real GMII/FCS/parser/IC/RM.
module tb_rx_capacity;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] data=0;reg valid=0;
 wire [7:0] rx,a,b;wire rv,rs,re,init,ae,be;
 reg [7:0] bd[0:63];reg [63:0] bv=0;
 reg [3:0] selection=3;wire [31:0] status;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(8'd0),.tx_valid(1'b0),.tx_ready(),
  .rx_data(rx),.rx_valid(rv),.rx_ready(1'b1),.rx_sop(rs),.rx_eop(re),.initialized(init),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(),.gmii_b_tx_er(),
  .gmii_a_rxd(data),.gmii_b_rxd(bd[63]),.gmii_a_rx_dv(valid),.gmii_b_rx_dv(bv[63]),.gmii_a_rx_er(1'b0),.gmii_b_rx_er(1'b0),
  .status_select(selection),.status_data(status),.time_synchronized());
 `include "golden/constants.vh"
 reg [7:0] frames[0:WIRE_BYTES-1];integer cycle=0,got=0,fd,start_cycle;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)bv<=0;else bv<={bv[62:0],valid};
  bd[0]<=data;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  if(rv)begin $fwrite(fd,"%0d,%0d,%0d\n",rs,re,rx);if(re)got<=got+1;end
  if(a!==b||ae!==be)$fatal(1,"A/B transmit mismatch");
 end
 task check(input integer s,input integer wanted);
  begin selection=s;@(negedge clk);if(status!==wanted)$fatal(1,"status %0d got %0d wanted %0d",s,status,wanted);end
 endtask
 initial begin
  fd=$fopen("application.csv","w");$fwrite(fd,"sop,eop,data\n");$readmemh("golden/wire.mem",frames);
  repeat(8)@(negedge clk);reset=0;wait(init);@(negedge clk);start_cycle=cycle;
  for(integer f=0;f<8192;f=f+1)begin
   while(cycle<start_cycle+f*512)@(negedge clk);
   for(integer p=0;p<72;p=p+1)begin data=frames[f*72+p];valid=1;@(negedge clk);end
   valid=0;
   if(f%1024==1023)$display("RX_CAPACITY_PROGRESS frames=%0d delivered=%0d",f+1,got);
  end
  repeat(2000)@(negedge clk);
  if(got!=8192)$fatal(1,"receive capacity loss %0d",got);
  check(3,8192);check(4,8192);check(5,0);check(6,0);check(7,0);
  $display("RX_CAPACITY_PASS configured=4096 frames=8192");$fclose(fd);$finish;
 end
 initial begin #50000000;$fatal(1,"capacity watchdog");end
endmodule
