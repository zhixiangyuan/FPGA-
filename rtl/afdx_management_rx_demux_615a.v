// Load VL datagrams are unreliable by design: a busy endpoint causes a counted
// whole-datagram drop, allowing TFTP retry without blocking the shared MAC.
// Legacy SNMP/SNTP routes retain their existing byte-stream backpressure.
module afdx_management_rx_demux_615a #(
 parameter [15:0] SNMP_PORT=16'd161,SNTP_PORT=16'd123,LOAD_VLID=16'h1246
)(
 input wire clk,reset,input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,input wire [15:0] in_vlid,in_src_port,in_dst_port,
 output wire [7:0] snmp_data,output wire snmp_valid,input wire snmp_ready,
 output wire snmp_sop,snmp_eop,output wire [10:0] snmp_length,output wire [15:0] snmp_src_port,
 output wire [7:0] sntp_data,output wire sntp_valid,input wire sntp_ready,
 output wire sntp_sop,sntp_eop,output wire [10:0] sntp_length,output wire [15:0] sntp_src_port,sntp_dst_port,
 output wire [7:0] load_data,output wire load_valid,input wire load_ready,
 output wire load_sop,load_eop,output wire [10:0] load_length,output wire [15:0] load_src_port,load_dst_port,
 output reg [31:0] routed_count,sntp_routed_count,load_routed_count,dropped_count,load_dropped_count,
 output reg [15:0] last_dropped_port
);
 localparam [2:0] NONE=0,SNMP=1,SNTP=2,LOAD=3,DRAIN=4;
 reg [2:0] route;
 assign in_ready=!reset&&(route==SNMP?snmp_ready:route==SNTP?sntp_ready:route==LOAD||route==DRAIN);
 assign snmp_valid=!reset&&route==SNMP&&in_valid;
 assign sntp_valid=!reset&&route==SNTP&&in_valid;
 assign load_valid=!reset&&route==LOAD&&in_valid&&load_ready;
 assign snmp_data=in_data;assign sntp_data=in_data;assign load_data=in_data;
 assign snmp_sop=snmp_valid&&in_sop;assign snmp_eop=snmp_valid&&in_eop;
 assign sntp_sop=sntp_valid&&in_sop;assign sntp_eop=sntp_valid&&in_eop;
 assign load_sop=load_valid&&in_sop;assign load_eop=load_valid&&in_eop;
 assign snmp_length=in_length;assign sntp_length=in_length;assign load_length=in_length;
 assign snmp_src_port=in_src_port;assign sntp_src_port=in_src_port;assign sntp_dst_port=in_dst_port;
 assign load_src_port=in_src_port;assign load_dst_port=in_dst_port;
 always @(posedge clk)begin
  if(reset)begin
   route<=NONE;routed_count<=0;sntp_routed_count<=0;load_routed_count<=0;dropped_count<=0;load_dropped_count<=0;last_dropped_port<=0;
  end else if(route==NONE)begin
   if(in_valid)begin
    if(in_vlid==LOAD_VLID)begin
     if(load_ready)route<=LOAD;
     else begin route<=DRAIN;load_dropped_count<=load_dropped_count+1'b1;end
    end else if(in_dst_port==SNMP_PORT)route<=SNMP;
    else if(in_src_port==SNTP_PORT)route<=SNTP;
    else begin route<=DRAIN;last_dropped_port<=in_dst_port;dropped_count<=dropped_count+1'b1;end
   end
  end else if(in_valid&&in_ready)begin
   if(route==LOAD&&!load_ready)begin
    route<=DRAIN;load_dropped_count<=load_dropped_count+1'b1;
   end
   if(in_eop)begin
    route<=NONE;
    if(route==SNMP)routed_count<=routed_count+1'b1;
    else if(route==SNTP)sntp_routed_count<=sntp_routed_count+1'b1;
    else if(route==LOAD&&load_ready)load_routed_count<=load_routed_count+1'b1;
   end
  end
 end
endmodule
