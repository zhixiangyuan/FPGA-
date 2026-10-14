// RFC4330 unicast v4 profile, 48-byte packets, one outstanding request.
// Network adapter supplies actual RX GMII-start UTC as rx_timestamp.
// request_t1 is the request enqueue timestamp: TX queue delay must be measured
// by integration and included in the reported synchronization error bound.
module afdx_sntp_client #(
 parameter integer TIMEOUT_CYCLES=125000000,
 parameter [31:0] SERVER_IP=32'h0a000002,
 parameter [15:0] CLIENT_PORT=16'd49152,
 parameter [31:0] MAX_ROOT_DISTANCE=32'h00018000
)(
 input wire clk,reset,request_start,input wire [63:0] utc_time,
 output wire request_ready,
 output reg [7:0] tx_data,output wire tx_valid,input wire tx_ready,
 output wire tx_sop,tx_eop,output wire [10:0] tx_length,
 output wire [15:0] tx_src_port,tx_dst_port,
 input wire [7:0] rx_data,input wire rx_valid,output wire rx_ready,
 input wire rx_sop,rx_eop,input wire [10:0] rx_length,
 input wire [31:0] rx_src_ip,input wire [15:0] rx_src_port,rx_dst_port,
 input wire [63:0] rx_timestamp,
 output reg sync_valid,output reg [63:0] sync_t1,sync_t2,sync_t3,sync_t4,
 output reg response_accepted,response_rejected,timeout,
 output reg [31:0] accepted_count,rejected_count,timeout_count,
 output wire [63:0] request_timestamp
);
 reg sending,pending,receiving,checking,malformed;
 reg [5:0] tx_index,rx_index;
 reg [31:0] elapsed;
 reg [63:0] request_t1,receive_t4;
 reg [7:0] response[0:47];
 wire [63:0] origin={response[24],response[25],response[26],response[27],response[28],response[29],response[30],response[31]};
 wire [63:0] received_at={response[32],response[33],response[34],response[35],response[36],response[37],response[38],response[39]};
 wire [63:0] transmitted_at={response[40],response[41],response[42],response[43],response[44],response[45],response[46],response[47]};
 wire [31:0] root_delay={response[4],response[5],response[6],response[7]};
 wire [31:0] root_dispersion={response[8],response[9],response[10],response[11]};
 wire packet_legal=!malformed && response[0][7:6]!=3 && response[0][5:3]==4 && response[0][2:0]==4 &&
   response[1]>0 && response[1]<=15 && origin==request_t1 && received_at!=0 && transmitted_at!=0 &&
   !root_delay[31] && ({1'b0,root_delay}>>1)+{1'b0,root_dispersion}<={1'b0,MAX_ROOT_DISTANCE};
 assign request_ready=!reset&&!sending&&!pending&&!receiving&&!checking;
 assign request_timestamp=request_t1;
 assign tx_valid=!reset&&sending;
 assign tx_sop=tx_valid&&tx_index==0;
 assign tx_eop=tx_valid&&tx_index==47;
 assign tx_length=48;
 assign tx_src_port=CLIENT_PORT;assign tx_dst_port=123;
 assign rx_ready=!reset&&!checking;
 always @*begin
  tx_data=0;
  if(tx_index==0)tx_data=8'h23;
  else if(tx_index==2)tx_data=8'd6;
  else if(tx_index==3)tx_data=8'he8;
  else if(tx_index>=40)tx_data=request_t1>>(8*(47-tx_index));
 end
 function [31:0] inc;input [31:0] value;
 begin inc=value==32'hffffffff ? value : value+32'd1;end endfunction
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   sending<=0;pending<=0;receiving<=0;checking<=0;malformed<=0;
   tx_index<=0;rx_index<=0;elapsed<=0;request_t1<=0;receive_t4<=0;
   sync_valid<=0;sync_t1<=0;sync_t2<=0;sync_t3<=0;sync_t4<=0;
   response_accepted<=0;response_rejected<=0;timeout<=0;
   accepted_count<=0;rejected_count<=0;timeout_count<=0;
   for(i=0;i<48;i=i+1)response[i]<=0;
  end else begin
   sync_valid<=0;response_accepted<=0;response_rejected<=0;timeout<=0;
   if(request_start&&request_ready)begin
    sending<=1;tx_index<=0;request_t1<=utc_time;
   end
   if(tx_valid&&tx_ready)begin
    if(tx_eop)begin sending<=0;pending<=1;elapsed<=0;end
    else tx_index<=tx_index+1'b1;
   end
   if(pending)begin
    if(elapsed>=TIMEOUT_CYCLES-1)begin
     pending<=0;receiving<=0;timeout<=1;timeout_count<=inc(timeout_count);
    end else elapsed<=elapsed+1'b1;
   end
   if(rx_valid&&rx_ready)begin
    if(!receiving)begin
     response[0]<=rx_data;rx_index<=1;receive_t4<=rx_timestamp;
     malformed<=!pending||!rx_sop||rx_length!=48||rx_src_ip!=SERVER_IP||rx_src_port!=123||rx_dst_port!=CLIENT_PORT;
     receiving<=!rx_eop;
     if(rx_eop)begin malformed<=1;checking<=1;end
    end else begin
     if(rx_index<48)response[rx_index]<=rx_data;
     if(rx_index<63)rx_index<=rx_index+1'b1;
     if(rx_sop||rx_length!=48||rx_index>=48)malformed<=1;
     if(rx_eop)begin
      receiving<=0;checking<=1;
      if(rx_index!=47)malformed<=1;
     end
    end
   end
   if(checking)begin
    checking<=0;
    if(pending&&elapsed<TIMEOUT_CYCLES-1&&packet_legal)begin
     sync_t1<=request_t1;sync_t2<=received_at;sync_t3<=transmitted_at;sync_t4<=receive_t4;
     sync_valid<=1;response_accepted<=1;accepted_count<=inc(accepted_count);pending<=0;
    end else begin response_rejected<=1;rejected_count<=inc(rejected_count);end
   end
  end
 end
endmodule
