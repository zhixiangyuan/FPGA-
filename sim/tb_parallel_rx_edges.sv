`timescale 1ns/1ps
module tb_parallel_rx_edges;
 reg clk=0;always #4 clk=~clk;reg reset=1;reg [7:0] wire_data=0;reg dv=0,er=0;
 wire [7:0] data,payload;wire valid,ready,sop,eop,finished,good,pv,ps,pe;
 wire [15:0] wire_length;wire [31:0] drops,accepted,rejected;integer cycle=0,current=0,fd,received=0;
 wire application_ready=cycle%7!=0;
 afdx_mac_rx_checked mac(.clk(clk),.reset(reset),.gmii_rxd(wire_data),.gmii_rx_dv(dv),.gmii_rx_er(er),
  .stream_ready(ready),.stream_data(data),.stream_valid(valid),.stream_sop(sop),.stream_eop(eop),
  .frame_done(finished),.frame_good(good),.frame_length(wire_length),.drop_frames(drops));
 afdx_multi_vl_rx_parser #(.VL_COUNT(16),.BANKS(8),.PARALLEL_MAC_CHECK(1)) parser(
  .clk(clk),.reset(reset),.in_data(data),.in_valid(valid),.in_ready(ready),.in_sop(sop),.in_eop(eop),.in_length(wire_length),
  .cfg_da_prefix(32'h03000000),.cfg_vlid(16'h1234),.cfg_src_mac(48'h020000000009),
  .cfg_src_ip(32'h0a000001),.cfg_dst_ip(32'he0e0003c),.cfg_src_port(16'd24),.cfg_dst_port(16'd23),
  .payload_data(payload),.payload_valid(pv),.payload_ready(application_ready),.payload_sop(ps),.payload_eop(pe),
  .payload_length(),.payload_vlid(),.payload_sn_unchecked(),.payload_src_port(),.payload_dst_port(),
  .candidate_accepted(),.candidate_rejected(),.reject_reason(),.accepted_count(accepted),.rejected_count(rejected),
  .banks_busy(),.payload_discard(1'b0),.frame_done(finished),.frame_good(good),.wire_frame_length(wire_length));
 `include "golden/constants.vh"
 reg [7:0] fixture[0:WIRE_BYTES-1];reg [79:0] meta[0:CASE_COUNT-1];
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(pv&&dv)$fatal(1,"payload published before final wire verdict case=%0d",current);
  if(pv&&application_ready)begin $fwrite(fd,"%0d,%0d,%0d,%0d\n",current,ps,pe,payload);if(pe)received<=received+1;end
 end
 integer before_apps,before_drops,before_rejected,before_accepted;
 initial begin
  fd=$fopen("application.csv","w");$fwrite(fd,"case_id,sop,eop,data\n");
  $readmemh("golden/wire.mem",fixture);$readmemh("golden/meta.mem",meta);
  repeat(8)@(negedge clk);reset=0;
  for(current=0;current<CASE_COUNT;current=current+1)begin
   before_apps=received;before_drops=drops;before_rejected=rejected;before_accepted=accepted;
   for(integer p=0;p<meta[current][47:32];p=p+1)begin
    @(negedge clk);dv=1;er=p==meta[current][31:16];wire_data=fixture[meta[current][79:48]+p];
   end
   @(negedge clk);dv=0;er=0;repeat(2500)@(negedge clk);
   if(meta[current][15:0]!=0)begin
    if(received-before_apps!=1||accepted-before_accepted!=1||drops!=before_drops||rejected!=before_rejected)$fatal(1,"valid case=%0d lost",current);
   end else if(received!=before_apps||accepted!=before_accepted||drops-before_drops+rejected-before_rejected!=1)
    $fatal(1,"atomic reject ownership case=%0d app=%0d mac=%0d parser=%0d",current,received-before_apps,drops-before_drops,rejected-before_rejected);
  end
  $display("PARALLEL_RX_EDGES_PASS cases=%0d delivered=%0d",CASE_COUNT,received);$fclose(fd);$finish;
 end
 initial begin #10000000;$fatal(1,"parallel receive edges watchdog");end
endmodule
