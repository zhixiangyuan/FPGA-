`timescale 1ns/1ps
module tb_615a_endpoint;
 reg clk=0;always #4 clk=~clk;
 reg reset=1;
 reg [7:0] in_data=0;reg in_valid=0,in_sop=0,in_eop=0;
 reg [10:0] in_length=0;reg [15:0] in_src_port=0,in_dst_port=0;
 wire in_ready;wire [7:0] out_data;wire out_valid,out_sop,out_eop;
 wire [10:0] out_length;wire [15:0] out_src_port,out_dst_port;
 wire active_valid,operation_active;wire [15:0] active_length,active_crc,operation_status;
 wire [31:0] generation;wire [7:0] upload_count,download_count,error_count;
 integer cycle=0;
 wire out_ready=(cycle%5)!=1&&(cycle%17)!=3;
 `ifdef A615A_VO
 afdx_615a_endpoint dut(.*);
 `else
 afdx_615a_endpoint #(.TFTP_TIMEOUT_CYCLES(5000),.STATUS_PERIOD_CYCLES(2000),.DLP_TIMEOUT_CYCLES(100000),.SECOND_CYCLES(2000)) dut(.*);
 `endif
 `include "golden/constants.vh"
 reg [7:0] fixtures[0:FIXTURE_BYTES-1],packet[0:515];
 reg [511:0] cases[0:CASE_COUNT-1];
 reg [7:0] pending[0:1023][0:515];
 integer pending_length[0:1023],pending_src[0:1023],pending_dst[0:1023];
 integer head=0,tail=0,position=0,packet_length=0,packet_src=0,packet_dst=0,packet_start=0;
 integer current_case=0,kind=0,header_offset=0,header_length=0,data_offset=0,data_length=0,control_offset=0,control_length=0,flags=0;
 integer header_requests=0,data_requests=0,status_packets=0,init_received=0,control_acked=0,reset_trigger=0,unload_done=0;
 integer last_network_status=0,server_kind=0,server_offset=0,server_length=0,server_block=0,server_last_size=0;
 integer status_wait_injected=0,wrong_wait_injected=0,max_wait_aborted=0;
 integer frames=0,fd,rf,mf,watch,j,op,block_id,src_server;
 reg stalled=0;reg [52:0] held;
 wire [52:0] fields={out_data,out_sop,out_eop,out_length,out_src_port,out_dst_port};
 task idle(input integer n);repeat(n)@(negedge clk);endtask
 task enqueue_packet(input integer offset,input integer length,input integer src,input integer dst);
  integer k;
  begin
   if(tail>=1024)$fatal(1,"Peer queue full");
   for(k=0;k<length;k=k+1)pending[tail][k]=fixtures[offset+k];
   pending_length[tail]=length;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 task enqueue_ack(input integer block_number,input integer src,input integer dst);
  begin
   pending[tail][0]=0;pending[tail][1]=4;pending[tail][2]=block_number>>8;pending[tail][3]=block_number;
   pending_length[tail]=4;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 task enqueue_data(input integer block_number,input integer offset,input integer length,input integer src,input integer dst);
  integer k;
  begin
   pending[tail][0]=0;pending[tail][1]=3;pending[tail][2]=block_number>>8;pending[tail][3]=block_number;
   for(k=0;k<length;k=k+1)pending[tail][4+k]=fixtures[offset+k];
   pending_length[tail]=length+4;pending_src[tail]=src;pending_dst[tail]=dst;tail=tail+1;
  end
 endtask
 // Exactly one host stream driver. Peer replies and the test sequence enqueue
 // complete packets, preventing overlapping status and bulk receive writers.
 always @(negedge clk)begin
  if(reset||head==tail)begin in_valid=0;in_sop=0;in_eop=0;in_data=0;end
  else begin
   in_valid=1;in_sop=position==0;in_eop=position+1==pending_length[head];
   in_data=pending[head][position];in_length=pending_length[head];
   in_src_port=pending_src[head];in_dst_port=pending_dst[head];
  end
 end
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(reset)begin head=0;tail=0;position=0;stalled<=0;end
  else begin
   if(in_valid&&in_ready)begin
    if(position==0)$fwrite(rf,"%0d,%0d,%0d,%0d,%0d,",current_case,cycle,in_src_port,in_dst_port,in_length);
    $fwrite(rf,"%02x",in_data);
    if(in_eop)begin $fwrite(rf,"\n");head=head+1;position=0;end
    else position=position+1;
   end
   if(stalled&&(!out_valid||fields!==held))$fatal(1,"615A output changed under backpressure");
   stalled<=out_valid&&!out_ready;held<=fields;
   if(out_valid&&out_ready)begin
    if(out_sop)begin packet_start=cycle;packet_length=0;packet_src=out_src_port;packet_dst=out_dst_port;end
    if(packet_src!=out_src_port||packet_dst!=out_dst_port||packet_length>=516)$fatal(1,"615A packet metadata");
    packet[packet_length]=out_data;packet_length=packet_length+1;
    if(out_eop)begin
     if(packet_length!=out_length)$fatal(1,"615A packet length");
     $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,",current_case,frames,packet_start,cycle,packet_src,packet_dst,packet_length);
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
    end
   end
  end
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
 task wait_terminal(input integer code,input integer gen);
  begin
   watch=0;
   while((operation_status!=code||operation_active||generation!=gen||last_network_status!=code||head!=tail)&&watch<300000)begin idle(1);watch=watch+1;end
   if(watch>=300000)$fatal(1,"Terminal case=%0d code=%04x network=%04x gen=%0d/%0d active=%0d",current_case,operation_status,last_network_status,generation,gen,operation_active);
   idle(100);
  end
 endtask
 initial begin #30000000;$fatal(1,"615A system timeout");end
 initial begin
  fd=$fopen("packets.csv","w");rf=$fopen("peer_packets.csv","w");mf=$fopen("metadata.csv","w");
  $fwrite(fd,"case_id,frame,start_cycle,end_cycle,src_port,dst_port,bytes,data\n");
  $fwrite(rf,"case_id,cycle,src_port,dst_port,bytes,data\n");
  $fwrite(mf,"case_id,generation,valid,length,crc,uploads,downloads,errors,status_packets,header_requests,data_requests\n");
  $readmemh("golden/fixtures.mem",fixtures);$readmemh("golden/cases.mem",cases);restart();
  for(current_case=0;current_case<CASE_COUNT;current_case=current_case+1)begin
   kind=cases[current_case][511:480];header_offset=cases[current_case][479:448];header_length=cases[current_case][447:416];
   data_offset=cases[current_case][415:384];data_length=cases[current_case][383:352];control_offset=cases[current_case][351:320];control_length=cases[current_case][319:288];
   flags=cases[current_case][31:0];header_requests=0;data_requests=0;status_packets=0;last_network_status=0;
   init_received=0;control_acked=0;reset_trigger=0;unload_done=0;status_wait_injected=0;wrong_wait_injected=0;max_wait_aborted=0;
   if(kind==0)begin enqueue_packet(LND_OFFSET,LND_LENGTH,40000,WELL_KNOWN_PORT);wait_initial();idle(100);end
   else if(kind==3)begin enqueue_packet(UNKNOWN_OFFSET,UNKNOWN_LENGTH,40000,WELL_KNOWN_PORT);idle(500);end
   else begin
    if(kind==2)enqueue_packet(LND_OFFSET,LND_LENGTH,40000,WELL_KNOWN_PORT);else enqueue_packet(LUI_OFFSET,LUI_LENGTH,40000,WELL_KNOWN_PORT);
    wait_initial();wait_accepted();
    if((flags&4)==0)begin
     if(kind==2)enqueue_packet(LNR_OFFSET,LNR_LENGTH,40000,WELL_KNOWN_PORT);else enqueue_packet(LUR_OFFSET,LUR_LENGTH,40000,WELL_KNOWN_PORT);
    end
    if(kind==4)begin
     watch=0;while(!reset_trigger&&watch<300000)begin idle(1);watch=watch+1;end
     if(!reset_trigger)$fatal(1,"Reset never reached staging");restart();
    end else wait_terminal(cases[current_case][287:256],cases[current_case][255:224]);
   end
   if(active_valid!==cases[current_case][128]||active_length!=cases[current_case][223:192]||active_crc!=cases[current_case][191:160]||
      generation!=cases[current_case][255:224]||upload_count!=cases[current_case][127:96]||download_count!=cases[current_case][95:64]||error_count!=cases[current_case][63:32])
    $fatal(1,"Metadata mismatch case %0d valid=%0d len=%0d gen=%0d up=%0d down=%0d error=%0d",current_case,active_valid,active_length,generation,upload_count,download_count,error_count);
   $fwrite(mf,"%0d,%0d,%0d,%0d,%04x,%0d,%0d,%0d,%0d,%0d,%0d\n",current_case,generation,active_valid,active_length,active_crc,upload_count,download_count,error_count,status_packets,header_requests,data_requests);
  end
  $fclose(fd);$fclose(rf);$fclose(mf);$display("A615A_DIRECTED_PASS cases=%0d frames=%0d",CASE_COUNT,frames);$finish;
 end
endmodule
