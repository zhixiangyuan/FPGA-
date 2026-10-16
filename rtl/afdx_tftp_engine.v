// RFC1350 octet transport, one bounded transfer at a time, client and server.
// The validated UDP peer IP is selected upstream; both UDP TIDs are checked here.
// File policy and atomic visibility belong to the file backend, not this layer.
// Filename profile: 1..32 bytes. No netascii or option negotiation is provided.
module afdx_tftp_engine #(
 parameter integer TIMEOUT_CYCLES=12500000,
 parameter integer MAX_RETRIES=3,
 parameter integer MAX_FILE_BYTES=4096,
 parameter [15:0] TID_SEED=16'hc159,
 parameter [2:0] TID_PREFIX=3'b110
)(
 input wire clk,reset,cancel,
 input wire start,input wire start_write,input wire [255:0] start_name,input wire [5:0] start_name_length,
 output wire start_ready,output wire busy,output wire port_match,
 output reg done,failed,aborted,output reg [15:0] failure_code,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,
 input wire [15:0] in_src_port,in_dst_port,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,
 output wire out_sop,out_eop,output wire [10:0] out_length,
 output wire [15:0] out_src_port,out_dst_port,
 output wire file_open_valid,input wire file_open_ready,input wire [15:0] file_open_error,
 output reg [255:0] file_name,output reg [5:0] file_name_length,
 output reg file_write,output reg file_client,input wire [15:0] file_read_length,
 output wire file_read_enable,output wire [15:0] file_read_address,input wire [7:0] file_read_data,
 output wire file_write_valid,input wire file_write_ready,output wire [7:0] file_write_data,
 output wire [15:0] file_write_address,
 output wire file_finish_valid,input wire file_finish_ready,input wire [15:0] file_finish_error,
 output wire [15:0] file_finish_length,
 output reg [31:0] retry_count,duplicate_count,reject_count,completed_count
);
 localparam IDLE=0,WAIT_PACKET=1,PARSE_ISSUE=2,PARSE_BYTE=3,OPEN_FILE=4,
  BUILD=5,READ_ISSUE=6,READ_STORE=7,TX_PRIME=8,TX_STREAM=9,
  RX_ISSUE=10,RX_BYTE=11,FINISH_FILE=12,HANDLE_PACKET=13;
 localparam AFTER_WAIT=0,AFTER_DONE=1,AFTER_IDLE=2;
 reg [3:0] state;
 reg [1:0] after_tx;
 reg [7:0] rx_mem[0:515],tx_mem[0:515];
 reg [9:0] rx_count,rx_size,rx_index,tx_index,build_index;
 reg [10:0] rx_declared;
 reg [15:0] rx_src,rx_dst,rx_opcode,rx_block;
 reg rx_collect,rx_full,rx_bad;
 reg [31:0] rx_watch;
 reg [7:0] rx_q,tx_q;
 reg [15:0] local_tid,peer_tid,tid_lfsr,block_no,file_offset,read_length;
 reg peer_locked,receiving,tx_final;
 reg [9:0] payload_length;
 reg [10:0] tx_length;
 reg [15:0] build_opcode,build_block;
 reg [31:0] timer;
 localparam integer RETRY_BITS=MAX_RETRIES>0?$clog2(MAX_RETRIES+1):1;
 reg [RETRY_BITS-1:0] retries;
 wire [63:0] retry_period=(64'd0+TIMEOUT_CYCLES)<<retries;
 wire [31:0] retry_limit=(|retry_period[63:32])?32'hffffffff:retry_period[31:0];
 wire [63:0] dally_period=(64'd0+TIMEOUT_CYCLES)<<(MAX_RETRIES+1);
 wire [31:0] dally_limit=(|dally_period[63:32])?32'hffffffff:dally_period[31:0];
 reg [5:0] mode_index;
 reg parse_mode,parse_bad,parse_duplicate;
 reg [5:0] parse_count;
 reg small_tx;
 reg [15:0] small_src,small_dst,small_code,small_block;
 reg small_ack;
 reg dally_valid;
 reg [15:0] dally_local,dally_peer,dally_block;
 reg [31:0] dally_timer;
 reg busy_session;
 reg cancel_pending;
 // Bulk and status endpoints use disjoint halves of the dynamic UDP range.
 wire [15:0] candidate_tid={TID_PREFIX,tid_lfsr[12:0]};
 wire [12:0] alternate_tid=tid_lfsr[12:0]+13'd1;
 wire [15:0] new_tid=candidate_tid==local_tid?{TID_PREFIX,alternate_tid}:candidate_tid;
 wire [16:0] next_offset={1'b0,file_offset}+((block_no==0)?17'd0:{7'd0,payload_length});
 wire [16:0] remaining_bytes={1'b0,read_length}-next_offset;
 wire [9:0] next_payload=remaining_bytes>=512?10'd512:remaining_bytes[9:0];
 wire rx_fire=in_valid&&in_ready;
 assign port_match=!reset&&((local_tid!=0&&in_dst_port==local_tid)||(dally_valid&&in_dst_port==dally_local));
 wire tx_fire=out_valid&&out_ready;
 wire wait_state=state==WAIT_PACKET||state==IDLE;
 assign start_ready=!reset&&!cancel&&!cancel_pending&&state==IDLE&&!rx_full&&!rx_collect;
 assign busy=state!=IDLE;
 assign in_ready=!reset&&!cancel&&!cancel_pending&&!rx_full&&wait_state;
 assign file_open_valid=!reset&&!cancel&&!cancel_pending&&state==OPEN_FILE;
 assign file_read_enable=!reset&&state==READ_ISSUE;
 assign file_read_address=file_offset+{6'd0,build_index}-16'd4;
 assign file_write_valid=!reset&&!cancel&&!cancel_pending&&state==RX_BYTE;
 assign file_write_data=rx_q;
 assign file_write_address=file_offset+{6'd0,rx_index}-16'd4;
 assign file_finish_valid=!reset&&!cancel&&!cancel_pending&&state==FINISH_FILE;
 assign file_finish_length=file_offset+{6'd0,payload_length};
 assign out_valid=!reset&&state==TX_STREAM;
 assign out_sop=out_valid&&tx_index==0;
 assign out_eop=out_valid&&tx_index+1'b1==out_length;
 assign out_length=small_tx?(small_ack?11'd4:11'd5):tx_length;
 assign out_src_port=small_tx?small_src:local_tid;
 assign out_dst_port=small_tx?small_dst:peer_tid;
 assign out_data=small_tx?(tx_index==0?8'd0:tx_index==1?(small_ack?8'd4:8'd5):
                         tx_index==2?(small_ack?small_block[15:8]:small_code[15:8]):
                         tx_index==3?(small_ack?small_block[7:0]:small_code[7:0]):8'd0):tx_q;
 // The small ACK path is four bytes; errors include a terminating empty string.
 // Reuse the sized length net. An inline conditional in this comparison
 // triggers a Verific elaboration assertion in the bundled synthesis tool.
 wire last_tx=tx_index+1'b1==out_length;
 wire rx_read=state==PARSE_ISSUE||state==RX_ISSUE;
 wire tx_write_enable=state==BUILD||state==READ_STORE;
 wire [7:0] request_byte=build_index<2+file_name_length?file_name[(build_index-2)*8+:8]:
  build_index==3+file_name_length?8'h6f:build_index==4+file_name_length?8'h63:
  build_index==5+file_name_length?8'h74:build_index==6+file_name_length?8'h65:
  build_index==7+file_name_length?8'h74:8'd0;
 wire [7:0] build_byte=build_index==0?8'd0:build_index==1?build_opcode[7:0]:
  (build_opcode==1||build_opcode==2)?request_byte:
  build_index==2?build_block[15:8]:build_index==3?build_block[7:0]:8'd0;
 wire [7:0] tx_write_data=state==READ_STORE?file_read_data:build_byte;
 wire tx_read_enable=state==TX_PRIME||(tx_fire&&!small_tx&&!last_tx);
 wire [9:0] tx_read_address=state==TX_PRIME?10'd0:tx_index+1'b1;
 always @(posedge clk)begin
  if(rx_fire&&(!rx_collect||rx_count<516))rx_mem[!rx_collect?10'd0:rx_count]<=in_data;
  if(rx_read)rx_q<=rx_mem[rx_index];
  if(tx_write_enable)tx_mem[build_index]<=tx_write_data;
  if(tx_read_enable)tx_q<=tx_mem[tx_read_address];
 end
 // RX packet collection is independent of RAM reads and file writes. A packet
 // is never acted on before its actual length and framing have been checked.
 always @(posedge clk)begin
  if(reset)begin
   rx_count<=0;rx_size<=0;rx_collect<=0;rx_full<=0;rx_bad<=0;rx_watch<=0;
   rx_src<=0;rx_dst<=0;rx_opcode<=0;rx_block<=0;rx_declared<=0;
  end else begin
   if(state==HANDLE_PACKET)rx_full<=0;
   if(cancel)begin rx_collect<=0;rx_full<=0;rx_watch<=0;end
   if(rx_collect)begin
    if(rx_fire)rx_watch<=0;
    else if(rx_watch+1>=TIMEOUT_CYCLES)begin rx_collect<=0;rx_watch<=0;end
    else rx_watch<=rx_watch+1'b1;
   end
   if(rx_fire)begin
    if(!rx_collect)begin
     rx_src<=in_src_port;rx_dst<=in_dst_port;rx_opcode<={in_data,8'd0};rx_block<=0;
     rx_declared<=in_length;rx_count<=1;rx_bad<=!in_sop||in_length<2||in_length>516;
     rx_collect<=!in_eop;rx_watch<=0;
     if(in_eop)begin rx_full<=1;rx_size<=1;rx_bad<=1;end
    end else begin
     if(rx_count==1)rx_opcode[7:0]<=in_data;
     if(rx_count==2)rx_block[15:8]<=in_data;
     if(rx_count==3)rx_block[7:0]<=in_data;
     if(in_sop||rx_count>=516||in_length!=rx_declared||in_src_port!=rx_src||in_dst_port!=rx_dst)rx_bad<=1;
     if(rx_count<1023)rx_count<=rx_count+1'b1;
     if(in_eop)begin
      rx_collect<=0;rx_full<=1;rx_size<=rx_count+1'b1;
      if(rx_count+1'b1!=rx_declared)rx_bad<=1;
     end
    end
   end
  end
 end
 task prepare;
  input [15:0] op,b;
  input [10:0] length;
  input [1:0] next_action;
  begin
   build_opcode<=op;build_block<=b;tx_length<=length;build_index<=0;
   small_tx<=0;after_tx<=next_action;state<=BUILD;
  end
 endtask
 task transient;
  input ack;
  input [15:0] code_or_block,src,dst;
  begin
   small_tx<=1;small_ack<=ack;small_code<=code_or_block;small_block<=code_or_block;
   small_src<=src;small_dst<=dst;tx_index<=0;state<=TX_STREAM;
  end
 endtask
 task abort_transfer;
  input [15:0] code;
  begin aborted<=1;failed<=1;failure_code<=code;end
 endtask
 always @(posedge clk)begin
  if(reset)begin
   state<=IDLE;done<=0;failed<=0;aborted<=0;failure_code<=0;cancel_pending<=0;
   local_tid<=0;peer_tid<=0;peer_locked<=0;receiving<=0;tid_lfsr<=TID_SEED;
   file_name<=0;file_name_length<=0;file_write<=0;file_client<=0;
   block_no<=0;file_offset<=0;read_length<=0;payload_length<=0;tx_final<=0;
   timer<=0;retries<=0;retry_count<=0;duplicate_count<=0;reject_count<=0;completed_count<=0;
   tx_index<=0;build_index<=0;tx_length<=0;build_opcode<=0;build_block<=0;after_tx<=AFTER_WAIT;
   rx_index<=0;mode_index<=0;parse_mode<=0;parse_bad<=0;parse_duplicate<=0;parse_count<=0;
   small_tx<=0;small_src<=0;small_dst<=0;small_code<=0;small_block<=0;small_ack<=0;
   dally_valid<=0;dally_timer<=0;dally_local<=0;dally_peer<=0;dally_block<=0;
  end else begin
   done<=0;failed<=0;aborted<=0;
   if(cancel)cancel_pending<=1;
   if(dally_valid)begin
    if(dally_timer+1>=dally_limit)dally_valid<=0;
    else dally_timer<=dally_timer+1'b1;
   end
   if((cancel||cancel_pending)&&state!=TX_STREAM&&state!=TX_PRIME)begin
    if(busy_session)begin aborted<=1;failed<=1;failure_code<=0;end
    state<=IDLE;cancel_pending<=0;
   end else case(state)
    IDLE:begin
     timer<=0;retries<=0;
     if(rx_full)state<=HANDLE_PACKET;
     else if(start&&start_ready)begin
      if(start_name_length==0||start_name_length>32)begin failed<=1;failure_code<=4;end
      else begin
       local_tid<=new_tid;tid_lfsr<={tid_lfsr[14:0],tid_lfsr[15]^tid_lfsr[13]^tid_lfsr[12]^tid_lfsr[10]};
       peer_tid<=69;peer_locked<=0;file_client<=1;file_write<=!start_write;receiving<=!start_write;
       file_name<=start_name;file_name_length<=start_name_length;file_offset<=0;block_no<=0;state<=OPEN_FILE;
      end
     end
    end
    WAIT_PACKET:begin
     if(rx_full)state<=HANDLE_PACKET;
     else if(timer+1>=retry_limit)begin
      timer<=0;
      if(retries>=MAX_RETRIES)begin abort_transfer(0);state<=IDLE;end
      else begin retries<=retries+1'b1;retry_count<=retry_count+1'b1;small_tx<=0;after_tx<=AFTER_WAIT;state<=TX_PRIME;end
     end else timer<=timer+1'b1;
    end
    HANDLE_PACKET:begin
     // Unrelated traffic cannot reset the retry timer or poison a file session.
     state<=busy_session?WAIT_PACKET:IDLE;
     if(rx_bad)reject_count<=reject_count+1'b1;
     else if(dally_valid&&rx_dst==dally_local&&rx_src==dally_peer&&rx_opcode==3&&rx_block==dally_block&&rx_size>=4)begin
      duplicate_count<=duplicate_count+1'b1;transient(1,dally_block,dally_local,dally_peer);
     end else if(rx_dst==69&&(rx_opcode==1||rx_opcode==2)&&rx_size<10)begin
      reject_count<=reject_count+1'b1;transient(0,4,69,rx_src);
     end else if(busy_session&&!file_client&&rx_dst==69&&rx_src==peer_tid&&
                 rx_opcode==(receiving?16'd2:16'd1)&&block_no==(receiving?16'd0:16'd1))begin
      parse_duplicate<=1;parse_mode<=0;parse_bad<=0;mode_index<=0;parse_count<=0;
      rx_index<=2;state<=PARSE_ISSUE;
     end else if(!busy_session&&rx_dst==69&&(rx_opcode==1||rx_opcode==2))begin
      local_tid<=new_tid;tid_lfsr<={tid_lfsr[14:0],tid_lfsr[15]^tid_lfsr[13]^tid_lfsr[12]^tid_lfsr[10]};
      peer_tid<=rx_src;peer_locked<=1;receiving<=rx_opcode==2;file_write<=rx_opcode==2;file_client<=0;
      file_name<=0;file_name_length<=0;parse_mode<=0;parse_bad<=0;mode_index<=0;parse_duplicate<=0;parse_count<=0;
      file_offset<=0;block_no<=0;rx_index<=2;state<=PARSE_ISSUE;
     end else if(rx_dst!=local_tid||(peer_locked&&rx_src!=peer_tid)||!busy_session)begin
      reject_count<=reject_count+1'b1;transient(0,5,rx_dst,rx_src);
     end else if(rx_opcode==5&&rx_size>=5)begin abort_transfer(rx_block);state<=IDLE;end
     else if(receiving&&rx_opcode==3&&rx_size>=4&&rx_size<=516)begin
      if(rx_block==block_no+1'b1)begin
       if(!peer_locked)begin peer_tid<=rx_src;peer_locked<=1;end
       if({1'b0,file_offset}+rx_size-4>MAX_FILE_BYTES)begin
        abort_transfer(3);prepare(5,3,5,AFTER_IDLE);
       end else begin
        payload_length<=rx_size-4;block_no<=rx_block;rx_index<=4;timer<=0;retries<=0;
        if(rx_size==4)state<=FINISH_FILE;else state<=RX_ISSUE;
       end
      end else if(rx_block==block_no&&peer_locked)begin
       duplicate_count<=duplicate_count+1'b1;small_tx<=0;after_tx<=AFTER_WAIT;state<=TX_PRIME;
      end else reject_count<=reject_count+1'b1;
     end else if(!receiving&&rx_opcode==4&&rx_size==4)begin
      if(rx_block==block_no)begin
       if(!peer_locked)begin peer_tid<=rx_src;peer_locked<=1;end
       timer<=0;retries<=0;
       if(block_no!=0&&tx_final)begin done<=1;completed_count<=completed_count+1'b1;state<=IDLE;end
       else begin
        if(block_no!=0)file_offset<=file_offset+payload_length;
        block_no<=block_no+1'b1;
        payload_length<=next_payload;tx_final<=next_payload<512;
        prepare(3,block_no+1'b1,{1'b0,next_payload}+11'd4,AFTER_WAIT);
       end
      end else duplicate_count<=duplicate_count+1'b1; // RFC1123: no DATA resend on duplicate ACK.
     end else begin abort_transfer(4);prepare(5,4,5,AFTER_IDLE);end
    end
    PARSE_ISSUE:state<=PARSE_BYTE;
    PARSE_BYTE:begin
     if(!parse_mode)begin
      if(rx_q==0)begin
       if(parse_count==0||(parse_duplicate&&parse_count!=file_name_length))parse_bad<=1;
       parse_mode<=1;mode_index<=0;
      end else if(parse_count<32)begin
       if(parse_duplicate)begin if(file_name[parse_count*8+:8]!=rx_q)parse_bad<=1;end
       else begin file_name[parse_count*8+:8]<=rx_q;file_name_length<=parse_count+1'b1;end
       parse_count<=parse_count+1'b1;
      end else parse_bad<=1;
     end else begin
      if(mode_index<5)begin
       if((rx_q|8'h20)!=octet_character(mode_index))parse_bad<=1;
      end else if(mode_index!=5||rx_q!=0)parse_bad<=1;
      if(mode_index<63)mode_index<=mode_index+1'b1;
     end
     if(rx_index+1'b1==rx_size)begin
      if(parse_bad||!parse_mode||mode_index!=5||rx_q!=0)begin
       if(parse_duplicate)transient(0,4,local_tid,peer_tid);
       else prepare(5,4,5,AFTER_IDLE);
      end else if(parse_duplicate)begin
       duplicate_count<=duplicate_count+1'b1;small_tx<=0;after_tx<=AFTER_WAIT;state<=TX_PRIME;
      end else state<=OPEN_FILE;
     end else begin rx_index<=rx_index+1'b1;state<=PARSE_ISSUE;end
    end
    OPEN_FILE:if(file_open_ready)begin
     if(file_open_error!=0||(!file_write&&file_read_length>MAX_FILE_BYTES))begin
      failure_code<=file_open_error!=0?file_open_error:16'd3;failed<=1;aborted<=1;
      if(file_client)state<=IDLE;
      else prepare(5,file_open_error!=0?file_open_error:16'd3,5,AFTER_IDLE);
     end else begin
      read_length<=file_read_length;timer<=0;retries<=0;
      if(file_client)prepare(file_write?16'd1:16'd2,0,{5'd0,file_name_length}+11'd9,AFTER_WAIT);
      else if(file_write)prepare(4,0,4,AFTER_WAIT);
      else begin
       block_no<=1;payload_length<=file_read_length>=512?10'd512:file_read_length[9:0];
       tx_final<=file_read_length<512;
       prepare(3,1,file_read_length>=512?11'd516:{1'b0,file_read_length[9:0]}+11'd4,AFTER_WAIT);
      end
     end
    end
    BUILD:begin
     if(build_index+1'b1==tx_length)state<=TX_PRIME;
     else if(build_opcode==3&&build_index==3)begin build_index<=4;state<=READ_ISSUE;end
     else build_index<=build_index+1'b1;
    end
    READ_ISSUE:state<=READ_STORE;
    READ_STORE:begin
     if(build_index+1'b1==tx_length)state<=TX_PRIME;
     else begin build_index<=build_index+1'b1;state<=READ_ISSUE;end
    end
    TX_PRIME:begin tx_index<=0;small_tx<=0;state<=TX_STREAM;end
    TX_STREAM:if(tx_fire)begin
     if(last_tx)begin
      if(cancel||cancel_pending)begin abort_transfer(0);state<=IDLE;cancel_pending<=0;end
      else if(small_tx)begin small_tx<=0;state<=busy_session?WAIT_PACKET:IDLE;end
      else if(after_tx==AFTER_DONE)begin
       done<=1;completed_count<=completed_count+1'b1;dally_timer<=0;state<=IDLE;
      end else if(after_tx==AFTER_IDLE)state<=IDLE;
      else begin timer<=0;state<=WAIT_PACKET;end
     end else tx_index<=tx_index+1'b1;
    end
    RX_ISSUE:state<=RX_BYTE;
    RX_BYTE:if(file_write_ready)begin
     if(rx_index+1'b1==rx_size)begin
      if(payload_length<512)state<=FINISH_FILE;
      else begin file_offset<=file_offset+payload_length;prepare(4,block_no,4,AFTER_WAIT);end
     end else begin rx_index<=rx_index+1'b1;state<=RX_ISSUE;end
    end
    FINISH_FILE:if(file_finish_ready)begin
     if(file_finish_error!=0)begin abort_transfer(file_finish_error);prepare(5,file_finish_error,5,AFTER_IDLE);end
     else begin
      dally_valid<=1;dally_local<=local_tid;dally_peer<=peer_tid;dally_block<=block_no;dally_timer<=0;
      prepare(4,block_no,4,AFTER_DONE);
     end
    end
    default:state<=IDLE;
   endcase
  end
 end
 // Session liveness is distinct from the FSM's temporary packet/ERROR states.
 always @(posedge clk)begin
  if(reset)busy_session<=0;
  else if((cancel||cancel_pending)&&state!=TX_STREAM&&state!=TX_PRIME)busy_session<=0;
  else if((state==IDLE&&start&&start_ready&&start_name_length!=0&&start_name_length<=32)||
          (state==HANDLE_PACKET&&!rx_bad&&!busy_session&&rx_size>=10&&rx_dst==69&&(rx_opcode==1||rx_opcode==2)))busy_session<=1;
  else if(done||failed||aborted||state==IDLE)busy_session<=0;
 end
 function [7:0] octet_character;
  input [5:0] i;
  begin case(i)0:octet_character=8'h6f;1:octet_character=8'h63;2:octet_character=8'h74;
   3:octet_character=8'h65;default:octet_character=8'h74;endcase end
 endfunction
endmodule
