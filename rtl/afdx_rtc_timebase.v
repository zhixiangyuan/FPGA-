// UTC is NTP Q32.32, epoch 1900; monotonic cycles never step on sync.
// Four timestamps must come from a validated SNTP exchange, not raw packets.
module afdx_rtc_timebase #(
 parameter integer CLK_HZ=125000000,
 parameter [63:0] INITIAL_TIME=64'he900000000000000,
 parameter [63:0] MAX_DELAY=64'h0000000100000000
)(
 input wire clk,reset,
 input wire sync_valid,
 input wire [63:0] t1,t2,t3,t4,
 output reg [63:0] utc_time,monotonic_cycles,
 output reg synchronized,sync_accepted,sync_rejected,
 output reg signed [63:0] last_offset,
 output reg [63:0] last_delay,
 output reg [31:0] sync_count,error_count
);
 localparam [63:0] TICK_BASE=64'h0000000100000000/CLK_HZ;
 localparam [63:0] TICK_REM=64'h0000000100000000%CLK_HZ;
 // The remainder is always less than CLK_HZ; 32 bits cover the supported
 // integer clock range without building a needless 64-bit accumulator.
 reg [31:0] remainder;
 wire [32:0] remainder_sum={1'b0,remainder}+{1'b0,TICK_REM[31:0]};
 wire extra_tick=remainder_sum>=CLK_HZ;
 wire [32:0] remainder_reduced=remainder_sum-CLK_HZ;
 wire [63:0] increment=TICK_BASE+extra_tick;
 // Differences use modular NTP arithmetic, valid within a +/-68 year era.
 wire signed [63:0] network_elapsed=$signed(t4-t1);
 wire signed [63:0] server_elapsed=$signed(t3-t2);
 wire signed [64:0] delay_q={network_elapsed[63],network_elapsed}-{server_elapsed[63],server_elapsed};
 wire signed [63:0] delta_a=$signed(t2-t1),delta_b=$signed(t3-t4);
 wire signed [64:0] offset_sum={delta_a[63],delta_a}+{delta_b[63],delta_b};
 wire signed [64:0] offset_q=offset_sum>>>1;
 wire legal=(t1!=0)&&(t3!=0)&&network_elapsed>=0&&server_elapsed>=0&&delay_q>=0&&delay_q<=$signed({1'b0,MAX_DELAY});
 function [31:0] inc;input [31:0] v;
 begin inc=v==32'hffffffff ? v : v+32'd1;end endfunction
 always @(posedge clk)begin
  if(reset)begin
   utc_time<=INITIAL_TIME;monotonic_cycles<=0;remainder<=0;synchronized<=0;
   sync_accepted<=0;sync_rejected<=0;last_offset<=0;last_delay<=0;sync_count<=0;error_count<=0;
  end else begin
   monotonic_cycles<=monotonic_cycles+1'b1;
   remainder<=extra_tick?remainder_reduced[31:0]:remainder_sum[31:0];
   utc_time<=utc_time+increment;
   sync_accepted<=0;sync_rejected<=0;
   if(sync_valid)begin
    if(legal)begin
     utc_time<=utc_time+increment+offset_q[63:0];
     last_offset<=offset_q[63:0];last_delay<=delay_q[63:0];
     synchronized<=1;sync_accepted<=1;sync_count<=inc(sync_count);
    end else begin sync_rejected<=1;error_count<=inc(error_count);end
   end
  end
 end
endmodule
