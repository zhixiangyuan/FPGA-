`timescale 1ns/1ps
module tb_submission;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;
 reg [7:0] rx_data=0;reg rx_valid=0,rx_ready=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.rx_data(rx_data),
  .tx_valid(tx_valid),.rx_valid(rx_valid),.tx_ready(tx_ready),.rx_ready(rx_ready));
 `include "golden/constants.vh"
 reg [7:0] input_bytes[0:RX_BYTES-1];
 integer cycle=0,age=0,epoch=-1,frames=0,frame_size=0,frame_start=0;
 integer fd,ef,cf;
 reg previous_valid=0;
 wire unit_request;
 afdx_poll_timer #(.START_CYCLES(1),.PERIOD_CYCLES(7)) unit_timer(
  .clk(clk),.reset(reset),.request(unit_request));
 always @(posedge clk)begin
  cycle=cycle+1;
  if(reset)age=0;else age=age+1;
  if(tx_valid)begin
   if(reset)$fatal(1,"TX while reset");
   if(!previous_valid)begin frame_start=cycle;frame_size=0;end
   $fwrite(fd,"%02x\n",tx_data);frame_size=frame_size+1;
  end
  if(previous_valid&&!tx_valid)begin
   $fwrite(ef,"%0d,%0d,%0d,%0d,%0d,%0d\n",frames,epoch,frame_start,cycle-1,frame_size,age);
   frames=frames+1;
  end
  previous_valid=tx_valid;
  // Independent timer oracle: first active edge, then every seven edges.
  #1;
  if(!reset&&age<60&&unit_request!==(((age-1)%7)==0))$fatal(1,"Poll timer phase/period");
  if(tx_ready!==1'b0)$fatal(1,"valid-only output contract");
 end
 task idle(input integer n);
  repeat(n)@(negedge clk);
 endtask
 task restart;
  begin
   @(negedge clk);reset=1;rx_valid=0;rx_data=0;
   idle(4);epoch=epoch+1;reset=0;
  end
 endtask
 task send_frame(input integer offset,input integer size);
  integer j;
  begin
   for(j=0;j<size;j=j+1)begin
    rx_data=input_bytes[offset+j];rx_valid=1;
    // The official valid-only stream must ignore changing rx_ready.
    rx_ready=~rx_ready;@(negedge clk);
   end
   rx_valid=0;rx_data=0;idle(16);
  end
 endtask
 task wait_frames(input integer target);
  integer watchdog;
  begin
   watchdog=0;
   while(frames<target&&watchdog<260000)begin idle(1);watchdog=watchdog+1;end
   if(frames!=target)$fatal(1,"TX frame wait target=%0d actual=%0d",target,frames);
  end
 endtask
 task require_frames(input integer target);
  if(frames!=target)$fatal(1,"Unexpected output target=%0d actual=%0d",target,frames);
 endtask
 task synchronized_time;
  begin
   idle(1000);
   if(dut.core.rtc_synchronized!==1'b1||dut.core.rtc_sync_count!==32'd1)
    $fatal(1,"Autonomous SNTP failed to synchronize");
  end
 endtask
 initial begin #40000000;$fatal(1,"Submission timeout");end
 initial begin
  fd=$fopen("actual_tx.mem","w");ef=$fopen("tx_events.csv","w");cf=$fopen("counters.csv","w");
  $fwrite(ef,"frame,epoch,start_cycle,end_cycle,bytes,age\n");
  $readmemh("golden/rx_wire.mem",input_bytes);
  `include "golden/stimulus.vh"
  $fwrite(cf,"key,value\nframes,%0d\nuptime,%0d\n",frames,dut.core.uptime_ticks);
  $fclose(fd);$fclose(ef);$fclose(cf);
  $display("SUBMISSION_RTL_PASS frames=%0d",frames);$finish;
 end
endmodule
