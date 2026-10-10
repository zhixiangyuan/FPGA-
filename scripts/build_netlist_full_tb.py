from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'sim/tb_b1_gmii_loopback.sv').read_text(encoding='utf-8')
def replace(old,new):
    global s
    assert old in s,old
    s=s.replace(old,new)
replace('module tb_b1_gmii_loopback;', 'module tb_b1_netlist_full;')
replace('    localparam integer MAX_BYTES = 65536;', '''    localparam integer MAX_BYTES = 65536;
`ifdef QUICK_PRESSURE_ONLY
    localparam integer SN_WRAP_FRAMES = 1;
`else
    localparam integer SN_WRAP_FRAMES = 256;
`endif''')
replace("afdx_network_tx_top #(.RESET_SN(8'd1), .CLK_HZ(32'd1000000)) dut (",'afdx_network_tx_top dut (')
s=re.sub(r"32'd1000\b","32'd125000",s)
s=re.sub(r"32'd1001\b","32'd125001",s)
s=re.sub(r"32'd5000\b","32'd12500",s)
replace('integer expected_bag = 1000;', 'integer expected_bag = 125000;')
replace('timeout < 30000','timeout < 200000')
replace('#100000000;', '#1000000000;')
replace('i<FRAME_COUNT','i<12+SN_WRAP_FRAMES')
replace('tx_wire_frames != 268 || tx_sent != 256','tx_wire_frames != 12+SN_WRAP_FRAMES || tx_sent != SN_WRAP_FRAMES')
replace('rx_good != 256 || rx_delivered != 256','rx_good != SN_WRAP_FRAMES || rx_delivered != SN_WRAP_FRAMES')
replace('tx_wire_bytes != 22554','tx_wire_bytes != 4122+72*SN_WRAP_FRAMES')
replace('rx_seen != 256 || rx_frames_checked != 268','rx_seen != SN_WRAP_FRAMES || rx_frames_checked != 12+SN_WRAP_FRAMES')
replace('tx_wire_frames != 270 || tx_sent != 258 || rx_good != 258 || rx_delivered != 258','tx_wire_frames != 14+SN_WRAP_FRAMES || tx_sent != 2+SN_WRAP_FRAMES || rx_good != 2+SN_WRAP_FRAMES || rx_delivered != 2+SN_WRAP_FRAMES')
replace('done_pulses != 270','done_pulses != 14+SN_WRAP_FRAMES')
replace('tx_wire_bytes != 22698 || rx_frames_checked != 270','tx_wire_bytes != 4266+72*SN_WRAP_FRAMES || rx_frames_checked != 14+SN_WRAP_FRAMES')
replace('    integer gmii_dump_fd;', '''    reg inject_rx=0;
    reg [7:0] inject_rxd=0;
    reg inject_dv=0;
    reg pressure_phase=0;
    integer pressure_rx_before;
    integer pressure_seen_before, pressure_good_before, pressure_drop_before;
    integer gmii_dump_fd;''')
replace('gmii_rxd <= gmii_txd;', 'gmii_rxd <= inject_rx ? inject_rxd : gmii_txd;')
replace('gmii_rx_dv <= gmii_tx_en;', 'gmii_rx_dv <= inject_rx ? inject_dv : gmii_tx_en;')
replace('gmii_rx_er <= gmii_tx_er;', "gmii_rx_er <= inject_rx ? 1'b0 : gmii_tx_er;")
replace('''                    expected_rx_frame <= -1;
                end else begin''','''                    if (pressure_phase && rx_frames_checked == pressure_rx_before)
                        expected_rx_frame <= 1;
                    else expected_rx_frame <= -1;
                end else begin''')
replace('    integer i;','''    task automatic inject_golden_wire(input integer frame_idx);
        integer k, offset, length;
        begin
            offset=meta_mem[frame_idx][119:88];
            length=meta_mem[frame_idx][87:72];
            for(k=0;k<length;k=k+1) begin
                @(negedge clk); inject_rxd=wire_mem[offset+k]; inject_dv=1;
            end
            @(negedge clk); inject_dv=0;
            repeat(16) @(posedge clk);
        end
    endtask

    integer i;''')
replace('        $fclose(gmii_dump_fd);','''        // Real top-level GMII input exercises both synthesized RX FIFO banks.
        // Three correct Golden frames enter while the consumer is paused;
        // exactly two are retained and the third is explicitly dropped.
        @(negedge clk);
        pressure_phase=1; pressure_rx_before=rx_frames_checked;
        pressure_seen_before=rx_seen; pressure_good_before=rx_good;
        pressure_drop_before=rx_drop;
        expected_rx_frame=0; rx_byte_index=0; rx_ready=0; inject_rx=1;
        inject_golden_wire(0); inject_golden_wire(1); inject_golden_wire(2);
        repeat(4) @(posedge clk);
        if(rx_seen!=pressure_seen_before+3 || rx_good!=pressure_good_before+2 || rx_drop!=pressure_drop_before+1)
            $fatal(1,"RX pressure conservation failed seen=%0d good=%0d drop=%0d",rx_seen,rx_good,rx_drop);
        if(rx_banks_busy!==2'b11 || !rx_drop_reason[4])
            $fatal(1,"RX pressure did not retain both banks/report no-space");
        @(negedge clk); rx_ready=1;
        wait_rx_frame(pressure_rx_before+2);
        @(negedge clk); inject_rx=0; pressure_phase=0; msg_jitter_cycles=32'd12500;
        send_valid_frame(3,1);
        if(tx_wire_frames!=SN_WRAP_FRAMES+15 || done_pulses!=SN_WRAP_FRAMES+15 || tx_sent!=SN_WRAP_FRAMES+3)
            $fatal(1,"TX recovery after RX pressure failed");
        if(rx_frames_checked!=SN_WRAP_FRAMES+17 || rx_good!=SN_WRAP_FRAMES+5 || rx_delivered!=SN_WRAP_FRAMES+5 || rx_seen!=SN_WRAP_FRAMES+6 || rx_drop!=1)
            $fatal(1,"RX pressure/recovery final counters failed");
        if(tx_wire_bytes!=4339+72*SN_WRAP_FRAMES || late_count!=2)
            $fatal(1,"Final wire count/BAG late count failed");
        $display("B1_NETLIST_FIFO_PRESSURE = PASS retained=2 dropped=1 recovery=1 (overflow is not lossless)");
        $fclose(gmii_dump_fd);''')
old='''        $display("B1_REAL_GMII_LOOPBACK = PASS boundaries=11 rejected_descriptors=6 malformed_payloads=3 recovery=1 sn_wrap_frames=256 late_count_frames=2 wire_bytes=%0d rx_checked=%0d late_count=%0d",
            tx_wire_bytes, rx_frames_checked, late_count);'''
new='''`ifdef DUT_IS_NETLIST
        $display("B1_POST_SYNTH_NETLIST_FULL = PASS boundaries=11 rejected_descriptors=6 malformed_payloads=3 sn_wrap_frames=%0d fifo_pressure=1 wire_bytes=%0d rx_checked=%0d late_count=%0d",
            SN_WRAP_FRAMES, tx_wire_bytes, rx_frames_checked, late_count);
`else
        $display("B1_FULL_TB_QUICK_RTL = PASS sn_frames=%0d fifo_pressure=1 wire_bytes=%0d rx_checked=%0d",
            SN_WRAP_FRAMES, tx_wire_bytes, rx_frames_checked);
`endif'''
replace(old,new)
s='// Netlist suite: same approved protocol Golden, real 125MHz/BAG cycle counts.\n// QUICK_PRESSURE_ONLY is used only for preliminary RTL TB validation; netlist runner never sets it.\n'+s
(ROOT/'sim/tb_b1_netlist_full.sv').write_text(s,encoding='utf-8')
print('FULL_NETLIST_TB_PREPARED no production RTL changed')
