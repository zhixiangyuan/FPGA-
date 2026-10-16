// Production arbiter: business plus SNMP, SNTP and the load-service VL.
module afdx_service_tx_arbiter_615a(
 input wire clk,reset,
 input wire gmii_tx_valid,input wire [31:0] cfg_load_bag_cycles,
 input wire [10:0] biz_msg_length,
 input wire [15:0] biz_msg_vlid,biz_msg_src_port,biz_msg_dst_port,
 input wire biz_msg_valid,output wire biz_msg_ready,
 input wire [7:0] biz_payload_data,input wire biz_payload_valid,output wire biz_payload_ready,input wire biz_payload_last,
 input wire [10:0] snmp_msg_length,
 input wire [15:0] snmp_msg_vlid,snmp_msg_src_port,snmp_msg_dst_port,
 input wire snmp_msg_valid,output wire snmp_msg_ready,
 input wire [7:0] snmp_payload_data,input wire snmp_payload_valid,output wire snmp_payload_ready,input wire snmp_payload_last,
 input wire [10:0] sntp_msg_length,
 input wire [15:0] sntp_msg_vlid,sntp_msg_src_port,sntp_msg_dst_port,
 input wire sntp_msg_valid,output wire sntp_msg_ready,
 input wire [7:0] sntp_payload_data,input wire sntp_payload_valid,output wire sntp_payload_ready,input wire sntp_payload_last,
 input wire [10:0] load_msg_length,
 input wire [15:0] load_msg_vlid,load_msg_src_port,load_msg_dst_port,
 input wire load_msg_valid,output wire load_msg_ready,
 input wire [7:0] load_payload_data,input wire load_payload_valid,output wire load_payload_ready,input wire load_payload_last,
 input wire tx_msg_done,tx_msg_error,
 output wire tx_msg_valid,input wire tx_msg_ready,
 output wire [10:0] tx_msg_length,
 output wire [15:0] tx_msg_vlid,tx_msg_src_port,tx_msg_dst_port,
 output wire [7:0] tx_payload_data,output wire tx_payload_valid,input wire tx_payload_ready,output wire tx_payload_last,
 output wire service_active,
 output reg [31:0] service_sent_count,service_error_count,
 output reg [31:0] snmp_sent_count,sntp_sent_count,load_sent_count
);
 localparam SEL_IDLE=0,SEL_DESCR=1,SEL_STREAM=2,SEL_DONE=3;
 localparam SRC_BIZ=0,SRC_SNMP=1,SRC_SNTP=2,SRC_LOAD=3;
 reg [1:0] state;
 reg [1:0] selected;
 reg last_service;
 reg [1:0] last_svc_src;
 reg wire_valid_d,load_started;
 reg [31:0] load_age;
 // Do not reserve the shared frame builder while this VL still owes its BAG.
 // The builder independently checks BAG again; this only schedules eligibility.
 wire load_pending=load_msg_valid&&(!load_started||load_age>=cfg_load_bag_cycles);
 always @(posedge clk)begin
  if(reset)begin wire_valid_d<=0;load_started<=0;load_age<=0;end
  else begin
   wire_valid_d<=gmii_tx_valid;
   if(gmii_tx_valid&&!wire_valid_d&&state!=SEL_IDLE&&selected==SRC_LOAD)begin
    load_started<=1;load_age<=0;
   end else if(load_started&&load_age<cfg_load_bag_cycles)load_age<=load_age+1'b1;
  end
 end
 wire service_any=snmp_msg_valid||sntp_msg_valid||load_pending;
 // Rotate all three services; business still alternates with the service class.
 wire [1:0] svc_pick=last_svc_src==SRC_SNMP?
  (sntp_msg_valid?SRC_SNTP:load_pending?SRC_LOAD:SRC_SNMP):
  last_svc_src==SRC_SNTP?(load_pending?SRC_LOAD:snmp_msg_valid?SRC_SNMP:SRC_SNTP):
  (snmp_msg_valid?SRC_SNMP:sntp_msg_valid?SRC_SNTP:SRC_LOAD);
 // Descriptor and payload selection stay combinational: the frame builder
 // samples the message fields on the same cycle it accepts the descriptor.
 assign service_active=selected!=SRC_BIZ&&state!=SEL_IDLE;
 assign tx_msg_valid=!reset&&state==SEL_DESCR;
 assign tx_msg_length=selected==SRC_SNMP?snmp_msg_length:selected==SRC_SNTP?sntp_msg_length:selected==SRC_LOAD?load_msg_length:biz_msg_length;
 assign tx_msg_vlid=selected==SRC_SNMP?snmp_msg_vlid:selected==SRC_SNTP?sntp_msg_vlid:selected==SRC_LOAD?load_msg_vlid:biz_msg_vlid;
 assign tx_msg_src_port=selected==SRC_SNMP?snmp_msg_src_port:selected==SRC_SNTP?sntp_msg_src_port:selected==SRC_LOAD?load_msg_src_port:biz_msg_src_port;
 assign tx_msg_dst_port=selected==SRC_SNMP?snmp_msg_dst_port:selected==SRC_SNTP?sntp_msg_dst_port:selected==SRC_LOAD?load_msg_dst_port:biz_msg_dst_port;
 assign biz_msg_ready=!reset&&state==SEL_DESCR&&selected==SRC_BIZ&&tx_msg_ready;
 assign snmp_msg_ready=!reset&&state==SEL_DESCR&&selected==SRC_SNMP&&tx_msg_ready;
 assign sntp_msg_ready=!reset&&state==SEL_DESCR&&selected==SRC_SNTP&&tx_msg_ready;
 assign load_msg_ready=!reset&&state==SEL_DESCR&&selected==SRC_LOAD&&tx_msg_ready;
 assign tx_payload_valid=!reset&&state==SEL_STREAM&&
  (selected==SRC_SNMP?snmp_payload_valid:selected==SRC_SNTP?sntp_payload_valid:selected==SRC_LOAD?load_payload_valid:biz_payload_valid);
 assign tx_payload_data=selected==SRC_SNMP?snmp_payload_data:selected==SRC_SNTP?sntp_payload_data:selected==SRC_LOAD?load_payload_data:biz_payload_data;
 assign tx_payload_last=selected==SRC_SNMP?snmp_payload_last:selected==SRC_SNTP?sntp_payload_last:selected==SRC_LOAD?load_payload_last:biz_payload_last;
 assign biz_payload_ready=!reset&&state==SEL_STREAM&&selected==SRC_BIZ&&tx_payload_ready;
 assign snmp_payload_ready=!reset&&state==SEL_STREAM&&selected==SRC_SNMP&&tx_payload_ready;
 assign sntp_payload_ready=!reset&&state==SEL_STREAM&&selected==SRC_SNTP&&tx_payload_ready;
 assign load_payload_ready=!reset&&state==SEL_STREAM&&selected==SRC_LOAD&&tx_payload_ready;
 always @(posedge clk)begin
  if(reset)begin
   state<=SEL_IDLE;selected<=SRC_BIZ;last_service<=0;last_svc_src<=SRC_SNMP;
   service_sent_count<=0;service_error_count<=0;snmp_sent_count<=0;sntp_sent_count<=0;load_sent_count<=0;
  end else case(state)
   SEL_IDLE:begin
    if(!last_service)begin
     if(service_any)begin selected<=svc_pick;state<=SEL_DESCR;end
     else if(biz_msg_valid)begin selected<=SRC_BIZ;state<=SEL_DESCR;end
    end else begin
     if(biz_msg_valid)begin selected<=SRC_BIZ;state<=SEL_DESCR;end
     else if(service_any)begin selected<=svc_pick;state<=SEL_DESCR;end
    end
   end
   SEL_DESCR:if(tx_msg_valid&&tx_msg_ready)begin
    last_service<=selected!=SRC_BIZ;
    if(selected!=SRC_BIZ)last_svc_src<=selected;
    state<=SEL_STREAM;
   end
   SEL_STREAM:if(tx_payload_valid&&tx_payload_ready&&tx_payload_last)state<=SEL_DONE;
   SEL_DONE:if(tx_msg_done||tx_msg_error)begin
    if(selected!=SRC_BIZ)begin
     if(tx_msg_error)service_error_count<=service_error_count+1'b1;
     else begin
      service_sent_count<=service_sent_count+1'b1;
      if(selected==SRC_SNMP)snmp_sent_count<=snmp_sent_count+1'b1;
      else if(selected==SRC_SNTP)sntp_sent_count<=sntp_sent_count+1'b1;
      else load_sent_count<=load_sent_count+1'b1;
     end
    end
    state<=SEL_IDLE;
   end
   default:state<=SEL_IDLE;
  endcase
 end
endmodule
