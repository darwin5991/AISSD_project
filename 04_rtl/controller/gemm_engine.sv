// Existing arithmetic and 3-stage MAC, connected to the NPU's seven SRAM ports.
module gemm_engine(
    input logic clk,rst_n,start,
    input logic [31:0] config_words [0:9],
    output wire [7:0] config_error,
    output wire active,done,fault,
    output wire [7:0] error_code,
    output wire [6:0] ram_en,ram_we,
    output wire [14:0] ram_address [0:6],
    output wire [31:0] ram_wdata [0:6],
    input wire [31:0] ram_rdata [0:6]
);
    wire execute_enable;
    wire mac_input_valid,bias_load,result_load,relu_en,source_buffer,destination_buffer;
    wire signed [5:0] bias_shift;
    wire [4:0] output_shift;
    wire signed [7:0] input_bytes[0:3],weight_bytes[0:3][0:3],bias_bytes[0:3];
    wire signed [31:0] partial_sum[0:3];
    wire psum_valid;
    wire [31:0] output_word;
    gemm_controller u_control(.*);
    unpack_int8x4 u_input(.word_in(ram_rdata[source_buffer]),.data_out(input_bytes));
    for(genvar b=0;b<4;b++) begin:g_weights
        unpack_int8x4 u_weight(.word_in(ram_rdata[b+2]),.data_out(weight_bytes[b]));
    end
    unpack_int8x4 u_bias(.word_in(ram_rdata[6]),.data_out(bias_bytes));
    mac_array u_mac(.clk(clk),.rst_n(rst_n),.input_valid(mac_input_valid),
        .input_data(input_bytes),.weight_data(weight_bytes),.partial_sum(partial_sum),.psum_valid(psum_valid));
    accumulator_postprocess u_accumulator(.clk(clk),.rst_n(rst_n),
        .bias_load(bias_load),.bias_data(bias_bytes),.bias_shift(bias_shift),
        .partial_sum(partial_sum),.psum_valid(psum_valid && execute_enable),
        .result_load(result_load),.relu_en(relu_en),.output_shift(output_shift),.output_data(output_word));
    for(genvar b=0;b<7;b++) begin:g_write_data
        assign ram_wdata[b]=ram_we[b]?output_word:32'd0;
    end
endmodule
