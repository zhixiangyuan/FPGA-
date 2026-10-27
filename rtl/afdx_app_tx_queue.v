// Application bursts: big-endian VLID (2 bytes), then 1..1471 payload bytes.
// At least one tx_valid=0 cycle terminates each message. Once a burst starts,
// it never stalls; credits are reserved at its first byte. No Ethernet in TB.
// Payload RAM is shared by all configured VLs, rather than replicated per VL.
module afdx_app_tx_queue #(
 parameter integer VL_COUNT=128, SLOTS=16,
 parameter [15:0] VL_BASE=16'h1234,
 parameter [31:0] BAG_CYCLES=125000
)(
 input wire clk,reset, input wire [7:0] tx_data,input wire tx_valid,
 output wire tx_ready,
 output wire msg_valid,input wire msg_ready,
 output wire [15:0] msg_vlid,output wire [10:0] msg_length,
 output wire [7:0] payload_data,output wire payload_valid,
 input wire payload_ready,output wire payload_last,input wire msg_done,msg_error,
 input wire gmii_tx_en,
 output reg [31:0] accepted_count,rejected_count,sent_count,
 output wire [SLOTS-1:0] occupied
);
 localparam SW=$clog2(SLOTS), IDLE=0,HEADER=1,BODY=2,DROP=3;
 localparam SCAN=0,LOOK=1,DESC=2,DATA=3,WAIT_DONE=4;
 reg [7:0] ram[0:SLOTS*2048-1];
 reg [SLOTS-1:0] busy,committed;
 reg [15:0] vlids[0:SLOTS-1];reg [10:0] lengths[0:SLOTS-1];
 reg [31:0] ticket[0:SLOTS-1],next_ticket;
 reg [31:0] last_start[0:VL_COUNT-1];reg [VL_COUNT-1:0] seen;
 reg [31:0] cycle;
 reg [1:0] capture;reg [2:0] state;
 reg [SW-1:0] wr_slot,rd_slot,scan_slot;
 reg [10:0] wr_index,rd_index;reg [7:0] vl_hi,read_byte;
 reg [15:0] captured_vlid;reg bad;
 reg gmii_d;reg [31:0] scan_last;reg scan_seen;
 wire [15:0] incoming_vlid={vl_hi,tx_data};
 wire incoming_legal=incoming_vlid>=VL_BASE&&({1'b0,incoming_vlid}-{1'b0,VL_BASE})<VL_COUNT;
 wire [15:0] read_vl_index=vlids[rd_slot]-VL_BASE;
 wire [15:0] scan_vl_index=vlids[scan_slot]-VL_BASE;
 reg older_same_vl;integer k;
 always @*begin
  older_same_vl=0;
  for(k=0;k<SLOTS;k=k+1)if(committed[k]&&vlids[k]==vlids[scan_slot]&&
     $signed(ticket[k]-ticket[scan_slot])<0)older_same_vl=1;
 end
 reg free_found;reg [SW-1:0] free_slot;integer n;
 always @*begin
  free_found=0;free_slot=0;
  for(n=0;n<SLOTS;n=n+1)if(!busy[n]&&!free_found)begin free_found=1;free_slot=n;end
 end
 assign tx_ready=!reset&&(capture!=IDLE||free_found);
 assign occupied=busy;
 assign msg_valid=!reset&&state==DESC;
 assign msg_vlid=vlids[rd_slot];assign msg_length=lengths[rd_slot];
 assign payload_valid=!reset&&state==DATA;
 assign payload_data=read_byte;
 assign payload_last=rd_index+1'b1==lengths[rd_slot];
 wire prefetch=(state==DESC&&msg_ready)||(state==DATA&&payload_ready&&!payload_last);
 wire [10:0] next_index=state==DESC?11'd0:rd_index+1'b1;
 // Synchronous read/write; RAM data has no reset or combinational read port.
 always @(posedge clk)begin
  if(!reset&&capture==BODY&&tx_valid&&!bad&&wr_index<1471)
   ram[{wr_slot,11'd0}+wr_index]<=tx_data;
  if(!reset&&prefetch)read_byte<=ram[{rd_slot,11'd0}+next_index];
 end
 always @(posedge clk)begin
  if(!reset&&state==SCAN&&committed[scan_slot])scan_last<=last_start[scan_vl_index];
 end
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   busy<=0;committed<=0;seen<=0;cycle<=0;capture<=IDLE;state<=SCAN;
   wr_slot<=0;rd_slot<=0;scan_slot<=0;wr_index<=0;rd_index<=0;
   vl_hi<=0;captured_vlid<=0;bad<=0;gmii_d<=0;scan_seen<=0;
   accepted_count<=0;rejected_count<=0;sent_count<=0;next_ticket<=0;
   for(i=0;i<SLOTS;i=i+1)begin vlids[i]<=VL_BASE;lengths[i]<=0;end
  end else begin
   cycle<=cycle+1'b1;gmii_d<=gmii_tx_en;
   if(gmii_tx_en&&!gmii_d)begin
    seen[read_vl_index]<=1;last_start[read_vl_index]<=cycle;
   end
   case(capture)
    IDLE:if(tx_valid)begin
     if(free_found)begin
      wr_slot<=free_slot;busy[free_slot]<=1;vl_hi<=tx_data;wr_index<=0;bad<=0;capture<=HEADER;
     end else begin capture<=DROP;rejected_count<=rejected_count+1'b1;end
    end
    HEADER:if(tx_valid)begin captured_vlid<=incoming_vlid;bad<=!incoming_legal;capture<=BODY;end
     else begin busy[wr_slot]<=0;capture<=IDLE;rejected_count<=rejected_count+1'b1;end
    BODY:if(tx_valid)begin
     if(wr_index<1471)wr_index<=wr_index+1'b1;else bad<=1;
    end else begin
     capture<=IDLE;
     if(bad||wr_index==0)begin busy[wr_slot]<=0;rejected_count<=rejected_count+1'b1;end
     else begin
      vlids[wr_slot]<=captured_vlid;lengths[wr_slot]<=wr_index;
      ticket[wr_slot]<=next_ticket;next_ticket<=next_ticket+1'b1;
      committed[wr_slot]<=1;accepted_count<=accepted_count+1'b1;
     end
    end
    DROP:if(!tx_valid)capture<=IDLE;
   endcase
   case(state)
    SCAN:begin
     if(committed[scan_slot])begin scan_seen<=seen[scan_vl_index];state<=LOOK;end
     else scan_slot<=scan_slot+1'b1;
    end
    LOOK:if(!older_same_vl&&(!scan_seen||cycle-scan_last>=BAG_CYCLES))begin rd_slot<=scan_slot;rd_index<=0;state<=DESC;end
     else begin scan_slot<=scan_slot+1'b1;state<=SCAN;end
    DESC:if(msg_ready)state<=DATA;
    DATA:if(payload_ready)begin if(payload_last)state<=WAIT_DONE;else rd_index<=rd_index+1'b1;end
    WAIT_DONE:if(msg_done)begin
     busy[rd_slot]<=0;committed[rd_slot]<=0;sent_count<=sent_count+1'b1;
     scan_slot<=rd_slot+1'b1;state<=SCAN;
    end
    default:state<=SCAN;
   endcase
   if(msg_error&&state!=SCAN&&state!=LOOK)begin
    busy[rd_slot]<=0;committed[rd_slot]<=0;rejected_count<=rejected_count+1'b1;
    scan_slot<=rd_slot+1'b1;state<=SCAN;
   end
  end
 end
endmodule
