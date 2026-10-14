// Development profile: 16 configured consecutive VL IDs by default.
// Input must be a complete validated packet retained in an upstream bank.
// This gate holds ownership of that bank until delivery or draining finishes.
module afdx_multi_vl_sn_gate #(
 parameter integer VL_COUNT=16,
 parameter [15:0] VL_BASE=16'h1234
)(
 input wire clk,reset,
 input wire [VL_COUNT-1:0] cfg_integrity_enable,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,
 input wire [15:0] in_vlid,input wire [7:0] in_sn,
 output wire [7:0] app_data,output wire app_valid,input wire app_ready,
 output wire app_sop,app_eop,output wire [10:0] app_length,
 output wire [15:0] app_vlid,output wire [7:0] app_sn,
 output reg accepted,rejected,reset_control,delivered,
 output reg [31:0] accepted_count,rejected_count,control_count,
 output reg [31:0] missing_count,delivered_count
);
 localparam IDLE=0,PASS=1,DRAIN=2;
 reg [1:0] state;
 reg [7:0] psn[0:VL_COUNT-1];
 reg [VL_COUNT-1:0] psn_valid;
 wire [16:0] index_wide={1'b0,in_vlid}-{1'b0,VL_BASE};
 wire configured=in_vlid>=VL_BASE && index_wide<VL_COUNT;
 // The safe index prevents an out-of-range read even for invalid metadata.
 wire [15:0] index=configured?index_wide[15:0]:16'd0;
 function [7:0] next_sn;input [7:0] s;
 begin next_sn=(s==255 || s==0)?8'd1:s+8'd1;end endfunction
 function [31:0] inc;input [31:0] v;
 begin inc=v==32'hffffffff ? v : v+32'd1;end endfunction
 wire plus_one=in_sn==next_sn(psn[index]);
 wire plus_two=in_sn==next_sn(next_sn(psn[index]));
 assign in_ready=!reset&&(state==DRAIN||(state==PASS&&app_ready));
 assign app_valid=!reset&&state==PASS&&in_valid;
 assign app_data=app_valid?in_data:8'd0;
 assign app_sop=app_valid&&in_sop;
 assign app_eop=app_valid&&in_eop;
 assign app_length=app_valid?in_length:11'd0;
 assign app_vlid=app_valid?in_vlid:16'd0;
 assign app_sn=app_valid?in_sn:8'd0;
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;psn_valid<=0;
   for(i=0;i<VL_COUNT;i=i+1)psn[i]<=0;
   accepted<=0;rejected<=0;reset_control<=0;delivered<=0;
   accepted_count<=0;rejected_count<=0;control_count<=0;
   missing_count<=0;delivered_count<=0;
  end else begin
   accepted<=0;rejected<=0;reset_control<=0;delivered<=0;
   if(state==IDLE&&in_valid)begin
    if(!configured||!in_sop||in_length==0||in_length>1471)begin
     state<=DRAIN;rejected<=1;rejected_count<=inc(rejected_count);
    end else begin
     psn_valid[index]<=1;psn[index]<=in_sn;
     if(in_sn==0)begin
      state<=DRAIN;reset_control<=1;control_count<=inc(control_count);
     end else if(!cfg_integrity_enable[index]||!psn_valid[index]||plus_one||plus_two)begin
      state<=PASS;accepted<=1;accepted_count<=inc(accepted_count);
      if(cfg_integrity_enable[index]&&psn_valid[index]&&plus_two)
       missing_count<=inc(missing_count);
     end else begin
      state<=DRAIN;rejected<=1;rejected_count<=inc(rejected_count);
     end
    end
   end
   if(in_valid&&in_ready&&in_eop)begin
    state<=IDLE;
    if(state==PASS)begin delivered<=1;delivered_count<=inc(delivered_count);end
   end
  end
 end
endmodule
