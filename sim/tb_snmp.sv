`timescale 1ns/1ps
module tb_snmp;
 reg clk=0;always #4 clk=~clk;reg reset=1;
 reg [7:0] in_data=0;reg in_valid=0,in_sop=0,in_eop=0;
 wire in_ready;reg [10:0] in_length=0;reg [15:0] in_src_port=49152;
 reg [31:0] uptime_ticks=0;reg trap_start=0;wire trap_ready;
 wire [7:0] out_data;wire out_valid,out_sop,out_eop;reg out_ready=0;
 wire [10:0] out_length;wire [15:0] out_src_port,out_dst_port;
 wire [31:0] request_count,response_count,error_count,trap_count;wire [5:0] sys_name_length;
 afdx_snmp_agent dut(.*);
 `include "golden/constants.vh"
 reg [191:0] meta[0:CASE_COUNT-1];reg [7:0] requests[0:RX_BYTES-1],responses[0:TX_BYTES-1];
 integer cycle=0,current=0,index=0,fd,events,i,j,waits;reg stalled=0;reg [36:0] held;
 always @(posedge clk)begin
  cycle=cycle+1;
  if(reset)stalled<=0;
  else begin
   if(stalled&&(!out_valid||{out_data,out_sop,out_eop,out_length,out_dst_port}!==held))$fatal(1,"SNMP backpressure instability");
   stalled<=out_valid&&!out_ready;
   if(out_valid&&!out_ready)held<={out_data,out_sop,out_eop,out_length,out_dst_port};
   if(out_valid&&out_ready)begin
    if(index>=meta[current][95:64]||out_data!==responses[meta[current][127:96]+index]||
       out_length!=meta[current][95:64]||out_sop!=(index==0)||out_eop!=(index+1==out_length)||out_src_port!=161||
       out_dst_port!=(meta[current][31:0]?162:49152))$fatal(1,"SNMP Golden case=%0d byte=%0d got=%02x expected=%02x",current,index,out_data,responses[meta[current][127:96]+index]);
    $fwrite(fd,"%0d,%0d,%02x\n",current,index,out_data);index=index+1;
   end
  end
 end
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/requests.mem",requests);$readmemh("golden/responses.mem",responses);
  fd=$fopen("actual_snmp.csv","w");events=$fopen("snmp_events.csv","w");
  $fwrite(fd,"case_id,byte_index,data\n");$fwrite(events,"case_id,response_bytes,name_length,request_count,response_count,error_count,trap_count\n");
  repeat(4)@(negedge clk);reset=0;#1;
  for(i=0;i<CASE_COUNT;i=i+1)begin
   current=i;index=0;uptime_ticks=meta[i][63:32];in_length=meta[i][159:128];
   if(meta[i][31:0])begin
    if(!trap_ready)$fatal(1,"Trap not ready");trap_start=1;@(negedge clk);trap_start=0;
   end else begin
    for(j=0;j<in_length;j=j+1)begin
     in_data=requests[meta[i][191:160]+j];in_valid=1;in_sop=(j==0);in_eop=(j+1==in_length);
     waits=0;do begin @(posedge clk);waits=waits+1;if(waits>2000)$fatal(1,"Input timeout");end while(!in_ready);
     @(negedge clk);
    end
    in_valid=0;in_sop=0;in_eop=0;
   end
   waits=0;
   do begin
    out_ready=(cycle%5!=0)&&(cycle%7!=0);@(negedge clk);waits=waits+1;
    if(waits>2000)$fatal(1,"SNMP response timeout case=%0d state=%0d cursor=%0d length=%0d errors=%0d index=%0d expected=%0d",i,dut.state,dut.cursor,dut.received_length,error_count,index,meta[i][95:64]);
   end while(index!=meta[i][95:64]||!in_ready);
   repeat(5)@(negedge clk);
   $fwrite(events,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",i,index,sys_name_length,request_count,response_count,error_count,trap_count);
  end
  reset=1;@(negedge clk);
  if(out_valid||request_count||response_count||error_count||trap_count||sys_name_length!=7)$fatal(1,"Reset recovery");
  $fclose(fd);$fclose(events);$display("SNMP_AGENT = PASS cases=%0d",CASE_COUNT);$finish;
 end
 initial begin #2000000;$fatal(1,"Timeout");end
endmodule
