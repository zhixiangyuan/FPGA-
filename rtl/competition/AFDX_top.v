// Application-evaluation wrapper. Each contiguous tx_valid burst consists of
// VLID high byte, VLID low byte, then 1..1471 payload bytes. A low-valid cycle
// ends the burst. At the start of a burst tx_ready must be high; the queue then
// reserves the whole slot. rx_data uses the same VLID+payload format, with
// rx_sop/rx_eop also exposed. rx_ready controls output byte consumption.
// GMII A/B are independent PHY links; a TB connects them to a peer/link model.
// clk is 125 MHz. reset is synchronous active high. Initialization is exposed.
module AFDX_top #(
 parameter integer TX_VL_COUNT=128,RX_VL_COUNT=4096,
 parameter integer MANAGEMENT_ENABLE=1,SNTP_AUTO_ENABLE=1,
 parameter [15:0] VL_BASE=16'h1234,
 parameter [47:0] ES_MAC=48'h020000000009,PEER_MAC=48'h020000000009,
 parameter [31:0] ES_IP=32'h0a000001,PEER_IP=32'h0a000001
)(
 input wire clk,reset,
 input wire [7:0] tx_data,input wire tx_valid,output wire tx_ready,
 output wire [7:0] rx_data,output wire rx_valid,input wire rx_ready,
 output wire rx_sop,rx_eop,initialized,
 output wire [7:0] gmii_a_txd,gmii_b_txd,
 output wire gmii_a_tx_en,gmii_b_tx_en,gmii_a_tx_er,gmii_b_tx_er,
 input wire [7:0] gmii_a_rxd,gmii_b_rxd,
 input wire gmii_a_rx_dv,gmii_b_rx_dv,gmii_a_rx_er,gmii_b_rx_er,
 input wire [3:0] status_select,output reg [31:0] status_data,
 output wire time_synchronized
);
 wire [31:0] app_accepted,app_rejected,app_sent,rx_delivered,rx_duplicates,rx_integrity_errors;
 wire [31:0] mac_a_dropped,mac_b_dropped,parser_a_rejected,parser_b_rejected;
 wire [31:0] snmp_requests,snmp_responses,service_errors;
 always @*begin
  case(status_select)
   0:status_data=app_accepted;1:status_data=app_rejected;2:status_data=app_sent;
   3:status_data=rx_delivered;4:status_data=rx_duplicates;5:status_data=rx_integrity_errors;
   6:status_data=mac_a_dropped;7:status_data=mac_b_dropped;
   8:status_data=parser_a_rejected;9:status_data=parser_b_rejected;
   10:status_data=snmp_requests;11:status_data=snmp_responses;12:status_data=service_errors;
   default:status_data=0;
  endcase
 end
 afdx_competition_core #(.TX_VL_COUNT(TX_VL_COUNT),.RX_VL_COUNT(RX_VL_COUNT),.VL_BASE(VL_BASE),
  .ES_MAC(ES_MAC),.PEER_MAC(PEER_MAC),.ES_IP(ES_IP),.PEER_IP(PEER_IP),
  .MANAGEMENT_ENABLE(MANAGEMENT_ENABLE),.SNTP_AUTO_ENABLE(SNTP_AUTO_ENABLE)) core(
  .clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),.rx_sop(rx_sop),.rx_eop(rx_eop),.initialized(initialized),
  .gmii_a_txd(gmii_a_txd),.gmii_b_txd(gmii_b_txd),.gmii_a_tx_en(gmii_a_tx_en),.gmii_b_tx_en(gmii_b_tx_en),
  .gmii_a_tx_er(gmii_a_tx_er),.gmii_b_tx_er(gmii_b_tx_er),.gmii_a_rxd(gmii_a_rxd),.gmii_b_rxd(gmii_b_rxd),
  .gmii_a_rx_dv(gmii_a_rx_dv),.gmii_b_rx_dv(gmii_b_rx_dv),.gmii_a_rx_er(gmii_a_rx_er),.gmii_b_rx_er(gmii_b_rx_er),
  .app_accepted(app_accepted),.app_rejected(app_rejected),.app_sent(app_sent),
  .rx_delivered(rx_delivered),.rx_duplicates(rx_duplicates),.rx_integrity_errors(rx_integrity_errors),
  .mac_a_dropped(mac_a_dropped),.mac_b_dropped(mac_b_dropped),.parser_a_rejected(parser_a_rejected),.parser_b_rejected(parser_b_rejected),
  .snmp_requests(snmp_requests),.snmp_responses(snmp_responses),.service_errors(service_errors),.time_synchronized(time_synchronized));
endmodule
