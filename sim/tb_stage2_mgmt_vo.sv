`timescale 1ns/1ps
module tb_stage2_mgmt_vo;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] gmii_rxd=0;reg gmii_rx_dv=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 reg [31:0] uptime_override=0;
 reg sntp_request_start=0;
 wire unused_rx_ready;
 afdx_stage2_mgmt_top dut(.clk(clk),.reset(reset),.rx_data(gmii_rxd),.rx_valid(gmii_rx_dv),.rx_ready(1'b0),
  .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
  .uptime_override(uptime_override),.uptime_override_en(1'b1),
  .sntp_request_start(sntp_request_start));
 `include "golden/constants.vh"
 reg [7:0] rx_bytes[0:RX_BYTES-1];
 reg [63:0] frames[0:FRAME_COUNT-1];
 reg [31:0] uptimes[0:FRAME_COUNT-1];
 reg expect_tx[0:FRAME_COUNT-1];
 integer cycle=0,i,j,fd,efd,rfd,rx_start=0,rx_end=0,next_heartbeat=25000;
 integer tx_index=0,tx_frame=0,tx_start=0,tx_bytes_total=0,offset=0,length=0,expected_tx_seen=1;
 reg tx_d=0;
 always @(posedge clk)begin
  cycle=cycle+1;
  if(cycle>=next_heartbeat)begin
   $display("MGMT_VO_PROGRESS cycle=%0d tx_frames=%0d",cycle,tx_frame);
   next_heartbeat=next_heartbeat+25000;
  end
  if(tx_valid&&!tx_d)begin tx_start=cycle;tx_index=0;end
  if(tx_valid)begin $fwrite(fd,"%02X\n",tx_data);tx_index=tx_index+1;tx_bytes_total=tx_bytes_total+1;end
  if(!tx_valid&&tx_d)begin
   $fwrite(efd,"%0d,%0d,%0d,%0d\n",tx_frame,tx_start,cycle-1,tx_index);
   $display("MGMT_VO_FRAME %0d bytes=%0d cycle=%0d",tx_frame,tx_index,tx_start);
   tx_frame=tx_frame+1;
  end
  tx_d<=tx_valid;
 end
 initial begin #250000000;$fatal(1,"VO system timeout");end
 initial begin
  $readmemh("golden/rx_wire.mem",rx_bytes);
  $readmemh("golden/frames.mem",frames);
  $readmemh("golden/uptime.mem",uptimes);
  $readmemh("tx_expect.mem",expect_tx);
  fd=$fopen("actual_tx.mem","w");
  efd=$fopen("tx_events.csv","w");
  rfd=$fopen("rx_events.csv","w");
  $fwrite(efd,"frame,start_cycle,end_cycle,bytes\n");
  $fwrite(rfd,"frame,start_cycle,end_cycle,bytes\n");
  repeat(4)@(negedge clk);reset=0;
  $display("MGMT_VO_CLOCK_STARTED");
  sntp_request_start=1;
  @(negedge clk);sntp_request_start=0;
  // Inject the server response only after the real SNTP request has left GMII.
  wait(tx_frame>=1);
  repeat(16)@(negedge clk);
  for(i=0;i<FRAME_COUNT;i=i+1)begin
   offset=frames[i][63:32];length=frames[i][31:0];
   uptime_override=uptimes[i];
   if(length>0)begin
    rx_start=cycle;
    for(j=0;j<length;j=j+1)begin gmii_rxd=rx_bytes[offset+j];gmii_rx_dv=1;@(negedge clk);end
    rx_end=cycle;gmii_rx_dv=0;gmii_rxd=0;
    $fwrite(rfd,"%0d,%0d,%0d,%0d\n",i,rx_start,rx_end,length);
   end
   if(expect_tx[i]&&i!=0)begin
    expected_tx_seen=expected_tx_seen+1;
    begin : wait_for_expected_frame
     fork
      begin wait(tx_frame>=expected_tx_seen);end
      begin
       repeat(160000)@(negedge clk);
       if(tx_frame<expected_tx_seen)$fatal(1,"VO output timeout expected=%0d got=%0d cycle=%0d",expected_tx_seen,tx_frame,cycle);
      end
     join_any
     disable wait_for_expected_frame;
    end
    // Wait a complete minimum BAG interval from the previous GMII frame end.
    repeat(125000)@(negedge clk);
   end else if(!expect_tx[i])repeat(500)@(negedge clk);
  end
  repeat(4)@(negedge clk);
  $fclose(fd);$fclose(efd);$fclose(rfd);
  $display("MGMT_VO_RUN cases=%0d tx_frames=%0d tx_bytes=%0d",FRAME_COUNT,tx_frame,tx_bytes_total);
  $finish;
 end
endmodule
