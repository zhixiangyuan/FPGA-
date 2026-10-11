// Approved single-VL profile, 2026-10-11. Input is an entire validated
// candidate already retained in a parser bank. No further payload storage
// is needed: the bank stays owned until PASS delivery or DROP draining ends.
module afdx_single_vl_sn_gate(
 input wire clk,reset,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,
 input wire [15:0] in_vlid,input wire [7:0] in_sn,
 output wire [7:0] app_data,output wire app_valid,input wire app_ready,
 output wire app_sop,app_eop,output wire [10:0] app_length,
 output wire [15:0] app_vlid,output wire [7:0] app_sn,
 output reg psn_valid,output reg [7:0] psn,
 output reg accepted,rejected,reset_control,delivered,
 output reg [31:0] accepted_count,rejected_count,control_count,
 output reg [31:0] missing_count,delivered_count
);
 localparam IDLE=0,PASS=1,DRAIN=2;
 reg [1:0] state;
 function [7:0] next_sn;input [7:0] s;
 begin next_sn=(s==255 || s==0)?8'd1:s+8'd1;end endfunction
 function [31:0] inc;input [31:0] v;
 begin inc=v==32'hffffffff ? v : v+32'd1;end endfunction
 wire plus_one=in_sn==next_sn(psn);
 wire plus_two=in_sn==next_sn(next_sn(psn));
 assign in_ready=!reset && (state==DRAIN || (state==PASS && app_ready));
 assign app_valid=!reset && state==PASS && in_valid;
 assign app_data=app_valid?in_data:8'd0;
 assign app_sop=app_valid&&in_sop;
 assign app_eop=app_valid&&in_eop;
 assign app_length=app_valid?in_length:11'd0;
 assign app_vlid=app_valid?in_vlid:16'd0;
 assign app_sn=app_valid?in_sn:8'd0;
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;psn_valid<=0;psn<=0;
   accepted<=0;rejected<=0;reset_control<=0;delivered<=0;
   accepted_count<=0;rejected_count<=0;control_count<=0;
   missing_count<=0;delivered_count<=0;
  end else begin
   accepted<=0;rejected<=0;reset_control<=0;delivered<=0;
   if(state==IDLE && in_valid)begin
    psn_valid<=1;psn<=in_sn;
    if(in_sn==0)begin
     state<=DRAIN;reset_control<=1;control_count<=inc(control_count);
    end else if(!psn_valid || plus_one || plus_two)begin
     state<=PASS;accepted<=1;accepted_count<=inc(accepted_count);
     if(psn_valid && plus_two)missing_count<=inc(missing_count);
    end else begin
     state<=DRAIN;rejected<=1;rejected_count<=inc(rejected_count);
    end
   end
   if(in_valid && in_ready && in_eop)begin
    state<=IDLE;
    if(state==PASS)begin delivered<=1;delivered_count<=inc(delivered_count);end
   end
  end
 end
endmodule
