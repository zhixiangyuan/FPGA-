// Parallel physical checker: DA..SN is delayed four bytes to exclude FCS.
// Protocol payload banks publish only after the final MAC verdict.
module afdx_mac_rx_checked(
 input wire clk,reset,input wire [7:0] gmii_rxd,input wire gmii_rx_dv,gmii_rx_er,
 input wire stream_ready,output wire [7:0] stream_data,
 output wire stream_valid,stream_sop,stream_eop,
 output wire frame_done,frame_good,output wire [15:0] frame_length,
 output reg [31:0] drop_frames
);
 localparam PRE=0,FRAME=1,DISCARD=2;
 reg [1:0] phase;reg dv_prev,allocated,stream_finished,length_known;
 reg [3:0] pre_count;reg [15:0] wire_count,ip_total;
 reg [31:0] crc,tail;reg bad_pre,bad_phy,bad_space,bad_size;
 wire found_sfd=gmii_rx_dv&&phase==PRE&&gmii_rxd==8'hd5&&pre_count==7;
 wire [15:0] payload_length=ip_total-16'd28;
 wire [15:0] padding=payload_length<17?17-payload_length:0;
 wire [15:0] body_length=43+payload_length+padding;
 wire [31:0] final_crc=~crc;
 wire [31:0] expected_tail={final_crc[7:0],final_crc[15:8],final_crc[23:16],final_crc[31:24]};
 wire [31:0] next_crc;
 mac_crc32_byte update(.state_in(crc),.data(tail[31:24]),.state_out(next_crc));
 assign stream_data=tail[31:24];
 assign stream_valid=!reset&&gmii_rx_dv&&phase==FRAME&&allocated&&wire_count>=4&&!stream_finished;
 assign stream_sop=stream_valid&&wire_count==4;
 assign stream_eop=stream_valid&&length_known&&wire_count-4+1==body_length;
 assign frame_done=!reset&&dv_prev&&!gmii_rx_dv;
 assign frame_good=phase==FRAME&&allocated&&!bad_pre&&!bad_phy&&!bad_space&&!bad_size&&wire_count>=64&&wire_count<=1518&&tail==expected_tail;
 assign frame_length=wire_count-4;
 always @(posedge clk)begin
  if(reset)begin
   phase<=PRE;dv_prev<=0;allocated<=0;stream_finished<=0;length_known<=0;pre_count<=0;wire_count<=0;ip_total<=0;
   crc<=32'hffffffff;tail<=0;bad_pre<=0;bad_phy<=0;bad_space<=0;bad_size<=0;drop_frames<=0;
  end else begin
   dv_prev<=gmii_rx_dv;
   if(gmii_rx_dv&&!dv_prev)begin bad_pre<=0;bad_phy<=gmii_rx_er;bad_space<=0;bad_size<=0;end
   else if(gmii_rx_dv&&gmii_rx_er)bad_phy<=1;
   if(gmii_rx_dv)case(phase)
    PRE:begin
     if(gmii_rxd==8'h55&&pre_count<7)pre_count<=pre_count+1'b1;
     else if(found_sfd)begin
      phase<=FRAME;allocated<=stream_ready;bad_space<=!stream_ready;
      wire_count<=0;ip_total<=0;stream_finished<=0;length_known<=0;crc<=32'hffffffff;tail<=0;
     end else begin bad_pre<=1;phase<=DISCARD;end
    end
    FRAME:begin
     tail<={tail[23:0],gmii_rxd};
     if(wire_count!=16'hffff)wire_count<=wire_count+1'b1;
     if(wire_count>=1518)bad_size<=1;
     if(wire_count>=4)crc<=next_crc;
     if(stream_valid)begin
      if(wire_count-4==16)ip_total[15:8]<=stream_data;
      if(wire_count-4==17)begin ip_total[7:0]<=stream_data;length_known<=1;end
      if(stream_eop)stream_finished<=1;
      if(!stream_ready)bad_space<=1;
     end
    end
   endcase
   if(frame_done)begin
    if(!frame_good&&drop_frames!=32'hffffffff)drop_frames<=drop_frames+1'b1;
    phase<=PRE;pre_count<=0;wire_count<=0;allocated<=0;stream_finished<=0;
   end
  end
 end
endmodule
