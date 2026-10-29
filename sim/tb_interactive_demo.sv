`timescale 1ns/1ps
// Test-only application/peer/link driver. Production DUT is observed, never forced.
module tb_interactive_demo;
 reg clk=0; always #4 clk=~clk;
 reg reset=1; reg [7:0] tx_data=0; reg tx_valid=0; wire tx_ready;
 wire [7:0] rx_data,a,b; wire rv,rs,re,init,ae,be,ts,aer,ber;
 reg [1:0] mask=3; reg error_a=0;
 reg manual_claim=0,manual_valid=0; reg [7:0] manual_data=0;
 reg echo_active=0; integer qhead=0,qtail=0,echo_index=0;
 reg [7:0] echo_ram[0:1023][0:2047],capture[0:2047]; integer echo_lengths[0:1023];
 wire [7:0] net_data=manual_valid?manual_data:echo_ram[qhead%1024][echo_index];
 wire net_valid=manual_valid||echo_active;
 reg [7:0] bd[0:63]; reg [63:0] bv=0;
 AFDX_top dut(.clk(clk),.reset(reset),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
 .rx_data(rx_data),.rx_valid(rv),.rx_ready(1'b1),.rx_sop(rs),.rx_eop(re),.initialized(init),
 .gmii_a_txd(a),.gmii_b_txd(b),.gmii_a_tx_en(ae),.gmii_b_tx_en(be),.gmii_a_tx_er(aer),.gmii_b_tx_er(ber),
 .gmii_a_rxd(net_data),.gmii_b_rxd(bd[63]),.gmii_a_rx_dv(net_valid&&mask[0]),.gmii_b_rx_dv(bv[63]),
 .gmii_a_rx_er(error_a&&net_valid),.gmii_b_rx_er(1'b0),.status_select(4'd0),.status_data(),.time_synchronized(ts));
 integer cycle=0,size=0,fd,fb,af,inf,sf,tf,ia,ib,cf,rc,op,n,x,value,seq=1,cid=0;
 reg prev=0; reg [7:0] data[0:2047]; string filename;
 task flush_logs;
 begin $fflush(fd);$fflush(fb);$fflush(af);$fflush(inf);$fflush(sf);$fflush(tf);$fflush(ia);$fflush(ib);end endtask
 always @(posedge clk) begin
 cycle<=cycle+1;
 if(reset)bv<=0;else bv<={bv[62:0],net_valid&&mask[1]};
 bd[0]<=net_data;for(integer d=1;d<64;d=d+1)bd[d]<=bd[d-1];
 if(ae)begin
 if(!prev)size=0;
 capture[size]=a;size=size+1;$fwrite(fd,"%0d,%02x\n",cycle,a);
 end
 if(be)$fwrite(fb,"%0d,%02x\n",cycle,b);
 if(net_valid&&mask[0])$fwrite(ia,"%0d,%02x,%0d\n",cycle,net_data,error_a);
 if(bv[63])$fwrite(ib,"%0d,%02x,0\n",cycle,bd[63]);
 if(prev&&!ae&&{capture[12],capture[13]}<16'h12b4)begin
 if(qtail-qhead>=1024)$fatal(1,"test link FIFO overflow");
 for(integer d=0;d<size;d=d+1)echo_ram[qtail%1024][d]=capture[d];
 echo_lengths[qtail%1024]=size;qtail=qtail+1;
 end
 prev=ae;
 if(a!==b||ae!==be||aer||ber)$fatal(1,"dual TX fork or TX error");
 if(rv)$fwrite(af,"%0d,%0d,%0d,%0d\n",cycle,rs,re,rx_data);
 if(dut.core.services.plane.rtc_sync_accepted)
 $fwrite(tf,"%0d,%016x,%016x,%016x,%016x,%0d,%0d\n",cycle,
 dut.core.services.plane.sntp_t1,dut.core.services.plane.sntp_t2,dut.core.services.plane.sntp_t3,
 dut.core.services.plane.sntp_t4,dut.core.services.plane.rtc_last_offset,dut.core.services.plane.rtc_last_delay);
 end
 always @(negedge clk)begin
 if(reset)begin echo_active=0;echo_index=0;qhead=0;end
 else if(echo_active)begin
 if(echo_index+1==echo_lengths[qhead%1024])begin echo_active=0;echo_index=0;qhead=qhead+1;end
 else echo_index=echo_index+1;
 end else if(!manual_claim&&qhead<qtail)begin echo_active=1;echo_index=0;end
 end
 task idle(input integer count);repeat(count)@(negedge clk);endtask
 initial begin
 fd=$fopen("wire_a.csv","w");fb=$fopen("wire_b.csv","w");af=$fopen("application.csv","w");
 inf=$fopen("inputs.csv","w");sf=$fopen("status.csv","w");
 tf=$fopen("rtc.csv","w");$fwrite(tf,"cycle,t1,t2,t3,t4,offset,delay\n");
 ia=$fopen("ingress_a.csv","w");ib=$fopen("ingress_b.csv","w");
 $fwrite(ia,"cycle,data,error\n");$fwrite(ib,"cycle,data,error\n");
 $fwrite(fd,"cycle,data\n");$fwrite(fb,"cycle,data\n");$fwrite(af,"cycle,sop,eop,data\n");
 $fwrite(inf,"id,vl,length,cycle\n");
 $fwrite(sf,"cycle,accepted,rejected,sent,delivered,duplicates,integrity,dropa,dropb,parsea,parseb,requests,responses,errors,sync\n");
 idle(8);reset=0;wait(init);
 // Same 100-us user boundary in GUI and automated mailbox transport tests.
 while(cycle<12500)idle(1);
 forever begin
 idle(128);filename=$sformatf("cmd_%0d.txt",seq);cf=$fopen(filename,"r");
 if(cf)begin
 while(!$feof(cf))begin
 rc=$fscanf(cf,"%d %d %d\n",op,n,x);
 if(rc==3)begin
 if(op==1||op==3)begin
 if(n<1||n>2048)$fatal(1,"invalid mailbox length");
 for(integer p=0;p<n;p=p+1)begin rc=$fscanf(cf,"%d\n",value);if(rc!=1)$fatal(1,"truncated mailbox");data[p]=value;end
 end
 case(op)
 1:begin
 @(negedge clk);while(!tx_ready)@(negedge clk);
 $fwrite(inf,"%0d,%0d,%0d,%0d\n",cid,{data[0],data[1]},n-2,cycle);cid=cid+1;
 for(integer p=0;p<n;p=p+1)begin tx_valid=1;tx_data=data[p];@(negedge clk);end
 tx_valid=0;tx_data=0;
 end
 2:begin mask=n;error_a=x;end
 3:begin
 @(negedge clk);manual_claim=1;while(echo_active)@(negedge clk);
 for(integer p=0;p<n;p=p+1)begin manual_valid=1;manual_data=data[p];@(negedge clk);end
 manual_valid=0;idle(128);manual_claim=0;
 end
 4:idle(n);
 default:$fatal(1,"unknown mailbox operation");
 endcase
 end
 end
 $fclose(cf);seq=seq+1;
 end
 end
 end
 always @(negedge clk)if(cycle%1024==0)begin
 $fwrite(sf,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",cycle,
 dut.app_accepted,dut.app_rejected,dut.app_sent,dut.rx_delivered,dut.rx_duplicates,dut.rx_integrity_errors,
 dut.mac_a_dropped,dut.mac_b_dropped,dut.parser_a_rejected,dut.parser_b_rejected,
 dut.snmp_requests,dut.snmp_responses,dut.service_errors,ts);flush_logs;
 end
endmodule
