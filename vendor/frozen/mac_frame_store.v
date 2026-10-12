// A single atomic frame bank using the unchanged production byte FIFO.
module mac_frame_store #(parameter integer DEPTH=2048)(
    input wire clk,reset, input wire begin_valid, output wire begin_ready,
    input wire [7:0] in_data, input wire in_valid, output wire in_ready,
    input wire commit_valid,abort_valid,
    output wire [7:0] out_data,output wire out_valid,input wire out_ready,
    output reg busy,committed,output reg [15:0] frame_length,
    output wire [31:0] occupancy
);
    reg flush;
    reg [15:0] written;
    wire fifo_ready,fifo_valid,full,empty;
    wire begin_fire=begin_valid&&begin_ready;
    wire writable=(busy&&!committed)||begin_fire;
    wire push=in_valid&&writable&&!reset&&!flush&&!abort_valid;
    wire pop=fifo_valid&&committed&&out_ready&&!reset&&!flush;
    assign begin_ready=!reset&&!flush&&!busy;
    // Abort has sequential priority; do not feed it back into credit because
    // an owner may derive abort from the accepted malformed input beat.
    assign in_ready=!reset&&!flush&&writable&&fifo_ready;
    assign out_valid=!reset&&!flush&&committed&&fifo_valid;
    afdx_byte_fifo #(.DEPTH(DEPTH)) bytes(.clk(clk),.reset(reset||flush),
      .push_data(in_data),.push_valid(push),.push_ready(fifo_ready),
      .out_data(out_data),.out_valid(fifo_valid),.out_ready(committed&&out_ready&&!flush),
      .full(full),.empty(empty),.occupancy(occupancy));
    always @(posedge clk) begin
        if(reset) begin busy<=0;committed<=0;flush<=1;written<=0;frame_length<=0;end
        else begin
            flush<=0;
            if(abort_valid) begin busy<=0;committed<=0;flush<=1;written<=0;frame_length<=0;end
            else begin
                if(begin_fire) begin busy<=1;written<=push&&fifo_ready?16'd1:16'd0;end
                else if(push&&fifo_ready) written<=written+1'b1;
                if(commit_valid&&busy&&!committed) begin
                    committed<=1;frame_length<=written+(push&&fifo_ready?16'd1:16'd0);
                end
                if(pop&&occupancy==1) begin busy<=0;committed<=0;flush<=1;written<=0;end
            end
        end
    end
endmodule
