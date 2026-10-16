`timescale 1ns/1ps
module tb_tftp_endpoint;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,start=0,start_write=0;
 wire start_ready,busy,done,failed;
 reg [7:0] in_data=0;reg in_valid=0,in_sop=0,in_eop=0;
 reg [10:0] in_length=0;reg [15:0] in_src_port=0,in_dst_port=0;
 wire in_ready;wire [7:0] out_data;wire out_valid,out_sop,out_eop;
 wire [10:0] out_length;wire [15:0] out_src_port,out_dst_port;
 wire active_valid;wire [15:0] active_length,active_crc;wire [31:0] generation;
 integer cycle=0;
 wire out_ready=(cycle%5)!=1&&(cycle%13)!=2;
 afdx_tftp_file_endpoint dut(.*);
 `include "golden/constants.vh"
 reg [7:0] rx_bytes[0:RX_BYTES-1],expected[0:EXPECTED_BYTES-1],packet[0:515];
 integer frame_count=0,consumed=0,packet_length=0,last_length=0,last_src=0,last_dst=0;
 integer tid=0,old_tid=0,fd,ef,cf,epoch=0;
 reg was_stalled=0;reg [52:0] held;
 wire [52:0] fields={out_data,out_sop,out_eop,out_length,out_src_port,out_dst_port};
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)was_stalled<=0;
  else begin
   if(was_stalled&&(!out_valid||fields!==held))$fatal(1,"Endpoint stalled output changed");
   was_stalled<=out_valid&&!out_ready;held<=fields;
   if(out_valid&&out_ready)begin
    if(out_sop)begin packet_length=0;last_length=out_length;last_src=out_src_port;last_dst=out_dst_port;end
    if(out_length!=last_length||out_src_port!=last_src||out_dst_port!=last_dst)$fatal(1,"Endpoint metadata drift");
    packet[packet_length]=out_data;packet_length=packet_length+1;$fwrite(fd,"%02x\n",out_data);
    if(out_eop)begin
     if(packet_length!=out_length)$fatal(1,"Endpoint frame length");
     $fwrite(ef,"%0d,%0d,%0d,%0d,%0d,%0d\n",frame_count,epoch,cycle,last_src,last_dst,packet_length);
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
    in_length=length;in_src_port=src;in_dst_port=dst;watch=0;@(posedge clk);
    while(!in_ready)begin @(negedge clk);watch=watch+1;if(watch>100000)$fatal(1,"Endpoint RX blocked");@(posedge clk);end
    @(negedge clk);
   end
   in_valid=0;in_sop=0;in_eop=0;
  end
 endtask
 task expect_packet(input integer offset,input integer length,input integer src,input integer dst);
  integer watch,j;
  begin
   watch=0;while(frame_count<=consumed&&watch<100000)begin idle(1);watch=watch+1;end
   if(frame_count!=consumed+1)$fatal(1,"Endpoint packet wait %0d/%0d",frame_count,consumed+1);
   if(last_length!=length||last_dst!=dst||(src!=0&&last_src!=src)||last_src==0||last_src==69)
    $fatal(1,"Endpoint packet %0d metadata len=%0d src=%0d dst=%0d",consumed,last_length,last_src,last_dst);
   for(j=0;j<length;j=j+1)if(packet[j]!==expected[offset+j])
    $fatal(1,"Endpoint packet %0d byte %0d got %02x expected %02x",consumed,j,packet[j],expected[offset+j]);
   consumed=consumed+1;idle(2);
  end
 endtask
 task quiet(input integer n);begin idle(n);if(frame_count!=consumed)$fatal(1,"Unexpected endpoint packet");end endtask
 task snapshot(input integer index);
  begin idle(2);$fwrite(cf,"%0d,%0d,%0d,%0d,%04x\n",index,generation,active_valid,active_length,active_crc);end
 endtask
 task client_start(input integer writing);
  begin while(!start_ready)idle(1);start_write=writing;start=1;idle(1);start=0;end
 endtask
 initial begin #20000000;$fatal(1,"Endpoint timeout");end
 initial begin
  fd=$fopen("actual.mem","w");ef=$fopen("packets.csv","w");cf=$fopen("metadata.csv","w");
  $fwrite(ef,"frame,epoch,cycle,src_port,dst_port,bytes\n");$fwrite(cf,"index,generation,valid,length,crc\n");
  $readmemh("golden/rx.mem",rx_bytes);$readmemh("golden/expected.mem",expected);
  `include "golden/stimulus.vh"
  $display("TFTP_ENDPOINT_PASS packets=%0d generation=%0d",frame_count,generation);
  $fclose(fd);$fclose(ef);$fclose(cf);$finish;
 end
endmodule
