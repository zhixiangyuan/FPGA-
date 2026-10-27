// Business application endpoint. Full Ethernet encoding/FCS and both receive
// paths are in RTL. The testbench supplies only application bytes and wires
// the two independent GMII networks (optionally with faults/delay).
// Management services share the same dual-network sender at frame boundaries.
module afdx_competition_core #(
 parameter integer TX_VL_COUNT=128,RX_VL_COUNT=4096,TX_SLOTS=16,
 parameter integer MANAGEMENT_ENABLE=1,SNTP_AUTO_ENABLE=1,
 parameter [15:0] VL_BASE=16'h1234,
 parameter [47:0] ES_MAC=48'h020000000009,PEER_MAC=48'h020000000009,
 parameter [31:0] ES_IP=32'h0a000001,PEER_IP=32'h0a000001,
 parameter [31:0] GROUP_IP=32'he0e0003c,
 parameter [31:0] BAG_CYCLES=125000,
 parameter [31:0] RECOVERY_CYCLES=625000,
 parameter [47:0] MANAGER_MAC=48'h02000000000a,
 parameter [31:0] MANAGER_IP=32'h0a000009
)(
 input wire clk,reset,
 input wire [7:0] tx_data,input wire tx_valid,output wire tx_ready,
 output wire [7:0] rx_data,output wire rx_valid,input wire rx_ready,
 output wire rx_sop,rx_eop,initialized,
 output wire [7:0] gmii_a_txd,gmii_b_txd,
 output wire gmii_a_tx_en,gmii_b_tx_en,gmii_a_tx_er,gmii_b_tx_er,
 input wire [7:0] gmii_a_rxd,gmii_b_rxd,
 input wire gmii_a_rx_dv,gmii_b_rx_dv,gmii_a_rx_er,gmii_b_rx_er,
 output wire [31:0] app_accepted,app_rejected,app_sent,
 output wire [31:0] rx_delivered,rx_duplicates,rx_integrity_errors,
 output wire [31:0] mac_a_dropped,mac_b_dropped,
 output wire [31:0] parser_a_rejected,parser_b_rejected,
 output wire [31:0] snmp_requests,snmp_responses,service_errors,
 output wire time_synchronized
);
 localparam [15:0] MGMT_BASE=VL_BASE+TX_VL_COUNT;
 wire msg_valid,msg_ready,pvalid,pready,plast,msg_done,msg_error,tx_ready_raw;
 wire [15:0] msg_vlid;wire [10:0] msg_length;wire [7:0] pdata;
 wire send_valid,send_ready,send_pvalid,send_pready,send_plast,service_active;
 wire [15:0] send_vlid,send_src_port,send_dst_port;
 wire [10:0] send_length;wire [7:0] send_data;
 wire [7:0] frame_data;wire frame_valid,frame_ready,frame_sop,frame_eop,frame_afdx;
 wire [15:0] frame_length;
 wire [1:0] ready,done,reject;
 reg [1:0] done_seen;
 wire pair_done=&(done|done_seen);
 always @(posedge clk)begin
  if(reset||msg_done||msg_error)done_seen<=0;else done_seen<=done_seen|done;
 end
 afdx_app_tx_queue #(.VL_COUNT(TX_VL_COUNT),.SLOTS(TX_SLOTS),.VL_BASE(VL_BASE),.BAG_CYCLES(BAG_CYCLES)) queue(
  .clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid&&initialized),.tx_ready(tx_ready_raw),
  .msg_valid(msg_valid),.msg_ready(msg_ready),.msg_vlid(msg_vlid),.msg_length(msg_length),
  .payload_data(pdata),.payload_valid(pvalid),.payload_ready(pready),.payload_last(plast),
  .msg_done(msg_done&&!service_active),.msg_error(msg_error&&!service_active),.gmii_tx_en(gmii_a_tx_en&&!service_active),
  .accepted_count(app_accepted),.rejected_count(app_rejected),.sent_count(app_sent),.occupied());
 assign tx_ready=tx_ready_raw&&initialized;
 afdx_multi_vl_tx #(.VL_COUNT(TX_VL_COUNT+(MANAGEMENT_ENABLE!=0?3:0)),.VL_BASE(VL_BASE)) sender(
  .clk(clk),.reset(reset),.msg_valid(send_valid),.msg_ready(send_ready),.msg_payload_length(send_length),
  .msg_da_const(32'h03000000),.msg_vlid(send_vlid),.msg_src_mac(ES_MAC),.msg_src_ip(ES_IP),
  .msg_dst_ip(service_active?MANAGER_IP:GROUP_IP),.msg_src_port(send_src_port),.msg_dst_port(send_dst_port),.msg_ttl(8'd1),
  .msg_bag_cycles(BAG_CYCLES),.msg_jitter_cycles(32'd12500),
  .payload_data(send_data),.payload_valid(send_pvalid),.payload_ready(send_pready),.payload_last(send_plast),.payload_abort(1'b0),
  .mac_tx_data(frame_data),.mac_tx_valid(frame_valid),.mac_tx_ready(frame_ready),
  .mac_tx_sop(frame_sop),.mac_tx_eop(frame_eop),.mac_tx_length(frame_length),.mac_tx_afdx(frame_afdx),
  .mac_tx_done(pair_done),.mac_tx_reject(|reject),.gmii_tx_en(gmii_a_tx_en),
  .msg_done(msg_done),.msg_error(msg_error),.error_code(),.late_count());
 assign frame_ready=&ready;
 wire [7:0] network_txd[0:1],network_rxd[0:1];
 wire [1:0] network_en,network_er,network_dv,network_rx_er;
 assign gmii_a_txd=network_txd[0];assign gmii_b_txd=network_txd[1];
 assign gmii_a_tx_en=network_en[0];assign gmii_b_tx_en=network_en[1];
 assign gmii_a_tx_er=network_er[0];assign gmii_b_tx_er=network_er[1];
 assign network_rxd[0]=gmii_a_rxd;assign network_rxd[1]=gmii_b_rxd;
 assign network_dv={gmii_b_rx_dv,gmii_a_rx_dv};assign network_rx_er={gmii_b_rx_er,gmii_a_rx_er};
 wire [7:0] candidate_data[0:1],candidate_sn[0:1];
 wire [15:0] candidate_vlid[0:1];wire [10:0] candidate_length[0:1];
 wire [1:0] candidate_valid,candidate_ready,candidate_sop,candidate_eop,candidate_discard;
 wire [31:0] mac_drop[0:1],parse_drop[0:1];
 wire [7:0] svc_data[0:1],svc_sn[0:1];wire [15:0] svc_vlid[0:1],svc_src[0:1],svc_dst[0:1];
 wire [10:0] svc_length[0:1];wire [1:0] svc_valid,svc_ready,svc_sop,svc_eop,svc_discard;
 wire [7:0] svc_rx_data;wire svc_rx_valid,svc_rx_ready,svc_rx_sop,svc_rx_eop;
 wire [15:0] svc_rx_vlid,svc_rx_src,svc_rx_dst;wire [10:0] svc_rx_length;
 wire business_initialized,service_initialized;
 assign initialized=business_initialized&&service_initialized;
 assign mac_a_dropped=mac_drop[0];assign mac_b_dropped=mac_drop[1];
 assign parser_a_rejected=parse_drop[0];assign parser_b_rejected=parse_drop[1];
 genvar net;
 generate for(net=0;net<2;net=net+1)begin: network
  wire [7:0] mac_data;wire mac_valid,mac_ready,mac_sop,mac_eop;wire [15:0] mac_length;
  wire business_ready,service_ready;
  assign mac_ready=business_ready&&service_ready;
  // Atomic fork: either both MACs consume this client byte, or neither does.
  mac_gmii_tx mac_tx(.clk(clk),.reset(reset),.client_data(frame_data),.client_valid(frame_valid&&ready[1-net]),
   .client_sop(frame_sop),.client_eop(frame_eop),.client_length(frame_length),.client_afdx_prepared(frame_afdx),.client_ready(ready[net]),
   .gmii_txd(network_txd[net]),.gmii_tx_en(network_en[net]),.gmii_tx_er(network_er[net]),
   .done(done[net]),.reject(reject[net]),.sent_frames(),.rejected_frames(),.counter_saturated());
  afdx_mac_rx_buffered #(.BANKS(16)) mac_rx(.clk(clk),.reset(reset),
   .gmii_rxd(network_rxd[net]),.gmii_rx_dv(network_dv[net]),.gmii_rx_er(network_rx_er[net]),
   .client_data(mac_data),.client_valid(mac_valid),.client_sop(mac_sop),.client_eop(mac_eop),.client_ready(mac_ready),.client_length(mac_length),
   .accepted(),.dropped(),.drop_reason(),.seen_frames(),.good_frames(),.drop_frames(mac_drop[net]),
   .delivered_frames(),.banks_busy(),.counter_saturated());
  afdx_multi_vl_rx_parser #(.VL_COUNT(RX_VL_COUNT),.ENABLE_DISCARD(1)) parser(
   .clk(clk),.reset(reset),.in_data(mac_data),.in_valid(mac_valid&&service_ready),.in_ready(business_ready),
   .in_sop(mac_sop),.in_eop(mac_eop),.in_length(mac_length),
   .cfg_da_prefix(32'h03000000),.cfg_vlid(VL_BASE),.cfg_src_mac(PEER_MAC),
   .cfg_src_ip(PEER_IP),.cfg_dst_ip(GROUP_IP),.cfg_src_port(16'd24),.cfg_dst_port(16'd23),
   .payload_data(candidate_data[net]),.payload_valid(candidate_valid[net]),.payload_ready(candidate_ready[net]),
   .payload_sop(candidate_sop[net]),.payload_eop(candidate_eop[net]),.payload_length(candidate_length[net]),
   .payload_vlid(candidate_vlid[net]),.payload_sn_unchecked(candidate_sn[net]),.payload_src_port(),.payload_dst_port(),
   .candidate_accepted(),.candidate_rejected(),.reject_reason(),.accepted_count(),.rejected_count(parse_drop[net]),.banks_busy(),
   .payload_discard(candidate_discard[net]));
  if(MANAGEMENT_ENABLE!=0)begin: management
   afdx_multi_vl_rx_parser #(.VL_COUNT(3),.CHECK_PORTS(0),.ENABLE_DISCARD(1)) parser(
    .clk(clk),.reset(reset),.in_data(mac_data),.in_valid(mac_valid&&business_ready),.in_ready(service_ready),
    .in_sop(mac_sop),.in_eop(mac_eop),.in_length(mac_length),
    .cfg_da_prefix(32'h03000000),.cfg_vlid(MGMT_BASE),.cfg_src_mac(MANAGER_MAC),
    .cfg_src_ip(MANAGER_IP),.cfg_dst_ip(ES_IP),.cfg_src_port(16'd0),.cfg_dst_port(16'd0),
    .payload_data(svc_data[net]),.payload_valid(svc_valid[net]),.payload_ready(svc_ready[net]),
    .payload_sop(svc_sop[net]),.payload_eop(svc_eop[net]),.payload_length(svc_length[net]),
    .payload_vlid(svc_vlid[net]),.payload_sn_unchecked(svc_sn[net]),
    .payload_src_port(svc_src[net]),.payload_dst_port(svc_dst[net]),
    .candidate_accepted(),.candidate_rejected(),.reject_reason(),.accepted_count(),.rejected_count(),.banks_busy(),
    .payload_discard(svc_discard[net]));
  end else begin: no_management
   assign service_ready=1'b1;assign svc_valid[net]=0;assign svc_sop[net]=0;assign svc_eop[net]=0;
   assign svc_data[net]=0;assign svc_sn[net]=0;assign svc_length[net]=0;assign svc_vlid[net]=0;
   assign svc_src[net]=0;assign svc_dst[net]=0;
  end
 end endgenerate
 afdx_redundant_rx #(.VL_COUNT(RX_VL_COUNT),.FAST_DISCARD(1),.VL_BASE(VL_BASE),.RECOVERY_CYCLES(RECOVERY_CYCLES)) receiver(
  .clk(clk),.reset(reset),
  .a_data(candidate_data[0]),.a_valid(candidate_valid[0]),.a_ready(candidate_ready[0]),
  .a_sop(candidate_sop[0]),.a_eop(candidate_eop[0]),.a_vlid(candidate_vlid[0]),.a_sn(candidate_sn[0]),.a_length(candidate_length[0]),
  .a_src_port(16'd24),.a_dst_port(16'd23),
  .b_data(candidate_data[1]),.b_valid(candidate_valid[1]),.b_ready(candidate_ready[1]),
  .b_sop(candidate_sop[1]),.b_eop(candidate_eop[1]),.b_vlid(candidate_vlid[1]),.b_sn(candidate_sn[1]),.b_length(candidate_length[1]),
  .b_src_port(16'd24),.b_dst_port(16'd23),
  .rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),.rx_sop(rx_sop),.rx_eop(rx_eop),.initialized(business_initialized),
  .a_discard(candidate_discard[0]),.b_discard(candidate_discard[1]),
  .rx_vlid(),.rx_src_port(),.rx_dst_port(),.rx_length(),
  .delivered_count(rx_delivered),.duplicate_count(rx_duplicates),.integrity_error_count(rx_integrity_errors),.control_count());
 generate if(MANAGEMENT_ENABLE!=0)begin: services
  wire poll;
  afdx_poll_timer #(.START_CYCLES(8192),.PERIOD_CYCLES(2000000000)) timer(
   .clk(clk),.reset(reset),.request(poll));
  afdx_redundant_rx #(.VL_COUNT(3),.FAST_DISCARD(1),.PREFIX_VLID(0),.VL_BASE(MGMT_BASE)) receiver(
   .clk(clk),.reset(reset),
   .a_data(svc_data[0]),.a_valid(svc_valid[0]),.a_ready(svc_ready[0]),.a_sop(svc_sop[0]),.a_eop(svc_eop[0]),
   .a_vlid(svc_vlid[0]),.a_sn(svc_sn[0]),.a_length(svc_length[0]),.a_src_port(svc_src[0]),.a_dst_port(svc_dst[0]),
   .b_data(svc_data[1]),.b_valid(svc_valid[1]),.b_ready(svc_ready[1]),.b_sop(svc_sop[1]),.b_eop(svc_eop[1]),
   .b_vlid(svc_vlid[1]),.b_sn(svc_sn[1]),.b_length(svc_length[1]),.b_src_port(svc_src[1]),.b_dst_port(svc_dst[1]),
   .rx_data(svc_rx_data),.rx_valid(svc_rx_valid),.rx_ready(svc_rx_ready),.rx_sop(svc_rx_sop),.rx_eop(svc_rx_eop),
   .rx_vlid(svc_rx_vlid),.rx_length(svc_rx_length),.rx_src_port(svc_rx_src),.rx_dst_port(svc_rx_dst),
   .initialized(service_initialized),.a_discard(svc_discard[0]),.b_discard(svc_discard[1]),
   .delivered_count(),.duplicate_count(),.integrity_error_count(),.control_count());
  afdx_management_plane #(.ES_IP(ES_IP),.MANAGER_IP(MANAGER_IP),.MANAGER_MAC(MANAGER_MAC),.SNTP_SERVER_IP(MANAGER_IP),
   .MGMT_VLID(MGMT_BASE),.SNTP_VLID(MGMT_BASE+16'd1),.LOAD_VLID(MGMT_BASE+16'd2)) plane(
   .clk(clk),.reset(reset),.svc_data(svc_rx_data),.svc_valid(svc_rx_valid),.svc_ready(svc_rx_ready),
   .svc_sop(svc_rx_sop),.svc_eop(svc_rx_eop),.svc_length(svc_rx_length),.svc_vlid(svc_rx_vlid),
   .svc_src_port(svc_rx_src),.svc_dst_port(svc_rx_dst),
   .host_msg_valid(msg_valid),.host_msg_ready(msg_ready),.host_vlid(msg_vlid),.host_length(msg_length),
   .host_data(pdata),.host_valid(pvalid),.host_ready(pready),.host_last(plast),
   .out_msg_valid(send_valid),.out_msg_ready(send_ready),.out_length(send_length),.out_vlid(send_vlid),
   .out_src_port(send_src_port),.out_dst_port(send_dst_port),.out_data(send_data),.out_valid(send_pvalid),
   .out_ready(send_pready),.out_last(send_plast),.finish(msg_done),.error(msg_error),.gmii_en(gmii_a_tx_en),
   .time_request(poll&&(SNTP_AUTO_ENABLE!=0)),.active_service(service_active),
   .snmp_requests(snmp_requests),.snmp_responses(snmp_responses),.service_errors(service_errors),.time_synchronized(time_synchronized));
 end else begin: business_only
  assign service_initialized=1'b1;
  assign send_valid=msg_valid;assign msg_ready=send_ready;assign send_length=msg_length;assign send_vlid=msg_vlid;
  assign send_src_port=16'd24;assign send_dst_port=16'd23;
  assign send_data=pdata;assign send_pvalid=pvalid;assign pready=send_pready;assign send_plast=plast;
  assign service_active=0;assign svc_ready=2'b11;assign svc_discard=0;
  assign snmp_requests=0;assign snmp_responses=0;assign service_errors=0;assign time_synchronized=0;
 end endgenerate
endmodule
