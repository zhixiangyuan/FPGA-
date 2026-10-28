`timescale 1ns/1ps
// Fixed application timestamps from the saved competition_010 workload.
// Never wait for ready to make a candidate look less loaded.
module tb_jitter_replay;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] tx_data=0;reg tx_valid=0;wire tx_ready;
 wire [7:0] rx_data,a,b;wire rv,rs,re,initialized,ae,be,aer,ber;
 reg ready=1;reg [7:0] bd[0:63];reg [63:0] bv=0;reg [2:0] mode=0;
 integer cycle=0,got=0,af,ia,wa,wb,trace;
 `include "golden/constants.vh"
 reg [95:0] stimulus[0:OFFER_COUNT-1];reg [39:0] modes[0:3];
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .rx_data(rx_data),.rx_valid(rv),.rx_ready(ready),.rx_sop(rs),.rx_eop(re),.initialized(initialized),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(aer),.gmii_b_tx_er(ber),
  .gmii_a_rxd(a),.gmii_a_rx_dv(ae&&mode!=2),.gmii_a_rx_er(mode==3),
  .gmii_b_rxd(bd[63]),.gmii_b_rx_dv(bv[63]&&mode!=1),.gmii_b_rx_er(1'b0),
  .status_select(4'd0),.status_data(),.time_synchronized());
`ifdef JITTER_BIAS_16
 defparam dut.core.queue.LENGTH_BIAS_16=`JITTER_BIAS_16;
`endif
 always @(posedge clk)begin
  cycle<=cycle+1;ready<=cycle%19!=0&&cycle%19!=1;
  if(!reset&&cycle%500000==0)$display("JITTER_REPLAY_PROGRESS cycle=%0d delivered=%0d",cycle,got);
  if(reset)bv<=0;else bv<={bv[62:0],be};
  bd[0]<=b;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  if(!reset&&rv&&ready)begin
   $fwrite(af,"%0d,%0d,%0d,%0d,%0d\n",cycle,rs,re,rx_data,mode);
   if(re)got<=got+1;
  end
  if(aer||ber)$fatal(1,"TX error");
  if(ae)$fwrite(wa,"%0d,%02x\n",cycle,a);
  if(be)$fwrite(wb,"%0d,%02x\n",cycle,b);
  if(dut.core.msg_valid&&dut.core.msg_ready)
   $fwrite(trace,"%0d,descriptor,%0d,%0d\n",cycle,dut.core.msg_vlid,dut.core.msg_length);
 end
 function [7:0] pattern(input integer id,input integer pos);
  pattern=(id*13+pos*37+(pos>>2)+53)&255;
 endfunction
 initial begin
  $readmemh("golden/modes.mem",modes);
  for(integer m=0;m<4;m=m+1)begin
   while(cycle<modes[m][39:8])@(negedge clk);
   mode=modes[m][7:0];
  end
 end
 initial begin
  af=$fopen("application.csv","w");$fwrite(af,"cycle,sop,eop,data,mode\n");
  ia=$fopen("inputs.csv","w");$fwrite(ia,"id,vl,length,cycle\n");
  wa=$fopen("wire_a.csv","w");$fwrite(wa,"cycle,data\n");
  wb=$fopen("wire_b.csv","w");$fwrite(wb,"cycle,data\n");
  trace=$fopen("schedule.csv","w");$fwrite(trace,"cycle,event,vl,length\n");
  $readmemh("golden/offers.mem",stimulus);
  repeat(8)@(negedge clk);reset=0;wait(initialized);@(negedge clk);
  for(integer f=0;f<OFFER_COUNT;f=f+1)begin
   while(cycle<stimulus[f][95:64])@(negedge clk);
   if(cycle!=stimulus[f][95:64]||!tx_ready)$fatal(1,"fixed offered input blocked f=%0d cycle=%0d",f,cycle);
   $fwrite(ia,"%0d,%0d,%0d,%0d\n",stimulus[f][31:0],stimulus[f][63:48],stimulus[f][47:32],cycle);
   tx_valid=1;tx_data=stimulus[f][63:56];@(negedge clk);tx_data=stimulus[f][55:48];
   for(integer p=0;p<stimulus[f][47:32];p=p+1)begin
    @(negedge clk);tx_data=pattern(stimulus[f][31:0],p);
   end
   @(negedge clk);tx_valid=0;tx_data=0;
  end
  @(negedge clk);tx_valid=1;tx_data=8'h12;@(negedge clk);tx_valid=0;
  repeat(5000)@(negedge clk);
  if(got!=688||dut.app_accepted!=688||dut.app_sent!=688||dut.app_rejected!=4||dut.rx_delivered!=688)
   $fatal(1,"final counters got=%0d accepted=%0d sent=%0d rejected=%0d",got,dut.app_accepted,dut.app_sent,dut.app_rejected);
  $display("JITTER_REPLAY_FUNCTIONAL_PASS messages=%0d",got);
  $fclose(af);$fclose(ia);$fclose(wa);$fclose(wb);$fclose(trace);$finish;
 end
 initial begin #100000000;$fatal(1,"jitter replay watchdog");end
endmodule
