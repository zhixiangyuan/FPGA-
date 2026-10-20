// Decode bounded 615A ERROR message controls without buffering the datagram.
// The endpoint uses these results only when TFTP confirms a matching peer/TID.
module afdx_615a_error_decoder(
 input wire clk,reset,input wire [7:0] data,input wire valid,ready,sop,eop,input wire [10:0] length,
 output reg last_wait,last_abort,output reg [15:0] wait_seconds,abort_code
);
 reg [9:0] index;
 reg [15:0] opcode,error_number,hexadecimal;
 reg [10:0] declared;
 reg [47:0] prefix;
 reg [16:0] decimal;
 reg decimal_good,hexadecimal_good,framing_good;
 wire digit=data>=8'h30&&data<=8'h39;
 wire upper_hex=data>=8'h41&&data<=8'h46;
 wire lower_hex=data>=8'h61&&data<=8'h66;
 wire [20:0] decimal_next=({4'd0,decimal}<<3)+({4'd0,decimal}<<1)+{17'd0,data[3:0]};
 wire [3:0] hex_digit=digit?data[3:0]:data[3:0]+4'd9;
 always @(posedge clk)begin
  if(reset)begin
   index<=0;opcode<=0;error_number<=0;hexadecimal<=0;declared<=0;prefix<=0;decimal<=0;
   decimal_good<=1;hexadecimal_good<=1;framing_good<=0;last_wait<=0;last_abort<=0;wait_seconds<=0;abort_code<=0;
  end else if(valid&&ready)begin
   if(sop)begin
    index<=1;opcode<={data,8'd0};error_number<=0;hexadecimal<=0;declared<=length;prefix<=0;decimal<=0;
    decimal_good<=1;hexadecimal_good<=1;framing_good<=!eop;
   end else begin
    if(index==1)opcode[7:0]<=data;
    if(index==2)error_number[15:8]<=data;
    if(index==3)error_number[7:0]<=data;
    if(index>=4&&index<10)prefix[(index-4)*8+:8]<=data;
    if(index>=9&&index<14&&!eop)begin
     if(!digit||decimal_next>65535)decimal_good<=0;
     decimal<=decimal_next[16:0];
    end
    if(index>=10&&index<14&&!eop)begin
     if(!digit&&!upper_hex&&!lower_hex)hexadecimal_good<=0;
     hexadecimal<={hexadecimal[11:0],hex_digit};
    end
    if(length!=declared)framing_good<=0;
    index<=index+1'b1;
    if(eop)begin
     last_wait<=0;last_abort<=0;
     if(framing_good&&declared==index+1'b1&&opcode==5&&error_number==0&&data==0)begin
      if(prefix[39:0]==40'h3a54494157&&declared>=11&&declared<=15&&decimal_good)begin
       last_wait<=1;wait_seconds<=decimal[15:0];
      end
      if(prefix==48'h3a54524f4241&&declared==15&&hexadecimal_good)begin
       last_abort<=1;abort_code<=hexadecimal;
      end
     end
    end
   end
  end
 end
endmodule
