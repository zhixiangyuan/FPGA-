// Serial, synchronous RAM lookup: independent A/B integrity PSN plus one
// delivery PSN per VL. Frame ownership is held until EOP, including draining.
// RECOVERY_CYCLES is the redundancy SkewMAX window; it NEVER bypasses IC.
// SN0 is a control record (not application data); the next SN must be 1/2.
// Per-network reset generations prevent a late B SN0 resetting newer A data.
// Generation comparison uses a bounded modulo-256 window (<128 resets skew).
module afdx_redundant_rx #(
 parameter integer VL_COUNT=4096, FAST_DISCARD=0, PREFIX_VLID=1,
 parameter [15:0] VL_BASE=16'h1234,
 parameter [31:0] RECOVERY_CYCLES=625000,
 parameter [VL_COUNT-1:0] INTEGRITY_ENABLE={VL_COUNT{1'b1}},
 parameter [VL_COUNT-1:0] REDUNDANCY_ENABLE={VL_COUNT{1'b1}}
)(
 input wire clk,reset,
 input wire [7:0] a_data,input wire a_valid,output wire a_ready,
 input wire a_sop,a_eop,input wire [15:0] a_vlid,input wire [7:0] a_sn,
 input wire [10:0] a_length,
 input wire [15:0] a_src_port,a_dst_port,
 input wire [7:0] b_data,input wire b_valid,output wire b_ready,
 input wire b_sop,b_eop,input wire [15:0] b_vlid,input wire [7:0] b_sn,
 input wire [10:0] b_length,
 input wire [15:0] b_src_port,b_dst_port,
 output wire [7:0] rx_data,output wire rx_valid,input wire rx_ready,
 output wire rx_sop,rx_eop,
 output wire [15:0] rx_vlid,rx_src_port,rx_dst_port,output wire [10:0] rx_length,
 output wire initialized,output wire a_discard,b_discard,
 output reg [31:0] delivered_count,duplicate_count,integrity_error_count,control_count
);
 localparam IW=VL_COUNT>1?$clog2(VL_COUNT):1;
 localparam INIT=0,IDLE=1,READ=2,CHECK=3,HI=4,LO=5,PASS=6,DRAIN=7;
 reg [2:0] state;reg [IW-1:0] scrub,index;
 reg [82:0] table_ram[0:VL_COUNT-1];reg [82:0] entry,updated;
 reg [31:0] cycle;reg channel,prefer_b;
 reg [15:0] vlid;reg [7:0] sn;reg legal;
 wire chosen_b=b_valid&&(!a_valid||prefer_b);
 wire [15:0] chosen_vlid=chosen_b?b_vlid:a_vlid;
 wire [7:0] selected_data=channel?b_data:a_data;
 wire selected_valid=channel?b_valid:a_valid;
 wire selected_eop=channel?b_eop:a_eop;
 wire source_fire=selected_valid&&(state==DRAIN||(state==PASS&&rx_ready));
 wire stale=cycle-entry[31:0]>=RECOVERY_CYCLES;
 wire network_seen=channel?entry[49]:entry[58];
 wire [7:0] network_psn=channel?entry[48:41]:entry[57:50];
 wire [7:0] network_epoch=channel?entry[74:67]:entry[82:75];
 wire [7:0] reset_epoch=network_seen&&network_psn==0?network_epoch:network_epoch+8'd1;
 wire [7:0] reset_distance=reset_epoch-entry[66:59];
 function [7:0] next_sn;input [7:0] v;begin next_sn=v==255?8'd1:v+1'b1;end endfunction
 wire integrity_ok=!INTEGRITY_ENABLE[index]||!network_seen||sn==next_sn(network_psn)||sn==next_sn(next_sn(network_psn));
 wire [8:0] serial_distance=sn>=entry[39:32]?{1'b0,sn}-{1'b0,entry[39:32]}:
                            9'd255+{1'b0,sn}-{1'b0,entry[39:32]};
 wire deliver_ok=!REDUNDANCY_ENABLE[index]||stale||
   (network_epoch==entry[66:59]&&(!entry[40]||(serial_distance!=0&&serial_distance<=127)));
 assign initialized=!reset&&state!=INIT;
 assign a_discard=!reset&&FAST_DISCARD!=0&&state==DRAIN&&!channel;
 assign b_discard=!reset&&FAST_DISCARD!=0&&state==DRAIN&&channel;
 assign a_ready=!reset&&!channel&&(state==DRAIN||(state==PASS&&rx_ready));
 assign b_ready=!reset&&channel&&(state==DRAIN||(state==PASS&&rx_ready));
 assign rx_valid=!reset&&(state==HI||state==LO||(state==PASS&&selected_valid));
 assign rx_data=state==HI?vlid[15:8]:state==LO?vlid[7:0]:selected_data;
 assign rx_sop=PREFIX_VLID!=0?state==HI:state==PASS&&(channel?b_sop:a_sop);
 assign rx_eop=state==PASS&&selected_eop;
 assign rx_vlid=vlid;assign rx_length=channel?b_length:a_length;
 assign rx_src_port=channel?b_src_port:a_src_port;assign rx_dst_port=channel?b_dst_port:a_dst_port;
 always @*begin
  updated=entry;
  if(channel)begin updated[49]=1;updated[48:41]=sn;end
  else begin updated[58]=1;updated[57:50]=sn;end
  if(sn==0)begin
   if(channel)updated[74:67]=reset_epoch;else updated[82:75]=reset_epoch;
   if(reset_distance!=0&&reset_distance<=127)begin
    updated[66:59]=reset_epoch;updated[40]=0;updated[31:0]=cycle;
   end
  end else if(integrity_ok&&deliver_ok)begin
   updated[40]=1;updated[39:32]=sn;updated[31:0]=cycle;updated[66:59]=network_epoch;
  end
 end
 // No array-wide reset. Initialization writes one entry per cycle (32.768 us
 // at 125 MHz for 4096 VLs), permitting real block RAM inference.
 always @(posedge clk)begin
  if(!reset&&state==INIT)table_ram[scrub]<=83'd0;
  else if(!reset&&state==CHECK&&legal)table_ram[index]<=updated;
  if(!reset&&state==READ)entry<=table_ram[index];
 end
 always @(posedge clk)begin
  if(reset)begin
   state<=INIT;scrub<=0;index<=0;cycle<=0;channel<=0;prefer_b<=0;
   vlid<=0;sn<=0;legal<=0;delivered_count<=0;duplicate_count<=0;integrity_error_count<=0;control_count<=0;
  end else begin
   cycle<=cycle+1'b1;
   case(state)
    INIT:if(scrub==VL_COUNT-1)state<=IDLE;else scrub<=scrub+1'b1;
    IDLE:if(a_valid||b_valid)begin
     channel<=chosen_b;vlid<=chosen_vlid;sn<=chosen_b?b_sn:a_sn;
     legal<=chosen_vlid>=VL_BASE&&({1'b0,chosen_vlid}-{1'b0,VL_BASE})<VL_COUNT&&
             (chosen_b?b_sop:a_sop)&&(chosen_b?b_length:a_length)!=0;
     index<=chosen_vlid-VL_BASE;state<=READ;
    end
    READ:state<=CHECK;
    CHECK:begin
     if(!legal)begin integrity_error_count<=integrity_error_count+1'b1;state<=DRAIN;end
     else if(sn==0)begin control_count<=control_count+1'b1;state<=DRAIN;end
     else if(!integrity_ok)begin integrity_error_count<=integrity_error_count+1'b1;state<=DRAIN;end
     else if(!deliver_ok)begin duplicate_count<=duplicate_count+1'b1;state<=DRAIN;end
     else state<=PREFIX_VLID!=0?HI:PASS;
    end
    HI:if(rx_ready)state<=LO;
    LO:if(rx_ready)state<=PASS;
    PASS,DRAIN:if((source_fire&&selected_eop)||(state==DRAIN&&FAST_DISCARD!=0&&selected_valid))begin
     if(state==PASS)delivered_count<=delivered_count+1'b1;
     prefer_b<=!channel;state<=IDLE;
    end
    default:state<=INIT;
   endcase
  end
 end
endmodule
