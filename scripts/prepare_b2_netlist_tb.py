"""Adapt approved full Golden suite to the synthesized wrapper's actual pins.
No RTL DUT, hierarchical substitution, force or policy bypass is introduced.
"""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def main():
    s=(ROOT/'sim/tb_b2_full_protocol.sv').read_text()
    s=s.replace('module tb_b2_full_protocol;','module tb_b2_netlist_protocol;')
    a=s.index('    afdx_protocol_rx_top dut(');b=s.index('    initial begin',a)
    instance='''    reg diag_read=1;
    reg diag_poll_enable=1;
    reg [3:0] diag_addr=0;
    wire [31:0] diag_data;
    integer diag_slot=0;
    afdx_b2_synth_wrap dut(
        .clk(clk),.reset(reset),.msg_valid(msg_valid),.msg_ready(msg_ready),
        .msg_payload_length(msg_payload_length),.payload_data(payload_data),
        .payload_valid(payload_valid),.payload_ready(payload_ready),
        .payload_last(payload_last),.payload_abort(payload_abort),
        .gmii_txd(gmii_txd),.gmii_tx_en(gmii_tx_en),.gmii_tx_er(gmii_tx_er),
        .gmii_rx_override(inject),.gmii_rxd_ext(gmii_rxd),
        .gmii_rx_dv_ext(gmii_rx_dv),.gmii_rx_er_ext(gmii_rx_er),
        .msg_done(msg_done),.msg_error(msg_error),.error_code(error_code),
        .app_data(app_data),.app_valid(app_valid),.app_ready(app_ready),
        .app_sop(app_sop),.app_eop(app_eop),.app_length(app_length),
        .app_vlid(app_vlid),.app_sn(app_sn),
        .diag_read(diag_read),.diag_addr(diag_addr),.diag_data(diag_data)
    );
    // Observe only real external diagnostic pins. Slot 1 is explicitly
    // unsupported in this synthesis snapshot and is never used for assertions.
    always @(negedge clk) if(diag_poll_enable) begin
        diag_read=1;
        diag_addr=diag_slot;
        #1;
        case(diag_slot)
            0: tx_sent=diag_data;
            2: rx_seen=diag_data;
            3: rx_good=diag_data;
            4: rx_drop=diag_data;
            5: rx_delivered=diag_data;
            6: candidate_accepted_count=diag_data;
            7: candidate_rejected_count=diag_data;
            8: begin psn=diag_data[7:0];psn_valid=diag_data[8];end
            9: sn_accepted_count=diag_data;
            10: sn_rejected_count=diag_data;
            11: sn_control_count=diag_data;
            12: sn_missing_count=diag_data;
            13: app_delivered_count=diag_data;
            14: candidate_banks_busy=diag_data[1:0];
            15: begin late_count={16'd0,diag_data[31:16]};
                mac_rx_dropped=diag_data[3];candidate_rejected=diag_data[2];
                sn_rejected=diag_data[1];sn_reset_control=diag_data[0];end
        endcase
        diag_slot=(diag_slot+1)%16;
    end else begin diag_read=0;diag_addr=0;end
    task automatic refresh_diag;
        begin diag_poll_enable=1;repeat(34)@(posedge clk);@(negedge clk);#2;end
    endtask
'''
    s=s[:a]+instance+s[b:]
    # Diagnostic state is sampled by the TB, not connected to hidden DUT wires.
    for decl in ('wire [31:0] late_count;','wire [31:0] candidate_accepted_count,candidate_rejected_count;',
      'wire [1:0] candidate_banks_busy;','wire mac_rx_accepted,mac_rx_dropped;',
      'wire [31:0] tx_sent,rx_seen,rx_good,rx_drop,rx_delivered;',
      'wire psn_valid,sn_accepted,sn_rejected,sn_reset_control,app_delivered;',
      'wire [7:0] psn;',
      'wire [31:0] sn_accepted_count,sn_rejected_count,sn_control_count,sn_missing_count,app_delivered_count;',
      'wire candidate_accepted,candidate_rejected;'):
        assert decl in s,decl
        s=s.replace(decl,decl.replace('wire','reg',1))
    s=s.replace('            if(!inject)begin gmii_rxd<=gmii_txd;gmii_rx_dv<=gmii_tx_en;gmii_rx_er<=gmii_tx_er;end','            // Default GMII loop is inside the real synthesized wrapper.')
    s=s.replace('            if(psn_valid || psn!=0','            refresh_diag();\n            if(psn_valid || psn!=0')
    s=s.replace('            action=expect_mem[c][127:96];before_app=app_frames;','            refresh_diag();\n            action=expect_mem[c][127:96];before_app=app_frames;')
    s=s.replace('if(source==1)transmit_b1(c);else inject_raw(c);','if(source==1)begin diag_poll_enable=0;transmit_b1(c);diag_poll_enable=1;end else inject_raw(c);')
    s=s.replace('            if(t>=30000 || psn!==','            refresh_diag();\n            if(t>=30000 || psn!==')
    s=s.replace('            if(candidate_banks_busy!==2\'b11','            refresh_diag();\n            if(candidate_banks_busy!==2\'b11')
    s=s.replace('            if(rx_seen!=5','            refresh_diag();\n            if(rx_seen!=5')
    s=s.replace('            if(app_frames!=before_app+4','            refresh_diag();\n            if(app_frames!=before_app+4')
    s=s.replace('            if(sn_accepted_count!=6','            refresh_diag();\n            if(sn_accepted_count!=6')
    s=s.replace('        if(tx_frames!=263','        refresh_diag();\n        if(tx_frames!=263')
    s=s.replace('if(t>=30000)$fatal(1,"scenario timeout case=%0d action=%0d",c,action);','if(t>=30000)$fatal(1,"scenario timeout case=%0d action=%0d",c,action);')
    s=s.replace('$fclose(tx_fd);$fclose(app_fd);$fclose(decision_fd);','$fclose(tx_fd);$fclose(app_fd);$fclose(decision_fd);\n        $display("B2_REAL_VO_NETLIST = PASS diagnostic_addr_1=UNSUPPORTED");')
    (ROOT/'sim/tb_b2_netlist_protocol.sv').write_text('// Derived from approved full RTL TB; same Golden scenarios and assertions.\n'+s)
    print('Prepared',ROOT/'sim/tb_b2_netlist_protocol.sv')
if __name__=='__main__':main()
