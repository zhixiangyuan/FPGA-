// Application bursts: big-endian VLID (2 bytes), then 1..1471 payload bytes.
// At least one tx_valid=0 cycle terminates each message. Once a burst starts,
// it never stalls; credits are reserved at its first byte. No Ethernet in TB.
// Payload RAM is shared by all configured VLs, rather than replicated per VL.
module afdx_app_tx_queue #(
 parameter integer VL_COUNT=128, SLOTS=16, PIPELINED_MAC=0,
 parameter integer LENGTH_BIAS_16=24,
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
 input wire [15:0] gmii_vlid,completed_vlid,input wire gmii_done,
 output reg [31:0] accepted_count,rejected_count,sent_count,
 output wire [SLOTS-1:0] occupied
);
 localparam SW=$clog2(SLOTS), IDLE=0,HEADER=1,BODY=2,DROP=3;
 localparam SCAN=0,LOOK=1,DESC=2,DATA=3,WAIT_DONE=4;
 reg [7:0] ram[0:SLOTS*2048-1];
 reg [SLOTS-1:0] busy,committed;
 reg [15:0] vlids[0:SLOTS-1];reg [10:0] lengths[0:SLOTS-1];
 reg [31:0] ticket[0:SLOTS-1],next_ticket;
 reg [31:0] arrival[0:SLOTS-1];
 reg [31:0] priority_score[0:SLOTS-1];
 reg [31:0] last_start[0:VL_COUNT-1];reg [VL_COUNT-1:0] seen;
 reg [VL_COUNT-1:0] pending_wire;
 reg [31:0] cycle;
 reg [1:0] capture;reg [2:0] state;
 reg [SW-1:0] wr_slot,rd_slot,scan_slot;
 reg [10:0] wr_index,rd_index;reg [7:0] vl_hi,read_byte;
 reg [15:0] captured_vlid;reg bad;
 reg gmii_d;reg [31:0] scan_last;reg scan_seen;
 reg candidate_found;reg [SW-1:0] candidate_slot;reg [31:0] candidate_ticket;
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
 // Ready-time aging with bounded length compensation. Short frames can
 // bypass a newly completed long frame; older long frames regain priority.
 // Same-VL FIFO order remains protected by older_same_vl.
 wire [31:0] priority_key=priority_score[scan_slot];
 wire eligible=committed[scan_slot]&&!older_same_vl&&
   (!PIPELINED_MAC||!pending_wire[scan_vl_index])&&(!scan_seen||cycle-scan_last>=BAG_CYCLES);
 wire prefer_scan=eligible&&(!candidate_found||$signed(priority_key-candidate_ticket)<0);
 wire [SW-1:0] next_candidate=prefer_scan?scan_slot:candidate_slot;
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
  if(!reset&&state==SCAN&&committed[scan_slot])begin
   if(PIPELINED_MAC!=0&&gmii_tx_en&&!gmii_d&&gmii_vlid==vlids[scan_slot])scan_last<=cycle;
   else scan_last<=last_start[scan_vl_index];
  end
 end
 integer i;
 always @(posedge clk)begin
  if(reset)begin
   busy<=0;committed<=0;seen<=0;pending_wire<=0;cycle<=0;capture<=IDLE;state<=SCAN;
   wr_slot<=0;rd_slot<=0;scan_slot<=0;wr_index<=0;rd_index<=0;
   vl_hi<=0;captured_vlid<=0;bad<=0;gmii_d<=0;scan_seen<=0;
   candidate_found<=0;candidate_slot<=0;candidate_ticket<=0;
   accepted_count<=0;rejected_count<=0;sent_count<=0;next_ticket<=0;
   for(i=0;i<SLOTS;i=i+1)begin vlids[i]<=VL_BASE;lengths[i]<=0;arrival[i]<=0;priority_score[i]<=0;end
  end else begin
   cycle<=cycle+1'b1;gmii_d<=gmii_tx_en;
   if(PIPELINED_MAC==0)begin
    if(gmii_tx_en&&!gmii_d)begin seen[read_vl_index]<=1;last_start[read_vl_index]<=cycle;end
   end else begin
    if(gmii_done&&completed_vlid>=VL_BASE&&completed_vlid-VL_BASE<VL_COUNT)sent_count<=sent_count+1'b1;
    if(gmii_tx_en&&!gmii_d&&gmii_vlid>=VL_BASE&&gmii_vlid-VL_BASE<VL_COUNT)begin
     seen[gmii_vlid-VL_BASE]<=1;last_start[gmii_vlid-VL_BASE]<=cycle;pending_wire[gmii_vlid-VL_BASE]<=0;
    end
   end
   case(capture)
    IDLE:if(tx_valid)begin
     if(free_found)begin
      wr_slot<=free_slot;busy[free_slot]<=1;arrival[free_slot]<=cycle;vl_hi<=tx_data;wr_index<=0;bad<=0;capture<=HEADER;
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
      priority_score[wr_slot]<=arrival[wr_slot]+((wr_index*LENGTH_BIAS_16)>>4);
      ticket[wr_slot]<=next_ticket;next_ticket<=next_ticket+1'b1;
      committed[wr_slot]<=1;accepted_count<=accepted_count+1'b1;
     end
    end
    DROP:if(!tx_valid)capture<=IDLE;
   endcase
   case(state)
    SCAN:begin
     scan_seen<=seen[scan_vl_index]||(PIPELINED_MAC!=0&&gmii_tx_en&&!gmii_d&&gmii_vlid==vlids[scan_slot]);
     state<=LOOK;
    end
    LOOK:begin
     if(scan_slot==SLOTS-1)begin
      scan_slot<=0;candidate_found<=0;
      if(candidate_found||eligible)begin rd_slot<=next_candidate;rd_index<=0;state<=DESC;end
      else state<=SCAN;
     end else begin
      if(prefer_scan)begin candidate_found<=1;candidate_slot<=scan_slot;candidate_ticket<=priority_key;end
      scan_slot<=scan_slot+1'b1;state<=SCAN;
     end
    end
    DESC:if(msg_ready)state<=DATA;
    DATA:if(payload_ready)begin if(payload_last)state<=WAIT_DONE;else rd_index<=rd_index+1'b1;end
    WAIT_DONE:if(msg_done)begin
     busy[rd_slot]<=0;committed[rd_slot]<=0;
     if(PIPELINED_MAC==0)sent_count<=sent_count+1'b1;
     else if(PIPELINED_MAC==1)pending_wire[read_vl_index]<=1;
     scan_slot<=0;candidate_found<=0;state<=SCAN;
    end
    default:state<=SCAN;
   endcase
   if(msg_error&&state!=SCAN&&state!=LOOK)begin
    busy[rd_slot]<=0;committed[rd_slot]<=0;rejected_count<=rejected_count+1'b1;
    scan_slot<=0;candidate_found<=0;state<=SCAN;
   end
  end
 end
endmodule
