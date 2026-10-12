module mac_gmii_rx #(parameter integer DEPTH=2048,parameter [31:0] COUNTER_MAX=32'hffffffff)(
 input wire clk,reset,input wire [7:0] gmii_rxd,input wire gmii_rx_dv,gmii_rx_er,
 output wire [7:0] client_data,output wire client_valid,input wire client_ready,
 output wire client_sop,client_eop,output wire [15:0] client_length,
 output reg accepted,dropped,output reg [4:0] drop_reason,
 output reg [31:0] seen_frames,good_frames,drop_frames,delivered_frames,
 output wire [1:0] banks_busy,output reg counter_saturated
);
 localparam PRE=0,FRAME=1,DISCARD=2;
 reg [1:0] phase;
 reg dv_prev,write_bank,prefer_bank,allocated;
 reg [3:0] pre_count;
 reg [15:0] wire_count,out_index;
 reg [31:0] crc,tail;
 reg bad_pre,bad_phy,bad_space,bad_size;
 reg qhead,qtail;
 reg [1:0] qcount;
 reg qbank[0:1];reg [15:0] qlength[0:1];
 wire [1:0] begin_ready,in_ready,committed,valid;
 wire [7:0] data0,data1;
 wire [15:0] len0,len1;
 wire [31:0] occ0,occ1,crc_next;
 wire found_sfd=gmii_rx_dv&&phase==PRE&&gmii_rxd==8'hd5&&pre_count==7;
 wire selected_bank=begin_ready[prefer_bank]?prefer_bank:!prefer_bank;
 wire any_free=|begin_ready;
 wire end_frame=dv_prev&&!gmii_rx_dv;
 wire [31:0] final_crc=~crc;
 wire [31:0] expected_tail={final_crc[7:0],final_crc[15:8],final_crc[23:16],final_crc[31:24]};
 wire [4:0] flags={bad_space,bad_phy,(bad_size||wire_count<64||wire_count>1518),
                   (tail!=expected_tail),bad_pre||phase!=FRAME};
 wire commit=end_frame&&phase==FRAME&&allocated&&(flags==0);
 wire frame_pop=client_valid&&client_ready&&client_eop;
 wire selected_out=qbank[qhead];
 assign client_data=selected_out?data1:data0;
 assign client_valid=!reset&&qcount!=0&&(selected_out?valid[1]:valid[0]);
 assign client_length=qcount!=0?qlength[qhead]:0;
 assign client_sop=client_valid&&out_index==0;
 assign client_eop=client_valid&&out_index+1==client_length;
 wire push=gmii_rx_dv&&phase==FRAME&&allocated&&wire_count>=4&&!bad_space&&!bad_size;
 function [31:0] increment;input [31:0] v;begin increment=v>=COUNTER_MAX?v:v+1'b1;end endfunction
 mac_crc32_byte update(.state_in(crc),.data(tail[31:24]),.state_out(crc_next));
 mac_frame_store #(.DEPTH(DEPTH)) bank0(.clk(clk),.reset(reset),
  .begin_valid(found_sfd&&any_free&&!selected_bank),.begin_ready(begin_ready[0]),
  .in_data(tail[31:24]),.in_valid(push&&!write_bank),.in_ready(in_ready[0]),
  .commit_valid(commit&&!write_bank),.abort_valid(end_frame&&phase==FRAME&&allocated&&!commit&&!write_bank),
  .out_data(data0),.out_valid(valid[0]),.out_ready(qcount!=0&&!selected_out&&client_ready),
  .busy(banks_busy[0]),.committed(committed[0]),.frame_length(len0),.occupancy(occ0));
 mac_frame_store #(.DEPTH(DEPTH)) bank1(.clk(clk),.reset(reset),
  .begin_valid(found_sfd&&any_free&&selected_bank),.begin_ready(begin_ready[1]),
  .in_data(tail[31:24]),.in_valid(push&&write_bank),.in_ready(in_ready[1]),
  .commit_valid(commit&&write_bank),.abort_valid(end_frame&&phase==FRAME&&allocated&&!commit&&write_bank),
  .out_data(data1),.out_valid(valid[1]),.out_ready(qcount!=0&&selected_out&&client_ready),
  .busy(banks_busy[1]),.committed(committed[1]),.frame_length(len1),.occupancy(occ1));
 always @(posedge clk) begin
  if(reset)begin phase<=PRE;dv_prev<=0;pre_count<=0;wire_count<=0;write_bank<=0;prefer_bank<=0;allocated<=0;
   crc<=32'hffffffff;tail<=0;bad_pre<=0;bad_phy<=0;bad_space<=0;bad_size<=0;
   qhead<=0;qtail<=0;qcount<=0;qbank[0]<=0;qbank[1]<=0;qlength[0]<=0;qlength[1]<=0;out_index<=0;
   accepted<=0;dropped<=0;drop_reason<=0;seen_frames<=0;good_frames<=0;drop_frames<=0;delivered_frames<=0;counter_saturated<=0;
  end else begin
   dv_prev<=gmii_rx_dv;accepted<=0;dropped<=0;
   if(gmii_rx_dv&&!dv_prev)begin seen_frames<=increment(seen_frames);if(seen_frames>=COUNTER_MAX)counter_saturated<=1;bad_pre<=0;bad_phy<=gmii_rx_er;bad_space<=0;bad_size<=0;end
   else if(gmii_rx_dv&&gmii_rx_er)bad_phy<=1;
   if(gmii_rx_dv)case(phase)
    PRE:begin
     if(gmii_rxd==8'h55&&pre_count<7)pre_count<=pre_count+1'b1;
     else if(found_sfd)begin phase<=FRAME;write_bank<=selected_bank;bad_space<=!any_free;allocated<=any_free;
      wire_count<=0;crc<=32'hffffffff;tail<=0;prefer_bank<=!selected_bank;end
     else begin bad_pre<=1;phase<=DISCARD;end
    end
    FRAME:begin
     tail<={tail[23:0],gmii_rxd};
     if(wire_count!=16'hffff)wire_count<=wire_count+1'b1;
     if(wire_count>=1518)bad_size<=1;
     if(wire_count>=4)crc<=crc_next;
     if(push&&!(write_bank?in_ready[1]:in_ready[0]))bad_space<=1;
    end
   endcase
   if(end_frame)begin
    if(commit)begin accepted<=1;good_frames<=increment(good_frames);if(good_frames>=COUNTER_MAX)counter_saturated<=1;
     qbank[qtail]<=write_bank;qlength[qtail]<=wire_count-4;qtail<=!qtail;end
    else begin dropped<=1;drop_frames<=increment(drop_frames);if(drop_frames>=COUNTER_MAX)counter_saturated<=1;drop_reason<=flags;end
    phase<=PRE;pre_count<=0;wire_count<=0;
   end
   if(client_valid&&client_ready)begin
    if(client_eop)begin out_index<=0;qhead<=!qhead;delivered_frames<=increment(delivered_frames);if(delivered_frames>=COUNTER_MAX)counter_saturated<=1;end
    else out_index<=out_index+1'b1;
   end
   case({commit,frame_pop})2'b10:qcount<=qcount+1'b1;2'b01:qcount<=qcount-1'b1;default:begin end endcase
  end
 end
endmodule
