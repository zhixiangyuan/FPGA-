// Buffers one complete management message (sop..eop) and replays it as a
// descriptor-first message for the shared AFDX TX frame builder. Only one
// message is in flight, so a second request stalls the upstream bank owner
// until the first one has been transmitted.
module afdx_service_message_fifo #(
 parameter integer DEPTH=512,
 parameter integer MAX_LENGTH=484
)(
 input wire clk,reset,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [15:0] in_vlid,in_src_port,in_dst_port,
 output wire msg_valid,input wire msg_ready,output wire [10:0] msg_length,
 output reg [15:0] msg_vlid,msg_src_port,msg_dst_port,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,output wire out_last,
 output reg [31:0] captured_count,overflow_count,sent_count
);
 localparam IDLE=0,CAPTURE=1,DESCR=2,STREAM=3;
 reg [7:0] store[0:DEPTH-1];
 reg [1:0] state;
 reg [10:0] byte_count;
 reg [9:0] rd;
 reg [10:0] hold_length;
 reg [7:0] read_byte;
 reg bad;
 wire in_fire=in_valid&&in_ready;
 wire [9:0] next_rd=rd+1'b1;
 // Capture never back-pressures the shared MAC receive path: an oversized or
 // malformed message is counted as an overflow and discarded instead of holding
 // the bank owner hostage, which would stall the business VLs behind it.
 assign in_ready=!reset&&(state==IDLE||state==CAPTURE);
 assign msg_valid=!reset&&state==DESCR;
 assign msg_length=hold_length;
 assign out_valid=!reset&&state==STREAM;
 assign out_data=out_valid?read_byte:8'd0;
 assign out_last=out_valid&&(rd+1'b1==hold_length[9:0]);
 // RAM write port stays independent of reset and control logic.
 always @(posedge clk)begin
  if(state==IDLE&&in_fire)store[9'd0]<=in_data;
  else if(state==CAPTURE&&in_fire&&byte_count<DEPTH)store[byte_count[8:0]]<=in_data;
 end
 // Registered read port keeps the store inferable as RAM.
 always @(posedge clk)begin
  if(state==DESCR&&msg_valid&&msg_ready)read_byte<=store[9'd0];
  else if(state==STREAM&&out_valid&&out_ready&&!out_last)read_byte<=store[next_rd[8:0]];
 end
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;byte_count<=0;rd<=0;hold_length<=0;bad<=0;
   msg_vlid<=0;msg_src_port<=0;msg_dst_port<=0;
   captured_count<=0;overflow_count<=0;sent_count<=0;
  end else case(state)
   IDLE:if(in_fire)begin
    msg_vlid<=in_vlid;msg_src_port<=in_src_port;msg_dst_port<=in_dst_port;bad<=0;byte_count<=11'd1;
    if(in_eop)begin hold_length<=11'd1;captured_count<=captured_count+1'b1;state<=DESCR;end
    else state<=CAPTURE;
   end
   CAPTURE:if(in_fire)begin
    if(byte_count>=DEPTH)bad<=1;
    byte_count<=byte_count+1'b1;
    if(in_eop)begin
     if(bad||byte_count>=DEPTH||byte_count+1'b1>MAX_LENGTH)begin
      overflow_count<=overflow_count+1'b1;state<=IDLE;
     end else begin
      hold_length<=byte_count+1'b1;captured_count<=captured_count+1'b1;state<=DESCR;
     end
    end
   end
   DESCR:if(msg_valid&&msg_ready)begin rd<=0;state<=STREAM;end
   STREAM:if(out_valid&&out_ready)begin
    if(out_last)begin sent_count<=sent_count+1'b1;state<=IDLE;end
    else rd<=next_rd;
   end
   default:state<=IDLE;
  endcase
 end
endmodule
