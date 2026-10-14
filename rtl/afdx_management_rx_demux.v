// Routes validated management-VL payloads to the management service endpoints
// by UDP destination port. Frames for any other port are drained and counted so
// an unexpected management port cannot stall the upstream bank owner.
module afdx_management_rx_demux #(
 parameter [15:0] SNMP_PORT=16'd161
)(
 input wire clk,reset,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,
 input wire [15:0] in_src_port,in_dst_port,
 output wire [7:0] snmp_data,output wire snmp_valid,input wire snmp_ready,
 output wire snmp_sop,snmp_eop,output wire [10:0] snmp_length,output wire [15:0] snmp_src_port,
 output reg [31:0] routed_count,dropped_count,
 output reg [15:0] last_dropped_port
);
 localparam ROUTE_NONE=0,ROUTE_SNMP=1,ROUTE_DRAIN=2;
 reg [1:0] route;
 wire select_snmp=route==ROUTE_SNMP;
 assign in_ready=!reset&&(select_snmp?snmp_ready:route==ROUTE_DRAIN);
 assign snmp_valid=!reset&&select_snmp&&in_valid;
 assign snmp_data=snmp_valid?in_data:8'd0;
 assign snmp_sop=snmp_valid&&in_sop;
 assign snmp_eop=snmp_valid&&in_eop;
 assign snmp_length=snmp_valid?in_length:11'd0;
 assign snmp_src_port=in_src_port;
 always @(posedge clk)begin
  if(reset)begin
   route<=ROUTE_NONE;routed_count<=0;dropped_count<=0;last_dropped_port<=0;
  end else if(route==ROUTE_NONE)begin
   if(in_valid)begin
    if(in_dst_port==SNMP_PORT)route<=ROUTE_SNMP;
    else begin
     route<=ROUTE_DRAIN;last_dropped_port<=in_dst_port;
     dropped_count<=dropped_count+1'b1;
    end
   end
  end else if(in_valid&&in_ready&&in_eop)begin
   route<=ROUTE_NONE;
   if(select_snmp)routed_count<=routed_count+1'b1;
  end
 end
endmodule
