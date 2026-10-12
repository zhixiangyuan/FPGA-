// Reflected Ethernet CRC update; caller owns initialization and final XOR.
module mac_crc32_byte(input wire [31:0] state_in, input wire [7:0] data,
                      output reg [31:0] state_out);
    integer i;
    always @* begin
        state_out = state_in ^ {24'b0,data};
        for (i=0;i<8;i=i+1)
            if (state_out[0]) state_out=(state_out>>1)^32'hedb88320;
            else state_out=state_out>>1;
    end
endmodule
