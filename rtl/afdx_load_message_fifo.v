// One complete load-service datagram, synchronous RAM, bounded at 516 bytes.
// An invalid/oversized packet is drained without exposing a descriptor.
module afdx_load_message_fifo(
 input wire clk,reset,input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,input wire [15:0] in_vlid,in_src_port,in_dst_port,
 output wire msg_valid,input wire msg_ready,output wire [10:0] msg_length,
 output reg [15:0] msg_vlid,msg_src_port,msg_dst_port,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,output wire out_last,
 output reg [31:0] captured_count,overflow_count,sent_count
);
 localparam [1:0] IDLE=0,CAPTURE=1,DESCR=2,STREAM=3;
 reg [1:0] state;
 reg [7:0] memory[0:1023];reg [7:0] q;
 reg [10:0] count,length;
 reg [9:0] read_index;
 reg bad;
 wire in_fire=in_valid&&in_ready;
 wire metadata_bad=in_sop||in_length!=length||in_vlid!=msg_vlid||in_src_port!=msg_src_port||in_dst_port!=msg_dst_port;
 wire write_enable=in_fire&&(state==IDLE||count<1024);
 wire [9:0] write_address=state==IDLE?10'd0:count[9:0];
 wire read_enable=(state==DESCR&&msg_ready)||(state==STREAM&&out_ready&&!out_last);
 wire [9:0] read_address=state==DESCR?10'd0:read_index+1'b1;
 assign in_ready=!reset&&(state==IDLE||state==CAPTURE);
 assign msg_valid=!reset&&state==DESCR;
 assign msg_length=length;
 assign out_valid=!reset&&state==STREAM;
 assign out_data=q;
 assign out_last=out_valid&&{1'b0,read_index}+11'd1==length;
 always @(posedge clk)begin
  if(write_enable)memory[write_address]<=in_data;
  if(read_enable)q<=memory[read_address];
 end
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;count<=0;length<=0;read_index<=0;bad<=0;
   msg_vlid<=0;msg_src_port<=0;msg_dst_port<=0;captured_count<=0;overflow_count<=0;sent_count<=0;
  end else case(state)
   IDLE:if(in_fire)begin
    count<=1;length<=in_length;msg_vlid<=in_vlid;msg_src_port<=in_src_port;msg_dst_port<=in_dst_port;
    bad<=!in_sop||in_length==0||in_length>516;
    if(in_eop)begin
     if(!in_sop||in_length!=1)overflow_count<=overflow_count+1'b1;
     else begin state<=DESCR;captured_count<=captured_count+1'b1;end
    end else state<=CAPTURE;
   end
   CAPTURE:if(in_fire)begin
    if(metadata_bad||count>=516)bad<=1;
    if(count!=2047)count<=count+1'b1;
    if(in_eop)begin
     if(bad||metadata_bad||count>=516||count+1'b1!=length)begin state<=IDLE;overflow_count<=overflow_count+1'b1;end
     else begin state<=DESCR;captured_count<=captured_count+1'b1;end
    end
   end
   DESCR:if(msg_ready)begin read_index<=0;state<=STREAM;end
   STREAM:if(out_ready)begin
    if(out_last)begin state<=IDLE;sent_count<=sent_count+1'b1;end
    else read_index<=read_index+1'b1;
   end
  endcase
 end
endmodule
