`timescale 1ns/1ps
module tb_v1_netlist;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;reg [7:0] rx_data=0;reg rx_valid=0,rx_ready=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 AFDX_top dut(.clk(clk),.reset(reset),.rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready));
 `include "v1_netlist_observer.vh"
 `include "golden/constants.vh"
 reg [255:0] meta[0:CASE_COUNT-1];reg [127:0] expected[0:CASE_COUNT-1];
 reg [7:0] incoming[0:131071],outgoing[0:131071];
 integer txq[0:1023],appq[0:1023];integer txhead=0,txtail=0,apphead=0,apptail=0;
 integer cycle=0,txframes=0,commits=0,txbytes=0,txidx=0,epoch=0,epoch_tx=0,epoch_commit=0;
 integer txfd,appfd,decisionfd,inputfd,last_start=0;reg have_start=0,tx_d=0;reg [1:0] commit_d=0;
 initial begin
  $readmemh("golden/meta.mem",meta);$readmemh("golden/expect.mem",expected);
  $readmemh("golden/incoming.mem",incoming);$readmemh("golden/outgoing.mem",outgoing);
  txfd=$fopen("actual_tx.csv","w");appfd=$fopen("app_commits.csv","w");decisionfd=$fopen("decisions.csv","w");inputfd=$fopen("input_events.csv","w");
  if(!txfd||!appfd||!decisionfd||!inputfd)$fatal(1,"CSV open failed");
  $fdisplay(txfd,"cycle,case_id,byte_index,data");$fdisplay(appfd,"cycle,case_id,bank,length,rx_sn,epoch");
  $fdisplay(decisionfd,"cycle,case_id,psn,valid,commits,sent");
  $fdisplay(inputfd,"case_id,epoch,start_cycle,end_cycle,bytes,action");
 end
 task automatic record_commit(input integer bank);
  integer n,sn,c;
  begin
   c=appq[apphead];n=bank?obs_lengths1:obs_lengths0;sn=bank?obs_origins1:obs_origins0;
   if(apphead>=apptail||n!==meta[c][159:128]||sn!==meta[c][127:96])$fatal(1,"actual application RAM commit metadata mismatch case=%0d length=%0d sn=%0d",c,n,sn);
   $fdisplay(appfd,"%0d,%0d,%0d,%0d,%0d,%0d",cycle,c,bank,n,sn,epoch);
   apphead=apphead+1;commits=commits+1;epoch_commit=epoch_commit+1;
  end
 endtask
 always @(posedge clk)begin
  cycle=cycle+1;
  if(tx_ready!==0)$fatal(1,"candidate tx_ready contract");
  if(reset)begin tx_d<=0;have_start=0;commit_d<=0;end
  else begin
   commit_d<=obs_committed;
   if(obs_committed[0]&&!commit_d[0])record_commit(0);
   if(obs_committed[1]&&!commit_d[1])record_commit(1);
   tx_d<=tx_valid;
   if(tx_valid&&!tx_d)begin
    if(txhead>=txtail)$fatal(1,"unexpected external response");
    if(have_start&&(cycle-last_start<125000||cycle-last_start>137500))$fatal(1,"external BAG/jitter violation gap=%0d",cycle-last_start);
    last_start=cycle;have_start=1;txidx=0;txframes=txframes+1;
   end
   if(tx_valid)begin
    if(txhead>=txtail||txidx>=meta[txq[txhead]][63:32]||tx_data!==outgoing[meta[txq[txhead]][95:64]+txidx])$fatal(1,"real VO external Golden mismatch case=%0d byte=%0d",txq[txhead],txidx);
    $fdisplay(txfd,"%0d,%0d,%0d,%02X",cycle,txq[txhead],txidx,tx_data);txidx=txidx+1;txbytes=txbytes+1;
   end
   if(!tx_valid&&tx_d)begin
    if(txidx!=meta[txq[txhead]][63:32])$fatal(1,"external length mismatch");txhead=txhead+1;epoch_tx=epoch_tx+1;
   end
  end
 end
 task automatic enqueue(input integer c,input integer send_reply);
  begin appq[apptail]=c;apptail=apptail+1;if(send_reply)begin txq[txtail]=c;txtail=txtail+1;end end
 endtask
 task automatic inject(input integer c);
  integer j,start;
  begin
   @(negedge clk);rx_valid=0;repeat(12)@(negedge clk);start=cycle+1;
   for(j=0;j<meta[c][223:192];j=j+1)begin rx_valid=1;rx_data=incoming[meta[c][255:224]+j];rx_ready=~rx_ready;@(negedge clk);end
   rx_valid=0;rx_data=0;$fdisplay(inputfd,"%0d,%0d,%0d,%0d,%0d,%0d",c,epoch,start,cycle,meta[c][223:192],meta[c][31:0]);
  end
 endtask
 task automatic reset_epoch;
  begin
   @(negedge clk);reset=1;rx_valid=0;rx_data=0;repeat(6)@(posedge clk);@(negedge clk);
   if(obs_psn_valid||obs_psn!=0||obs_committed!=0||obs_app_busy!=0||obs_parser_busy!=0||obs_mac_busy0||obs_mac_busy1)$fatal(1,"real VO reset state failed");
   epoch=epoch+1;epoch_tx=0;epoch_commit=0;reset=0;repeat(3)@(negedge clk);
  end
 endtask
 task automatic check_state(input integer c);
  integer fd;
  begin
   @(negedge clk);
   if(obs_psn!==expected[c][127:96]||obs_psn_valid!==expected[c][95:64])$fatal(1,"real VO PSN state mismatch case=%0d got=%0d expected=%0d",c,obs_psn,expected[c][127:96]);
   $fdisplay(decisionfd,"%0d,%0d,%0d,%0d,%0d,%0d",cycle,c,obs_psn,obs_psn_valid,epoch_commit,epoch_tx);
   fd=$fopen("frame_progress.csv","a");$fdisplay(fd,"%0d,%0d,%0d,%0d",cycle,c,txframes,commits);$fclose(fd);
  end
 endtask
 task automatic exercise(input integer c);
  integer action,t,old_complete,old_commit;
  begin
   action=meta[c][31:0];old_complete=epoch_tx;old_commit=epoch_commit;
   if(action==0)enqueue(c,1);inject(c);t=0;
   if(action==0)begin
    while((epoch_tx==old_complete||txhead!=txtail)&&t<180000)begin @(posedge clk);t=t+1;end
    if(t>=180000)$fatal(1,"real VO response timeout case=%0d",c);
   end else repeat(30000)@(posedge clk);
   t=0;while(obs_parser_busy!=0&&t<30000)begin @(posedge clk);t=t+1;end
   repeat(40)@(posedge clk);
   if(t>=30000||epoch_commit!=old_commit+(action==0)||epoch_tx!=old_complete+(action==0)||obs_app_busy!=0||obs_mac_busy0||obs_mac_busy1)$fatal(1,"real VO frame/commit conservation case=%0d",c);
   check_state(c);
  end
 endtask
 task automatic pressure_phase(input integer a,b,c,d,e,f,drop,recovery,cancel);
  integer t,old_commit;
  begin
   enqueue(a,1);inject(a);enqueue(b,1);inject(b);enqueue(c,1);inject(c);
   enqueue(d,1);inject(d);enqueue(e,1);inject(e);enqueue(f,1);inject(f);inject(drop);
   repeat(1000)@(posedge clk);@(negedge clk);
   if(obs_app_busy!==2'b11||obs_parser_busy!==2'b11||!obs_mac_busy0||!obs_mac_busy1||obs_psn!=13||epoch_commit!=3||epoch_tx!=1)$fatal(1,"real VO reserved-bank/PSN pressure state");
   t=0;while((epoch_tx!=7||txhead!=txtail)&&t<1000000)begin @(posedge clk);t=t+1;end
   repeat(20)@(posedge clk);
   if(t>=1000000||obs_psn!=16||epoch_commit!=7||obs_app_busy!=0||obs_parser_busy!=0)$fatal(1,"real VO pressure drain conservation");
   check_state(f);exercise(recovery);
   old_commit=epoch_commit;enqueue(cancel,0);inject(cancel);t=0;
   while(epoch_commit==old_commit&&t<10000)begin @(posedge clk);t=t+1;end
   repeat(20)@(posedge clk);@(negedge clk);
   if(t>=10000||epoch_tx!=8||obs_psn!=19||obs_app_busy==0||epoch_commit!=9)$fatal(1,"real VO reset cancel setup");
   check_state(cancel);$display("V1_NETLIST_PRESSURE = PASS retained=6 capacity_drop=1 reset_cancel=1");
  end
 endtask
 task automatic partial_reset(input integer c);
  integer j,start;
  begin
   @(negedge clk);repeat(12)@(negedge clk);start=cycle+1;
   for(j=0;j<100;j=j+1)begin rx_valid=1;rx_data=incoming[meta[c][255:224]+j];@(negedge clk);end
   $fdisplay(inputfd,"%0d,%0d,%0d,%0d,100,7",c,epoch,start,cycle);reset_epoch();repeat(100)@(posedge clk);
   if(epoch_commit!=0||tx_valid)$fatal(1,"real VO partial reset recovery");$display("V1_NETLIST_PARTIAL_RESET = PASS");
  end
 endtask
 initial begin
  repeat(5)@(posedge clk);`include "golden/scenario.vh"
  repeat(150000)@(posedge clk);@(negedge clk);
  if(txframes!=EXPECTED_TX_FRAMES||commits!=EXPECTED_APP_FRAMES||txhead!=txtail||apphead!=apptail)$fatal(1,"real VO final totals");
  $fclose(txfd);$fclose(appfd);$fclose(decisionfd);$fclose(inputfd);
  $display("V1_REAL_NETLIST = PASS tx_frames=%0d tx_bytes=%0d app_commits=%0d sn_wrap=256 clk_hz=125000000 bag_cycles=125000",txframes,txbytes,commits);$finish;
 end
 initial begin #430000000;$fatal(1,"real VO suite timeout");end
endmodule
