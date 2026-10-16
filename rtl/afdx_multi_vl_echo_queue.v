// Two atomic application banks per VL, round-robin eligible-VL scheduler.
// Global single-clock RAM stores payloads; ownership/credits are per VL.
module afdx_multi_vl_echo_queue #(
 parameter integer VL_COUNT=16,
 parameter [15:0] VL_BASE=16'h1234
)(
 input wire clk,reset,
 input wire [7:0] app_data,input wire app_valid,output wire app_ready,
 input wire app_sop,app_eop,input wire [10:0] app_length,
 input wire [7:0] app_sn,input wire [15:0] app_vlid,
 input wire [15:0] app_src_port,app_dst_port,
 output wire msg_valid,input wire msg_ready,output wire [10:0] msg_length,
 output wire [15:0] msg_vlid,msg_src_port,msg_dst_port,
 output wire [7:0] payload_data,output wire payload_valid,
 input wire payload_ready,output wire payload_last,input wire msg_done,msg_error,
 input wire gmii_tx_en,input wire [31:0] cfg_bag_cycles,
 output reg [31:0] stored_count,sent_count,error_count,
 output wire [2*VL_COUNT-1:0] banks_busy
);
 localparam IDLE=0,DESC=1,DATA=2,WAIT_DONE=3;
 reg [7:0] storage[0:VL_COUNT*2*1471-1];
 reg [10:0] lengths[0:2*VL_COUNT-1];
 reg [7:0] origins[0:2*VL_COUNT-1];
 reg [15:0] src_ports[0:2*VL_COUNT-1],dst_ports[0:2*VL_COUNT-1];
 reg [2*VL_COUNT-1:0] busy,committed;
 reg [VL_COUNT-1:0] wr_slot,rd_slot,have_start;
 reg [31:0] elapsed[0:VL_COUNT-1];
 reg writing;reg [15:0] write_vl,read_vl,rr;
 reg [10:0] wr_index,rd_index;
 reg [7:0] read_byte;
 reg [1:0] state;
 reg gmii_tx_en_d;
 wire [16:0] incoming_index={1'b0,app_vlid}-{1'b0,VL_BASE};
 wire incoming_legal=app_vlid>=VL_BASE&&incoming_index<VL_COUNT;
 wire [15:0] incoming_vl=incoming_legal?incoming_index[15:0]:16'd0;
wire [15:0] input_bank=2*incoming_vl+wr_slot[incoming_vl];
wire [15:0] write_bank=2*write_vl+wr_slot[write_vl];
wire [15:0] output_bank=2*read_vl+rd_slot[read_vl];
wire [VL_COUNT-1:0] scheduler_eligible;
wire [15:0] scheduler_choice;
wire scheduler_found;
genvar eligible_vl_index;
generate for(eligible_vl_index=0;eligible_vl_index<VL_COUNT;eligible_vl_index=eligible_vl_index+1)begin:eligible_vl
 wire bank0_committed=committed[2*eligible_vl_index];
 wire bank1_committed=committed[2*eligible_vl_index+1];
 wire selected_bank_committed=rd_slot[eligible_vl_index]?bank1_committed:bank0_committed;
 assign scheduler_eligible[eligible_vl_index]=selected_bank_committed&&
        (!have_start[eligible_vl_index]||elapsed[eligible_vl_index]>=cfg_bag_cycles);
end endgenerate
generate if(VL_COUNT==16)begin:balanced_scheduler
 wire [31:0] doubled_eligible={scheduler_eligible,scheduler_eligible};
 wire [15:0] eligible_from_rr=doubled_eligible>>rr[3:0];
 reg [3:0] selected_offset;
 wire [3:0] selected_vl=rr[3:0]+selected_offset;
 always @*begin
  selected_offset=0;
  casez(eligible_from_rr)
   16'b???????????????1:selected_offset=4'd0;
   16'b??????????????10:selected_offset=4'd1;
   16'b?????????????100:selected_offset=4'd2;
   16'b????????????1000:selected_offset=4'd3;
   16'b???????????10000:selected_offset=4'd4;
   16'b??????????100000:selected_offset=4'd5;
   16'b?????????1000000:selected_offset=4'd6;
   16'b????????10000000:selected_offset=4'd7;
   16'b???????100000000:selected_offset=4'd8;
   16'b??????1000000000:selected_offset=4'd9;
   16'b?????10000000000:selected_offset=4'd10;
   16'b????100000000000:selected_offset=4'd11;
   16'b???1000000000000:selected_offset=4'd12;
   16'b??10000000000000:selected_offset=4'd13;
   16'b?100000000000000:selected_offset=4'd14;
   16'b1000000000000000:selected_offset=4'd15;
   default:selected_offset=4'd0;
  endcase
 end
 assign scheduler_found=|eligible_from_rr;
 assign scheduler_choice={12'd0,selected_vl};
end else begin:generic_scheduler
 integer scan,index;
 reg found;
 reg [15:0] choice;
 always @*begin
  choice=0;found=0;index=0;
  for(scan=0;scan<VL_COUNT;scan=scan+1)begin
   index=rr+scan;if(index>=VL_COUNT)index=index-VL_COUNT;
   if(!found&&scheduler_eligible[index])begin
    choice=index;found=1;
   end
  end
 end
 assign scheduler_found=found;
 assign scheduler_choice=choice;
end endgenerate
 assign app_ready=!reset&&(writing||(incoming_legal&&!busy[input_bank]));
 assign banks_busy=busy;
 assign msg_valid=!reset&&state==DESC;
 assign msg_length=lengths[output_bank];
 assign msg_vlid=VL_BASE+read_vl;
 assign msg_src_port=src_ports[output_bank];assign msg_dst_port=dst_ports[output_bank];
 assign payload_valid=!reset&&state==DATA;
 // Registered single read port permits actual RAM inference. Prefetch the
 // first byte at descriptor acceptance, then advance only on byte handshakes.
 assign payload_data=payload_valid?read_byte:8'd0;
 wire [15:0] incoming_write_bank=writing?write_bank:input_bank;
 wire [10:0] incoming_write_offset=writing?wr_index:11'd0;
 wire prefetch=(state==DESC&&msg_valid&&msg_ready)||
               (state==DATA&&payload_valid&&payload_ready&&!payload_last);
 wire [10:0] prefetch_offset=state==DESC?11'd0:rd_index+1'b1;
 assign payload_last=payload_valid&&(rd_index+1'b1==lengths[output_bank]);
 wire app_fire=app_valid&&app_ready;
 wire input_malformed=(!writing&&(!app_sop||app_length==0||app_length>1471||app_sn==0||!incoming_legal))||
       (writing&&(app_sop||app_vlid!=VL_BASE+write_vl||app_length!=lengths[write_bank]||app_sn!=origins[write_bank]||
                  app_src_port!=src_ports[write_bank]||app_dst_port!=dst_ports[write_bank]))||
       (app_eop!=(writing?(wr_index+1'b1==lengths[write_bank]):app_length==1));
 // Keep RAM processes separate from reset/control logic. RAM contents and
 // output pipeline do not need reset: validity/ownership prevents exposure.
 always @(posedge clk)begin
  if(app_fire&&!input_malformed)storage[incoming_write_bank*1471+incoming_write_offset]<=app_data;
 end
 always @(posedge clk)begin
  if(!reset&&prefetch)read_byte<=storage[output_bank*1471+prefetch_offset];
 end
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   busy<=0;committed<=0;wr_slot<=0;rd_slot<=0;have_start<=0;
   writing<=0;write_vl<=0;read_vl<=0;rr<=0;wr_index<=0;rd_index<=0;state<=IDLE;gmii_tx_en_d<=0;
   stored_count<=0;sent_count<=0;error_count<=0;
   for(i=0;i<VL_COUNT;i=i+1)elapsed[i]<=0;
   for(i=0;i<2*VL_COUNT;i=i+1)begin lengths[i]<=0;origins[i]<=0;src_ports[i]<=0;dst_ports[i]<=0;end
  end else begin
   gmii_tx_en_d<=gmii_tx_en;
   for(i=0;i<VL_COUNT;i=i+1)if(have_start[i]&&elapsed[i]!=32'hffffffff)elapsed[i]<=elapsed[i]+1'b1;
   if(gmii_tx_en&&!gmii_tx_en_d)begin have_start[read_vl]<=1;elapsed[read_vl]<=0;end
   if(app_fire)begin
    if(input_malformed)begin
     error_count<=error_count+1'b1;
     if(writing)begin busy[write_bank]<=0;committed[write_bank]<=0;end
     writing<=0;wr_index<=0;
    end else begin
     if(!writing)begin
      busy[input_bank]<=1;
      lengths[input_bank]<=app_length;origins[input_bank]<=app_sn;
      src_ports[input_bank]<=app_src_port;dst_ports[input_bank]<=app_dst_port;write_vl<=incoming_vl;
     end
     if(app_eop)begin
      if(writing)begin committed[write_bank]<=1;wr_slot[write_vl]<=!wr_slot[write_vl];end
      else begin committed[input_bank]<=1;wr_slot[incoming_vl]<=!wr_slot[incoming_vl];end
      stored_count<=stored_count+1'b1;writing<=0;wr_index<=0;
     end else begin writing<=1;wr_index<=writing?wr_index+1'b1:11'd1;end
    end
   end
   case(state)
    IDLE:if(scheduler_found)begin read_vl<=scheduler_choice;rd_index<=0;state<=DESC;end
    DESC:if(msg_valid&&msg_ready)state<=DATA;
    DATA:if(payload_valid&&payload_ready)begin
     if(payload_last)state<=WAIT_DONE;
     else rd_index<=rd_index+1'b1;
    end
    WAIT_DONE:if(msg_done)begin
     busy[output_bank]<=0;committed[output_bank]<=0;rd_slot[read_vl]<=!rd_slot[read_vl];
     rr<=read_vl==VL_COUNT-1?16'd0:read_vl+1'b1;state<=IDLE;sent_count<=sent_count+1'b1;
    end
    default:state<=IDLE;
   endcase
   if(msg_error)begin
    error_count<=error_count+1'b1;busy[output_bank]<=0;committed[output_bank]<=0;
    rd_slot[read_vl]<=!rd_slot[read_vl];rr<=read_vl==VL_COUNT-1?16'd0:read_vl+1'b1;state<=IDLE;
   end
  end
 end
endmodule
