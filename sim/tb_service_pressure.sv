`timescale 1ns/1ps
// Test-only frame-serialized link: peer control traffic and returned business
// frames never collide. No force or DUT hierarchy is used; valid/ready are pins.
module tb_service_pressure;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] tx_data=0;reg tx_valid=0;wire tx_ready;
 wire [7:0] rx_data,a,b;wire rv,rs,re,init,ae,be,ts;
 reg [3:0] status_select=0;wire [31:0] status_data;
 reg manual_claim=0,manual_valid=0;reg [7:0] manual_data=0;
 reg echo_active=0;integer qhead=0,qtail=0,echo_index=0;
 reg [7:0] echo_ram[0:127][0:2047],capture[0:2047];integer echo_lengths[0:127];
 wire [7:0] net_data=manual_valid?manual_data:echo_ram[qhead%128][echo_index];
 wire net_valid=manual_valid||echo_active;
 reg [7:0] bd[0:63];reg [63:0] bv=0;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .rx_data(rx_data),.rx_valid(rv),.rx_ready(1'b1),.rx_sop(rs),.rx_eop(re),.initialized(init),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(),.gmii_b_tx_er(),
  .gmii_a_rxd(net_data),.gmii_b_rxd(bd[63]),.gmii_a_rx_dv(net_valid),.gmii_b_rx_dv(bv[63]),
  .gmii_a_rx_er(1'b0),.gmii_b_rx_er(1'b0),
  .status_select(status_select),.status_data(status_data),.time_synchronized(ts));
 `include "golden/constants.vh"
 reg [7:0] fixtures[0:FIXTURE_BYTES-1];
 integer cycle=0,frames=0,size=0,start=0,got=0,fd,ef,af,inf,pf;
 reg prev=0;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)bv<=0;else bv<={bv[62:0],net_valid};
  bd[0]<=net_data;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  if(ae)begin
   if(!prev)begin start=cycle;size=0;end
   capture[size]=a;size=size+1;$fwrite(fd,"%02x\n",a);
  end
  if(prev&&!ae)begin
   $fwrite(ef,"%0d,%0d,%0d\n",start,cycle-1,size);frames=frames+1;
   if({capture[12],capture[13]}<16'h12b4)begin
    if(qtail-qhead>=128)$fatal(1,"test link FIFO overflow");
    for(integer d=0;d<size;d=d+1)echo_ram[qtail%128][d]=capture[d];
    echo_lengths[qtail%128]=size;qtail=qtail+1;
   end
  end
  prev=ae;
  if(a!==b||ae!==be)$fatal(1,"A/B TX differ");
  if(rv)begin
   $fwrite(af,"%0d,%0d,%0d,%0d\n",cycle,rs,re,rx_data);
   if(re)got<=got+1;
  end
  if(!reset&&cycle%8192==0)begin
   $display("SERVICE_PROGRESS cycle=%0d app=%0d frames=%0d",cycle,got,frames);
   $fwrite(pf,"%0d,%0d,%0d\n",cycle,got,frames);$fflush(pf);
  end
 end
 always @(negedge clk)begin
  if(reset)begin echo_active=0;echo_index=0;qhead=0;end
  else if(echo_active)begin
   if(echo_index+1==echo_lengths[qhead%128])begin echo_active=0;echo_index=0;qhead=qhead+1;end
   else echo_index=echo_index+1;
  end else if(!manual_claim&&qhead<qtail)begin echo_active=1;echo_index=0;end
 end
 task idle(input integer count);repeat(count)@(negedge clk);endtask
 task send_peer(input integer offset,input integer length);
  begin
   @(negedge clk);manual_claim=1;while(echo_active)@(negedge clk);
   for(integer p=0;p<length;p=p+1)begin manual_valid=1;manual_data=fixtures[offset+p];@(negedge clk);end
   manual_valid=0;idle(128);manual_claim=0;
  end
 endtask
 function [7:0] pattern(input integer id,input integer p);
  pattern=(id*13+p*37+(p>>2)+53)&255;
 endfunction
 task offer(input integer id);
  integer vl;
  begin
   @(negedge clk);while(!tx_ready)@(negedge clk);vl='h1234+id%16;
   $fwrite(inf,"%0d,%0d,%0d,%0d\n",id,vl,1471,cycle);
   tx_valid=1;tx_data=vl>>8;@(negedge clk);tx_data=vl;
   for(integer p=0;p<1471;p=p+1)begin @(negedge clk);tx_data=pattern(id,p);end
   @(negedge clk);tx_valid=0;
  end
 endtask
 task check_status(input integer selection,input integer wanted);
  begin status_select=selection;@(negedge clk);if(status_data!==wanted)$fatal(1,"status %0d got %0d expected %0d",selection,status_data,wanted);end
 endtask
 integer begin_load,deadline;
 initial begin
  fd=$fopen("wire.mem","w");ef=$fopen("wire_events.csv","w");af=$fopen("application.csv","w");
  inf=$fopen("inputs.csv","w");pf=$fopen("progress.csv","w");
  $fwrite(ef,"start,end,bytes\n");$fwrite(af,"cycle,sop,eop,data\n");
  $fwrite(inf,"id,vl,length,cycle\n");$fwrite(pf,"cycle,app,frames\n");
  $readmemh("golden/fixtures.mem",fixtures);
  idle(8);reset=0;wait(init);wait(frames==1);
  send_peer(TIME_OFFSET,TIME_LENGTH);idle(1000);
  send_peer(BADCRC_OFFSET,BADCRC_LENGTH);send_peer(BADIP_OFFSET,BADIP_LENGTH);send_peer(BADUDP_OFFSET,BADUDP_LENGTH);
  send_peer(SET_OFFSET,SET_LENGTH);idle(256);send_peer(GET_OFFSET,GET_LENGTH);
  begin_load=cycle;
  for(integer id=0;id<BUSINESS_FRAMES;id=id+1)begin
   while(cycle<begin_load+id*8100)@(negedge clk);offer(id);
  end
  deadline=cycle+300000;
  while((got!=BUSINESS_FRAMES||frames!=BUSINESS_FRAMES+3)&&cycle<deadline)@(negedge clk);
  if(got!=BUSINESS_FRAMES||frames!=BUSINESS_FRAMES+3)$fatal(1,"lost app/service data app=%0d frames=%0d",got,frames);
  idle(1000);if(!ts)$fatal(1,"time sync failed");
  check_status(0,BUSINESS_FRAMES);check_status(1,0);check_status(2,BUSINESS_FRAMES);check_status(3,BUSINESS_FRAMES);
  check_status(4,BUSINESS_FRAMES);check_status(10,2);check_status(11,2);check_status(12,0);
  check_status(6,1);check_status(7,1);
  $display("SERVICE_PRESSURE_PASS app=%0d frames=%0d",got,frames);
  $fclose(fd);$fclose(ef);$fclose(af);$fclose(inf);$fclose(pf);$finish;
 end
 initial begin #5000000;$fatal(1,"service pressure watchdog");end
endmodule
