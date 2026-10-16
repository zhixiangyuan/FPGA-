// Configured ARINC615A-2 (A3) target profile: one 665-2 LSAP, one even-length
// config.bin (0..4096 bytes), no support files, encryption or compression.
// Upload uses LUI -> LUR -> target RRQ LUH -> target RRQ data -> LUS.
// Media-defined download uses LND -> LNR -> target WRQ data -> LNS.
// Status has its own TFTP session, so lost bulk packets cannot stop status.
// The 665 header layout accepted by this profile is defined by header_byte().
module afdx_615a_endpoint #(
 parameter integer TFTP_TIMEOUT_CYCLES=12500000,
 parameter integer STATUS_PERIOD_CYCLES=12500000,
 parameter integer DLP_TIMEOUT_CYCLES=1625000000,
 parameter integer SECOND_CYCLES=125000000,
 parameter [15:0] TFTP_SERVER_PORT=16'd59
)(
 input wire clk,reset,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,input wire [15:0] in_src_port,in_dst_port,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,
 output wire out_sop,out_eop,output wire [10:0] out_length,output wire [15:0] out_src_port,out_dst_port,
 output wire active_valid,output wire [15:0] active_length,active_crc,output wire [31:0] generation,
 output reg [15:0] operation_status,output wire operation_active,
 output reg [7:0] upload_count,download_count,error_count
);
 localparam [255:0] NAME_LUI=256'h49554c2e31305f58444641,NAME_LUR=256'h52554c2e31305f58444641,
  NAME_LUS=256'h53554c2e31305f58444641,NAME_LND=256'h444e4c2e31305f58444641,
  NAME_LNR=256'h524e4c2e31305f58444641,NAME_LNS=256'h534e4c2e31305f58444641,
  NAME_HEADER=256'h48554c2e6769666e6f63,NAME_DATA=256'h6e69622e6769666e6f63;
 localparam [63:0] LOAD_PN=64'h0031502d58444641,DATA_PN=64'h313030302d474643;
 localparam [31:0] HARDWARE_ID=32'h58444641;
 localparam [3:0] P_IDLE=0,P_INIT_UP=1,P_WAIT_LUR=2,P_GO_HEADER=3,P_HEADER=4,
  P_GO_DATA=5,P_DATA=6,P_DONE=7,P_FAILED=8,P_INIT_DOWN=9,P_WAIT_LNR=10,P_GO_SEND=11,P_SEND=12,P_WAITING=13;
 localparam [2:0] K_NONE=0,K_LUI=1,K_LND=2,K_LUR=3,K_LNR=4,K_HEADER=5,K_DATA_RX=6,K_DATA_TX=7;
 reg [3:0] phase;
 reg [2:0] file_kind;
 reg download_operation,have_list,init_denied,bulk_cancel;
 reg [31:0] status_version,operation_timer;
 reg [3:0] retry_phase;
 reg [15:0] bulk_wait_seconds;
 reg [31:0] bulk_wait_tick;
 reg [1:0] bulk_wait_retries;
 wire bulk_start_ready,bulk_busy,bulk_done,bulk_failed,bulk_aborted,bulk_port_match;
 wire b_peer_error,s_peer_error,b_error_wait,b_error_abort,s_error_wait,s_error_abort;
 wire [15:0] b_wait_seconds,b_abort_code,s_wait_seconds,s_abort_code;
 wire [15:0] bulk_failure;
 wire bulk_start=(phase==P_GO_HEADER||phase==P_GO_DATA||phase==P_GO_SEND)&&bulk_start_ready;
 wire [255:0] bulk_start_name=phase==P_GO_HEADER?NAME_HEADER:NAME_DATA;
 wire bulk_start_write=phase==P_GO_SEND;
 wire b_rx_ready,s_rx_ready,b_tx_valid,s_tx_valid,b_tx_sop,s_tx_sop,b_tx_eop,s_tx_eop,b_tx_ready,s_tx_ready;
 wire [7:0] b_tx_data,s_tx_data;
 wire [10:0] b_tx_length,s_tx_length;
 wire [15:0] b_tx_src,b_tx_dst,s_tx_src,s_tx_dst;
 wire b_open,b_open_ready,b_write,b_client,b_read,b_write_valid,b_write_ready,b_finish,b_finish_ready;
 wire [255:0] b_name;wire [5:0] b_name_length;
 wire [15:0] b_open_error,b_read_length,b_read_address,b_write_address,b_finish_error,b_finish_length;
 wire [7:0] b_read_data,b_write_data;
 wire s_start_ready,s_busy,s_done,s_failed,s_aborted,s_port_match,s_open,s_write,s_client,s_read,s_write_valid,s_finish;
 wire [255:0] s_name;wire [5:0] s_name_length;
 wire [15:0] s_failure,s_read_address,s_write_address,s_finish_length;
 wire [7:0] s_read_data,s_write_data;
 reg [31:0] status_submitted,status_acked,status_failed_version,status_inflight_version,status_timer;
 reg [15:0] status_sequence,status_sequence_q,status_code_q;
 reg [15:0] status_exception_q,status_wait_seconds;
 reg [31:0] status_wait_tick;
 reg [1:0] status_wait_retries;
 reg status_retry_requested;
 reg status_download_q,status_have_list_q;
 wire status_terminal=phase==P_DONE||phase==P_FAILED;
 wire status_needed=phase!=P_IDLE&&phase!=P_INIT_UP&&phase!=P_INIT_DOWN&&status_wait_seconds==0&&
  (status_retry_requested||status_submitted!=status_version||(!status_terminal&&status_timer+1>=STATUS_PERIOD_CYCLES));
 wire status_start=status_needed&&s_start_ready;
 wire [255:0] status_name=download_operation?NAME_LNS:NAME_LUS;
 wire [15:0] status_file_length=status_have_list_q?(status_download_q?16'd51:16'd63):16'd28;
 wire new_operation_allowed=phase==P_IDLE||(status_terminal&&!s_busy&&!status_retry_requested&&status_wait_seconds==0&&
  (status_acked==status_version||status_failed_version==status_version));
 wire bulk_wait_allowed=bulk_failed&&b_peer_error&&b_error_wait&&bulk_wait_retries<2&&
  (file_kind==K_HEADER||file_kind==K_DATA_RX||file_kind==K_DATA_TX);
 wire status_wait_allowed=s_failed&&s_peer_error&&s_error_wait&&status_wait_retries<2;
 wire [15:0] bulk_abort_status=b_peer_error?(b_error_abort&&(b_abort_code==16'h1003||b_abort_code==16'h1004||b_abort_code==16'h1005)?b_abort_code:16'h1004):16'h1003;
 wire [15:0] status_abort_status=s_peer_error&&s_error_abort&&(s_abort_code==16'h1003||s_abort_code==16'h1004||s_abort_code==16'h1005)?s_abort_code:16'h1004;
 assign operation_active=phase!=P_IDLE&&!status_terminal;
 // One byte-stream packet arbiter, with a source held until accepted EOP.
 reg tx_owner_active,tx_owner_status,last_tx_status,rx_packet,rx_owner_status;
 wire select_status=rx_packet?rx_owner_status:s_port_match;
 assign in_ready=!reset&&(select_status?s_rx_ready:b_rx_ready);
 assign out_valid=!reset&&tx_owner_active&&(tx_owner_status?s_tx_valid:b_tx_valid);
 assign out_data=tx_owner_status?s_tx_data:b_tx_data;
 assign out_sop=out_valid&&(tx_owner_status?s_tx_sop:b_tx_sop);
 assign out_eop=out_valid&&(tx_owner_status?s_tx_eop:b_tx_eop);
 assign out_length=tx_owner_status?s_tx_length:b_tx_length;
 assign out_src_port=tx_owner_status?s_tx_src:b_tx_src;
 assign out_dst_port=tx_owner_status?s_tx_dst:b_tx_dst;
 assign b_tx_ready=!reset&&tx_owner_active&&!tx_owner_status&&out_ready;
 assign s_tx_ready=!reset&&tx_owner_active&&tx_owner_status&&out_ready;
 always @(posedge clk)begin
  if(reset)begin tx_owner_active<=0;tx_owner_status<=0;last_tx_status<=1;rx_packet<=0;rx_owner_status<=0;end
  else begin
   if(in_valid&&in_ready)begin
    if(!rx_packet)rx_owner_status<=s_port_match;
    rx_packet<=!in_eop;
   end
   if(!tx_owner_active&&(b_tx_valid||s_tx_valid))begin
    tx_owner_active<=1;tx_owner_status<=s_tx_valid&&(!b_tx_valid||!last_tx_status);
   end else if(out_valid&&out_ready&&out_eop)begin tx_owner_active<=0;last_tx_status<=tx_owner_status;end
  end
 end
 afdx_tftp_engine #(.TIMEOUT_CYCLES(TFTP_TIMEOUT_CYCLES),.TID_PREFIX(3'b110),.SERVER_PORT(TFTP_SERVER_PORT)) bulk(
  .clk(clk),.reset(reset),.cancel(bulk_cancel),.start(bulk_start),.start_write(bulk_start_write),
  .start_name(bulk_start_name),.start_name_length(6'd10),.start_ready(bulk_start_ready),.busy(bulk_busy),.port_match(bulk_port_match),
  .done(bulk_done),.failed(bulk_failed),.aborted(bulk_aborted),.peer_error(b_peer_error),.failure_code(bulk_failure),
  .in_data(in_data),.in_valid(in_valid&&!select_status),.in_ready(b_rx_ready),.in_sop(in_sop),.in_eop(in_eop),
  .in_length(in_length),.in_src_port(in_src_port),.in_dst_port(in_dst_port),
  .out_data(b_tx_data),.out_valid(b_tx_valid),.out_ready(b_tx_ready),.out_sop(b_tx_sop),.out_eop(b_tx_eop),
  .out_length(b_tx_length),.out_src_port(b_tx_src),.out_dst_port(b_tx_dst),
  .file_open_valid(b_open),.file_open_ready(b_open_ready),.file_open_error(b_open_error),
  .file_name(b_name),.file_name_length(b_name_length),.file_write(b_write),.file_client(b_client),.file_read_length(b_read_length),
  .file_read_enable(b_read),.file_read_address(b_read_address),.file_read_data(b_read_data),
  .file_write_valid(b_write_valid),.file_write_ready(b_write_ready),.file_write_data(b_write_data),.file_write_address(b_write_address),
  .file_finish_valid(b_finish),.file_finish_ready(b_finish_ready),.file_finish_error(b_finish_error),.file_finish_length(b_finish_length),
  .retry_count(),.duplicate_count(),.reject_count(),.completed_count());
 afdx_tftp_engine #(.TIMEOUT_CYCLES(TFTP_TIMEOUT_CYCLES),.TID_PREFIX(3'b111),.TID_SEED(16'he267),.SERVER_PORT(TFTP_SERVER_PORT)) status_transport(
  .clk(clk),.reset(reset),.cancel(1'b0),.start(status_start),.start_write(1'b1),
  .start_name(status_name),.start_name_length(6'd11),.start_ready(s_start_ready),.busy(s_busy),.port_match(s_port_match),
  .done(s_done),.failed(s_failed),.aborted(s_aborted),.peer_error(s_peer_error),.failure_code(s_failure),
  .in_data(in_data),.in_valid(in_valid&&select_status),.in_ready(s_rx_ready),.in_sop(in_sop),.in_eop(in_eop),
  .in_length(in_length),.in_src_port(in_src_port),.in_dst_port(in_dst_port),
  .out_data(s_tx_data),.out_valid(s_tx_valid),.out_ready(s_tx_ready),.out_sop(s_tx_sop),.out_eop(s_tx_eop),
  .out_length(s_tx_length),.out_src_port(s_tx_src),.out_dst_port(s_tx_dst),
  .file_open_valid(s_open),.file_open_ready(1'b1),.file_open_error((s_client&&!s_write)?16'd0:16'd2),
  .file_name(s_name),.file_name_length(s_name_length),.file_write(s_write),.file_client(s_client),.file_read_length(status_file_length),
  .file_read_enable(s_read),.file_read_address(s_read_address),.file_read_data(s_read_data),
  .file_write_valid(s_write_valid),.file_write_ready(1'b1),.file_write_data(s_write_data),.file_write_address(s_write_address),
  .file_finish_valid(s_finish),.file_finish_ready(1'b1),.file_finish_error(16'd2),.file_finish_length(s_finish_length),
  .retry_count(),.duplicate_count(),.reject_count(),.completed_count());
 afdx_615a_error_decoder bulk_errors(.clk(clk),.reset(reset),.data(in_data),.valid(in_valid&&!select_status),
  .ready(in_ready),.sop(in_sop),.eop(in_eop),.length(in_length),.last_wait(b_error_wait),.last_abort(b_error_abort),.wait_seconds(b_wait_seconds),.abort_code(b_abort_code));
 afdx_615a_error_decoder status_errors(.clk(clk),.reset(reset),.data(in_data),.valid(in_valid&&select_status),
  .ready(in_ready),.sop(in_sop),.eop(in_eop),.length(in_length),.last_wait(s_error_wait),.last_abort(s_error_abort),.wait_seconds(s_wait_seconds),.abort_code(s_abort_code));
 // Classify an opened file using both the operation phase and TFTP direction.
 wire [2:0] opening_kind=(!b_client&&!b_write&&b_name_length==11&&new_operation_allowed&&b_name==NAME_LUI)?K_LUI:
  (!b_client&&!b_write&&b_name_length==11&&new_operation_allowed&&b_name==NAME_LND)?K_LND:
  (!b_client&&b_write&&b_name_length==11&&phase==P_WAIT_LUR&&b_name==NAME_LUR)?K_LUR:
  (!b_client&&b_write&&b_name_length==11&&phase==P_WAIT_LNR&&b_name==NAME_LNR)?K_LNR:
  (b_client&&b_write&&b_name_length==10&&phase==P_HEADER&&b_name==NAME_HEADER)?K_HEADER:
  (b_client&&b_write&&b_name_length==10&&phase==P_DATA&&b_name==NAME_DATA)?K_DATA_RX:
  (b_client&&!b_write&&b_name_length==10&&phase==P_SEND&&b_name==NAME_DATA&&active_valid)?K_DATA_TX:K_NONE;
 wire store_begin_ready,store_finish_ready,store_write_ready,store_read_valid,store_committed,store_rejected,store_staging;
 wire [15:0] store_finish_error,store_stage_length,store_stage_crc;
 wire [7:0] store_read_data;
 reg [15:0] body_count,header_crc16,header_expected_crc16,expected_data_crc,expected_data_length;
 reg [31:0] header_crc32,header_seed,expected_load_crc,data_words,load_crc32;
 reg body_bad;
 wire load_crc_ok=(load_crc32^32'hffffffff)==expected_load_crc;
 assign b_open_error=opening_kind==K_NONE?16'd2:16'd0;
 assign b_open_ready=opening_kind!=K_DATA_RX||store_begin_ready;
 wire [2:0] read_kind=b_open?opening_kind:file_kind;
 wire initialization_denied=b_open?(opening_kind==K_LND&&!active_valid):init_denied;
 assign b_read_length=read_kind==K_LUI||read_kind==K_LND?(initialization_denied?16'd18:16'd10):active_length;
 reg [7:0] bulk_rom_q,status_rom_q;
 assign b_read_data=file_kind==K_DATA_TX?store_read_data:bulk_rom_q;
 assign s_read_data=status_rom_q;
 assign b_write_ready=file_kind==K_DATA_RX?store_write_ready:1'b1;
 wire header_valid=!body_bad&&body_count==84&&header_crc16==header_expected_crc16&&data_words<=2048;
 wire control_valid=!body_bad&&body_count==(file_kind==K_LUR?16'd29:16'd21);
 assign b_finish_ready=file_kind==K_DATA_RX?(load_crc_ok?store_finish_ready:1'b1):1'b1;
 assign b_finish_error=file_kind==K_DATA_RX?(load_crc_ok?store_finish_error:16'd3):
  file_kind==K_HEADER?(header_valid?16'd0:16'd3):control_valid?16'd0:16'd4;
 afdx_atomic_file_store store(
  .clk(clk),.reset(reset),.begin_valid(b_open&&b_open_ready&&opening_kind==K_DATA_RX),.begin_ready(store_begin_ready),
  .check_length(1'b1),.expected_length(expected_data_length),.check_crc(1'b1),.expected_crc(expected_data_crc),
  .write_valid(b_write_valid&&file_kind==K_DATA_RX),.write_ready(store_write_ready),.write_address(b_write_address),.write_data(b_write_data),
  // Never expose an image which passes its file CRC but fails the total load CRC.
  .finish_valid(b_finish&&file_kind==K_DATA_RX&&load_crc_ok),.finish_ready(store_finish_ready),.finish_error(store_finish_error),
  .abort_stage(bulk_aborted||bulk_cancel),.read_lock(bulk_busy&&file_kind==K_DATA_TX),
  .read_enable(b_read&&file_kind==K_DATA_TX),.read_address(b_read_address),.read_data(store_read_data),.read_valid(store_read_valid),
  .active_valid(active_valid),.active_length(active_length),.active_crc(active_crc),.generation(generation),
  .committed(store_committed),.rejected(store_rejected),.staging_active(store_staging),.staging_length(store_stage_length),.staging_crc(store_stage_crc));
 always @(posedge clk)begin
  if(b_read)bulk_rom_q<=initialization_byte(b_read_address,init_denied);
  if(s_read)status_rom_q<=status_byte(s_read_address);
 end
 // Control files are checked serially. The configured 665-2 header consists
 // of a fixed identity/layout plus independently validated length and CRCs.
 always @(posedge clk)begin
  if(reset)begin
   body_count<=0;body_bad<=0;header_crc16<=16'hffff;header_expected_crc16<=0;
   header_crc32<=32'hffffffff;header_seed<=0;expected_load_crc<=0;data_words<=0;
   expected_data_crc<=0;expected_data_length<=0;load_crc32<=0;
  end else begin
   if(b_open&&b_open_ready&&b_open_error==0)begin
    body_count<=0;body_bad<=0;
    if(opening_kind==K_HEADER)begin
     header_crc16<=16'hffff;header_crc32<=32'hffffffff;header_expected_crc16<=0;data_words<=0;expected_data_crc<=0;expected_load_crc<=0;
    end
    if(opening_kind==K_DATA_RX)load_crc32<=header_seed;
   end
   if(b_write_valid&&b_write_ready)begin
    body_count<=body_count+1'b1;
    if(b_write_address!=body_count)body_bad<=1;
    if(file_kind==K_LUR||file_kind==K_LNR)begin
     if(b_write_data!=control_byte(file_kind==K_LNR,b_write_address))body_bad<=1;
    end else if(file_kind==K_HEADER)begin
     if(b_write_address<72&&b_write_data!=header_byte(b_write_address))body_bad<=1;
     if(b_write_address>=84)body_bad<=1;
     if(b_write_address<78)header_crc16<=crc16_byte(header_crc16,b_write_data);
     if(b_write_address<80)header_crc32<=crc32_byte(header_crc32,b_write_data);
     if(b_write_address>=72&&b_write_address<76)data_words<={data_words[23:0],b_write_data};
     if(b_write_address>=76&&b_write_address<78)expected_data_crc<={expected_data_crc[7:0],b_write_data};
     if(b_write_address>=78&&b_write_address<80)header_expected_crc16<={header_expected_crc16[7:0],b_write_data};
     if(b_write_address>=80&&b_write_address<84)expected_load_crc<={expected_load_crc[23:0],b_write_data};
    end else if(file_kind==K_DATA_RX)load_crc32<=crc32_byte(load_crc32,b_write_data);
   end
   if(b_finish&&b_finish_ready&&file_kind==K_HEADER&&b_finish_error==0)begin
    header_seed<=header_crc32;expected_data_length<={data_words[14:0],1'b0};
   end
  end
 end
 always @(posedge clk)begin
  if(reset)begin
   phase<=P_IDLE;file_kind<=K_NONE;download_operation<=0;have_list<=0;init_denied<=0;
   operation_status<=0;status_version<=0;operation_timer<=0;bulk_cancel<=0;
   upload_count<=0;download_count<=0;error_count<=0;retry_phase<=P_IDLE;bulk_wait_seconds<=0;bulk_wait_tick<=0;bulk_wait_retries<=0;
  end else begin
   bulk_cancel<=0;
   if(operation_active&&phase!=P_WAITING&&status_wait_seconds==0)operation_timer<=operation_timer+1'b1;
   else operation_timer<=0;
   if(b_read||(b_write_valid&&b_write_ready)||bulk_done||(b_open&&b_open_ready&&opening_kind!=K_NONE))operation_timer<=0;
   if(bulk_start)begin
    if(phase==P_GO_HEADER)phase<=P_HEADER;
    else if(phase==P_GO_DATA)phase<=P_DATA;
    else phase<=P_SEND;
   end
   if(b_open&&b_open_ready)begin
    file_kind<=opening_kind;
    if(opening_kind==K_LUI||opening_kind==K_LND)begin
     phase<=opening_kind==K_LUI?P_INIT_UP:P_INIT_DOWN;
     download_operation<=opening_kind==K_LND;have_list<=0;
     init_denied<=opening_kind==K_LND&&!active_valid;
     bulk_wait_retries<=0;bulk_wait_seconds<=0;
    end
   end
   if(b_finish&&b_finish_ready&&b_finish_error==0&&(file_kind==K_LUR||file_kind==K_LNR))begin
    have_list<=1;operation_status<=2;status_version<=status_version+1'b1;
   end
   if(bulk_done)case(file_kind)
    K_LUI:begin phase<=P_WAIT_LUR;operation_status<=1;status_version<=status_version+1'b1;end
    K_LND:begin
     if(init_denied)phase<=P_IDLE;
     else begin phase<=P_WAIT_LNR;operation_status<=1;status_version<=status_version+1'b1;end
    end
    K_LUR:phase<=P_GO_HEADER;
    K_LNR:phase<=P_GO_SEND;
    K_HEADER:begin phase<=P_GO_DATA;status_version<=status_version+1'b1;bulk_wait_retries<=0;end
    K_DATA_RX:begin phase<=P_DONE;operation_status<=3;status_version<=status_version+1'b1;if(upload_count!=255)upload_count<=upload_count+1'b1;end
    K_DATA_TX:begin phase<=P_DONE;operation_status<=3;status_version<=status_version+1'b1;if(download_count!=255)download_count<=download_count+1'b1;end
    default:begin end
   endcase
   if(phase==P_WAITING)begin
    if(bulk_wait_seconds==0)phase<=retry_phase;
    else if(bulk_wait_tick+1>=SECOND_CYCLES)begin
     bulk_wait_tick<=0;bulk_wait_seconds<=bulk_wait_seconds-1'b1;
     if(bulk_wait_seconds==1)phase<=retry_phase;
    end else bulk_wait_tick<=bulk_wait_tick+1'b1;
   end
   if(bulk_wait_allowed&&phase!=P_FAILED&&!(s_failed&&!status_wait_allowed))begin
    phase<=P_WAITING;retry_phase<=file_kind==K_HEADER?P_GO_HEADER:file_kind==K_DATA_RX?P_GO_DATA:P_GO_SEND;
    bulk_wait_seconds<=b_wait_seconds;bulk_wait_tick<=0;bulk_wait_retries<=bulk_wait_retries+1'b1;
    status_version<=status_version+1'b1;operation_timer<=0;
   end else if((bulk_failed&&file_kind!=K_NONE&&phase!=P_IDLE&&phase!=P_FAILED&&phase!=P_DONE)||
      (s_failed&&!status_wait_allowed&&phase!=P_IDLE&&phase!=P_FAILED)||
      (operation_active&&phase!=P_WAITING&&status_wait_seconds==0&&operation_timer+1>=DLP_TIMEOUT_CYCLES))begin
    phase<=P_FAILED;operation_status<=s_failed?status_abort_status:bulk_abort_status;status_version<=status_version+1'b1;bulk_cancel<=1;
    if(error_count!=255)error_count<=error_count+1'b1;
   end
  end
 end
 // Status snapshots stay immutable throughout each TFTP write and its retries.
 always @(posedge clk)begin
  if(reset)begin
   status_submitted<=0;status_acked<=0;status_failed_version<=0;status_inflight_version<=0;status_timer<=0;
   status_sequence<=0;status_sequence_q<=0;status_code_q<=0;status_download_q<=0;status_have_list_q<=0;
   status_exception_q<=0;status_wait_seconds<=0;status_wait_tick<=0;status_wait_retries<=0;status_retry_requested<=0;
  end else begin
   if(status_timer+1<STATUS_PERIOD_CYCLES)status_timer<=status_timer+1'b1;
   if(status_start)begin
    status_submitted<=status_version;status_inflight_version<=status_version;status_timer<=0;
    status_code_q<=operation_status;status_download_q<=download_operation;status_have_list_q<=have_list;
    status_exception_q<=phase==P_WAITING?bulk_wait_seconds:16'd0;status_retry_requested<=0;
    if(status_submitted!=status_version)status_wait_retries<=0;
    status_sequence_q<=status_sequence;status_sequence<=status_sequence+1'b1;
   end
   if(s_done)begin status_acked<=status_inflight_version;status_wait_retries<=0;end
   if(s_failed)status_failed_version<=status_inflight_version;
   if(status_wait_seconds!=0)begin
    if(status_wait_tick+1>=SECOND_CYCLES)begin status_wait_tick<=0;status_wait_seconds<=status_wait_seconds-1'b1;end
    else status_wait_tick<=status_wait_tick+1'b1;
   end
   if(status_wait_allowed)begin
    status_wait_seconds<=s_wait_seconds;status_wait_tick<=0;status_wait_retries<=status_wait_retries+1'b1;status_retry_requested<=1;
   end
  end
 end
 function [7:0] initialization_byte;
  input [15:0] i;input denied;reg [63:0] reason;
  begin
   reason=64'h6567616d69206f6e;
   initialization_byte=0;
   if(i==3)initialization_byte=denied?18:10;
   else if(i==4)initialization_byte=8'h41;
   else if(i==5)initialization_byte=8'h33;
   else if(i==6)initialization_byte=denied?8'h10:0;
   else if(i==7)initialization_byte=denied?0:1;
   else if(i==8)initialization_byte=denied?9:1;
   else if(denied&&i>=9&&i<17)initialization_byte=reason[(i-9)*8+:8];
  end
 endfunction
 function [7:0] control_byte;
  input downloading;input [15:0] i;
  begin
   control_byte=0;
   if(i==3)control_byte=downloading?21:29;
   else if(i==4)control_byte=8'h41;
   else if(i==5)control_byte=8'h33;
   else if(i==7)control_byte=1;
   else if(i==8)control_byte=11;
   else if(i>=9&&i<19)control_byte=downloading?NAME_DATA[(i-9)*8+:8]:NAME_HEADER[(i-9)*8+:8];
   else if(!downloading&&i==20)control_byte=8;
   else if(!downloading&&i>=21&&i<28)control_byte=LOAD_PN[(i-21)*8+:8];
  end
 endfunction
 function [7:0] header_byte;
  input [15:0] i;
  begin
   header_byte=0;
   if(i==3)header_byte=42;
   else if(i==4)header_byte=8'h80;
   else if(i==5)header_byte=8'h03;
   else if(i==11)header_byte=14;
   else if(i==15)header_byte=19;
   else if(i==19)header_byte=23;
   else if(i==29)header_byte=7;
   else if(i>=30&&i<37)header_byte=LOAD_PN[(i-30)*8+:8];
   else if(i==39)header_byte=1;
   else if(i==41)header_byte=4;
   else if(i>=42&&i<46)header_byte=HARDWARE_ID[(i-42)*8+:8];
   else if(i==47)header_byte=1;
   else if(i==51)header_byte=10;
   else if(i>=52&&i<62)header_byte=NAME_DATA[(i-52)*8+:8];
   else if(i==63)header_byte=8;
   else if(i>=64&&i<72)header_byte=DATA_PN[(i-64)*8+:8];
  end
 endfunction
 function [7:0] description_byte;
  input [15:0] code;input [15:0] i;reg [63:0] text;
  begin
   text=code>=16'h1000 ? 64'h002064656c696166:code==3?64'h00202020656e6f64:code==2?64'h00676e6964616f6c:64'h0020207964616572;
   description_byte=text[i*8+:8];
  end
 endfunction
 function [7:0] ratio_byte;
  input [15:0] code;input [15:0] i;
  begin ratio_byte=code==3&&i==0?8'h31:8'h30;end
 endfunction
 function [7:0] status_byte;
  input [15:0] i;reg [15:0] file_status;
  begin
   file_status=status_code_q>=16'h1000 ? 16'h1007:status_code_q;
   status_byte=0;
   if(i==3)status_byte=status_file_length[7:0];
   else if(i==4)status_byte=8'h41;
   else if(i==5)status_byte=8'h33;
   else if(i==6)status_byte=status_code_q[15:8];
   else if(i==7)status_byte=status_code_q[7:0];
   else if(i==8)status_byte=8;
   else if(i>=9&&i<17)status_byte=description_byte(status_code_q,i-9);
   else if(i==17)status_byte=status_sequence_q[15:8];
   else if(i==18)status_byte=status_sequence_q[7:0];
   else if(i==19)status_byte=status_exception_q[15:8];
   else if(i==20)status_byte=status_exception_q[7:0];
   else if(i>=23&&i<26)status_byte=ratio_byte(status_code_q,i-23);
   else if(i==27)status_byte=have_list_byte(status_have_list_q);
   else if(status_have_list_q)begin
    if(i==28)status_byte=11;
    else if(i>=29&&i<39)status_byte=status_download_q?NAME_DATA[(i-29)*8+:8]:NAME_HEADER[(i-29)*8+:8];
    else if(status_download_q)begin
     if(i==40)status_byte=file_status[15:8];else if(i==41)status_byte=file_status[7:0];
     else if(i==42)status_byte=8;else if(i>=43&&i<51)status_byte=description_byte(status_code_q,i-43);
    end else begin
     if(i==40)status_byte=8;else if(i>=41&&i<48)status_byte=LOAD_PN[(i-41)*8+:8];
     else if(i>=49&&i<52)status_byte=ratio_byte(status_code_q,i-49);
     else if(i==52)status_byte=file_status[15:8];else if(i==53)status_byte=file_status[7:0];
     else if(i==54)status_byte=8;else if(i>=55&&i<63)status_byte=description_byte(status_code_q,i-55);
    end
   end
  end
 endfunction
 function [7:0] have_list_byte;
  input present;begin have_list_byte=present?8'd1:8'd0;end
 endfunction
 function [15:0] crc16_byte;
  input [15:0] previous;input [7:0] value;integer i;reg [15:0] c;
  begin c=previous^{value,8'd0};for(i=0;i<8;i=i+1)c=c[15]?(c<<1)^16'h1021:c<<1;crc16_byte=c;end
 endfunction
 function [31:0] crc32_byte;
  input [31:0] previous;input [7:0] value;integer i;reg [31:0] c;
  begin c=previous^{value,24'd0};for(i=0;i<8;i=i+1)c=c[31]?(c<<1)^32'h04c11db7:c<<1;crc32_byte=c;end
 endfunction
endmodule
