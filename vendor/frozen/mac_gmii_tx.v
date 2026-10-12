module mac_gmii_tx #(parameter integer DEPTH=2048,parameter [31:0] COUNTER_MAX=32'hffffffff)(
    input wire clk,reset,
    input wire [7:0] client_data,input wire client_valid,output wire client_ready,
    input wire client_sop,client_eop,input wire [15:0] client_length,
    input wire client_afdx_prepared,
    output reg [7:0] gmii_txd,output reg gmii_tx_en,output wire gmii_tx_er,
    output reg done,reject,output reg [31:0] sent_frames,rejected_frames,output reg counter_saturated
);
    localparam I_IDLE=0,I_FILL=1,I_SKIP=2,I_WAIT=3;
    localparam T_IDLE=0,T_PRE=1,T_SFD=2,T_DATA=3,T_PAD=4,T_FCS=5,T_IFG=6;
    reg [1:0] ingest;
    reg [2:0] phase;
    reg [15:0] expected,received,remaining;
    reg prepared;
    reg [3:0] pre_count,gap_count;
    reg [5:0] pad_left;
    reg [1:0] fcs_index;
    reg [31:0] crc,fcs;
    wire bready,iready,busy,committed,bvalid;
    wire [7:0] bdata;
    wire [15:0] blength;
    wire [31:0] occupancy,crc_next;
    wire first_legal=client_sop&&(client_length>=14)&&(client_length<=1514)&&
                      (!client_afdx_prepared||client_length>=60);
    assign client_ready=!reset&&((ingest==I_IDLE&&bready)||(ingest==I_FILL&&iready)||(ingest==I_SKIP));
    wire fire=client_valid&&client_ready;
    wire finish_bad=fire&&ingest==I_FILL&&(client_sop||
                    (client_eop&&received+1!=expected)||(!client_eop&&received+1>=expected));
    wire commit=fire&&ingest==I_FILL&&client_eop&&!client_sop&&received+1==expected;
    function [31:0] increment;input [31:0] v;begin increment=v>=COUNTER_MAX?v:v+1'b1;end endfunction
    mac_frame_store #(.DEPTH(DEPTH)) bank(.clk(clk),.reset(reset),
      .begin_valid(fire&&ingest==I_IDLE&&first_legal&&!client_eop),.begin_ready(bready),
      .in_data(client_data),.in_valid(fire&&((ingest==I_IDLE&&first_legal&&!client_eop)||(ingest==I_FILL&&!finish_bad))),
      .in_ready(iready),.commit_valid(commit),.abort_valid(finish_bad),
      .out_data(bdata),.out_valid(bvalid),.out_ready(phase==T_DATA),
      .busy(busy),.committed(committed),.frame_length(blength),.occupancy(occupancy));
    mac_crc32_byte update(.state_in(crc),.data(phase==T_PAD?8'h00:bdata),.state_out(crc_next));
    assign gmii_tx_er=1'b0;
    always @* begin
        gmii_tx_en=!reset&&(phase>=T_PRE&&phase<=T_FCS);
        gmii_txd=0;
        case(phase)
          T_PRE:gmii_txd=8'h55;
          T_SFD:gmii_txd=8'hd5;
          T_DATA:gmii_txd=bdata;
          T_PAD:gmii_txd=0;
          T_FCS:case(fcs_index)
            0:gmii_txd=fcs[7:0];1:gmii_txd=fcs[15:8];
            2:gmii_txd=fcs[23:16];3:gmii_txd=fcs[31:24];
          endcase
        endcase
    end
    always @(posedge clk) begin
        if(reset) begin ingest<=I_IDLE;phase<=T_IDLE;expected<=0;received<=0;prepared<=0;
            remaining<=0;pre_count<=0;gap_count<=0;pad_left<=0;fcs_index<=0;
            crc<=32'hffffffff;fcs<=0;done<=0;reject<=0;sent_frames<=0;rejected_frames<=0;counter_saturated<=0;end
        else begin
            done<=0;reject<=0;
            if(fire) case(ingest)
              I_IDLE:begin
                if(!first_legal||client_eop) begin
                  if(client_eop)begin reject<=1;rejected_frames<=increment(rejected_frames);if(rejected_frames>=COUNTER_MAX)counter_saturated<=1;end
                  else ingest<=I_SKIP;
                end else begin ingest<=I_FILL;expected<=client_length;received<=1;prepared<=client_afdx_prepared;end
              end
              I_FILL:begin
                received<=received+1'b1;
                if(finish_bad) begin
                  if(client_eop)begin reject<=1;rejected_frames<=increment(rejected_frames);if(rejected_frames>=COUNTER_MAX)counter_saturated<=1;ingest<=I_IDLE;end
                  else ingest<=I_SKIP;
                end else if(commit) ingest<=I_WAIT;
              end
              I_SKIP:if(client_eop)begin reject<=1;rejected_frames<=increment(rejected_frames);if(rejected_frames>=COUNTER_MAX)counter_saturated<=1;ingest<=I_IDLE;end
            endcase
            if(ingest==I_WAIT&&phase==T_IDLE&&bready) ingest<=I_IDLE;
            case(phase)
              T_IDLE:if(committed)begin phase<=T_PRE;pre_count<=0;remaining<=blength;
                    pad_left<=(!prepared&&blength<60)?60-blength:0;crc<=32'hffffffff;end
              T_PRE:if(pre_count==6)phase<=T_SFD;else pre_count<=pre_count+1'b1;
              T_SFD:phase<=T_DATA;
              T_DATA:begin
                crc<=crc_next;remaining<=remaining-1'b1;
                if(remaining==1)begin
                  if(pad_left!=0)phase<=T_PAD;
                  else begin fcs<=~crc_next;fcs_index<=0;phase<=T_FCS;end
                end
              end
              T_PAD:begin crc<=crc_next;pad_left<=pad_left-1'b1;
                if(pad_left==1)begin fcs<=~crc_next;fcs_index<=0;phase<=T_FCS;end
              end
              T_FCS:if(fcs_index==3)begin done<=1;sent_frames<=increment(sent_frames);if(sent_frames>=COUNTER_MAX)counter_saturated<=1;phase<=T_IFG;gap_count<=0;end
                    else fcs_index<=fcs_index+1'b1;
              T_IFG:if(gap_count==11)phase<=T_IDLE;else gap_count<=gap_count+1'b1;
            endcase
        end
    end
endmodule
