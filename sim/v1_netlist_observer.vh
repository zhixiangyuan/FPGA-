// Read-only connections to actual exported wires. No RTL DUT or force.
wire [7:0] obs_psn = dut.\protocol|sn_gate|psn ;
wire obs_psn_valid = dut.\protocol|sn_gate|psn_valid~regout ;
wire [1:0] obs_committed = dut.\application|committed ;
wire [1:0] obs_app_busy = dut.\application|busy ;
wire [1:0] obs_parser_busy = dut.\protocol|rx_protocol|banks_busy ;
wire obs_mac_busy0 = dut.\protocol|tx_mac|mac|rx|bank0|busy~regout ;
wire obs_mac_busy1 = dut.\protocol|tx_mac|mac|rx|bank1|busy~regout ;
wire [10:0] obs_lengths0 = {dut.\application|lengths[0][10]~regout ,dut.\application|lengths[0][9]~regout ,dut.\application|lengths[0][8]~regout ,dut.\application|lengths[0][7]~regout ,dut.\application|lengths[0][6]~regout ,dut.\application|lengths[0][5]~regout ,dut.\application|lengths[0][4]~regout ,dut.\application|lengths[0][3]~regout ,dut.\application|lengths[0][2]~regout ,dut.\application|lengths[0][1]~regout ,dut.\application|lengths[0][0]~regout };
wire [7:0] obs_origins0 = {dut.\application|origins[0][7]~regout ,dut.\application|origins[0][6]~regout ,dut.\application|origins[0][5]~regout ,dut.\application|origins[0][4]~regout ,dut.\application|origins[0][3]~regout ,dut.\application|origins[0][2]~regout ,dut.\application|origins[0][1]~regout ,dut.\application|origins[0][0]~regout };
wire [10:0] obs_lengths1 = {dut.\application|lengths[1][10]~regout ,dut.\application|lengths[1][9]~regout ,dut.\application|lengths[1][8]~regout ,dut.\application|lengths[1][7]~regout ,dut.\application|lengths[1][6]~regout ,dut.\application|lengths[1][5]~regout ,dut.\application|lengths[1][4]~regout ,dut.\application|lengths[1][3]~regout ,dut.\application|lengths[1][2]~regout ,dut.\application|lengths[1][1]~regout ,dut.\application|lengths[1][0]~regout };
wire [7:0] obs_origins1 = {dut.\application|origins[1][7]~regout ,dut.\application|origins[1][6]~regout ,dut.\application|origins[1][5]~regout ,dut.\application|origins[1][4]~regout ,dut.\application|origins[1][3]~regout ,dut.\application|origins[1][2]~regout ,dut.\application|origins[1][1]~regout ,dut.\application|origins[1][0]~regout };
