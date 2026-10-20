`timescale 1ns/1ps
module tb_multi_vl_sn;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;
 reg [15:0] cfg_integrity_enable=16'hffff;
 reg [7:0] in_data=0,in_sn=0;
 reg in_valid=0,in_sop=0,in_eop=0,app_ready=0;
 reg [10:0] in_length=0;reg [15:0] in_vlid=0;
 wire in_ready,app_valid,app_sop,app_eop;
 wire [7:0] app_data,app_sn;wire [10:0] app_length;wire [15:0] app_vlid;
 wire accepted,rejected,reset_control,delivered;
 wire [31:0] accepted_count,rejected_count,control_count,missing_count,delivered_count;
 afdx_multi_vl_sn_gate dut(.*);
 integer fd,logfd,nread,kind,vl,sn,len,decision,missing,en,byte_index;
 integer vector_count=0,app_bytes=0;
 integer expected_accept=0,expected_reject=0,expected_control=0,expected_missing=0;
 integer cycle=0,wait_cycles;
 always @(posedge clk)cycle<=cycle+1;
 task automatic do_reset;
 begin
  @(negedge clk);reset=1;in_valid=0;app_ready=0;
  repeat(3)@(negedge clk);reset=0;
  expected_accept=0;expected_reject=0;expected_control=0;expected_missing=0;
 end endtask
 initial begin
  logfd=$fopen("actual_sn.csv","w");
  $fwrite(logfd,"vector,vl,sn,decision,psn,accepted,rejected,control,missing,delivered\n");
  fd=$fopen("golden/vectors.txt","r");if(!fd)$fatal(1,"Golden missing");
  do_reset();
  while(!$feof(fd))begin
   nread=$fscanf(fd,"%d %d %d %d %d %d %d\n",kind,vl,sn,len,decision,missing,en);
   if(nread!=7)$fatal(1,"Golden format");
   if(kind==1)do_reset();
   else begin
    @(negedge clk);
    if(vl>=0&&vl<16)cfg_integrity_enable[vl]=en;
    in_vlid=16'h1234+vl;in_sn=sn;in_length=len;
    in_valid=1;in_sop=1;in_eop=(len==1);in_data=vector_count;
    @(posedge clk);#1;
    if(accepted!=(decision==1)||rejected!=(decision==2)||reset_control!=(decision==3))
     $fatal(1,"Decision vector=%0d vl=%0d sn=%0d expected=%0d",vector_count,vl,sn,decision);
    if(vl>=0&&vl<16&&(dut.psn[vl]!=sn||!dut.psn_valid[vl]))$fatal(1,"PSN not advanced");
    case(decision)
     1:expected_accept=expected_accept+1;
     2:expected_reject=expected_reject+1;
     3:expected_control=expected_control+1;
    endcase
    expected_missing=expected_missing+missing;
    for(byte_index=0;byte_index<len;byte_index=byte_index+1)begin
     // Deterministic periodic stalls; upstream bytes must remain retained.
     wait_cycles=0;
     do begin
      @(negedge clk);app_ready=((cycle%5)!=0)&&((cycle%7)!=0);
      in_data=(vector_count+byte_index)&255;
      in_sop=(byte_index==0);in_eop=(byte_index==len-1);
      @(posedge clk);
      if(decision==1)begin
       if(!app_valid||app_data!=in_data||app_sn!=sn||app_vlid!=in_vlid||
          app_length!=len||app_sop!=in_sop||app_eop!=in_eop)$fatal(1,"Payload metadata mismatch");
      end else if(app_valid)$fatal(1,"Rejected payload leak");
      wait_cycles=wait_cycles+1;if(wait_cycles>50)$fatal(1,"Handshake timeout");
     end while(!in_ready);
     if(decision==1)app_bytes=app_bytes+1;
     #1;
    end
    if(delivered!=(decision==1))$fatal(1,"Delivery pulse mismatch");
    if(accepted_count!=expected_accept||rejected_count!=expected_reject||
       control_count!=expected_control||missing_count!=expected_missing||delivered_count!=expected_accept)
       $fatal(1,"Counters mismatch");
    $fwrite(logfd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",vector_count,vl,sn,decision,
      vl>=0&&vl<16?$signed({24'd0,dut.psn[vl]}):-1,accepted_count,rejected_count,control_count,missing_count,delivered_count);
    @(negedge clk);in_valid=0;in_sop=0;in_eop=0;
   end
   vector_count=vector_count+1;
  end
  // Partial delivery reset must cancel ownership and clear all VL baselines.
  @(negedge clk);in_valid=1;in_sop=1;in_eop=0;in_length=9;in_sn=202;in_vlid=16'h1234;app_ready=1;
  repeat(3)@(negedge clk);do_reset();
  if(app_valid||dut.psn_valid!=0||accepted_count!=0)$fatal(1,"Partial reset failure");
  $fclose(fd);$fclose(logfd);
  $display("MULTI_VL_SN = PASS vectors=%0d application_bytes=%0d",vector_count,app_bytes);$finish;
 end
 initial begin #10000000;$fatal(1,"Wall simulation timeout");end
endmodule
