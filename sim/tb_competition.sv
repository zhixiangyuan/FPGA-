`timescale 1ns/1ps
module tb_competition;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] tx_data=0;reg tx_valid=0;wire tx_ready;
 wire [7:0] rx_data;wire rx_valid,rx_sop,rx_eop,initialized;
 reg rx_ready=1;wire [7:0] a,b;wire ae,be,aer,ber;
 reg [7:0] bd[0:63];reg [63:0] bv=0;
 reg [2:0] mode=0;integer cycle=0,i,j,cid=0,n=0,fd,wfa,wfb;
 integer start_a=0,start_b=0;
 wire [31:0] accepted,rejected,sent,delivered,duplicates,integrity,dropa,dropb,parsea,parseb;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),.rx_sop(rx_sop),.rx_eop(rx_eop),.initialized(initialized),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(aer),.gmii_b_tx_er(ber),
  .gmii_a_rxd(a),.gmii_a_rx_dv(ae&&mode!=2),.gmii_a_rx_er(mode==3),
  .gmii_b_rxd(bd[63]),.gmii_b_rx_dv(bv[63]&&mode!=1),.gmii_b_rx_er(1'b0),.status_select(4'd0),.status_data(),.time_synchronized());
 assign accepted=dut.app_accepted;assign rejected=dut.app_rejected;assign sent=dut.app_sent;
 assign delivered=dut.rx_delivered;assign duplicates=dut.rx_duplicates;assign integrity=dut.rx_integrity_errors;
 assign dropa=dut.mac_a_dropped;assign dropb=dut.mac_b_dropped;
 assign parsea=dut.parser_a_rejected;assign parseb=dut.parser_b_rejected;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)bv<=0;else bv<={bv[62:0],be};
  bd[0]<=b;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  // Randomized deterministic backpressure, including gaps within payload.
  rx_ready<=cycle%19!=0&&cycle%19!=1;
  if(!reset&&rx_valid&&rx_ready)begin
   $fwrite(fd,"%0d,%0d,%0d,%0d,%0d\n",cycle,rx_sop,rx_eop,rx_data,mode);
   if(rx_eop)n<=n+1;
  end
  if(aer||ber)$fatal(1,"unexpected TX error");
  if(ae)$fwrite(wfa,"%0d,%02x\n",cycle,a);
  if(be)$fwrite(wfb,"%0d,%02x\n",cycle,b);
 end
 function [7:0] pattern(input integer id,input integer pos);
  pattern=(id*13+pos*37+(pos>>2)+53)&255;
 endfunction
 task offer(input integer vl,input integer length,input integer id);
  begin
   @(negedge clk);while(!tx_ready)@(negedge clk);
   $fwrite(inputs,"%0d,%0d,%0d,%0d\n",id,vl,length,cycle);
   tx_valid=1;tx_data=vl>>8;@(negedge clk);tx_data=vl;
   for(integer p=0;p<length;p=p+1)begin @(negedge clk);tx_data=pattern(id,p);end
   @(negedge clk);tx_valid=0;tx_data=0;
  end
 endtask
 integer inputs;
 task settle(input integer wanted);
  integer deadline;
  begin
   deadline=cycle+1000000;
   while(n<wanted&&cycle<deadline)@(negedge clk);
   if(n!=wanted)$fatal(1,"application loss got=%0d wanted=%0d sent=%0d reject=%0d integrity=%0d drop=%0d/%0d parser=%0d/%0d",n,wanted,sent,rejected,integrity,dropa,dropb,parsea,parseb);
   repeat(5000)@(negedge clk);
   if(n!=wanted)$fatal(1,"duplicate application delivery");
  end
 endtask
 integer lengths[0:3];integer target,begin_cycle;
 initial begin
  fd=$fopen("application.csv","w");$fwrite(fd,"cycle,sop,eop,data,mode\n");
  inputs=$fopen("inputs.csv","w");$fwrite(inputs,"id,vl,length,cycle\n");
  wfa=$fopen("wire_a.csv","w");wfb=$fopen("wire_b.csv","w");
  $fwrite(wfa,"cycle,data\n");$fwrite(wfb,"cycle,data\n");
  lengths[0]=1;lengths[1]=64;lengths[2]=512;lengths[3]=1471;
  repeat(8)@(negedge clk);reset=0;wait(initialized);
  for(i=0;i<128;i=i+1)begin offer('h1234+i,lengths[i%4],cid);cid=cid+1;end
  settle(cid);
  // One network at a time, including rejoining a network whose PSN is stale.
  mode=1;repeat(125000)@(negedge clk);
  for(i=0;i<16;i=i+1)begin offer('h1234+i,64,cid);cid=cid+1;end
  settle(cid);mode=2;repeat(125000)@(negedge clk);
  for(i=0;i<16;i=i+1)begin offer('h1234+i,512,cid);cid=cid+1;end
  settle(cid);mode=3;repeat(125000)@(negedge clk);
  for(i=0;i<16;i=i+1)begin offer('h1234+i,64,cid);cid=cid+1;end
  settle(cid);mode=0;repeat(125000)@(negedge clk);
  begin_cycle=cycle;
  for(i=0;i<512;i=i+1)begin
   while(cycle<begin_cycle+i*8000)@(negedge clk);
   offer('h1234+(i%16),1471,cid);cid=cid+1;
  end
  settle(cid);
  // Illegal TX VL, empty payload, truncated VLID and oversize burst are atomic rejects.
  offer('h1234+128,64,cid);offer('h1234,0,cid);offer('h1234,1472,cid);
  @(negedge clk);tx_valid=1;tx_data=8'h12;@(negedge clk);tx_valid=0;
  repeat(1000)@(negedge clk);
  // The one automatic SNTP request loops back with the ES source identity;
  // it is correctly rejected by both peer receive profiles, not app-delivered.
  if(rejected!=4||accepted!=cid||sent!=cid||delivered!=cid||dropa<16||parsea!=1||parseb!=1)
   $fatal(1,"final counters accepted=%0d sent=%0d delivered=%0d rejected=%0d dropa=%0d",accepted,sent,delivered,rejected,dropa);
  $display("COMPETITION_PASS messages=%0d duplicates=%0d rejected=%0d integrity=%0d",cid,duplicates,rejected,integrity);
  $fclose(fd);$fclose(inputs);$fclose(wfa);$fclose(wfb);$finish;
 end
 initial begin #100000000;$fatal(1,"watchdog");end
endmodule
