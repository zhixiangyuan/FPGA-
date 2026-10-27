`timescale 1ns/1ps
module tb_rx_policing;
 reg clk=0,reset=1;
 reg [7:0] in_data=0;
 reg in_valid=0,in_sop=0,in_eop=0;
 reg [10:0] in_length=0;
 reg [15:0] in_vlid=16'h1234;
 reg [7:0] in_sn=0;
 reg app_ready=1;
 wire in_ready;
 wire [7:0] app_data;
 wire app_valid,app_sop,app_eop;
 wire [10:0] app_length;
 wire [15:0] app_vlid;
 wire [7:0] app_sn;
 wire accepted,rejected,reset_control,delivered;
 wire [31:0] accepted_count,rejected_count,control_count,missing_count,delivered_count;
 integer i;

 afdx_multi_vl_sn_gate #(
  .VL_COUNT(1),.VL_BASE(16'h1234),
  .POLICING_ENABLE(1),.MIN_BAG_CYCLES(100),.MAX_FRAME_BYTES(8)
 ) dut(.clk(clk),.reset(reset),.cfg_integrity_enable(1'b1),
  .in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),
  .in_sop(in_sop),.in_eop(in_eop),.in_length(in_length),
  .in_vlid(in_vlid),.in_sn(in_sn),
  .app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
  .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),
  .app_vlid(app_vlid),.app_sn(app_sn),
  .accepted(accepted),.rejected(rejected),.reset_control(reset_control),.delivered(delivered),
  .accepted_count(accepted_count),.rejected_count(rejected_count),.control_count(control_count),
  .missing_count(missing_count),.delivered_count(delivered_count));

 always #4 clk=~clk;

 task send_frame(input [15:0] vl,input [7:0] sn,input integer len);
  integer n;
  begin
   in_vlid=vl;in_sn=sn;in_length=len[10:0];
   for(n=0;n<len;n=n+1)begin
    in_data=n[7:0];in_sop=(n==0);in_eop=(n==len-1);in_valid=1;
    @(posedge clk);
    while(!in_ready)@(posedge clk);
   end
   in_valid=0;in_sop=0;in_eop=0;
   while(dut.state!=0)@(posedge clk);
   repeat(2)@(posedge clk);
  end
 endtask

 initial begin
  reset=1;repeat(4)@(posedge clk);reset=0;repeat(2)@(posedge clk);
  send_frame(16'h1234,8'd1,4);
  if(delivered_count!=1||accepted_count!=1)$fatal(1,"first frame not accepted");
  // The second frame violates the 100-cycle receive BAG and must not advance PSN.
  send_frame(16'h1234,8'd2,4);
  if(dut.bag_violations!=1||rejected_count!=1||delivered_count!=1)
   $fatal(1,"BAG violation not classified");
  repeat(101)@(posedge clk);
  send_frame(16'h1234,8'd2,4);
  if(delivered_count!=2||accepted_count!=2)$fatal(1,"post-BAG frame not accepted");
  repeat(101)@(posedge clk);
  send_frame(16'h1234,8'd3,9);
  if(dut.length_violations!=1||delivered_count!=2)$fatal(1,"oversize frame not rejected");
  $display("RX_POLICER_PASS bag=%0d length=%0d accepted=%0d delivered=%0d",
   dut.bag_violations,dut.length_violations,accepted_count,delivered_count);
  $finish;
 end

 initial begin #10000;$fatal(1,"policing test timeout");end
endmodule
