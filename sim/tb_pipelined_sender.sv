`timescale 1ns/1ps
module tb_pipelined_sender;
 reg clk=0;always #4 clk=~clk;reg reset=1;
 reg mv=0,pv=0,pl=0;reg [10:0] length=0;reg [15:0] vl=16'h1234;reg [7:0] data=0;
 reg direct_mode=1;
 wire mr,pr,md,me;wire [7:0] frame,tx;wire fv,fr,fs,fe,fa,en,er,done,reject,start;
 wire [15:0] flen,start_vl,end_vl;integer cycle=0,fd,ef,good=0,errors=0,onwire=0,size,first,frame_vl;reg previous=0;
 afdx_multi_vl_tx #(.VL_COUNT(2),.RESET_SN(254),.PIPELINED_MAC(1),.STREAMING_MAC(1)) sender(
  .clk(clk),.reset(reset),.msg_valid(mv),.msg_ready(mr),.msg_payload_length(length),
  .msg_da_const(32'h03000000),.msg_vlid(vl),.msg_src_mac(48'h020000000009),.msg_src_ip(32'h0a000001),
  .msg_dst_ip(32'he0e0003c),.msg_src_port(16'd24),.msg_dst_port(16'd23),.msg_ttl(8'd1),
  .msg_bag_cycles(32'd125000),.msg_jitter_cycles(32'd12500),
  .payload_data(data),.payload_valid(pv),.payload_ready(pr),.payload_last(pl),.payload_abort(1'b0),
  .mac_tx_data(frame),.mac_tx_valid(fv),.mac_tx_ready(fr),.mac_tx_sop(fs),.mac_tx_eop(fe),.mac_tx_length(flen),.mac_tx_afdx(fa),
  .mac_tx_done(done),.mac_tx_reject(reject),.gmii_tx_en(en),.gmii_vlid(start_vl),.msg_done(md),.msg_error(me),.error_code(),.late_count());
 afdx_mac_tx_stream mac(.clk(clk),.reset(reset),.client_data(frame),.client_valid(fv),.client_ready(fr),
  .client_direct(direct_mode),.client_vlid(vl),
  .client_sop(fs),.client_eop(fe),.client_length(flen),.client_afdx_prepared(fa),
  .gmii_txd(tx),.gmii_tx_en(en),.gmii_tx_er(er),.done(done),.reject(reject),
  .started_vlid(start_vl),.completed_vlid(end_vl));
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(md)good<=good+1;if(me)errors<=errors+1;if(done)onwire<=onwire+1;
  if(er)$fatal(1,"TX PHY error");
  if(en)begin if(!previous)begin first=cycle;size=0;frame_vl=start_vl;end size=size+1;$fwrite(fd,"%02x\n",tx);end
  if(previous&&!en)$fwrite(ef,"%0d,%0d,%0d,%0d\n",frame_vl,first,cycle-1,size);
  previous=en;
 end
 function [7:0] pattern(input integer id,input integer pos);pattern=(id*13+pos*37+(pos>>2)+53)&255;endfunction
 task message(input integer id,input [15:0] v,input integer n,input integer actual);
  begin
   @(negedge clk);mv=1;vl=v;length=n;@(posedge clk);while(!mr)@(posedge clk);
   @(negedge clk);mv=0;
   for(integer p=0;p<actual;p=p+1)begin
    @(negedge clk);pv=1;pl=p+1==actual;data=pattern(id,p);
    @(posedge clk);while(!pr)@(posedge clk);
   end
   @(negedge clk);pv=0;pl=0;
   while(!md&&!me)@(negedge clk);
   if((actual==n&&me)||(actual!=n&&md))$fatal(1,"wrong message result");
  end
 endtask
 initial begin
  fd=$fopen("wire.mem","w");ef=$fopen("events.csv","w");$fwrite(ef,"vl,start,end,bytes\n");
  repeat(8)@(negedge clk);reset=0;
  message(0,'h1234,64,64);message(1,'h1235,1471,1471);
  message(2,'h1234,1,1);message(3,'h1234,512,512);
  direct_mode=0;message(99,'h1234,10,3);direct_mode=1;
  message(4,'h1234,1,1);message(5,'h1234,1471,1471);
  while(onwire<6)@(negedge clk);repeat(100)@(negedge clk);
  if(good!=6||errors!=1)$fatal(1,"message counts good=%0d error=%0d",good,errors);
  $display("PIPELINED_SENDER_PASS wrap_254_255_1 errors=1 real_1ms_BAG");
  $fclose(fd);$fclose(ef);$finish;
 end
 initial begin #6000000;$fatal(1,"pipelined sender watchdog");end
endmodule
