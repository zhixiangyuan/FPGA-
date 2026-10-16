`timescale 1ns/1ps
module tb_atomic_file_store;
 reg clk=0;always #4 clk=~clk;
 reg reset=1,begin_valid=0,check_length=0,check_crc=0,write_valid=0,finish_valid=0,abort_stage=0,read_lock=0,read_enable=0;
 reg [15:0] expected_length=0,expected_crc=0,write_address=0,read_address=0;
 reg [7:0] write_data=0;
 wire begin_ready,write_ready,finish_ready,read_valid,active_valid,committed,rejected,staging_active;
 wire [7:0] read_data;wire [15:0] finish_error,active_length,active_crc,staging_length,staging_crc;wire [31:0] generation;
 afdx_atomic_file_store dut(.*);
 `include "golden/constants.vh"
 reg [7:0] vectors[0:VECTOR_BYTES-1];
 integer fd;
 task idle(input integer n);repeat(n)@(negedge clk);endtask
 task begin_file(input integer size,input integer crc);
  begin
   if(!begin_ready)$fatal(1,"Store not ready");
   expected_length=size;expected_crc=crc;check_length=1;check_crc=1;begin_valid=1;idle(1);begin_valid=0;
  end
 endtask
 task write_blob(input integer offset,input integer size);
  integer j;
  begin
   for(j=0;j<size;j=j+1)begin
    if(!write_ready)$fatal(1,"Store write blocked");
    write_valid=1;write_address=j;write_data=vectors[offset+j];idle(1);
   end
   write_valid=0;
  end
 endtask
 task finish_file(input integer error);
  begin
   idle(1);
   if(!finish_ready||finish_error!=error)$fatal(1,"Store finish error %0d expected %0d",finish_error,error);
   finish_valid=1;idle(1);finish_valid=0;idle(1);
  end
 endtask
 task read_blob(input integer offset,input integer size,input integer crc,input integer gen);
  integer j;
  begin
   if(!active_valid||active_length!=size||active_crc!=crc||generation!=gen)$fatal(1,"Store metadata");
   read_lock=1;
   for(j=0;j<size;j=j+1)begin
    read_address=j;read_enable=1;idle(1);
    if(!read_valid||read_data!==vectors[offset+j])$fatal(1,"Store readback byte %0d",j);
    $fwrite(fd,"%02x\n",read_data);
   end
   read_address=size;read_enable=1;idle(1);if(read_valid)$fatal(1,"Read past visible EOF");
   read_enable=0;read_lock=0;idle(1);
  end
 endtask
 initial begin #2000000;$fatal(1,"Atomic store timeout");end
 initial begin
  $readmemh("golden/vectors.mem",vectors);fd=$fopen("readback.mem","w");
  idle(4);reset=0;idle(1);
  `include "golden/stimulus.vh"
  $fclose(fd);$display("ATOMIC_STORE_PASS generation=%0d",generation);$finish;
 end
endmodule
