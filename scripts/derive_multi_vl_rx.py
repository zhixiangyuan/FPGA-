"""Create a reviewed development parser fork without changing frozen B2."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'vendor/frozen/afdx_single_vl_rx_candidate.v'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='d9f70c2aec4a71995eb16a7f4030165c6fe4e2378d128588dd2268cf98573558'
text=source.read_text()
def replace(old,new):
 global text
 assert text.count(old)==1,old
 text=text.replace(old,new)
replace('module afdx_single_vl_rx_candidate #(\n', 'module afdx_multi_vl_rx_parser #(\n    parameter integer VL_COUNT=16,\n    parameter integer CHECK_PORTS=1,\n')
replace('    output wire [7:0]  payload_sn_unchecked,', '    output wire [7:0]  payload_sn_unchecked,\n    output wire [15:0] payload_src_port,payload_dst_port,')
replace('    reg [7:0] bank_sn [0:1];','''    reg [7:0] bank_sn [0:1];
    reg [15:0] bank_src_port[0:1],bank_dst_port[0:1];
    reg [15:0] wire_vlid,wire_src_port,wire_dst_port,udp_checksum;
    reg [31:0] udp_sum;
    reg [7:0] udp_hi;
''')
replace('    wire out_bank = qbank[qhead];', '''    wire out_bank = qbank[qhead];
    assign payload_src_port=payload_valid?bank_src_port[out_bank]:16'd0;
    assign payload_dst_port=payload_valid?bank_dst_port[out_bank]:16'd0;''')
replace('                4: if (in_data != vlid_q[15:8]) beat_error=ERR_ETHERNET;\n                5: if (in_data != vlid_q[7:0]) beat_error=ERR_ETHERNET;', '''                5: if ({wire_vlid[15:8],in_data}<vlid_q ||
                       ({1'b0,wire_vlid[15:8],in_data}-{1'b0,vlid_q})>=VL_COUNT)
                       beat_error=ERR_ETHERNET;''')
for field in ('src_port_q[15:8]','src_port_q[7:0]','dst_port_q[15:8]','dst_port_q[7:0]'):
 replace(f'if (in_data != {field}) beat_error=ERR_UDP;',f'if (CHECK_PORTS && in_data != {field}) beat_error=ERR_UDP;')
replace("                40,41: if (in_data != 8'h00) beat_error=ERR_UDP;", '                40,41: begin end')
replace('    wire [3:0] final_error =', '''    function [15:0] fold_udp;
        input [31:0] sum;
        reg [16:0] first,second;
        begin first={1'b0,sum[15:0]}+{1'b0,sum[31:16]};
              second={1'b0,first[15:0]}+first[16];
              fold_udp=second[15:0];end
    endfunction
    wire [31:0] udp_pseudo=udp_sum+{16'd0,src_ip_q[31:16]}+{16'd0,src_ip_q[15:0]}+
        {16'd0,dst_ip_q[31:16]}+{16'd0,dst_ip_q[15:0]}+32'd17+{16'd0,udp_length};
    wire udp_checksum_legal=udp_checksum==0 || fold_udp(udp_pseudo)==16'hffff;
    wire [3:0] final_error =''')
replace("                             folded_sum(ip_sum) != 16'hffff ? ERR_IP_CHECKSUM :", "                             folded_sum(ip_sum) != 16'hffff ? ERR_IP_CHECKSUM :\n                             !udp_checksum_legal ? ERR_UDP :")
replace('            bank_sn[0]<=0; bank_sn[1]<=0;', '''            bank_sn[0]<=0; bank_sn[1]<=0;
            bank_src_port[0]<=0;bank_src_port[1]<=0;bank_dst_port[0]<=0;bank_dst_port[1]<=0;
            wire_vlid<=0;wire_src_port<=0;wire_dst_port<=0;udp_checksum<=0;udp_sum<=0;udp_hi<=0;''')
replace('                    ip_total<=0; udp_length<=0; ip_sum<=0; ip_hi<=0;', '''                    ip_total<=0; udp_length<=0; ip_sum<=0; ip_hi<=0;
                    wire_vlid<=0;wire_src_port<=0;wire_dst_port<=0;
                    udp_checksum<=0;udp_sum<=0;udp_hi<=0;''')
replace('                    byte_index<=byte_index+16\'d1;', '''                    byte_index<=byte_index+16'd1;
                    if(byte_index==4)wire_vlid[15:8]<=in_data;
                    if(byte_index==5)wire_vlid[7:0]<=in_data;
                    if(byte_index==34)wire_src_port[15:8]<=in_data;
                    if(byte_index==35)wire_src_port[7:0]<=in_data;
                    if(byte_index==36)wire_dst_port[15:8]<=in_data;
                    if(byte_index==37)wire_dst_port[7:0]<=in_data;
                    if(byte_index==40)udp_checksum[15:8]<=in_data;
                    if(byte_index==41)udp_checksum[7:0]<=in_data;
                    if(byte_index>=34 && byte_index<payload_end)begin
                        if(!byte_index[0])begin
                            udp_hi<=in_data;
                            if(byte_index+1==payload_end)udp_sum<=udp_sum+{16'd0,in_data,8'd0};
                        end else udp_sum<=udp_sum+{16'd0,udp_hi,in_data};
                    end''')
replace('                            bank_vlid[write_bank]<=vlid_q;', '''                            bank_vlid[write_bank]<=wire_vlid;
                            bank_src_port[write_bank]<=wire_src_port;
                            bank_dst_port[write_bank]<=wire_dst_port;''')
text='// Stage2 development fork: configured VL range, UDP checksum validation and port metadata.\n'+text
target=ROOT/'rtl/afdx_multi_vl_rx_parser.v'
if target.exists():raise FileExistsError('Do not overwrite development RTL')
target.write_text(text,encoding='utf-8');print(target)
