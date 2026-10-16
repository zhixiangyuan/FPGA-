// Bounded raw TFTP file endpoint used for transport/RAM acceptance. This module
// is not a 615A controller. The 615A controller supplies its own file policy.
module afdx_tftp_file_endpoint #(
 parameter integer TIMEOUT_CYCLES=12500000,
 parameter integer MAX_RETRIES=3
)(
 input wire clk,reset,start,start_write,
 output wire start_ready,busy,done,failed,
 input wire [7:0] in_data,input wire in_valid,output wire in_ready,
 input wire in_sop,in_eop,input wire [10:0] in_length,input wire [15:0] in_src_port,in_dst_port,
 output wire [7:0] out_data,output wire out_valid,input wire out_ready,
 output wire out_sop,out_eop,output wire [10:0] out_length,output wire [15:0] out_src_port,out_dst_port,
 output wire active_valid,output wire [15:0] active_length,active_crc,
 output wire [31:0] generation
);
 wire aborted,file_open_valid,file_open_ready,file_write,file_client;
 wire [15:0] failure_code,file_open_error,file_read_address,file_write_address,file_finish_length;
 wire [255:0] file_name;wire [5:0] file_name_length;
 wire file_read_enable,file_write_valid,file_write_ready,file_finish_valid,file_finish_ready;
 wire [7:0] file_read_data,file_write_data;
 wire [15:0] file_finish_error;
 wire begin_ready,committed,rejected,read_valid,staging_active;
 wire [15:0] staging_length,staging_crc;
 wire known_file=file_name_length==10&&file_name==256'h6e69622e6769666e6f63;
 assign file_open_error=!known_file?16'd1:(!file_write&&!active_valid)?16'd1:16'd0;
 assign file_open_ready=file_open_error!=0||!file_write||begin_ready;
 afdx_tftp_engine #(.TIMEOUT_CYCLES(TIMEOUT_CYCLES),.MAX_RETRIES(MAX_RETRIES)) transport(
  .clk(clk),.reset(reset),.cancel(1'b0),.start(start),.start_write(start_write),.start_name(256'h6e69622e6769666e6f63),.start_name_length(6'd10),
  .start_ready(start_ready),.busy(busy),.port_match(),.done(done),.failed(failed),.aborted(aborted),.failure_code(failure_code),
  .in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),.in_sop(in_sop),.in_eop(in_eop),.in_length(in_length),
  .in_src_port(in_src_port),.in_dst_port(in_dst_port),.out_data(out_data),.out_valid(out_valid),.out_ready(out_ready),
  .out_sop(out_sop),.out_eop(out_eop),.out_length(out_length),.out_src_port(out_src_port),.out_dst_port(out_dst_port),
  .file_open_valid(file_open_valid),.file_open_ready(file_open_ready),.file_open_error(file_open_error),
  .file_name(file_name),.file_name_length(file_name_length),.file_write(file_write),.file_client(file_client),.file_read_length(active_length),
  .file_read_enable(file_read_enable),.file_read_address(file_read_address),.file_read_data(file_read_data),
  .file_write_valid(file_write_valid),.file_write_ready(file_write_ready),.file_write_data(file_write_data),.file_write_address(file_write_address),
  .file_finish_valid(file_finish_valid),.file_finish_ready(file_finish_ready),.file_finish_error(file_finish_error),.file_finish_length(file_finish_length),
  .retry_count(),.duplicate_count(),.reject_count(),.completed_count());
 afdx_atomic_file_store store(
  .clk(clk),.reset(reset),.begin_valid(file_open_valid&&file_open_ready&&file_write&&file_open_error==0),.begin_ready(begin_ready),
  .check_length(1'b0),.expected_length(16'd0),.check_crc(1'b0),.expected_crc(16'd0),
  .write_valid(file_write_valid),.write_ready(file_write_ready),.write_address(file_write_address),.write_data(file_write_data),
  .finish_valid(file_finish_valid),.finish_ready(file_finish_ready),.finish_error(file_finish_error),.abort_stage(aborted),
  .read_lock(busy&&!file_write),.read_enable(file_read_enable),.read_address(file_read_address),.read_data(file_read_data),.read_valid(read_valid),
  .active_valid(active_valid),.active_length(active_length),.active_crc(active_crc),.generation(generation),.committed(committed),.rejected(rejected),
  .staging_active(staging_active),.staging_length(staging_length),.staging_crc(staging_crc));
endmodule
