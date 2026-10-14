`timescale 1ns/1ps
module tb_stage2_mgmt;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] gmii_rxd=0;reg gmii_rx_dv=0;
 reg rx_ready=0;
 reg [31:0] uptime_override=0;
 reg sntp_request_start=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 afdx_stage2_mgmt_top dut(.clk(clk),.reset(reset),.rx_data(gmii_rxd),.rx_valid(gmii_rx_dv),.rx_ready(rx_ready),
  .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .uptime_override(uptime_override),.uptime_override_en(1'b1),
  .sntp_request_start(sntp_request_start));
 `include "golden/constants.vh"
 reg [7:0] rx_bytes[0:RX_BYTES-1];
 reg [63:0] frames[0:FRAME_COUNT-1];
 reg [31:0] uptimes[0:FRAME_COUNT-1];
 integer cycle=0,i,j,fd,efd,cfd,rfd,rx_start=0,rx_end=0;
 integer tx_index=0,tx_frame=0,tx_start=0,tx_bytes_total=0,offset=0,length=0;
 reg tx_d=0;
 // Handshake stall watch: these nets exist in the top as named observability
 // wires, so they survive vopt inlining of the service modules.
 integer biz_valid_cycles=0,biz_stall_cycles=0,last_biz_valid=0;
 integer tx_valid_cycles=0,last_tx_msg_valid=0,service_active_cycles=0;
 always @(posedge clk)begin
  if(dut.biz_msg_valid)begin
   last_biz_valid=cycle;biz_valid_cycles=biz_valid_cycles+1;
   if(!dut.biz_msg_ready)biz_stall_cycles=biz_stall_cycles+1;
  end
  if(dut.tx_msg_valid)begin last_tx_msg_valid=cycle;tx_valid_cycles=tx_valid_cycles+1;end
  if(dut.service_active)service_active_cycles=service_active_cycles+1;
 end
 always @(posedge clk)begin
  cycle=cycle+1;
  if(tx_valid&&!tx_d)begin tx_start=cycle;tx_index=0;end
  if(tx_valid)begin $fwrite(fd,"%02X\n",tx_data);tx_index=tx_index+1;tx_bytes_total=tx_bytes_total+1;end
  if(!tx_valid&&tx_d)begin
   $fwrite(efd,"%0d,%0d,%0d,%0d\n",tx_frame,tx_start,cycle-1,tx_index);
   tx_frame=tx_frame+1;
  end
  tx_d<=tx_valid;
 end
 initial begin #250000000;$fatal(1,"System timeout");end
 initial begin
  $readmemh("golden/rx_wire.mem",rx_bytes);
  $readmemh("golden/frames.mem",frames);
  $readmemh("golden/uptime.mem",uptimes);
  fd=$fopen("actual_tx.mem","w");
  efd=$fopen("tx_events.csv","w");
  cfd=$fopen("counters.csv","w");
  rfd=$fopen("rx_events.csv","w");
  $fwrite(efd,"frame,start_cycle,end_cycle,bytes\n");
  $fwrite(rfd,"frame,start_cycle,end_cycle,bytes\n");
  repeat(4)@(negedge clk);reset=0;
  // Start the time-service exchange before any SNMP traffic. Reset releases on
  // the documented RTC initial value, so the client captures exactly that value
  // as the request origin and the request frame is the first frame the shared
  // builder emits.
  sntp_request_start=1;
  @(negedge clk);sntp_request_start=0;
  repeat(240000)@(negedge clk);
  for(i=0;i<FRAME_COUNT;i=i+1)begin
   offset=frames[i][63:32];length=frames[i][31:0];
   // Drive the sysUpTime vector this frame expects, then hold it until the
   // next frame is injected so the agent samples a defined, intended value.
   uptime_override=uptimes[i];
   // The time-service request case has no GMII input of its own: the client
   // already emitted it when the test triggered the exchange.
   if(length>0)begin
    rx_start=cycle;
    for(j=0;j<length;j=j+1)begin gmii_rxd=rx_bytes[offset+j];gmii_rx_dv=1;@(negedge clk);end
    rx_end=cycle;gmii_rx_dv=0;gmii_rxd=0;
    $fwrite(rfd,"%0d,%0d,%0d,%0d\n",i,rx_start,rx_end,length);
    // Space incoming frames just past the 1 ms management bag, so the
    // single-message service buffers are free again before the next request.
    repeat(140000)@(negedge clk);
   end
  end
  repeat(200000)@(negedge clk);
  $fwrite(cfd,"key,value\n");
  $fwrite(cfd,"tx_frames,%0d\n",tx_frame);
  $fwrite(cfd,"tx_bytes,%0d\n",tx_bytes_total);
  $fwrite(cfd,"demux_routed,%0d\n",dut.demux_routed_count);
  $fwrite(cfd,"demux_dropped,%0d\n",dut.demux_dropped_count);
  $fwrite(cfd,"demux_last_dropped_port,%0d\n",dut.demux_last_dropped_port);
  $fwrite(cfd,"snmp_request,%0d\n",dut.snmp_request_count);
  $fwrite(cfd,"snmp_response,%0d\n",dut.snmp_response_count);
  $fwrite(cfd,"snmp_error,%0d\n",dut.snmp_error_count);
  $fwrite(cfd,"snmp_trap,%0d\n",dut.snmp_trap_count);
  $fwrite(cfd,"mgmt_parser_accepted,%0d\n",dut.mgmt_parser_accepted_count);
  $fwrite(cfd,"mgmt_parser_rejected,%0d\n",dut.mgmt_parser_rejected_count);
  $fwrite(cfd,"mgmt_gate_accepted,%0d\n",dut.mgmt_sn_accepted_count);
  $fwrite(cfd,"mgmt_gate_rejected,%0d\n",dut.mgmt_sn_rejected_count);
  $fwrite(cfd,"mgmt_gate_delivered,%0d\n",dut.mgmt_sn_delivered_count);
  $fwrite(cfd,"business_parser_accepted,%0d\n",dut.business_parser_accepted_count);
  $fwrite(cfd,"business_parser_rejected,%0d\n",dut.business_parser_rejected_count);
  $fwrite(cfd,"business_gate_accepted,%0d\n",dut.sn_accepted_count);
  $fwrite(cfd,"business_gate_delivered,%0d\n",dut.app_delivered_count);
  $fwrite(cfd,"application_stored,%0d\n",dut.stored_count);
  $fwrite(cfd,"application_sent,%0d\n",dut.sent_count);
  $fwrite(cfd,"application_error,%0d\n",dut.queue_error_count);
  $fwrite(cfd,"snmp_fifo_captured,%0d\n",dut.snmp_fifo_captured_count);
  $fwrite(cfd,"snmp_fifo_overflow,%0d\n",dut.snmp_fifo_overflow_count);
  $fwrite(cfd,"snmp_fifo_sent,%0d\n",dut.snmp_fifo_sent_count);
  $fwrite(cfd,"sntp_fifo_captured,%0d\n",dut.sntp_fifo_captured_count);
  $fwrite(cfd,"sntp_fifo_overflow,%0d\n",dut.sntp_fifo_overflow_count);
  $fwrite(cfd,"sntp_fifo_sent,%0d\n",dut.sntp_fifo_sent_count);
  $fwrite(cfd,"demux_sntp_routed,%0d\n",dut.demux_sntp_routed_count);
  $fwrite(cfd,"arbiter_snmp_sent,%0d\n",dut.arbiter_snmp_sent_count);
  $fwrite(cfd,"arbiter_sntp_sent,%0d\n",dut.arbiter_sntp_sent_count);
  $fwrite(cfd,"sntp_accepted,%0d\n",dut.sntp_accepted_count);
  $fwrite(cfd,"sntp_rejected,%0d\n",dut.sntp_rejected_count);
  $fwrite(cfd,"sntp_timeout,%0d\n",dut.sntp_timeout_count);
  $fwrite(cfd,"sntp_request_t1,0x%h\n",dut.sntp_request_t1);
  $fwrite(cfd,"sntp_t1,0x%h\n",dut.sntp_t1);
  $fwrite(cfd,"sntp_t2,0x%h\n",dut.sntp_t2);
  $fwrite(cfd,"sntp_t3,0x%h\n",dut.sntp_t3);
  $fwrite(cfd,"sntp_t4,0x%h\n",dut.sntp_t4);
  $fwrite(cfd,"sntp_rx_timestamp,0x%h\n",dut.sntp_rx_timestamp_hold);
  $fwrite(cfd,"rtc_synchronized,%0d\n",dut.rtc_synchronized);
  $fwrite(cfd,"rtc_sync_accepted,%0d\n",dut.rtc_sync_accepted);
  $fwrite(cfd,"rtc_sync_rejected,%0d\n",dut.rtc_sync_rejected);
  $fwrite(cfd,"rtc_sync_count,%0d\n",dut.rtc_sync_count);
  $fwrite(cfd,"rtc_error_count,%0d\n",dut.rtc_error_count);
  $fwrite(cfd,"rtc_last_offset,0x%h\n",dut.rtc_last_offset);
  $fwrite(cfd,"rtc_last_delay,0x%h\n",dut.rtc_last_delay);
  $fwrite(cfd,"rtc_utc_time,0x%h\n",dut.rtc_utc_time);
  $fwrite(cfd,"arbiter_service_sent,%0d\n",dut.arbiter_service_sent_count);
  $fwrite(cfd,"arbiter_service_error,%0d\n",dut.arbiter_service_error_count);
  $fwrite(cfd,"uptime_ticks,%0d\n",dut.uptime_ticks);
  $fwrite(cfd,"biz_msg_valid_end,%0d\n",dut.biz_msg_valid);
  $fwrite(cfd,"biz_msg_ready_end,%0d\n",dut.biz_msg_ready);
  $fwrite(cfd,"tx_msg_valid_end,%0d\n",dut.tx_msg_valid);
  $fwrite(cfd,"tx_msg_ready_end,%0d\n",dut.tx_msg_ready);
  $fwrite(cfd,"service_active_end,%0d\n",dut.service_active);
  $fwrite(cfd,"snmp_msg_valid_end,%0d\n",dut.snmp_msg_valid);
  $fwrite(cfd,"sntp_msg_valid_end,%0d\n",dut.sntp_msg_valid);
  $fwrite(cfd,"biz_valid_cycles,%0d\n",biz_valid_cycles);
  $fwrite(cfd,"biz_stall_cycles,%0d\n",biz_stall_cycles);
  $fwrite(cfd,"last_biz_valid_cycle,%0d\n",last_biz_valid);
  $fwrite(cfd,"tx_msg_valid_cycles,%0d\n",tx_valid_cycles);
  $fwrite(cfd,"last_tx_msg_valid_cycle,%0d\n",last_tx_msg_valid);
  $fwrite(cfd,"service_active_cycles,%0d\n",service_active_cycles);
  $fclose(fd);$fclose(efd);$fclose(cfd);$fclose(rfd);
  $display("MGMT_SERVICE_RUN frames=%0d tx_frames=%0d tx_bytes=%0d",FRAME_COUNT,tx_frame,tx_bytes_total);
  $finish;
 end
endmodule
