// Business payloads are already complete and atomic in the application RAM.
// Stream those frames without copying the complete frame into another bank.
// Service FIFOs may pause, so they retain the frozen store-and-forward MAC.
module afdx_mac_tx_stream(
 input wire clk,reset,input wire [7:0] client_data,input wire client_valid,
 output wire client_ready,input wire client_sop,client_eop,
 input wire [15:0] client_length,input wire client_afdx_prepared,client_direct,
 input wire [15:0] client_vlid,
 output reg [7:0] gmii_txd,output wire gmii_tx_en,gmii_tx_er,
 output wire done,reject,output wire [15:0] started_vlid,completed_vlid
);
 localparam IDLE=0,PRE=1,SFD=2,DATA=3,FCS=4,GAP=5,SERVICE_FILL=6,SERVICE_WAIT=7,SERVICE_GAP=8,DROP=9;
 reg [3:0] state;reg [3:0] pre,gap;reg [1:0] fcs_index;
 reg [15:0] remaining,vlid;reg [7:0] held;reg [31:0] crc,fcs;
 reg direct_done,direct_reject;reg last_received;
 reg [15:0] direct_completed_vlid;
 wire service=state==SERVICE_FILL||state==SERVICE_WAIT||state==SERVICE_GAP;
 wire [7:0] service_data;wire service_en,service_er,service_done,service_reject,service_ready;
 wire route_service=state==SERVICE_FILL||(state==IDLE&&!client_direct);
 mac_gmii_tx buffered(.clk(clk),.reset(reset),.client_data(client_data),.client_valid(client_valid&&route_service),
  .client_ready(service_ready),.client_sop(client_sop),.client_eop(client_eop),.client_length(client_length),
  .client_afdx_prepared(client_afdx_prepared),.gmii_txd(service_data),.gmii_tx_en(service_en),.gmii_tx_er(service_er),
  .done(service_done),.reject(service_reject),.sent_frames(),.rejected_frames(),.counter_saturated());
 assign client_ready=!reset&&((state==IDLE&&(client_direct||service_ready))||state==DROP||
   (state==DATA&&remaining>1&&!last_received)||(state==SERVICE_FILL&&service_ready));
 wire fire=client_valid&&client_ready;
 wire first_legal=client_sop&&!client_eop&&client_afdx_prepared&&client_length>=60&&client_length<=1514;
 wire underflow=state==DATA&&remaining>1&&!client_valid;
 assign gmii_tx_en=!reset&&(service?service_en:(state>=PRE&&state<=FCS));
 assign gmii_tx_er=!reset&&(service?service_er:underflow);
 assign done=service_done||direct_done;
 assign reject=service_reject||direct_reject;
 assign started_vlid=vlid;
 assign completed_vlid=service?vlid:direct_completed_vlid;
 wire [31:0] next_crc;
 mac_crc32_byte update(.state_in(crc),.data(held),.state_out(next_crc));
 always @*begin
  gmii_txd=0;
  if(service)gmii_txd=service_data;
  else case(state)
   PRE:gmii_txd=8'h55;SFD:gmii_txd=8'hd5;DATA:gmii_txd=held;
   FCS:case(fcs_index)0:gmii_txd=fcs[7:0];1:gmii_txd=fcs[15:8];2:gmii_txd=fcs[23:16];3:gmii_txd=fcs[31:24];endcase
  endcase
 end
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;pre<=0;gap<=0;fcs_index<=0;remaining<=0;vlid<=0;held<=0;crc<=32'hffffffff;fcs<=0;
   direct_done<=0;direct_reject<=0;last_received<=0;direct_completed_vlid<=0;
  end else begin
   direct_done<=0;direct_reject<=0;
   case(state)
    IDLE:if(fire)begin
     vlid<=client_vlid;
     if(!client_direct)state<=client_eop?SERVICE_WAIT:SERVICE_FILL;
     else if(first_legal)begin
      held<=client_data;remaining<=client_length;state<=PRE;pre<=0;crc<=32'hffffffff;last_received<=0;
     end else if(client_eop)direct_reject<=1;else state<=DROP;
    end
    PRE:if(pre==6)state<=SFD;else pre<=pre+1'b1;
    SFD:state<=DATA;
    DATA:begin
     crc<=next_crc;remaining<=remaining-1'b1;
     if(remaining==1)begin fcs<=~next_crc;fcs_index<=0;state<=FCS;end
     else if(underflow||client_sop||(client_eop&&remaining!=2)||(!client_eop&&remaining==2))begin
      direct_reject<=1;state<=GAP;gap<=0;
     end else begin held<=client_data;last_received<=client_eop;end
    end
    FCS:if(fcs_index==3)begin direct_done<=1;direct_completed_vlid<=vlid;state<=GAP;gap<=0;end else fcs_index<=fcs_index+1'b1;
    GAP:if(gap==11)state<=IDLE;else gap<=gap+1'b1;
    SERVICE_FILL:if(fire&&client_eop)state<=SERVICE_WAIT;
    SERVICE_WAIT:if(service_done||service_reject)begin state<=SERVICE_GAP;gap<=0;end
    SERVICE_GAP:if(gap==13)state<=IDLE;else gap<=gap+1'b1;
    DROP:if(fire&&client_eop)begin direct_reject<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
