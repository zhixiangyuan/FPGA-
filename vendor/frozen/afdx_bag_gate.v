// Single-VL minimum-start-interval gate. Timing is measured from observed
// GMII tx_en rising edges, never from request acceptance or tx_done.
module afdx_bag_gate (
    input  wire        clk,
    input  wire        reset,
    input  wire        gmii_tx_en,
    input  wire        frame_arm,
    input  wire        frame_cancel,
    input  wire        frame_pending,
    input  wire        frame_eop_fire,
    input  wire [31:0] bag_cycles,
    input  wire [31:0] jitter_cycles,
    output wire        release_final_byte,
    output reg         late_pulse,
    output reg  [31:0] late_count
);
    reg gmii_tx_en_d;
    reg have_start;
    reg frame_active;
    reg await_gmii_start;
    reg late_for_frame;
    reg [31:0] elapsed_from_start;
    reg [31:0] bag_cycles_q;
    reg [31:0] jitter_cycles_q;

    wire gmii_start = gmii_tx_en && !gmii_tx_en_d;
    wire [32:0] late_limit = {1'b0, bag_cycles_q} + {1'b0, jitter_cycles_q};
    wire beyond_late_limit = {1'b0, elapsed_from_start} > late_limit;
    wire late_at_start = late_for_frame ||
                         ((frame_pending || await_gmii_start) && beyond_late_limit);

    assign release_final_byte = frame_pending &&
                                (!have_start || elapsed_from_start >= bag_cycles_q);

    always @(posedge clk) begin
        if (reset) begin
            gmii_tx_en_d <= 1'b0;
            have_start <= 1'b0;
            frame_active <= 1'b0;
            await_gmii_start <= 1'b0;
            late_for_frame <= 1'b0;
            elapsed_from_start <= 32'd0;
            bag_cycles_q <= 32'd1;
            jitter_cycles_q <= 32'd0;
            late_pulse <= 1'b0;
            late_count <= 32'd0;
        end else begin
            gmii_tx_en_d <= gmii_tx_en;
            late_pulse <= 1'b0;

            if (have_start && elapsed_from_start != 32'hffffffff)
                elapsed_from_start <= elapsed_from_start + 1'b1;

            if (frame_arm) begin
                frame_active <= 1'b1;
                await_gmii_start <= 1'b0;
                late_for_frame <= 1'b0;
                bag_cycles_q <= bag_cycles;
                jitter_cycles_q <= jitter_cycles;
            end

            if (frame_cancel) begin
                frame_active <= 1'b0;
                await_gmii_start <= 1'b0;
                late_for_frame <= 1'b0;
            end

            if (frame_pending && frame_active && have_start && beyond_late_limit)
                late_for_frame <= 1'b1;

            if (frame_eop_fire)
                await_gmii_start <= 1'b1;

            if (gmii_start) begin
                if (frame_active && late_at_start) begin
                    late_pulse <= 1'b1;
                    if (late_count != 32'hffffffff)
                        late_count <= late_count + 1'b1;
                end
                have_start <= 1'b1;
                elapsed_from_start <= 32'd0;
                frame_active <= 1'b0;
                await_gmii_start <= 1'b0;
                late_for_frame <= 1'b0;
            end
        end
    end
endmodule
