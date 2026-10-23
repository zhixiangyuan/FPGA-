// Official eight-port production target, fixed 125 MHz GMII profile.
// Compile with the submission source list; rtl/AFDX_top.v is the V1.0 target.
// Default time polling is 16 seconds, longer than the unchanged 1s timeout.
// RTC starts with a configured NTP era value and becomes synchronized only
// after a validated peer response. sysUpTime always uses the real 10ms counter.
module AFDX_top #(
 parameter [31:0] ES_IP=32'h0a000001,
 parameter [47:0] ES_MAC=48'h020000000009,
 parameter [31:0] MANAGER_IP=32'h0a000009,
 parameter [47:0] MANAGER_MAC=48'h02000000000a,
 parameter integer SNTP_AUTO_ENABLE=1,
 parameter integer SNTP_START_CYCLES=16,
 parameter integer SNTP_POLL_CYCLES=2000000000,
 parameter integer RX_POLICING_ENABLE=0,
 parameter [31:0] RX_BAG_CYCLES=32'd125000,
 parameter integer RX_MAX_FRAME_BYTES=1471
)(
 input wire clk,reset,
 output wire [7:0] tx_data,
 input wire [7:0] rx_data,
 output wire tx_valid,
 input wire rx_valid,
 output wire tx_ready,
 input wire rx_ready
);
 wire poll_request;
 generate if(SNTP_AUTO_ENABLE!=0)begin: auto_time
  afdx_poll_timer #(.START_CYCLES(SNTP_START_CYCLES),.PERIOD_CYCLES(SNTP_POLL_CYCLES)) timer(
   .clk(clk),.reset(reset),.request(poll_request));
 end else begin: no_auto_time
  assign poll_request=1'b0;
 end endgenerate
 afdx_stage3_mgmt_top #(.ES_IP(ES_IP),.ES_MAC(ES_MAC),
  .MANAGER_IP(MANAGER_IP),.MANAGER_MAC(MANAGER_MAC),.SNTP_SERVER_IP(MANAGER_IP),
  .RX_POLICING_ENABLE(RX_POLICING_ENABLE),.RX_BAG_CYCLES(RX_BAG_CYCLES),
  .RX_MAX_FRAME_BYTES(RX_MAX_FRAME_BYTES)) core(
  .clk(clk),.reset(reset),.tx_data(tx_data),.rx_data(rx_data),
  .tx_valid(tx_valid),.rx_valid(rx_valid),.tx_ready(tx_ready),.rx_ready(rx_ready),
  .uptime_override(32'd0),.uptime_override_en(1'b0),.sntp_request_start(poll_request));
endmodule
