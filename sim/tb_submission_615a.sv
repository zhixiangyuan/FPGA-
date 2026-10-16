`timescale 1ns/1ps
module tb_submission_615a;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;
 reg [7:0] rx_data=0;reg rx_valid=0,rx_ready=0;
 wire [7:0] tx_data;wire tx_valid,tx_ready;
 AFDX_top dut(.clk(clk),.reset(reset),.rx_data(rx_data),.rx_valid(rx_valid),.rx_ready(rx_ready),
  .tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready));
 integer cycle=0;
 `include "golden/constants.vh"
 reg [7:0] fixtures[0:FIXTURE_BYTES-1],packet[0:515];
 reg [511:0] cases[0:CASE_COUNT-1];
 reg [7:0] pending[0:1023][0:515];
 integer pending_length[0:1023],pending_src[0:1023],pending_dst[0:1023],pending_vlid[0:1023];
 integer head=0,tail=0,position=0,packet_length=0,packet_src=0,packet_dst=0,packet_start=0;
 integer current_case=0,kind=0,header_offset=0,header_length=0,data_offset=0,data_length=0,control_offset=0,control_length=0,flags=0;
 integer header_requests=0,data_requests=0,status_packets=0,init_received=0,control_acked=0,reset_trigger=0,unload_done=0;
 integer last_network_status=0,server_kind=0,server_offset=0,server_length=0,server_block=0,server_last_size=0;
 integer status_wait_injected=0,wrong_wait_injected=0,max_wait_aborted=0;
 integer frames=0,fd,rf,mf,watch,j,op,block_id,src_server;
 reg [7:0] rx_wire[0:2047],tx_wire[0:2047];
 integer rx_wire_length=0,rx_gap=0,tx_wire_length=0,wire_start=0,wire_fd,wire_rf;
 integer load_sn=1,snmp_sn=1,time_sn=1,wire_vlid,udp_size,k,w;
 integer biz_sequence[0:15];
 integer bg_sent=0,bg_received=0,bg_due=0,rx_bg=0,last_load_start=-125000;
 wire queue_eligible=head!=tail&&(pending_vlid[head]!=16'h1246||cycle-last_load_start>=125000);reg bg_started=0;
 reg was_tx=0;reg [31:0] wire_crc;integer sum;
 task queue_aux(input integer offset,input integer length,input integer vlid,input integer src,input integer dst);
  begin enqueue_packet(offset,length,src,dst);pending_vlid[tail-1]=vlid;end
 endtask
 // Test-only Ethernet/IPv4/UDP encoder. Python reconstructs every observed wire
 // frame independently, including checksum, padding, AFDX SN and Ethernet FCS.
 task make_rx_wire(input integer background);
  integer x,y,n,vl,sn,total;reg [31:0] crc;
  begin
   vl=background?'h1235+(bg_sent%15):pending_vlid[head];n=background?1471:pending_length[head];
   if(vl>='h1234&&vl<='h1243)begin sn=biz_sequence[vl-'h1234];biz_sequence[vl-'h1234]=sn==255?1:sn+1;end
   else if(vl=='h1244)begin sn=snmp_sn;snmp_sn=snmp_sn==255?1:snmp_sn+1;end
   else if(vl=='h1245)begin sn=time_sn;time_sn=time_sn==255?1:time_sn+1;end
   else begin sn=load_sn;load_sn=load_sn==255?1:load_sn+1;end
   for(x=0;x<2047;x=x+1)rx_wire[x]=0;
   for(x=0;x<7;x=x+1)rx_wire[x]='h55;rx_wire[7]='hd5;
   rx_wire[8]='h03;rx_wire[12]=vl>>8;rx_wire[13]=vl;
   rx_wire[14]='h02;rx_wire[19]=(vl>='h1234&&vl<='h1243) ? 'h09:'h0a;
   rx_wire[20]='h08;rx_wire[21]=0;rx_wire[22]='h45;
   total=28+n;rx_wire[24]=total>>8;rx_wire[25]=total;rx_wire[28]='h40;
   rx_wire[30]=1;rx_wire[31]=17;
   rx_wire[34]=10;rx_wire[37]=(vl>='h1234&&vl<='h1243) ? 1:9;
   rx_wire[38]=(vl>='h1234&&vl<='h1243) ? 224:10;rx_wire[39]=(vl>='h1234&&vl<='h1243) ? 224:0;
   rx_wire[41]=(vl>='h1234&&vl<='h1243) ? 60:1;
   sum=0;for(x=22;x<42;x=x+2)sum=sum+{rx_wire[x],rx_wire[x+1]};
   while(sum>>16)sum=(sum&65535)+(sum>>16);sum=(~sum)&65535;
   rx_wire[32]=sum>>8;rx_wire[33]=sum;
   rx_wire[42]=background?0:pending_src[head]>>8;rx_wire[43]=background?24:pending_src[head];
   rx_wire[44]=background?0:pending_dst[head]>>8;rx_wire[45]=background?23:pending_dst[head];
   rx_wire[46]=(n+8)>>8;rx_wire[47]=n+8;
   for(x=0;x<n;x=x+1)begin
    if(background)begin
     if(x==0)rx_wire[50+x]=bg_sent>>8;
     else if(x==1)rx_wire[50+x]=bg_sent;
     else rx_wire[50+x]=(x*31+bg_sent*7+(x>>3))&255;
    end else rx_wire[50+x]=pending[head][x];
   end
   x=50+n;if(x<67)x=67;rx_wire[x]=sn;x=x+1;
   crc=32'hffffffff;
   for(y=8;y<x;y=y+1)begin
    crc=crc^rx_wire[y];repeat(8)crc=crc[0]?(crc>>1)^32'hedb88320:crc>>1;
   end
   crc=~crc;for(y=0;y<4;y=y+1)rx_wire[x+y]=crc>>(8*y);
   rx_wire_length=x+4;
   if(vl=='h1246)last_load_start=cycle;
   $fwrite(wire_rf,"%0d,%0d,%0d,",current_case,cycle,rx_wire_length);
   for(y=0;y<rx_wire_length;y=y+1)$fwrite(wire_rf,"%02x",rx_wire[y]);$fwrite(wire_rf,"\n");
  end
 endtask
 task idle(input integer n);repeat(n)@(negedge clk);endtask
 task enqueue_packet(input integer offset,input integer length,input integer src,input integer dst);
  integer k;
  begin
   if(tail>=1024)$fatal(1,"Peer queue full");
   for(k=0;k<length;k=k+1)pending[tail][k]=fixtures[offset+k];
   pending_vlid[tail]='h1246;pending_length[tail]=length;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 task enqueue_ack(input integer block_number,input integer src,input integer dst);
  begin
   pending[tail][0]=0;pending[tail][1]=4;pending[tail][2]=block_number>>8;pending[tail][3]=block_number;
   pending_vlid[tail]='h1246;pending_length[tail]=4;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 task enqueue_data(input integer block_number,input integer offset,input integer length,input integer src,input integer dst);
  integer k;
  begin
   pending[tail][0]=0;pending[tail][1]=3;pending[tail][2]=block_number>>8;pending[tail][3]=block_number;
   for(k=0;k<length;k=k+1)pending[tail][4+k]=fixtures[offset+k];
   pending_vlid[tail]='h1246;pending_length[tail]=length+4;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 // One serialized GMII peer; all replies are queued after complete wire TX.
 always @(negedge clk)begin
  if(reset)begin rx_valid=0;rx_data=0;end
  else if(rx_gap!=0)begin rx_valid=0;rx_data=0;rx_gap=rx_gap-1;end
  else if(position==0&&!queue_eligible&&(!bg_started||bg_sent>=BACKGROUND_PACKETS||cycle<bg_due))begin rx_valid=0;rx_data=0;end
  else begin
   if(position==0)begin
    rx_bg=!queue_eligible;make_rx_wire(rx_bg);
    if(rx_bg)begin bg_sent=bg_sent+1;bg_due=bg_due+9000;end
   end
   rx_valid=1;rx_data=rx_wire[position];rx_ready=~rx_ready;
  end
 end
 always @(posedge clk)begin
  cycle=cycle+1;
  if(reset)begin head=0;tail=0;position=0;rx_gap=0;end
  else if(rx_valid)begin
   position=position+1;
   if(position==rx_wire_length)begin
    if(!rx_bg&&pending_vlid[head]=='h1246)begin
     $fwrite(rf,"%0d,%0d,%0d,%0d,%0d,",current_case,cycle,pending_src[head],pending_dst[head],pending_length[head]);
     for(k=0;k<pending_length[head];k=k+1)$fwrite(rf,"%02x",pending[head][k]);$fwrite(rf,"\n");
    end
    if(!rx_bg)head=head+1;position=0;rx_gap=2048;
   end
  end
  if(tx_ready!==1'b0)$fatal(1,"valid-only contract");
  if(tx_valid)begin
   if(!was_tx)begin tx_wire_length=0;wire_start=cycle;end
   if(tx_wire_length>=2047)$fatal(1,"Oversized wire output");
   tx_wire[tx_wire_length]=tx_data;tx_wire_length=tx_wire_length+1;
  end
  if(was_tx&&!tx_valid)begin
   $fwrite(wire_fd,"%0d,%0d,%0d,%0d,",current_case,wire_start,cycle-1,tx_wire_length);
   for(k=0;k<tx_wire_length;k=k+1)$fwrite(wire_fd,"%02x",tx_wire[k]);$fwrite(wire_fd,"\n");
   wire_vlid={tx_wire[12],tx_wire[13]};
   if(wire_vlid=='h1246)begin
    udp_size={tx_wire[46],tx_wire[47]};packet_length=udp_size-8;
    if(packet_length<4||packet_length>516||tx_wire_length<54+packet_length)$fatal(1,"615A wire UDP length");
    packet_src={tx_wire[42],tx_wire[43]};packet_dst={tx_wire[44],tx_wire[45]};packet_start=wire_start;
    for(k=0;k<packet_length;k=k+1)packet[k]=tx_wire[50+k];
    $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,",current_case,frames,packet_start,cycle-1,packet_src,packet_dst,packet_length);
    for(j=0;j<packet_length;j=j+1)$fwrite(fd,"%02x",packet[j]);$fwrite(fd,"\n");frames=frames+1;
     op={packet[0],packet[1]};block_id={packet[2],packet[3]};
     if(packet_src>=57344)begin
      // Independent status TFTP server. The Python verifier parses all content.
      if(op==2&&packet_dst==WELL_KNOWN_PORT)begin
       if((flags&64)!=0&&status_wait_injected==0)begin
        enqueue_packet(ERROR_WAIT_OFFSET,ERROR_WAIT_LENGTH,55000,packet_src);status_wait_injected=1;
       end else enqueue_ack(0,55000,packet_src);
      end
      else if(op==3&&packet_dst==55000)begin
       if(block_id!=1||packet_length<12)$fatal(1,"Status transfer framing");
       last_network_status={packet[10],packet[11]};status_packets=status_packets+1;
       if((flags&4096)!=0&&{packet[23],packet[24]}==16'hffff&&max_wait_aborted==0)begin
        enqueue_packet(ERROR_ABORT_OFFSET,ERROR_ABORT_LENGTH,55000,packet_src);max_wait_aborted=1;
       end else enqueue_ack(block_id,55000,packet_src);
      end else $fatal(1,"Unexpected status opcode=%0d dst=%0d",op,packet_dst);
     end else if(op==3&&packet_dst==40000)begin
      init_received=init_received+1;enqueue_ack(block_id,40000,packet_src);
     end else if(op==4&&packet_dst==40000)begin
      if(block_id==0)enqueue_data(1,control_offset,control_length,40000,packet_src);
      else if(block_id==1)control_acked=1;
      else $fatal(1,"Control block number");
     end else if(op==1&&packet_dst==WELL_KNOWN_PORT)begin
      if(packet[9]==8'h4c)begin
       header_requests=header_requests+1;server_kind=0;server_offset=header_offset;server_length=header_length;
       if((flags&2)!=0||((flags&1)!=0&&header_requests==1))begin end
       else if((flags&256)!=0)enqueue_packet(ERROR_WAIT_ZERO_OFFSET,ERROR_WAIT_ZERO_LENGTH,30001,packet_src);
       else if((flags&512)!=0)enqueue_packet(ERROR_BAD_WAIT_OFFSET,ERROR_BAD_WAIT_LENGTH,30001,packet_src);
       else if((flags&4096)!=0)enqueue_packet(ERROR_WAIT_MAX_OFFSET,ERROR_WAIT_MAX_LENGTH,30001,packet_src);
       else if((flags&32)!=0)enqueue_packet(ERROR_ABORT_OFFSET,ERROR_ABORT_LENGTH,30001,packet_src);
       else if((flags&16)!=0&&header_requests==1)enqueue_packet(ERROR_WAIT_OFFSET,ERROR_WAIT_LENGTH,30001,packet_src);
       else begin
        server_block=1;server_last_size=server_length<512?server_length:512;enqueue_data(1,server_offset,server_last_size,30001,packet_src);
       end
      end else if(packet[9]==8'h62)begin
       data_requests=data_requests+1;server_kind=1;server_offset=data_offset;server_length=data_length;
       server_block=1;server_last_size=server_length<512?server_length:512;enqueue_data(1,server_offset,server_last_size,30002,packet_src);
      end else $fatal(1,"Unexpected requested file");
     end else if(op==4&&(packet_dst==30001||packet_dst==30002))begin
      if((flags&8)!=0&&packet_dst==30002&&block_id==1)reset_trigger=1;
      else if((flags&128)!=0&&packet_dst==30002&&block_id==1&&data_requests==1)
       enqueue_packet(ERROR_WAIT_OFFSET,ERROR_WAIT_LENGTH,30002,packet_src);
      else if((flags&2048)!=0&&packet_dst==30002&&block_id==1)begin
       if(wrong_wait_injected==0)begin
        enqueue_packet(ERROR_WAIT_OFFSET,ERROR_WAIT_LENGTH,30003,packet_src);wrong_wait_injected=1;
       end
      end
      else if(block_id==server_block&&server_last_size==512)begin
       if((flags&1024)!=0&&packet_dst==30002&&wrong_wait_injected==0)begin
        enqueue_packet(ERROR_WAIT_OFFSET,ERROR_WAIT_LENGTH,30003,packet_src);wrong_wait_injected=1;
       end
       server_last_size=server_length-block_id*512;if(server_last_size>512)server_last_size=512;
       enqueue_data(block_id+1,server_offset+block_id*512,server_last_size,packet_dst,packet_src);server_block=block_id+1;
      end
     end else if(op==2&&packet_dst==WELL_KNOWN_PORT)enqueue_ack(0,35000,packet_src);
     else if(op==3&&packet_dst==35000)begin
      enqueue_ack(block_id,35000,packet_src);if(packet_length<516)unload_done=1;
     end else if(op==5)begin end
     else $fatal(1,"Unexpected bulk opcode=%0d dst=%0d",op,packet_dst);
   end else if(wire_vlid=='h1245)begin
    // Copy the actual on-wire transmit timestamp into a valid server origin.
    pending_vlid[tail]='h1245;pending_src[tail]=123;pending_dst[tail]=49152;pending_length[tail]=48;
    for(k=0;k<48;k=k+1)pending[tail][k]=0;
    pending[tail][0]='h24;pending[tail][1]=2;pending[tail][2]=6;pending[tail][3]='he8;
    for(k=0;k<8;k=k+1)begin
     pending[tail][24+k]=tx_wire[90+k];pending[tail][32+k]=tx_wire[90+k];pending[tail][40+k]=tx_wire[90+k];
    end
    tail=tail+1;
   end else if(wire_vlid>='h1234&&wire_vlid<='h1243)begin
    if({tx_wire[46],tx_wire[47]}==1479)bg_received=bg_received+1;
   end else if(wire_vlid!='h1244)$fatal(1,"Unknown output VL");
  end
  was_tx=tx_valid;
 end
 task restart;
  begin reset=1;idle(4);reset=0;idle(4);end
 endtask
 task wait_initial;
  begin
   watch=0;while(init_received==0&&watch<300000)begin idle(1);watch=watch+1;end
   if(init_received==0)$fatal(1,"Initialization timeout case %0d",current_case);
  end
 endtask
 task wait_accepted;
  begin
   watch=0;while(last_network_status!=1&&watch<300000)begin idle(1);watch=watch+1;end
   if(last_network_status!=1)$fatal(1,"No accepted status case %0d",current_case);
  end
 endtask
 task wait_terminal(input integer code,input integer unused_gen);
  begin
   watch=0;
   while((last_network_status!=code||head!=tail||rx_valid||was_tx)&&watch<4000000)begin idle(1);watch=watch+1;end
   if(watch>=4000000)$fatal(1,"Terminal case=%0d expected=%04x network=%04x",current_case,code,last_network_status);
   idle(2000);
  end
 endtask
 initial begin #500000000;$fatal(1,"615A system timeout");end
 initial begin
  wire_fd=$fopen("wire_tx.csv","w");wire_rf=$fopen("wire_rx.csv","w");
  $fwrite(wire_fd,"case_id,start_cycle,end_cycle,bytes,data\n");$fwrite(wire_rf,"case_id,start_cycle,bytes,data\n");
  fd=$fopen("packets.csv","w");rf=$fopen("peer_packets.csv","w");mf=$fopen("metadata.csv","w");
  $fwrite(fd,"case_id,frame,start_cycle,end_cycle,src_port,dst_port,bytes,data\n");
  $fwrite(rf,"case_id,cycle,src_port,dst_port,bytes,data\n");
  $fwrite(mf,"case_id,generation,valid,length,crc,uploads,downloads,errors,status_packets,header_requests,data_requests\n");
  for(k=0;k<16;k=k+1)biz_sequence[k]=1;
  $readmemh("golden/fixtures.mem",fixtures);$readmemh("golden/cases.mem",cases);restart();
  for(current_case=0;current_case<CASE_COUNT;current_case=current_case+1)begin
   kind=cases[current_case][511:480];header_offset=cases[current_case][479:448];header_length=cases[current_case][447:416];
   data_offset=cases[current_case][415:384];data_length=cases[current_case][383:352];control_offset=cases[current_case][351:320];control_length=cases[current_case][319:288];
   flags=cases[current_case][31:0];header_requests=0;data_requests=0;status_packets=0;last_network_status=0;
   init_received=0;control_acked=0;reset_trigger=0;unload_done=0;status_wait_injected=0;wrong_wait_injected=0;max_wait_aborted=0;
   if(kind==0)begin enqueue_packet(LND_OFFSET,LND_LENGTH,40000,WELL_KNOWN_PORT);wait_initial();idle(2000);end
   else if(kind==3)begin enqueue_packet(UNKNOWN_OFFSET,UNKNOWN_LENGTH,40000,WELL_KNOWN_PORT);idle(500);end
   else begin
    if(kind==2)enqueue_packet(LND_OFFSET,LND_LENGTH,40000,WELL_KNOWN_PORT);else enqueue_packet(LUI_OFFSET,LUI_LENGTH,40000,WELL_KNOWN_PORT);
    wait_initial();wait_accepted();
    if(!bg_started)begin bg_started=1;bg_due=cycle+5000;end
    queue_aux(AUX_BIZ_OFFSET,AUX_BIZ_LENGTH,'h1234,24,23);
    queue_aux(AUX_SNMP_OFFSET,AUX_SNMP_LENGTH,'h1244,49152,161);
    if((flags&4)==0)begin
     if(kind==2)enqueue_packet(LNR_OFFSET,LNR_LENGTH,40000,WELL_KNOWN_PORT);else enqueue_packet(LUR_OFFSET,LUR_LENGTH,40000,WELL_KNOWN_PORT);
    end
    if(kind==4)begin
     watch=0;while(!reset_trigger&&watch<300000)begin idle(1);watch=watch+1;end
     if(!reset_trigger)$fatal(1,"Reset never reached staging");restart();
    end else wait_terminal(cases[current_case][287:256],cases[current_case][255:224]);
   end
  end
  watch=0;
  while((bg_sent<BACKGROUND_PACKETS||rx_valid||head!=tail||was_tx||bg_received<BACKGROUND_PACKETS)&&watch<5000000)begin idle(1);watch=watch+1;end
  if(bg_sent!=BACKGROUND_PACKETS||bg_received!=BACKGROUND_PACKETS)$fatal(1,"Continuous-load business loss sent=%0d received=%0d",bg_sent,bg_received);
  $fclose(fd);$fclose(rf);$fclose(mf);$fclose(wire_fd);$fclose(wire_rf);$display("SUBMISSION_615A_PASS cases=%0d frames=%0d",CASE_COUNT,frames);$finish;
 end
endmodule
