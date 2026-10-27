`timescale 1ns/1ps
module tb_redundant_rx;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] data=0;reg av=0,bv=0,sop=0,eop=0;
 reg [15:0] vl=0;reg [7:0] sn=0;wire ar,br;
 wire [7:0] rx;wire valid,rs,re,initialized;reg ready=1;
 wire [31:0] delivered,duplicates,errors,controls;
 afdx_redundant_rx #(.INTEGRITY_ENABLE({1'b0,{4095{1'b1}}}),
  .REDUNDANCY_ENABLE({2'b11,1'b0,{4093{1'b1}}})) dut(.clk(clk),.reset(reset),
  .a_data(data),.a_valid(av),.a_ready(ar),.a_sop(sop),.a_eop(eop),.a_vlid(vl),.a_sn(sn),.a_length(11'd3),
  .b_data(data),.b_valid(bv),.b_ready(br),.b_sop(sop),.b_eop(eop),.b_vlid(vl),.b_sn(sn),.b_length(11'd3),
  .a_src_port(16'd24),.a_dst_port(16'd23),.b_src_port(16'd24),.b_dst_port(16'd23),
  .rx_data(rx),.rx_valid(valid),.rx_ready(ready),.rx_sop(rs),.rx_eop(re),.initialized(initialized),
  .rx_vlid(),.rx_src_port(),.rx_dst_port(),.rx_length(),.a_discard(),.b_discard(),
  .delivered_count(delivered),.duplicate_count(duplicates),.integrity_error_count(errors),.control_count(controls));
 integer fd,cycle=0,count,case_id,p,got=0;reg [127:0] vectors[0:19999];
 always @(posedge clk)begin
  cycle<=cycle+1;ready<=cycle%7!=0;
  if(valid&&ready)begin $fwrite(fd,"%0d,%0d,%0d\n",rs,re,rx);if(re)got<=got+1;end
 end
 initial begin
  fd=$fopen("rx_unit.csv","w");$fwrite(fd,"sop,eop,data\n");
  $readmemh("vectors.mem",vectors);count=vectors[0][31:0];
  repeat(5)@(negedge clk);reset=0;wait(initialized);
  for(case_id=1;case_id<=count;case_id=case_id+1)begin
   repeat(vectors[case_id][31:1])@(negedge clk);
   @(negedge clk);vl=vectors[case_id][95:64];sn=vectors[case_id][63:32];
   for(p=0;p<3;p=p+1)begin
    av=vectors[case_id][127:96]==0;bv=!av;
    sop=p==0;eop=p==2;data=case_id>>(8*(2-p));
    @(posedge clk);while(!(av?ar:br))@(posedge clk);
    @(negedge clk);
   end
   av=0;bv=0;sop=0;eop=0;
  end
  repeat(50)@(negedge clk);
  $display("REDUNDANT_RX_PASS vectors=%0d delivered=%0d duplicate=%0d errors=%0d controls=%0d",count,delivered,duplicates,errors,controls);
  $fclose(fd);$finish;
 end
 initial begin #20000000;$fatal(1,"RX unit watchdog");end
endmodule
