// One-cycle trigger after START_CYCLES active edges, then every PERIOD_CYCLES.
// A busy consumer may skip a poll; the next poll still occurs on the schedule.
module afdx_poll_timer #(
 parameter integer START_CYCLES=16,
 parameter integer PERIOD_CYCLES=2000000000
)(
 input wire clk,reset,
 output reg request
);
 localparam integer MAX_CYCLES=START_CYCLES>PERIOD_CYCLES ? START_CYCLES : PERIOD_CYCLES;
 localparam integer WIDTH=MAX_CYCLES>1 ? $clog2(MAX_CYCLES) : 1;
 reg [WIDTH-1:0] remaining;
 always @(posedge clk)begin
  if(reset)begin remaining<=START_CYCLES-1;request<=0;end
  else begin
   request<=remaining==0;
   if(remaining==0)remaining<=PERIOD_CYCLES-1;
   else remaining<=remaining-1'b1;
  end
 end
endmodule
