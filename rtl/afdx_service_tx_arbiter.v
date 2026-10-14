// Shares the single AFDX TX message port between the business echo queue and
// one buffered management service source. Business and management messages
// alternate, so a busy service cannot starve the business VLs and a busy echo
// path still leaves service slots. A new descriptor is only issued after the
// previous frame completed, because the frame builder owns the wire until then.
module afdx_service_tx_arbiter(
 input wire clk,reset,
 input wire [10:0] biz_msg_length,
 input wire [15:0] biz_msg_vlid,biz_msg_src_port,biz_msg_dst_port,
 input wire biz_msg_valid,output wire biz_msg_ready,
 input wire [7:0] biz_payload_data,input wire biz_payload_valid,output wire biz_payload_ready,input wire biz_payload_last,
 input wire [10:0] svc_msg_length,
 input wire [15:0] svc_msg_src_port,svc_msg_dst_port,
 input wire svc_msg_valid,output wire svc_msg_ready,
 input wire [7:0] svc_payload_data,input wire svc_payload_valid,output wire svc_payload_ready,input wire svc_payload_last,
 input wire [15:0] svc_msg_vlid,
 input wire tx_msg_done,tx_msg_error,
 output wire tx_msg_valid,input wire tx_msg_ready,
 output wire [10:0] tx_msg_length,
 output wire [15:0] tx_msg_vlid,tx_msg_src_port,tx_msg_dst_port,
 output wire [7:0] tx_payload_data,output wire tx_payload_valid,input wire tx_payload_ready,output wire tx_payload_last,
 output wire service_active,
 output reg [31:0] service_sent_count,service_error_count
);
 localparam SEL_IDLE=0,SEL_DESCR=1,SEL_STREAM=2,SEL_DONE=3;
 reg [1:0] state;
 reg selected;
 reg last_service;
 // Descriptor and payload selection stay combinational: the frame builder
 // samples the message fields on the same cycle it accepts the descriptor.
 assign service_active=selected&&state!=SEL_IDLE;
 assign tx_msg_valid=!reset&&state==SEL_DESCR;
 assign tx_msg_length=selected?svc_msg_length:biz_msg_length;
 assign tx_msg_vlid=selected?svc_msg_vlid:biz_msg_vlid;
 assign tx_msg_src_port=selected?svc_msg_src_port:biz_msg_src_port;
 assign tx_msg_dst_port=selected?svc_msg_dst_port:biz_msg_dst_port;
 assign biz_msg_ready=!reset&&state==SEL_DESCR&&!selected&&tx_msg_ready;
 assign svc_msg_ready=!reset&&state==SEL_DESCR&&selected&&tx_msg_ready;
 assign tx_payload_valid=!reset&&state==SEL_STREAM&&(selected?svc_payload_valid:biz_payload_valid);
 assign tx_payload_data=selected?svc_payload_data:biz_payload_data;
 assign tx_payload_last=selected?svc_payload_last:biz_payload_last;
 assign biz_payload_ready=!reset&&state==SEL_STREAM&&!selected&&tx_payload_ready;
 assign svc_payload_ready=!reset&&state==SEL_STREAM&&selected&&tx_payload_ready;
 always @(posedge clk)begin
  if(reset)begin
   state<=SEL_IDLE;selected<=0;last_service<=0;
   service_sent_count<=0;service_error_count<=0;
  end else case(state)
   SEL_IDLE:begin
    if(!last_service)begin
     if(svc_msg_valid)begin selected<=1;state<=SEL_DESCR;end
     else if(biz_msg_valid)begin selected<=0;state<=SEL_DESCR;end
    end else begin
     if(biz_msg_valid)begin selected<=0;state<=SEL_DESCR;end
     else if(svc_msg_valid)begin selected<=1;state<=SEL_DESCR;end
    end
   end
   SEL_DESCR:if(tx_msg_valid&&tx_msg_ready)begin last_service<=selected;state<=SEL_STREAM;end
   SEL_STREAM:if(tx_payload_valid&&tx_payload_ready&&tx_payload_last)state<=SEL_DONE;
   SEL_DONE:if(tx_msg_done||tx_msg_error)begin
    if(selected)begin
     if(tx_msg_error)service_error_count<=service_error_count+1'b1;
     else service_sent_count<=service_sent_count+1'b1;
    end
    state<=SEL_IDLE;
   end
   default:state<=SEL_IDLE;
  endcase
 end
endmodule
