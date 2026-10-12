// Single-clock FWFT byte FIFO. No empty-cycle bypass.
module afdx_byte_fifo #(parameter integer DEPTH = 16) (
    input wire clk, input wire reset,
    input wire [7:0] push_data, input wire push_valid, output wire push_ready,
    output wire [7:0] out_data, output wire out_valid, input wire out_ready,
    output wire full, output wire empty, output wire [31:0] occupancy
);
    function integer bits_needed;
        input integer value;
        integer remaining;
        begin
            remaining = value - 1; bits_needed = 0;
            while (remaining > 0) begin
                bits_needed = bits_needed + 1; remaining = remaining >> 1;
            end
            if (bits_needed < 1) bits_needed = 1;
        end
    endfunction
    localparam integer PTR_W = bits_needed(DEPTH);
    localparam integer COUNT_W = bits_needed(DEPTH+1);
    reg [7:0] storage [0:DEPTH-1];
    reg [PTR_W-1:0] write_ptr, read_ptr;
    reg [COUNT_W-1:0] count;
    wire pop_fire, push_fire;
    assign empty = (count == 0);
    assign full = (count == DEPTH);
    assign occupancy = count;
    assign out_valid = !reset && !empty;
    assign out_data = out_valid ? storage[read_ptr] : 8'h00;
    assign pop_fire = out_valid && out_ready;
    assign push_ready = !reset && (!full || pop_fire);
    assign push_fire = push_valid && push_ready;
    always @(posedge clk) begin
        if (reset) begin
            write_ptr <= 0; read_ptr <= 0; count <= 0;
        end else begin
            if (push_fire) begin
                storage[write_ptr] <= push_data;
                if (write_ptr == DEPTH-1) write_ptr <= 0;
                else write_ptr <= write_ptr + 1'b1;
            end
            if (pop_fire) begin
                if (read_ptr == DEPTH-1) read_ptr <= 0;
                else read_ptr <= read_ptr + 1'b1;
            end
            case ({push_fire,pop_fire})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
