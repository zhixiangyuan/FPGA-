`timescale 1ns/1ps
module tb_rtc_timebase;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,sync_valid=0;
 reg [63:0] t1=0,t2=0,t3=0,t4=0;
 wire [63:0] utc_time,monotonic_cycles,last_delay;
 wire signed [63:0] last_offset;
 wire synchronized,sync_accepted,sync_rejected;
 wire [31:0] sync_count,error_count;
 afdx_rtc_timebase dut(.*);
 integer fd,outfd,kind,cycles,legal,nread,index=0,k;
 reg [63:0] held_utc,held_mono;
 initial begin
  fd=$fopen("golden/vectors.txt","r");outfd=$fopen("actual_rtc.csv","w");
  if(!fd||!outfd)$fatal(1,"Files missing");
  $fwrite(outfd,"index,monotonic_cycles,utc_time,last_offset,last_delay,accepted,rejected,sync_count,error_count\n");
  repeat(4)@(negedge clk);reset=0;
  while(!$feof(fd))begin
   nread=$fscanf(fd,"%d %d %h %h %h %h %d\n",kind,cycles,t1,t2,t3,t4,legal);
   if(nread!=7)$fatal(1,"Bad vector");
   sync_valid=(kind==1);
   for(k=0;k<cycles;k=k+1)begin
    @(posedge clk);#1;
    if(monotonic_cycles!=held_mono+1 && index!=0)$fatal(1,"Monotonic cycle skip");
    held_mono=monotonic_cycles;
   end
   if(kind==1&&(sync_accepted!=legal||sync_rejected==legal))$fatal(1,"Sync decision mismatch");
   if(kind==0&&(sync_accepted||sync_rejected))$fatal(1,"Spurious sync");
   $fwrite(outfd,"%0d,%0d,%016x,%0d,%0d,%0d,%0d,%0d,%0d\n",index,monotonic_cycles,
    utc_time,last_offset,last_delay,sync_accepted,sync_rejected,sync_count,error_count);
   index=index+1;
   @(negedge clk);sync_valid=0;
  end
  reset=1;@(posedge clk);#1;
  if(utc_time!=64'he900000000000000||monotonic_cycles!=0||synchronized||sync_count||error_count)$fatal(1,"Reset recovery");
  $fclose(fd);$fclose(outfd);$display("RTC_TIMEBASE = PASS vectors=%0d",index);$finish;
 end
 initial begin #20000000;$fatal(1,"Timeout");end
endmodule
