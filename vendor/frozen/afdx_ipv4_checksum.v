// One's-complement checksum for a fixed 20-byte IPv4 header.
// The checksum field in header_zero_checksum must be zero.
module afdx_ipv4_checksum (
    input  wire [159:0] header_zero_checksum,
    output wire [15:0]  checksum
);
    wire [31:0] sum_words =
        {16'd0, header_zero_checksum[159:144]} +
        {16'd0, header_zero_checksum[143:128]} +
        {16'd0, header_zero_checksum[127:112]} +
        {16'd0, header_zero_checksum[111:96]}  +
        {16'd0, header_zero_checksum[95:80]}   +
        {16'd0, header_zero_checksum[79:64]}   +
        {16'd0, header_zero_checksum[63:48]}   +
        {16'd0, header_zero_checksum[47:32]}   +
        {16'd0, header_zero_checksum[31:16]}   +
        {16'd0, header_zero_checksum[15:0]};
    wire [16:0] fold_once = {1'b0, sum_words[15:0]} + sum_words[31:16];
    wire [16:0] fold_twice = {1'b0, fold_once[15:0]} + fold_once[16];

    assign checksum = ~fold_twice[15:0];
endmodule
