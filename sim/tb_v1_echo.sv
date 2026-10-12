`timescale 1ns/1ps
module tb_v1_echo;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] rx_data=0;reg rx_valid=0,rx_ready=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 AFDX_top dut(.clk(clk),.reset(reset),.rx_data(rx_data),.rx_valid(rx_valid),
 .rx_ready(rx_ready),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready));
 `include "golden/constants.vh"
 reg [255:0] meta[0:CASE_COUNT-1];reg [127:0] expected[0:CASE_COUNT-1];
 reg [7:0] incoming[0:131071],outgoing[0:131071],payload[0:65535];
 integer txq[0:1023],appq[0:1023];integer txhead=0,txtail=0,apphead=0,apptail=0;
 integer cycle=0,txframes=0,appframes=0,txbytes=0,appbytes=0,txidx=0,appidx=0;
 integer txfd,appfd,decisionfd,last_start=0;reg have_start=0,tx_d=0,stalled=0;
 reg [44:0] held;reg payload_stalled=0;reg [8:0] held_payload;
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/expect.mem",expected);
  $readmemh("golden/incoming.mem",incoming);$readmemh("golden/outgoing.mem",outgoing);$readmemh("golden/payload.mem",payload);
  txfd=$fopen("actual_tx.csv","w");appfd=$fopen("actual_app.csv","w");decisionfd=$fopen("decisions.csv","w");
  if(!txfd||!appfd||!decisionfd)$fatal(1,"CSV open failed");
  $fdisplay(txfd,"cycle,case_id,byte_index,data");$fdisplay(appfd,"cycle,case_id,byte_index,data,sop,eop,length,sn");
  $fdisplay(decisionfd,"cycle,case_id,action,psn,valid,missing,stored,sent");
 end
 always @(posedge clk)begin
  cycle=cycle+1;
  if(tx_ready!==0)$fatal(1,"candidate tx_ready contract");
  if(reset)begin tx_d<=0;have_start=0;stalled<=0;payload_stalled<=0;end
  else begin
   if(dut.msg_error||dut.queue_error_count!=0)$fatal(1,"echo transaction error");
   if(stalled&&(!dut.app_valid||{dut.app_data,dut.app_sop,dut.app_eop,dut.app_length,dut.app_vlid,dut.app_sn}!==held))$fatal(1,"app backpressure instability");
   stalled<=dut.app_valid&&!dut.app_ready;
   if(dut.app_valid&&!dut.app_ready)held<={dut.app_data,dut.app_sop,dut.app_eop,dut.app_length,dut.app_vlid,dut.app_sn};
   if(payload_stalled&&(!dut.payload_valid||{dut.payload_data,dut.payload_last}!==held_payload))$fatal(1,"sender input backpressure instability");
   payload_stalled<=dut.payload_valid&&!dut.payload_ready;
   if(dut.payload_valid&&!dut.payload_ready)held_payload<={dut.payload_data,dut.payload_last};
   tx_d<=tx_valid;
   if(tx_valid&&!tx_d)begin
    if(txhead>=txtail)$fatal(1,"unexpected external response");
    if(have_start&&cycle-last_start<125000)$fatal(1,"external BAG violation");
    last_start=cycle;have_start=1;txidx=0;txframes=txframes+1;
   end
   if(tx_valid)begin
    if(txhead>=txtail||txidx>=meta[txq[txhead]][63:32]||tx_data!==outgoing[meta[txq[txhead]][95:64]+txidx])$fatal(1,"external Golden mismatch case=%0d byte=%0d got=%02x expected=%02x",txq[txhead],txidx,tx_data,outgoing[meta[txq[txhead]][95:64]+txidx]);
    $fdisplay(txfd,"%0d,%0d,%0d,%02X",cycle,txq[txhead],txidx,tx_data);txidx=txidx+1;txbytes=txbytes+1;
   end
   if(!tx_valid&&tx_d)begin
    if(txidx!=meta[txq[txhead]][63:32])$fatal(1,"external length mismatch");txhead=txhead+1;
   end
   if(dut.app_valid&&dut.app_ready)begin
    if(apphead>=apptail||dut.app_data!==payload[meta[appq[apphead]][191:160]+appidx]||dut.app_length!==meta[appq[apphead]][159:128]||dut.app_sn!==meta[appq[apphead]][127:96]||dut.app_vlid!==16'h1234||dut.app_sop!==(appidx==0)||dut.app_eop!==(appidx+1==meta[appq[apphead]][159:128]))$fatal(1,"actual SN-gated app mismatch case=%0d byte=%0d",appq[apphead],appidx);
    $fdisplay(appfd,"%0d,%0d,%0d,%02X,%0d,%0d,%0d,%0d",cycle,appq[apphead],appidx,dut.app_data,dut.app_sop,dut.app_eop,dut.app_length,dut.app_sn);
    appidx=appidx+1;appbytes=appbytes+1;
    if(dut.app_eop)begin appframes=appframes+1;apphead=apphead+1;appidx=0;end
   end
  end
 end
 task automatic enqueue(input integer c,input integer send_reply);
  begin appq[apptail]=c;apptail=apptail+1;if(send_reply)begin txq[txtail]=c;txtail=txtail+1;end end
 endtask
 task automatic inject(input integer c);
  integer j;
  begin
   @(negedge clk);rx_valid=0;repeat(12)@(negedge clk);
   for(j=0;j<meta[c][223:192];j=j+1)begin rx_valid=1;rx_data=incoming[meta[c][255:224]+j];rx_ready=~rx_ready;@(negedge clk);end
   rx_valid=0;rx_data=0;
  end
 endtask
 task automatic reset_epoch;
  begin
   @(negedge clk);reset=1;rx_valid=0;rx_data=0;repeat(6)@(posedge clk);@(negedge clk);
   if(dut.psn_valid||dut.psn!=0||dut.echo_banks_busy!=0||dut.candidate_banks_busy!=0||dut.stored_count!=0||dut.sent_count!=0||dut.app_delivered_count!=0)$fatal(1,"reset failed");
   reset=0;repeat(3)@(negedge clk);
  end
 endtask
 task automatic check_state(input integer c);
  integer fd;
  begin
   @(negedge clk);
   if(dut.psn!==expected[c][127:96]||dut.psn_valid!==expected[c][95:64]||dut.sn_missing_count!==expected[c][63:32])$fatal(1,"PSN mismatch case=%0d actual=%0d expected=%0d",c,dut.psn,expected[c][127:96]);
   if(dut.stored_count!=dut.app_delivered_count)$fatal(1,"application commit conservation");
   $fdisplay(decisionfd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",cycle,c,meta[c][31:0],dut.psn,dut.psn_valid,dut.sn_missing_count,dut.stored_count,dut.sent_count);
   fd=$fopen("frame_progress.csv","a");$fdisplay(fd,"%0d,%0d,%0d,%0d",cycle,c,txframes,appframes);$fclose(fd);
  end
 endtask
 task automatic exercise(input integer c);
  integer action,t,old_sent,old_app,old_rej,old_control,old_proto,old_drop;
  begin
   action=meta[c][31:0];old_sent=dut.sent_count;old_app=appframes;old_rej=dut.sn_rejected_count;
   old_control=dut.sn_control_count;old_proto=dut.candidate_rejected_count;old_drop=dut.rx_drop;
   if(action==0)enqueue(c,1);inject(c);t=0;
   case(action)
    0:while((dut.sent_count==old_sent||txhead!=txtail)&&t<180000)begin @(posedge clk);t=t+1;end
    1:while(dut.sn_rejected_count==old_rej&&t<30000)begin @(posedge clk);t=t+1;end
    2:while(dut.sn_control_count==old_control&&t<30000)begin @(posedge clk);t=t+1;end
    3:while(dut.candidate_rejected_count==old_proto&&t<30000)begin @(posedge clk);t=t+1;end
    4:while(dut.rx_drop==old_drop&&t<30000)begin @(posedge clk);t=t+1;end
    default:$fatal(1,"invalid ordinary action");
   endcase
   if(t>=(action==0?180000:30000))$fatal(1,"scenario timeout case=%0d",c);
   repeat(40)@(posedge clk);
   if(appframes!=old_app+(action==0)||dut.sn_rejected_count!=old_rej+(action==1)||dut.sn_control_count!=old_control+(action==2)||dut.candidate_rejected_count!=old_proto+(action==3)||dut.rx_drop!=old_drop+(action==4)||dut.sn_accepted_count!=dut.app_delivered_count)$fatal(1,"decision conservation case=%0d",c);
   check_state(c);
  end
 endtask
 task automatic pressure_phase(input integer a,b,c,d,e,f,drop,recovery,cancel);
  integer t;
  begin
   enqueue(a,1);inject(a);enqueue(b,1);inject(b);enqueue(c,1);inject(c);
   enqueue(d,1);inject(d);enqueue(e,1);inject(e);enqueue(f,1);inject(f);inject(drop);
   repeat(1000)@(posedge clk);@(negedge clk);
   if(dut.echo_banks_busy!==2'b11||dut.candidate_banks_busy!==2'b11||dut.protocol.mac_rx_banks_busy!==2'b11||dut.app_ready||dut.rx_seen!=8||dut.rx_good!=7||dut.rx_drop!=1||dut.psn!=13||dut.sn_accepted_count!=4||dut.stored_count!=3)$fatal(1,"pressure reserved state actual psn=%0d accepted=%0d stored=%0d rx=%0d/%0d/%0d",dut.psn,dut.sn_accepted_count,dut.stored_count,dut.rx_seen,dut.rx_good,dut.rx_drop);
   t=0;while((dut.sent_count!=7||txhead!=txtail)&&t<1000000)begin @(posedge clk);t=t+1;end
   repeat(20)@(posedge clk);
   if(t>=1000000||dut.psn!=16||dut.sn_accepted_count!=7||dut.app_delivered_count!=7||dut.echo_banks_busy!=0||dut.candidate_banks_busy!=0)$fatal(1,"pressure drain failed");
   check_state(f);exercise(recovery);
   enqueue(cancel,0);inject(cancel);t=0;
   while(dut.stored_count<9&&t<10000)begin @(posedge clk);t=t+1;end
   repeat(20)@(posedge clk);@(negedge clk);
   if(t>=10000||dut.sent_count!=8||dut.psn!=19||dut.echo_banks_busy==0||dut.app_delivered_count!=9)$fatal(1,"reset cancel setup");
   check_state(cancel);
   $display("V1_PRESSURE_RESET = PASS retained=6 capacity_drop=1 psn_not_advanced_on_drop=1 app_commits=9 replies=8 cancel=1");
  end
 endtask
 task automatic partial_reset(input integer c);
  integer j;
  begin
   @(negedge clk);repeat(12)@(negedge clk);
   for(j=0;j<100;j=j+1)begin rx_valid=1;rx_data=incoming[meta[c][255:224]+j];@(negedge clk);end
   reset_epoch();repeat(100)@(posedge clk);
   if(dut.stored_count!=0||dut.rx_seen!=0||tx_valid)$fatal(1,"partial wire reset recovery");
   $display("V1_PARTIAL_RESET = PASS");
  end
 endtask
 initial begin
  repeat(5)@(posedge clk);`include "golden/scenario.vh"
  repeat(100)@(posedge clk);@(negedge clk);
  if(txframes!=EXPECTED_TX_FRAMES||appframes!=EXPECTED_APP_FRAMES||txhead!=txtail||apphead!=apptail||dut.late_count!=0)$fatal(1,"final totals");
  $fclose(txfd);$fclose(appfd);$fclose(decisionfd);
  $display("V1_FULL_ECHO = PASS tx_frames=%0d tx_bytes=%0d app_frames=%0d app_bytes=%0d sn_wrap=256 clk_hz=125000000 bag_cycles=125000",txframes,txbytes,appframes,appbytes);$finish;
 end
 initial begin #420000000;$fatal(1,"suite timeout");end
endmodule
