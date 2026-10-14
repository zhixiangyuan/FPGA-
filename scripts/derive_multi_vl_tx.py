"""Reproducible development fork of the immutable B1 builder, never edits B1.

The resulting rtl/ file is reviewed and compiled as production development RTL.
This generator is an explicit derivation tool, not a simulation substitute.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'vendor/frozen/afdx_single_vl_tx.v'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='dcf165241bebae6c481ead513ebd8c7c72a689d312996a52914c6a36112afd8a'
text=source.read_text()
def replace(old,new):
    global text
    assert text.count(old)==1,old
    text=text.replace(old,new)
replace('module afdx_single_vl_tx #(\n', 'module afdx_multi_vl_tx #(\n    parameter integer VL_COUNT = 16,\n    parameter [15:0] VL_BASE = 16\'h1234,\n')
replace('    reg [7:0] next_sn;', '''    reg [7:0] next_sn [0:VL_COUNT-1];
    reg [15:0] active_vl;
    wire [16:0] descriptor_vl = {1'b0,msg_vlid}-{1'b0,VL_BASE};
    wire vl_legal = msg_vlid >= VL_BASE && descriptor_vl < VL_COUNT;
    wire [15:0] descriptor_index = vl_legal ? descriptor_vl[15:0] : 16'd0;
    integer init_vl;''')
replace("wire desc_bad_da = (msg_da_const[25:24] != 2'b11);", "wire desc_bad_da = (msg_da_const[25:24] != 2'b11) || !vl_legal;")
replace('    afdx_bag_gate bag_gate (\n        .clk(clk), .reset(reset), .gmii_tx_en(gmii_tx_en),\n        .frame_arm(legal_desc_fire), .frame_cancel(cancel_event),\n        .frame_pending(frame_pending), .frame_eop_fire(frame_eop_fire),\n        .bag_cycles(msg_bag_cycles), .jitter_cycles(msg_jitter_cycles),\n        .release_final_byte(sn_release), .late_pulse(late_pulse), .late_count(late_count)\n    );', '''    wire [VL_COUNT-1:0] releases,late_pulses;
    wire [31:0] late_counts [0:VL_COUNT-1];
    assign sn_release = releases[active_vl];
    assign late_pulse = late_pulses[active_vl];
    // Sum is diagnostic only; per-VL gates own the actual BAG state.
    reg [31:0] late_total;
    integer sum_vl;
    always @* begin
        late_total=0;
        for(sum_vl=0;sum_vl<VL_COUNT;sum_vl=sum_vl+1)
            late_total=late_total+late_counts[sum_vl];
    end
    assign late_count=late_total;
    genvar vl;
    generate for(vl=0;vl<VL_COUNT;vl=vl+1)begin: vl_bag
        afdx_bag_gate gate(
            .clk(clk),.reset(reset),
            .gmii_tx_en(gmii_tx_en && active_vl==vl),
            .frame_arm(legal_desc_fire && descriptor_index==vl),
            .frame_cancel(cancel_event && active_vl==vl),
            .frame_pending(frame_pending && active_vl==vl),
            .frame_eop_fire(frame_eop_fire && active_vl==vl),
            .bag_cycles(msg_bag_cycles),.jitter_cycles(msg_jitter_cycles),
            .release_final_byte(releases[vl]),.late_pulse(late_pulses[vl]),
            .late_count(late_counts[vl]));
    end endgenerate''')
replace('            next_sn <= RESET_SN;', '            active_vl <= 0;\n            for(init_vl=0;init_vl<VL_COUNT;init_vl=init_vl+1) next_sn[init_vl] <= RESET_SN;')
replace('                active_sn <= next_sn;', '                active_vl <= descriptor_index;\n                active_sn <= next_sn[descriptor_index];')
replace("if (active_sn == 8'd255) next_sn <= 8'd1;\n                            else next_sn <= active_sn + 1'b1;", "if (active_sn == 8'd255) next_sn[active_vl] <= 8'd1;\n                            else next_sn[active_vl] <= active_sn + 1'b1;")
text='// Stage2 development fork: independent per-VL SN and BAG, shared frame builder.\n// Derived from frozen B1 SHA256 dcf165241bebae6c481ead513ebd8c7c72a689d312996a52914c6a36112afd8a.\n'+text
target=ROOT/'rtl/afdx_multi_vl_tx.v'
if target.exists():
    raise FileExistsError('Refuse to overwrite a development source; review changes explicitly')
target.write_text(text,encoding='utf-8')
print(target)
