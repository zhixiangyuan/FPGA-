`timescale 1ns/1ps
module tb_acceptance_management_short;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] peer_data=0;reg peer_valid=0;
 wire [7:0] a,b,app;wire ae,be,ready,app_valid,initialized,time_sync;
 reg [3:0] sel=4'd0;wire [31:0] status_data;
 reg [7:0] bd[0:63];reg [63:0] bv=0;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(8'd0),.tx_valid(1'b0),.tx_ready(ready),
  .rx_data(app),.rx_valid(app_valid),.rx_ready(1'b1),.rx_sop(),.rx_eop(),.initialized(initialized),
  .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(),.gmii_b_tx_er(),
  .gmii_a_rxd(peer_data),.gmii_b_rxd(bd[63]),.gmii_a_rx_dv(peer_valid),.gmii_b_rx_dv(bv[63]),
  .gmii_a_rx_er(1'b0),.gmii_b_rx_er(1'b0),.status_select(sel),.status_data(status_data),.time_synchronized(time_sync));
 `include "mgolden/constants.vh"
 reg [7:0] fixtures[0:RX_BYTES-1];integer cycle=0,frames=0,size=0,st=0,fd,ef,af;
 reg prev=0;integer starts[0:7];integer vls[0:7];integer lens[0:7];reg [7:0] frame[0:2047];
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(!reset&&cycle%16384==0)$display("MANAGEMENT_NETLIST_PROGRESS cycles=%0d frames=%0d sync=%0d",cycle,frames,time_sync);
  if(reset)bv<=0;else bv<={bv[62:0],peer_valid};
  bd[0]<=0;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
  if(ae)begin
   if(!prev)begin st=cycle;size=0;end
   frame[size]=a;size=size+1;$fwrite(fd,"%02x\n",a);
  end
  if(prev&&!ae)begin
   if(frames>=8)$fatal(1,"too many network TX frames");
   starts[frames]=st;lens[frames]=size;vls[frames]={frame[12],frame[13]};
   $fwrite(ef,"%0d,%0d,%0d,%0d\n",vls[frames],st,cycle-1,size);frames=frames+1;
  end
  prev=ae;
  if(app_valid)$fatal(1,"management leaked into application output");
  if(a!==b||ae!==be)$fatal(1,"A/B MAC TX mismatch");
 end
 task peer(input integer offset,input integer length);
  begin
   @(negedge clk);
   for(integer p=0;p<length;p=p+1)begin peer_valid=1;peer_data=fixtures[offset+p];@(negedge clk);end
   peer_valid=0;repeat(128)@(negedge clk);
  end
 endtask
 initial begin
  fd=$fopen("network_tx.mem","w");ef=$fopen("frames.csv","w");af=$fopen("application_rx.mem","w");
  $fwrite(ef,"vl,start,end,bytes\n");$readmemh("mgolden/fixtures.mem",fixtures);
  repeat(8)@(negedge clk);reset=0;wait(initialized);
  `include "mgolden/stimulus.vh"
  begin: first_deadline
   integer deadline; deadline=cycle+12000;
   while((frames<2||!time_sync)&&cycle<deadline)@(negedge clk);
  end
  repeat(200)@(negedge clk);
  if(!time_sync||frames!=2)$fatal(1,"SET/SNTP short scenario frames=%0d sync=%0d",frames,time_sync);
  sel=10;@(negedge clk);if(status_data!=1)$fatal(1,"SET requests=%0d",status_data);
  sel=11;@(negedge clk);if(status_data!=1)$fatal(1,"SET responses=%0d",status_data);
  sel=12;@(negedge clk);if(status_data!=0)$fatal(1,"service errors=%0d",status_data);
  sel=6;@(negedge clk);if(status_data!=1)$fatal(1,"FCS errors=%0d",status_data);
  sel=8;@(negedge clk);if(status_data<2)$fatal(1,"parser rejected=%0d",status_data);
  reset=1;peer_valid=0;repeat(8)@(negedge clk);reset=0;wait(initialized);
  peer(GET_OFFSET,GET_LENGTH);
  begin: second_deadline
   integer deadline;deadline=cycle+3000;
   while(frames<3&&cycle<deadline)@(negedge clk);
  end
  repeat(100)@(negedge clk);
  if(frames!=3)$fatal(1,"independent GET frames=%0d",frames);
  sel=10;@(negedge clk);if(status_data!=1)$fatal(1,"GET requests=%0d",status_data);
  sel=11;@(negedge clk);if(status_data!=1)$fatal(1,"GET responses=%0d",status_data);
  sel=12;@(negedge clk);if(status_data!=0)$fatal(1,"GET errors=%0d",status_data);
  $display("ACCEPTANCE_MANAGEMENT_SHORT_PASS SET GET independent_reset SNTP CRC IP UDP AB");
  $fclose(fd);$fclose(ef);$fclose(af);$finish;
 end
 initial begin #2000000;$fatal(1,"management netlist watchdog");end
endmodule
