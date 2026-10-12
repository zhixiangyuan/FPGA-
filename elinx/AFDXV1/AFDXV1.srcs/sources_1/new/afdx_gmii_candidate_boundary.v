// Team candidate: continuous valid means a full GMII wire frame, 1 byte/clock.
// No PHY_ER pin exists in the eight-port contract; explicitly tie it low.
module afdx_gmii_candidate_boundary(
 input wire [7:0] rx_data,input wire rx_valid,
 output wire [7:0] gmii_rxd,output wire gmii_rx_dv,gmii_rx_er,
 input wire [7:0] gmii_txd,input wire gmii_tx_en,
 output wire [7:0] tx_data,output wire tx_valid
);
 assign gmii_rxd=rx_data;assign gmii_rx_dv=rx_valid;assign gmii_rx_er=1'b0;
 assign tx_data=gmii_txd;assign tx_valid=gmii_tx_en;
endmodule
