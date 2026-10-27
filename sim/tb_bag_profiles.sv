`timescale 1ns/1ps
module tb_bag_profiles;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,mv=0,pv=0;reg [7:0] pd=0;reg [31:0] bag=125000;
 wire mr,pr,done,error;wire [3:0] code;
 wire [7:0] md,gd;wire mvalid,mready,ms,me,ma,mt_done,reject,ge,ger;wire [15:0] ml;
 afdx_multi_vl_tx #(.VL_COUNT(1)) sender(.clk(clk),.reset(reset),.msg_valid(mv),.msg_ready(mr),.msg_payload_length(11'd1),
  .msg_da_const(32'h03000000),.msg_vlid(16'h1234),.msg_src_mac(48'h020000000009),
  .msg_src_ip(32'h0a000001),.msg_dst_ip(32'he0e0003c),.msg_src_port(16'd24),.msg_dst_port(16'd23),.msg_ttl(8'd1),
  .msg_bag_cycles(bag),.msg_jitter_cycles(bag/10),.payload_data(pd),.payload_valid(pv),.payload_ready(pr),
  .payload_last(1'b1),.payload_abort(1'b0),.mac_tx_data(md),.mac_tx_valid(mvalid),.mac_tx_ready(mready),
  .mac_tx_sop(ms),.mac_tx_eop(me),.mac_tx_length(ml),.mac_tx_afdx(ma),.mac_tx_done(mt_done),.mac_tx_reject(reject),
  .gmii_tx_en(ge),.msg_done(done),.msg_error(error),.error_code(code),.late_count());
 mac_gmii_tx mac(.clk(clk),.reset(reset),.client_data(md),.client_valid(mvalid),.client_ready(mready),
  .client_sop(ms),.client_eop(me),.client_length(ml),.client_afdx_prepared(ma),
  .gmii_txd(gd),.gmii_tx_en(ge),.gmii_tx_er(ger),.done(mt_done),.reject(reject),
  .sent_frames(),.rejected_frames(),.counter_saturated());
 integer cycle=0,profile=0,frames=0,start=0,size=0,fd,ef;reg prev=0;
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(ge)begin if(!prev)begin start=cycle;size=0;end $fwrite(fd,"%02x\n",gd);size=size+1;end
  if(prev&&!ge)begin $fwrite(ef,"%0d,%0d,%0d,%0d,%0d\n",profile,bag,start,cycle-1,size);frames=frames+1;end
  prev=ge;if(reject||ger)$fatal(1,"unexpected MAC error");
 end
 task send(input integer id);
  begin
   @(negedge clk);mv=1;do @(posedge clk);while(!mr);
   @(negedge clk);mv=0;pv=1;pd=(53+id*13)&255;
   do @(posedge clk);while(!pr);
   @(negedge clk);pv=0;wait(done);@(negedge clk);
  end
 endtask
 task invalid_bag(input integer value);
  begin
   @(negedge clk);bag=value;mv=1;@(posedge clk);#1;
   if(!error||code!=5)$fatal(1,"invalid BAG accepted %0d",value);
   @(negedge clk);mv=0;repeat(10)@(negedge clk);
  end
 endtask
 initial begin
  fd=$fopen("wire.mem","w");ef=$fopen("events.csv","w");$fwrite(ef,"profile,bag,start,end,bytes\n");
  for(profile=0;profile<8;profile=profile+1)begin
   reset=1;repeat(4)@(negedge clk);bag=125000<<profile;reset=0;
   send(profile*2);send(profile*2+1);repeat(20)@(negedge clk);
   $display("BAG_PROFILE_PASS ms=%0d",1<<profile);
  end
  invalid_bag(0);invalid_bag(375000);
  if(frames!=16)$fatal(1,"frame count");
  $display("BAG_PROFILES_PASS frames=%0d",frames);$fclose(fd);$fclose(ef);$finish;
 end
 initial begin #600000000;$fatal(1,"BAG watchdog");end
endmodule
