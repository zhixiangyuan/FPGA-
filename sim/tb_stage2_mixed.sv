`timescale 1ns/1ps
module tb_stage2_mixed;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] rx_data=0;reg rx_valid=0;
 reg rx_ready=0,sntp_start=0;reg [31:0] uptime=12345;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 `ifdef MGMT_LOAD_CORE
 `define MANAGEMENT_DUT afdx_stage3_mgmt_top
 `else
 `define MANAGEMENT_DUT afdx_stage2_mgmt_top
 `endif
 `MANAGEMENT_DUT dut(.clk(clk),.reset(reset),.rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),
  .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),.uptime_override(uptime),
  .uptime_override_en(1'b1),.sntp_request_start(sntp_start));
 `include "golden/constants.vh"
 reg [7:0] input_bytes[0:RX_BYTES-1];
 reg [127:0] schedule[0:CASE_COUNT-1];
 integer cycle=0,i,j,start_at,offset,size,first_cycle;
 integer data_fd,tx_fd,rx_fd,count_fd,tx_start,tx_size=0,tx_count=0;
 reg previous_tx=0;
 always @(posedge clk)begin
  if(reset)cycle<=0;else cycle<=cycle+1;
  if(!reset)begin
   if(tx_ready!==1'b0)$fatal(1,"valid-only tx_ready contract");
   if(tx_valid&&!previous_tx)begin tx_start=cycle;tx_size=0;end
   if(tx_valid)begin
    if(^tx_data===1'bx)$fatal(1,"unknown TX byte");
    $fwrite(data_fd,"%02x\n",tx_data);tx_size=tx_size+1;
   end
   if(!tx_valid&&previous_tx)begin
    $fwrite(tx_fd,"%0d,%0d,%0d,%0d\n",tx_count,tx_start,cycle-1,tx_size);tx_count=tx_count+1;
   end
   previous_tx<=tx_valid;
  end
 end
 initial begin #600000000;$fatal(1,"mixed traffic timeout");end
 initial begin
  $readmemh("golden/rx_wire.mem",input_bytes);$readmemh("golden/schedule.mem",schedule);
  data_fd=$fopen("actual_tx.mem","w");tx_fd=$fopen("tx_events.csv","w");
  rx_fd=$fopen("rx_events.csv","w");count_fd=$fopen("counters.csv","w");
  $fwrite(tx_fd,"frame,start_cycle,end_cycle,bytes\n");$fwrite(rx_fd,"id,start_cycle,end_cycle,bytes\n");
  repeat(4)@(negedge clk);
  `ifdef MGMT_LOAD_CORE
  if(dut.mgmt_gate.cfg_integrity_enable!==3'b111)
  `else
  if(dut.mgmt_gate.cfg_integrity_enable!==2'b11)
  `endif
   $fatal(1,"unknown/incomplete service integrity configuration");
  reset=0;sntp_start=1;
  @(negedge clk);sntp_start=0;
  for(i=0;i<CASE_COUNT;i=i+1)begin
   start_at=schedule[i][127:96];offset=schedule[i][95:64];size=schedule[i][63:32];
   while(cycle<start_at)@(negedge clk);
   uptime=schedule[i][31:0];first_cycle=cycle;
   for(j=0;j<size;j=j+1)begin
    // Toggle the external ready input during frames to test the FAQ contract.
    rx_ready=(cycle%3)==0;rx_data=input_bytes[offset+j];rx_valid=1;@(negedge clk);
   end
   rx_valid=0;rx_data=0;$fwrite(rx_fd,"%0d,%0d,%0d,%0d\n",i,first_cycle,cycle-1,size);
  end
  begin : drain
   fork
    begin wait(tx_count>=EXPECTED_FRAMES);end
    begin repeat(500000)@(negedge clk);$fatal(1,"drain timeout got=%0d expected=%0d",tx_count,EXPECTED_FRAMES);end
   join_any
   disable drain;
  end
  repeat(20000)@(negedge clk);
  $fwrite(count_fd,"key,value\n");
  $fwrite(count_fd,"stored,%0d\nsent,%0d\nqueue_error,%0d\n",dut.stored_count,dut.sent_count,dut.queue_error_count);
  $fwrite(count_fd,"snmp_request,%0d\nsnmp_response,%0d\nsnmp_error,%0d\n",dut.snmp_request_count,dut.snmp_response_count,dut.snmp_error_count);
  $fwrite(count_fd,"snmp_overflow,%0d\nsntp_overflow,%0d\narbiter_error,%0d\n",dut.snmp_fifo_overflow_count,dut.sntp_fifo_overflow_count,dut.arbiter_service_error_count);
  $fwrite(count_fd,"sntp_accepted,%0d\nsntp_rejected,%0d\nsntp_timeout,%0d\nrtc_sync,%0d\n",dut.sntp_accepted_count,dut.sntp_rejected_count,dut.sntp_timeout_count,dut.rtc_sync_count);
  $fwrite(count_fd,"t1,0x%h\nt2,0x%h\nt3,0x%h\nt4,0x%h\noffset,0x%h\ndelay,0x%h\n",dut.sntp_t1,dut.sntp_t2,dut.sntp_t3,dut.sntp_t4,dut.rtc_last_offset,dut.rtc_last_delay);
  $fclose(data_fd);$fclose(tx_fd);$fclose(rx_fd);$fclose(count_fd);
  $display("MIXED_TRAFFIC = PASS input_frames=%0d tx_frames=%0d",CASE_COUNT,tx_count);$finish;
 end
endmodule
