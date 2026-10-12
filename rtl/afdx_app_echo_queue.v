// Two atomic application banks. TX SN is owned solely by the frozen sender.
module afdx_app_echo_queue(
 input wire clk,reset,
 input wire [7:0] app_data,input wire app_valid,output wire app_ready,
 input wire app_sop,app_eop,input wire [10:0] app_length,
 input wire [7:0] app_sn,input wire [15:0] app_vlid,
 output wire msg_valid,input wire msg_ready,output wire [10:0] msg_length,
 output wire [7:0] payload_data,output wire payload_valid,
 input wire payload_ready,output wire payload_last,input wire msg_done,msg_error,
 output reg [31:0] stored_count,sent_count,error_count,
 output wire [1:0] banks_busy
);
 reg [7:0] bank0[0:1470],bank1[0:1470];
 reg [10:0] lengths[0:1];reg [7:0] origins[0:1];
 reg [1:0] busy,committed;
 reg wr_bank,rd_bank,writing;reg [10:0] wr_index,rd_index;
 reg [1:0] state;
 localparam IDLE=0,DESC=1,DATA=2,WAIT_DONE=3;
 assign app_ready=!reset&&(writing||!busy[wr_bank]);
 assign banks_busy=busy;
 assign msg_valid=!reset&&state==DESC;
 assign msg_length=lengths[rd_bank];
 assign payload_valid=!reset&&state==DATA;
 assign payload_data=rd_bank?bank1[rd_index]:bank0[rd_index];
 assign payload_last=payload_valid&&(rd_index+1'b1==lengths[rd_bank]);
 wire app_fire=app_valid&&app_ready;
 always @(posedge clk)begin
  if(reset)begin
   busy<=0;committed<=0;wr_bank<=0;rd_bank<=0;writing<=0;
   wr_index<=0;rd_index<=0;state<=IDLE;
   lengths[0]<=0;lengths[1]<=0;origins[0]<=0;origins[1]<=0;
   stored_count<=0;sent_count<=0;error_count<=0;
  end else begin
   if(app_fire)begin
    if((!writing&&(!app_sop||app_length==0||app_length>1471||app_vlid!=16'h1234||app_sn==0))||
       (writing&&(app_sop||app_length!=lengths[wr_bank]||app_sn!=origins[wr_bank]))||
       (app_eop!=(writing?(wr_index+1'b1==lengths[wr_bank]):app_length==1)))begin
      error_count<=error_count+1'b1;busy[wr_bank]<=0;committed[wr_bank]<=0;writing<=0;wr_index<=0;
    end else begin
     if(wr_bank)bank1[writing?wr_index:11'd0]<=app_data;
     else bank0[writing?wr_index:11'd0]<=app_data;
     if(!writing)begin busy[wr_bank]<=1;lengths[wr_bank]<=app_length;origins[wr_bank]<=app_sn;end
     if(app_eop)begin
      committed[wr_bank]<=1;stored_count<=stored_count+1'b1;
      wr_bank<=!wr_bank;writing<=0;wr_index<=0;
     end else begin writing<=1;wr_index<=writing?wr_index+1'b1:11'd1;end
    end
   end
   case(state)
    IDLE:if(committed[rd_bank])begin state<=DESC;rd_index<=0;end
    DESC:if(msg_valid&&msg_ready)state<=DATA;
    DATA:if(payload_valid&&payload_ready)begin
     if(payload_last)state<=WAIT_DONE;else rd_index<=rd_index+1'b1;
    end
    WAIT_DONE:if(msg_done)begin
     busy[rd_bank]<=0;committed[rd_bank]<=0;rd_bank<=!rd_bank;
     state<=IDLE;sent_count<=sent_count+1'b1;
    end
    default:state<=IDLE;
   endcase
   // A descriptor/payload error is observable, never silently counted sent.
   if(msg_error)begin
    error_count<=error_count+1'b1;busy[rd_bank]<=0;committed[rd_bank]<=0;
    rd_bank<=!rd_bank;state<=IDLE;
   end
  end
 end
endmodule
