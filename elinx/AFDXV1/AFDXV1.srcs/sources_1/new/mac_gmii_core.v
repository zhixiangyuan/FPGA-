module mac_gmii_core #(parameter [31:0] COUNTER_MAX=32'hffffffff)(
 input wire clk,reset,input wire [7:0] tx_data,input wire tx_valid,tx_sop,tx_eop,
 input wire [15:0] tx_length,input wire tx_afdx,output wire tx_ready,
 output wire [7:0] gmii_txd,output wire gmii_tx_en,gmii_tx_er,
 input wire [7:0] gmii_rxd,input wire gmii_rx_dv,gmii_rx_er,
 output wire [7:0] rx_data,output wire rx_valid,rx_sop,rx_eop,input wire rx_ready,
 output wire [15:0] rx_length,output wire tx_done,tx_reject,rx_accepted,rx_dropped,
 output wire [4:0] rx_drop_reason,output wire [31:0] tx_sent,tx_rejected,
 output wire [31:0] rx_seen,rx_good,rx_drop,rx_delivered,output wire [1:0] rx_banks_busy,
 output wire counter_saturated
);
 wire tx_sat,rx_sat;assign counter_saturated=tx_sat||rx_sat;
 mac_gmii_tx #(.COUNTER_MAX(COUNTER_MAX)) tx(.clk(clk),.reset(reset),.client_data(tx_data),.client_valid(tx_valid),.client_ready(tx_ready),
  .client_sop(tx_sop),.client_eop(tx_eop),.client_length(tx_length),.client_afdx_prepared(tx_afdx),
  .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),.done(tx_done),.reject(tx_reject),
  .sent_frames(tx_sent),.rejected_frames(tx_rejected),.counter_saturated(tx_sat));
 mac_gmii_rx #(.COUNTER_MAX(COUNTER_MAX)) rx(.clk(clk),.reset(reset),.gmii_rxd(gmii_rxd),.gmii_rx_dv(gmii_rx_dv),.gmii_rx_er(gmii_rx_er),
  .client_data(rx_data),.client_valid(rx_valid),.client_ready(rx_ready),.client_sop(rx_sop),.client_eop(rx_eop),
  .client_length(rx_length),.accepted(rx_accepted),.dropped(rx_dropped),.drop_reason(rx_drop_reason),
  .seen_frames(rx_seen),.good_frames(rx_good),.drop_frames(rx_drop),.delivered_frames(rx_delivered),.banks_busy(rx_banks_busy),.counter_saturated(rx_sat));
endmodule
