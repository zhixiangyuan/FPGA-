// RFC1157 SNMPv1 agent profile: one varbind, GET/GETNEXT/SET, coldStart Trap.
// MIB-II sysDescr.0, sysUpTime.0, sysName.0; public read, private read/write.
// Packet boundary/UDP/FCS/SN validation belongs to the upstream network path.
// Trap enterprise 0.0 is an explicitly unassigned engineering identity.
module afdx_snmp_agent #(
 parameter [31:0] LOCAL_IP=32'h0a000009
)(
 input wire clk,reset,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,
 input wire [15:0] in_src_port,
 input wire [31:0] uptime_ticks,
 input wire trap_start,output wire trap_ready,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,
 output wire out_sop,out_eop,output wire [10:0] out_length,
 output wire [15:0] out_src_port,out_dst_port,
 output reg [31:0] request_count,response_count,error_count,trap_count,
 output reg [5:0] sys_name_length
);
 localparam RX_IDLE=0,RX_BODY=1,ROOT=2,VERSION=3,COMMUNITY=4,PDU=5,RID=6,
   ERROR_FIELD=7,INDEX_FIELD=8,VBL=9,VB=10,OID=11,VALUE=12,RESOLVE=13,SEND=14,DROP=15,SET_COPY=16,OID_COPY=17,
   OID_COPY_PRIME=18,SET_COPY_PRIME=19,REPLY_COPY_PRIME=20,FIELD_REQ=21,FIELD_CAPTURE=22,
   COMMUNITY_REQ=23,COMMUNITY_CAPTURE=24;
 reg [4:0] state;
 reg [7:0] packet[0:483],sys_name[0:31];
 reg [7:0] packet_oid_ram[0:511],packet_set_ram[0:511],packet_reply_ram[0:511];
 reg [7:0] oid_read_data,set_read_data,reply_read_data;
 reg [7:0] oid_cache[0:7];
 reg [7:0] field_header[0:3],packet_read_data;
 reg [4:0] field_return_state;
 reg [1:0] field_index;
 reg field_valid,community_match;
 reg [3:0] community_index;
 reg [9:0] received_length,rx_index,cursor,message_end,pdu_end,vbl_end,vb_end;
 reg bad_frame,private_access,copy_response,trap_mode;
 reg [3:0] community_length,object_id;
 reg [9:0] pdu_tag_index,error_index,index_index,oid_start,oid_length,value_start,value_length;
 reg [7:0] pdu_tag,value_tag,error_status,error_binding;
 reg signed [31:0] request_id;
 reg [31:0] uptime_snapshot;
 reg [15:0] response_port;
 reg [9:0] tx_index,tx_size;
 reg [5:0] copy_index;
 reg [3:0] oid_copy_index;
 // BER definite lengths through 0x82 are parsed with bounds checked first.
 // Return {valid, value-start[9:0], length[9:0], end[9:0]}.
 function [30:0] tlv;
  input [9:0] position;
  input [9:0] packet_length;
  input [7:0] length_a,length_b,length_c;
  integer length,base,finish;
  begin
   tlv=0;length=0;base=0;finish=0;
   if(position+1<packet_length)begin
    if(length_a<128)begin length=length_a;base=position+2;end
    else if(length_a==8'h81&&position+2<packet_length)begin length=length_b;base=position+3;end
    else if(length_a==8'h82&&position+3<packet_length)begin length={length_b,length_c};base=position+4;end
    finish=base+length;
    if(base!=0&&finish<=packet_length&&finish<=484)tlv={1'b1,base[9:0],length[9:0],finish[9:0]};
   end
  end
 endfunction
 wire [30:0] field=tlv(cursor,received_length,field_header[1],field_header[2],field_header[3]);
 wire field_ok=field[30];wire [9:0] field_base=field[29:20],field_length=field[19:10],field_end=field[9:0];
 wire field_state=(state==ROOT)||(state==VERSION)||(state==COMMUNITY)||(state==PDU)||(state==RID)||
                  (state==ERROR_FIELD)||(state==INDEX_FIELD)||(state==VBL)||(state==VB)||(state==OID)||(state==VALUE);
 wire packet_read_enable=(state==FIELD_REQ)||(state==FIELD_CAPTURE&&field_index<3)||
                         (state==COMMUNITY_REQ)||(state==COMMUNITY_CAPTURE&&community_index+1'b1<community_length);
 wire [9:0] packet_read_address=state==FIELD_REQ?cursor:
                                state==FIELD_CAPTURE?cursor+field_index+1'b1:
                                state==COMMUNITY_REQ?field_base+community_index:field_base+community_index+1'b1;
 function signed [31:0] integer_value;
  input [9:0] start,length;integer j;reg signed [31:0] value;
  begin
   value=packet[start][7]?-1:0;
   for(j=0;j<4;j=j+1)if(j<length)value=(value<<8)|packet[start+j];
   integer_value=value;
  end
 endfunction
 function [7:0] oid_byte;input integer position;input [3:0] id;
  begin case(position)
   0:oid_byte=8'h2b;1:oid_byte=6;2:oid_byte=1;3:oid_byte=2;
   4:oid_byte=1;5:oid_byte=1;6:oid_byte=id;default:oid_byte=0;
  endcase end endfunction
 function [7:0] community_byte;input [3:0] length;input [9:0] position;
  begin
   community_byte=0;
   if(length==6)case(position)
    0:community_byte="p";1:community_byte="u";2:community_byte="b";
    3:community_byte="l";4:community_byte="i";5:community_byte="c";
    default:community_byte=0;
   endcase
   else if(length==7)case(position)
    0:community_byte="p";1:community_byte="r";2:community_byte="i";
    3:community_byte="v";4:community_byte="a";5:community_byte="t";
    6:community_byte="e";default:community_byte=0;
   endcase
  end
 endfunction
 function integer compare_oid;input [3:0] id;integer j;reg found;
  begin
   compare_oid=0;found=0;
   for(j=0;j<8;j=j+1)begin
    if(!found)begin
     if(j>=oid_length)begin compare_oid=-1;found=1;end
     else if(oid_cache[j]<oid_byte(j,id))begin compare_oid=-1;found=1;end
     else if(oid_cache[j]>oid_byte(j,id))begin compare_oid=1;found=1;end
    end
   end
   if(!found&&oid_length>8)compare_oid=1;
  end
 endfunction
 function [2:0] signed_length;input signed [31:0] value;
  begin
   if(value>=-128&&value<=127)signed_length=1;
   else if(value>=-32768&&value<=32767)signed_length=2;
   else if(value>=-8388608&&value<=8388607)signed_length=3;
   else signed_length=4;
  end endfunction
 function [2:0] unsigned_length;input [31:0] value;
  begin
   if(value<=127)unsigned_length=1;else if(value<=32767)unsigned_length=2;
   else if(value<=8388607)unsigned_length=3;else if(value<=2147483647)unsigned_length=4;
   else unsigned_length=5;
  end endfunction
 wire [2:0] rid_length=signed_length(request_id),tick_length=unsigned_length(uptime_snapshot);
 wire packet_store_write=!reset&&in_valid&&in_ready&&(state==RX_IDLE||rx_index<484);
 wire [8:0] packet_store_address=state==RX_IDLE?9'd0:rx_index[8:0];
 wire oid_read_enable=state==OID_COPY_PRIME||
                      (state==OID_COPY&&oid_copy_index<7&&oid_copy_index+1'b1<oid_length);
 wire [8:0] oid_read_address=state==OID_COPY_PRIME?oid_start[8:0]:oid_start[8:0]+oid_copy_index+1'b1;
 wire set_read_enable=state==SET_COPY_PRIME||(state==SET_COPY&&copy_index+1'b1<value_length);
 wire [8:0] set_read_address=state==SET_COPY_PRIME?value_start[8:0]:value_start[8:0]+copy_index+1'b1;
 wire reply_read_enable=state==REPLY_COPY_PRIME||
                        (state==SEND&&copy_response&&out_valid&&out_ready&&!out_eop);
 wire [8:0] reply_read_address=state==REPLY_COPY_PRIME?9'd0:tx_index[8:0]+1'b1;
 wire [5:0] response_value_length=object_id==1?6'd22:object_id==3?{3'd0,tick_length}:sys_name_length;
 wire [7:0] response_value_tag=object_id==3?8'h43:8'h04;
 wire [9:0] pdu_start=7+community_length;
 wire [9:0] err_start=pdu_start+4+rid_length;
 wire [9:0] vbl_start=err_start+6;
 wire [9:0] vb_start=vbl_start+2;
 wire [9:0] object_start=vb_start+2;
 wire [9:0] result_start=object_start+10;
 wire [9:0] result_end=result_start+2+response_value_length;
 function [7:0] response_byte;
  input [9:0] position;
  integer relative;reg [175:0] description;
  begin
   response_byte=0;relative=0;description="AFDX FPGA RTL endpoint";
   if(trap_mode)begin
    case(position)
     0:response_byte=8'h30;1:response_byte=32+tick_length;
     2:response_byte=2;3:response_byte=1;4:response_byte=0;
     5:response_byte=4;6:response_byte=6;
     7:response_byte="p";8:response_byte="u";9:response_byte="b";
     10:response_byte="l";11:response_byte="i";12:response_byte="c";
     13:response_byte=8'ha4;14:response_byte=19+tick_length;
     15:response_byte=6;16:response_byte=1;17:response_byte=0;
     18:response_byte=8'h40;19:response_byte=4;
     20:response_byte=LOCAL_IP[31:24];21:response_byte=LOCAL_IP[23:16];
     22:response_byte=LOCAL_IP[15:8];23:response_byte=LOCAL_IP[7:0];
     24,27:response_byte=2;25,28:response_byte=1;26,29:response_byte=0;
     30:response_byte=8'h43;31:response_byte=tick_length;
     default:begin
      if(position==32+tick_length)response_byte=8'h30;
      else if(position<32+tick_length)response_byte={8'd0,uptime_snapshot}>>(8*(31+tick_length-position));
     end
    endcase
   end else if(copy_response)begin
    response_byte=reply_read_data;
    if(position==pdu_tag_index)response_byte=8'ha2;
    if(position==error_index)response_byte=error_status;
    if(position==index_index)response_byte=error_binding;
   end else begin
    if(position==0)response_byte=8'h30;
    else if(position==1)response_byte=result_end-2;
    else if(position==2)response_byte=2;
    else if(position==3)response_byte=1;
    else if(position==4)response_byte=0;
    else if(position==5)response_byte=4;
    else if(position==6)response_byte=community_length;
    else if(position<pdu_start)response_byte=community_byte(community_length,position-7);
    else if(position==pdu_start)response_byte=8'ha2;
    else if(position==pdu_start+1)response_byte=result_end-pdu_start-2;
    else if(position==pdu_start+2)response_byte=2;
    else if(position==pdu_start+3)response_byte=rid_length;
    else if(position<err_start)response_byte=request_id>>(8*(err_start-1-position));
    else if(position==err_start||position==err_start+3)response_byte=2;
    else if(position==err_start+1||position==err_start+4)response_byte=1;
    else if(position==err_start+2||position==err_start+5)response_byte=0;
    else if(position==vbl_start||position==vb_start)response_byte=8'h30;
    else if(position==vbl_start+1)response_byte=result_end-vbl_start-2;
    else if(position==vb_start+1)response_byte=result_end-vb_start-2;
    else if(position==object_start)response_byte=6;
    else if(position==object_start+1)response_byte=8;
    else if(position<result_start)response_byte=oid_byte(position-object_start-2,object_id);
    else if(position==result_start)response_byte=response_value_tag;
    else if(position==result_start+1)response_byte=response_value_length;
    else begin
     relative=position-result_start-2;
     if(object_id==1)response_byte=description>>(8*(21-relative));
     else if(object_id==3)response_byte={8'd0,uptime_snapshot}>>(8*(tick_length-1-relative));
     else response_byte=sys_name[relative];
    end
   end
  end
 endfunction
 assign in_ready=!reset&&(state==RX_IDLE||state==RX_BODY);
 assign trap_ready=!reset&&state==RX_IDLE&&!in_valid;
 assign out_valid=!reset&&state==SEND;
 assign out_data=out_valid?response_byte(tx_index):8'd0;
 assign out_sop=out_valid&&tx_index==0;assign out_eop=out_valid&&tx_index+1==tx_size;
 assign out_length=tx_size;assign out_src_port=161;assign out_dst_port=trap_mode?16'd162:response_port;
 integer j;reg [3:0] selected;
 // Mirrored synchronous-read memories serve the mutually exclusive OID,
 // SET-copy, and error-response phases without wide variable-index muxes.
 // Keep each memory's write and registered read in separate processes for
 // Quartus RAM inference.
 always @(posedge clk)if(packet_store_write)packet_oid_ram[packet_store_address^9'h155]<=in_data;
 always @(posedge clk)if(packet_store_write)packet_set_ram[packet_store_address^9'h0aa]<=in_data;
 always @(posedge clk)if(packet_store_write)packet_reply_ram[packet_store_address^9'h1ff]<=in_data;
 always @(posedge clk)if(!reset&&oid_read_enable)oid_read_data<=packet_oid_ram[oid_read_address^9'h155];
 always @(posedge clk)if(!reset&&set_read_enable)set_read_data<=packet_set_ram[set_read_address^9'h0aa];
 always @(posedge clk)if(!reset&&reply_read_enable)reply_read_data<=packet_reply_ram[reply_read_address^9'h1ff];
 // Fetch a BER TLV header serially. Keeping one registered read path avoids
 // three parallel variable-index reads from the packet register array.
 always @(posedge clk)if(packet_read_enable)packet_read_data<=packet[packet_read_address];
 always @(posedge clk)begin
  if(reset)begin
   state<=RX_IDLE;received_length<=0;rx_index<=0;cursor<=0;bad_frame<=0;
   private_access<=0;copy_response<=0;trap_mode<=0;community_length<=0;object_id<=0;
   pdu_tag_index<=0;error_index<=0;index_index<=0;oid_start<=0;oid_length<=0;value_start<=0;value_length<=0;
   message_end<=0;pdu_end<=0;vbl_end<=0;vb_end<=0;pdu_tag<=0;value_tag<=0;error_status<=0;error_binding<=0;
   request_id<=0;uptime_snapshot<=0;response_port<=0;tx_index<=0;tx_size<=0;copy_index<=0;oid_copy_index<=0;
   field_return_state<=ROOT;field_index<=0;community_index<=0;field_valid<=0;community_match<=0;
   for(j=0;j<4;j=j+1)field_header[j]<=0;
   request_count<=0;response_count<=0;error_count<=0;trap_count<=0;sys_name_length<=7;
   for(j=0;j<32;j=j+1)sys_name[j]<=j==0?"a":j==1?"f":j==2?"d":j==3?"x":j==4?"-":j==5?"s":j==6?"2":0;
  end else begin
   if(trap_start&&trap_ready)begin
    trap_mode<=1;uptime_snapshot<=uptime_ticks;tx_size<=34+unsigned_length(uptime_ticks);tx_index<=0;state<=SEND;
   end else if(in_valid&&in_ready)begin
    if(state==RX_IDLE)begin
     packet[0]<=in_data;rx_index<=1;received_length<=in_length;response_port<=in_src_port;
     bad_frame<=!in_sop||in_length>484||in_length==0||in_eop;
     copy_response<=0;trap_mode<=0;error_status<=0;error_binding<=0;
     state<=in_eop?DROP:RX_BODY;
    end else begin
     if(rx_index<484)packet[rx_index]<=in_data;
     if(rx_index<1023)rx_index<=rx_index+1'b1;
     if(in_sop||in_length!=received_length)bad_frame<=1;
     if(in_eop)begin
      cursor<=0;state<=bad_frame||rx_index+1!=received_length?DROP:ROOT;
     end
    end
   end else if(field_state&&!field_valid)begin
    field_return_state<=state;field_index<=0;state<=FIELD_REQ;
   end else begin
    if(field_state&&field_valid)field_valid<=0;
    case(state)
    FIELD_REQ:begin field_index<=0;state<=FIELD_CAPTURE;end
    FIELD_CAPTURE:begin
     field_header[field_index]<=packet_read_data;
     if(field_index==3)begin field_valid<=1;state<=field_return_state;end
     else field_index<=field_index+1'b1;
    end
    COMMUNITY_REQ:state<=COMMUNITY_CAPTURE;
    COMMUNITY_CAPTURE:begin
     community_match<=community_match&&(packet_read_data==community_byte(community_length,community_index));
     if(community_index+1'b1>=community_length)begin
      if(community_match&&(packet_read_data==community_byte(community_length,community_index)))begin
       private_access<=community_length==7;cursor<=field_end;state<=PDU;
      end else state<=DROP;
     end else community_index<=community_index+1'b1;
    end
    ROOT:begin
     if(!field_ok||field_header[0]!=8'h30||field_end!=received_length)state<=DROP;
     else begin cursor<=field_base;message_end<=field_end;state<=VERSION;uptime_snapshot<=uptime_ticks;end
    end
    VERSION:if(!field_ok||field_header[0]!=2||field_length!=1||field_header[2]!=0)state<=DROP;
     else begin cursor<=field_end;state<=COMMUNITY;end
    COMMUNITY:begin
     if(!field_ok||field_header[0]!=4||(field_length!=6&&field_length!=7))state<=DROP;
     else begin community_length<=field_length;community_index<=0;community_match<=1;state<=COMMUNITY_REQ;end
    end
    PDU:if(!field_ok||field_end!=message_end||(field_header[0]!=8'ha0&&field_header[0]!=8'ha1&&field_header[0]!=8'ha3))state<=DROP;
     else begin pdu_tag_index<=cursor;pdu_tag<=field_header[0];pdu_end<=field_end;cursor<=field_base;state<=RID;end
    RID:if(!field_ok||field_header[0]!=2||field_length==0||field_length>4)state<=DROP;
     else begin request_id<=integer_value(field_base,field_length);cursor<=field_end;state<=ERROR_FIELD;end
    ERROR_FIELD:if(!field_ok||field_header[0]!=2||field_length!=1)state<=DROP;
     else begin error_index<=field_base;cursor<=field_end;state<=INDEX_FIELD;end
    INDEX_FIELD:if(!field_ok||field_header[0]!=2||field_length!=1)state<=DROP;
     else begin index_index<=field_base;cursor<=field_end;state<=VBL;end
    VBL:if(!field_ok||field_header[0]!=8'h30||field_end!=pdu_end)state<=DROP;
     else begin
      vbl_end<=field_end;cursor<=field_base;
      if(field_length==0)begin copy_response<=1;tx_size<=received_length;tx_index<=0;request_count<=request_count+1'b1;state<=REPLY_COPY_PRIME;end
      else state<=VB;
     end
    VB:if(!field_ok||field_header[0]!=8'h30||field_end>vbl_end)state<=DROP;
     else begin
      vb_end<=field_end;cursor<=field_base;state<=OID;
      if(field_end!=vbl_end)begin error_status<=1;error_binding<=0;end
     end
    OID:if(!field_ok||field_header[0]!=6||field_length==0||field_length>64||field_end>vb_end||packet[field_end-1][7])state<=DROP;
     else begin oid_start<=field_base;oid_length<=field_length;cursor<=field_end;oid_copy_index<=0;state<=OID_COPY_PRIME;end
    OID_COPY_PRIME:state<=OID_COPY;
    OID_COPY:begin
     oid_cache[oid_copy_index]<=oid_read_data;
     if(oid_copy_index+1'b1>=oid_length||oid_copy_index==7)state<=VALUE;
     else oid_copy_index<=oid_copy_index+1'b1;
    end
    VALUE:if(!field_ok||field_end!=vb_end)state<=DROP;
     else begin
      value_start<=field_base;value_length<=field_length;value_tag<=field_header[0];
      if(vb_end<vbl_end)begin cursor<=vb_end;state<=VB;end else state<=RESOLVE;
     end
    RESOLVE:begin
     request_count<=request_count+1'b1;selected=0;
     if(pdu_tag==8'ha1)begin
      if(compare_oid(1)<0)selected=1;else if(compare_oid(3)<0)selected=3;else if(compare_oid(5)<0)selected=5;
     end else begin
      if(compare_oid(1)==0)selected=1;else if(compare_oid(3)==0)selected=3;else if(compare_oid(5)==0)selected=5;
     end
     object_id<=selected;tx_index<=0;state<=SEND;
     if(error_status!=0||selected==0||(pdu_tag==8'ha3&&(!private_access||selected!=5||value_tag!=4||value_length>32)))begin
      copy_response<=1;tx_size<=received_length;
      if(error_status==0)begin
       error_binding<=1;
       if(selected==0)error_status<=2;
       else if(!private_access||selected!=5)error_status<=4;
       else error_status<=3;
      end
      error_count<=error_count+1'b1;
      state<=REPLY_COPY_PRIME;
     end else begin
      copy_response<=0;
      if(pdu_tag==8'ha3)begin
       sys_name_length<=value_length;copy_index<=0;
       tx_size<=7+community_length+4+rid_length+6+2+2+10+2+value_length;
       if(value_length!=0)state<=SET_COPY_PRIME;
      end else tx_size<=7+community_length+4+rid_length+6+2+2+10+2+(selected==1?22:selected==3?unsigned_length(uptime_snapshot):sys_name_length);
     end
    end
    REPLY_COPY_PRIME:state<=SEND;
    SET_COPY_PRIME:state<=SET_COPY;
    SET_COPY:begin
     sys_name[copy_index]<=set_read_data;
     copy_index<=copy_index+1'b1;
     if(copy_index+1'b1>=value_length)state<=SEND;
    end
    SEND:if(out_valid&&out_ready)begin
     if(out_eop)begin state<=RX_IDLE;if(trap_mode)trap_count<=trap_count+1'b1;else response_count<=response_count+1'b1;end
     else tx_index<=tx_index+1'b1;
    end
    DROP:begin error_count<=error_count+1'b1;state<=RX_IDLE;end
    default:begin end
    endcase
   end
  end
 end
endmodule
