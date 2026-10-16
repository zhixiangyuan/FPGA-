`timescale 1ns/1ps
module tb_tftp;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,start=0,start_write=0,cancel=0;
 reg [255:0] start_name=0;reg [5:0] start_name_length=0;
 wire start_ready,busy,done,failed,aborted;wire [15:0] failure_code;
 reg [7:0] in_data=0;reg in_valid=0,in_sop=0,in_eop=0;
 reg [10:0] in_length=0;reg [15:0] in_src_port=0,in_dst_port=0;
 wire in_ready;wire [7:0] out_data;wire out_valid,out_sop,out_eop;
 wire [10:0] out_length;wire [15:0] out_src_port,out_dst_port;
 wire file_open_valid,file_write,file_client,file_read_enable,file_write_valid,file_finish_valid;
 wire [255:0] file_name;wire [5:0] file_name_length;
 wire [15:0] file_read_address,file_write_address,file_finish_length;
 wire [7:0] file_write_data;
 reg [15:0] file_open_error=0,file_finish_error=0;
 reg [7:0] file_read_data=0;
 reg [15:0] active_length=0;
 reg [7:0] active[0:4095],staging[0:4095];
 wire [31:0] retry_count,duplicate_count,reject_count,completed_count;
 integer cycle=0;
 reg stall_output=0;
 wire out_ready=!stall_output&&(cycle%5)!=1&&(cycle%13)!=2;
 wire file_write_ready=(cycle%3)!=1;
 afdx_tftp_engine #(.TIMEOUT_CYCLES(5000),.MAX_RETRIES(3)) dut(.*,.port_match(),
  .file_open_ready(1'b1),.file_read_length(active_length),.file_finish_ready(1'b1));
 `include "golden/constants.vh"
 reg [7:0] rx_bytes[0:RX_BYTES-1],expected[0:EXPECTED_BYTES-1];
 reg [7:0] packet[0:515];
 integer frame_count=0,consumed=0,packet_length=0;
 integer last_length=0,last_src=0,last_dst=0,packet_start=0;
 integer opens=0,commits=0,writes=0,finishes=0,dones=0,failures=0,aborts=0;
 integer fd,ef,cf,i,epoch=0;
 reg was_stalled=0;
 reg [65:0] held_output;
 wire [65:0] output_fields={out_data,out_sop,out_eop,out_length,out_src_port,out_dst_port,13'd0};
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)begin active_length<=0;was_stalled<=0;end
  else begin
   if(was_stalled&&(!out_valid||output_fields!==held_output))$fatal(1,"TX changed under backpressure");
   was_stalled<=out_valid&&!out_ready;held_output<=output_fields;
   if(file_open_valid)begin opens=opens+1;if(file_write)writes=0;end
   if(file_read_enable)begin
    if(file_read_address>=active_length)$fatal(1,"Read past EOF %0d/%0d",file_read_address,active_length);
    file_read_data<=active[file_read_address];
   end
   if(file_write_valid&&file_write_ready)begin
    if(file_write_address>=4096)$fatal(1,"Staging overflow");
    staging[file_write_address]<=file_write_data;writes=writes+1;
   end
   if(file_finish_valid)begin
    finishes=finishes+1;
    if(file_finish_error==0)begin
     if(writes!=file_finish_length)$fatal(1,"Duplicate or missing staged data %0d/%0d",writes,file_finish_length);
     active_length<=file_finish_length;
     for(i=0;i<file_finish_length;i=i+1)active[i]<=staging[i];
     $fwrite(cf,"%0d,%0d,%0d,",epoch,commits,file_finish_length);
     for(i=0;i<file_finish_length;i=i+1)$fwrite(cf,"%02x",staging[i]);
     $fwrite(cf,"\n");commits=commits+1;
    end
   end
   if(done)dones=dones+1;
   if(failed)failures=failures+1;
   if(aborted)aborts=aborts+1;
   if(out_valid&&out_ready)begin
    if(out_sop)begin packet_start=cycle;packet_length=0;last_length=out_length;last_src=out_src_port;last_dst=out_dst_port;end
    if(last_length!=out_length||last_src!=out_src_port||last_dst!=out_dst_port)$fatal(1,"TX metadata drift");
    if(packet_length>=516)$fatal(1,"TX too large");
    packet[packet_length]=out_data;packet_length=packet_length+1;
    $fwrite(fd,"%02x\n",out_data);
    if(out_eop)begin
     if(packet_length!=out_length)$fatal(1,"Output length/sop/eop");
     $fwrite(ef,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",frame_count,epoch,cycle,last_src,last_dst,packet_length,packet_start);
     frame_count=frame_count+1;
    end
   end
  end
 end
 task idle(input integer n);repeat(n)@(negedge clk);endtask
 task restart;
  begin reset=1;start=0;in_valid=0;in_sop=0;in_eop=0;idle(4);reset=0;idle(2);epoch=epoch+1;end
 endtask
 task send_packet(input integer offset,input integer length,input integer src,input integer dst);
  integer j,watch;
  begin
   for(j=0;j<length;j=j+1)begin
    in_data=rx_bytes[offset+j];in_valid=1;in_sop=j==0;in_eop=j+1==length;
    in_length=length;in_src_port=src;in_dst_port=dst;watch=0;
    @(posedge clk);
    while(!in_ready)begin @(negedge clk);watch=watch+1;if(watch>50000)$fatal(1,"RX blocked");@(posedge clk);end
    @(negedge clk);
   end
   in_valid=0;in_sop=0;in_eop=0;
  end
 endtask
 task expect_packet(input integer offset,input integer length,input integer src,input integer dst);
  integer watch,j;
  begin
   watch=0;
   while(frame_count<=consumed&&watch<50000)begin idle(1);watch=watch+1;end
   if(frame_count!=consumed+1)$fatal(1,"Packet count expected %0d actual %0d",consumed+1,frame_count);
   if(last_length!=length||last_dst!=dst||(src!=0&&last_src!=src)||last_src==0||last_src==69)
    $fatal(1,"Packet %0d metadata length=%0d src=%0d dst=%0d",consumed,last_length,last_src,last_dst);
   for(j=0;j<length;j=j+1)if(packet[j]!==expected[offset+j])
    $fatal(1,"Packet %0d byte %0d got=%02x expected=%02x",consumed,j,packet[j],expected[offset+j]);
   consumed=consumed+1;idle(2);
  end
 endtask
 task quiet(input integer n);
  begin idle(n);if(frame_count!=consumed)$fatal(1,"Unexpected retransmit/output");end
 endtask
 task client_start(input integer writing);
  begin
   while(!start_ready)idle(1);
   start_name=256'h6e69622e6769666e6f63;start_name_length=10;start_write=writing;start=1;
   idle(1);start=0;
  end
 endtask
 integer tid=0,old_tid=0,saved_commits=0,saved_opens=0,saved_writes=0,saved_failures=0;
 initial begin #50000000;$fatal(1,"TFTP test timeout");end
 initial begin
  $readmemh("golden/rx.mem",rx_bytes);$readmemh("golden/expected.mem",expected);
  fd=$fopen("actual.mem","w");ef=$fopen("packets.csv","w");cf=$fopen("commits.csv","w");
  $fwrite(ef,"frame,epoch,cycle,src_port,dst_port,bytes,start_cycle\n");$fwrite(cf,"epoch,commit,length,data\n");
  `include "golden/stimulus.vh"
  $display("TFTP_DIRECTED_PASS packets=%0d opens=%0d commits=%0d finishes=%0d done=%0d failures=%0d retries=%0d duplicates=%0d rejects=%0d",frame_count,opens,commits,finishes,dones,failures,retry_count,duplicate_count,reject_count);
  $fclose(fd);$fclose(ef);$fclose(cf);$finish;
 end
endmodule
