// One-cycle trigger after START_CYCLES active edges, then every PERIOD_CYCLES.
// A busy consumer may skip a poll; the next poll still occurs on the schedule.
module afdx_poll_timer #(
 parameter integer START_CYCLES=16,
 parameter integer PERIOD_CYCLES=2000000000
)(
 input wire clk,reset,
 output reg request
);
 // Both parameters are integer values, so a 32-bit countdown covers every
 // legal configuration and keeps the literal assignments width-clean.
 localparam [31:0] START_VALUE=START_CYCLES-1;
 localparam [31:0] PERIOD_VALUE=PERIOD_CYCLES-1;
 reg [31:0] remaining;
 always @(posedge clk)begin
  if(reset)begin remaining<=START_VALUE;request<=0;end
  else begin
   request<=remaining==0;
   if(remaining==0)remaining<=PERIOD_VALUE;
   else remaining<=remaining-1'b1;
  end
 end
endmodule
