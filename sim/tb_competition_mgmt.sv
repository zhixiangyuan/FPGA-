`timescale 1ns/1ps
module tb_competition_mgmt;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] net_data=0;reg net_valid=0;reg [1:0] mask=3;
 wire [7:0] a,b,app_rx;wire ae,be,ready,rv,init,ts;
 wire [31:0] requests,responses,errors;
 reg [7:0] bd[0:63];reg [63:0] bv=0;
 reg [7:0] app_tx=0;reg app_valid=0;reg loopback=0;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(app_tx),.tx_valid(app_valid),.tx_ready(ready),
  .rx_data(app_rx),.rx_valid(rv),.rx_ready(1'b1),.rx_sop(),.rx_eop(),.initialized(init),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(),.gmii_b_tx_er(),
  .gmii_a_rxd(loopback?a:net_data),.gmii_b_rxd(bd[63]),
  .gmii_a_rx_dv(loopback?ae:net_valid&&mask[0]),.gmii_b_rx_dv(bv[63]),.gmii_a_rx_er(1'b0),.gmii_b_rx_er(1'b0),
  .status_select(4'd0),.status_data(),.time_synchronized(ts));
 assign requests=dut.snmp_requests;assign responses=dut.snmp_responses;assign errors=dut.service_errors;
 `include "golden/constants.vh"
 reg [7:0] fixtures[0:RX_BYTES-1];integer cycle=0,frames=0,size=0,fd,ef,appfd;
 reg prev=0;integer start=0;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)bv<=0;else bv<={bv[62:0],loopback?be:net_valid&&mask[1]};
  bd[0]<=loopback?b:net_data;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  if(ae)begin
   if(!prev)begin start=cycle;size=0;end
   $fwrite(fd,"%02x\n",a);size=size+1;
  end
  if(prev&&!ae)begin $fwrite(ef,"%0d,%0d,%0d\n",start,cycle-1,size);frames=frames+1;end
  prev=ae;
  if(a!==b||ae!==be)$fatal(1,"management A/B fork differs");
  if(rv)$fwrite(appfd,"%02x\n",app_rx);
 end
 task idle(input integer n);repeat(n)@(negedge clk);endtask
 task send_frame(input integer offset,input integer length,input integer networks);
  begin
   @(negedge clk);mask=networks;
   for(integer p=0;p<length;p=p+1)begin net_valid=1;net_data=fixtures[offset+p];@(negedge clk);end
   net_valid=0;idle(128);
  end
 endtask
 task wait_frames(input integer wanted);
  integer deadline;
  begin
   deadline=cycle+300000;
   while(frames<wanted&&cycle<deadline)@(negedge clk);
   if(frames!=wanted)$fatal(1,"service wait wanted=%0d got=%0d requests=%0d responses=%0d errors=%0d",wanted,frames,requests,responses,errors);
  end
 endtask
 initial begin
  fd=$fopen("service_tx.mem","w");ef=$fopen("service_events.csv","w");appfd=$fopen("service_app.mem","w");
  $fwrite(ef,"start,end,bytes\n");$readmemh("golden/fixtures.mem",fixtures);
  idle(8);reset=0;wait(init);
  `include "golden/stimulus.vh"
  idle(3000);
  if(!ts||errors!=0)$fatal(1,"SNTP synchronization or service error");
  $display("COMPETITION_MGMT_PASS frames=%0d snmp_requests=%0d snmp_responses=%0d",frames,requests,responses);
  $fclose(fd);$fclose(ef);$fclose(appfd);$finish;
 end
 initial begin #40000000;$fatal(1,"management watchdog");end
endmodule
