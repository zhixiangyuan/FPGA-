// Volatile bounded file store. Writes go to the inactive RAM bank; only a
// successful finish swaps the visible bank. Reset invalidates metadata only.
// Readers hold read_lock across a file transfer to prevent a mid-file swap.
module afdx_atomic_file_store #(
 parameter integer ADDRESS_BITS=12,
 parameter [15:0] CRC_INITIAL=16'hffff,
 parameter [15:0] CRC_POLYNOMIAL=16'h1021
)(
 input wire clk,reset,
 input wire begin_valid,output wire begin_ready,
 input wire check_length,input wire [15:0] expected_length,
 input wire check_crc,input wire [15:0] expected_crc,
 input wire write_valid,output wire write_ready,input wire [15:0] write_address,input wire [7:0] write_data,
 input wire finish_valid,output wire finish_ready,output wire [15:0] finish_error,
 input wire abort_stage,
 input wire read_lock,read_enable,input wire [15:0] read_address,
 output reg [7:0] read_data,output reg read_valid,
 output reg active_valid,output reg [15:0] active_length,active_crc,
 output reg [31:0] generation,output reg committed,rejected,
 output wire staging_active,output wire [15:0] staging_length,staging_crc
);
 localparam integer CAPACITY=1<<ADDRESS_BITS;
 reg [7:0] memory[0:2*CAPACITY-1];
 reg active_bank,staging,fault,length_check,crc_check;
 reg [15:0] count,crc,required_length,required_crc;
 wire write_fire=write_valid&&write_ready;
 wire legal_write=write_fire&&!fault&&write_address==count&&count<CAPACITY;
 assign staging_active=staging;
 assign staging_length=count;
 assign staging_crc=crc;
 assign begin_ready=!reset&&!staging;
 assign write_ready=!reset&&staging;
 assign finish_ready=!reset&&staging&&!write_valid&&!read_lock;
 assign finish_error=fault||(length_check&&count!=required_length)||(crc_check&&crc!=required_crc)?16'd3:16'd0;
 always @(posedge clk)begin
  if(legal_write)memory[{!active_bank,write_address[ADDRESS_BITS-1:0]}]<=write_data;
  if(read_enable&&active_valid&&read_address<active_length)
   read_data<=memory[{active_bank,read_address[ADDRESS_BITS-1:0]}];
 end
 always @(posedge clk)begin
  if(reset)begin
   active_bank<=0;active_valid<=0;active_length<=0;active_crc<=CRC_INITIAL;generation<=0;
   staging<=0;fault<=0;length_check<=0;crc_check<=0;count<=0;crc<=CRC_INITIAL;
   required_length<=0;required_crc<=0;committed<=0;rejected<=0;read_valid<=0;
  end else begin
   read_valid<=read_enable&&active_valid&&read_address<active_length;
   committed<=0;rejected<=0;
   if(abort_stage)begin staging<=0;fault<=0;end
   else begin
    if(begin_valid&&begin_ready)begin
     staging<=1;count<=0;crc<=CRC_INITIAL;fault<=check_length&&expected_length>CAPACITY;
     length_check<=check_length;required_length<=expected_length;crc_check<=check_crc;required_crc<=expected_crc;
    end
    if(write_fire)begin
     if(legal_write)begin count<=count+1'b1;crc<=crc_byte(crc,write_data);end
     else fault<=1;
    end
    if(finish_valid&&finish_ready)begin
     staging<=0;
     if(finish_error==0)begin
      active_bank<=!active_bank;active_valid<=1;active_length<=count;active_crc<=crc;
      generation<=generation+1'b1;committed<=1;
     end else rejected<=1;
    end
   end
  end
 end
 function [15:0] crc_byte;
  input [15:0] previous;input [7:0] value;integer bit_index;reg [15:0] c;
  begin
   c=previous^{value,8'd0};
   for(bit_index=0;bit_index<8;bit_index=bit_index+1)c=c[15]?(c<<1)^CRC_POLYNOMIAL:c<<1;
   crc_byte=c;
  end
 endfunction
endmodule
