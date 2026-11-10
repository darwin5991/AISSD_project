////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : accumulator_lane
// Description : One output lane: bias alignment, accumulation, result and postprocess.
// Status      : lane datapath implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Result capture and next-bias load may share an edge: separate registers.

module accumulator_lane (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                bias_load,
    input  logic signed [7:0]   bias_data,
    input  logic signed [5:0]   bias_shift,

    input  logic signed [31:0]  partial_sum,
    input  logic                psum_valid,

    input  logic                result_load,
    input  logic                relu_en,
    input  logic        [4:0]   output_shift,

    output logic signed [7:0]   output8
);

logic signed [31:0] bias32;
logic signed [31:0] acc32;
logic signed [31:0] result32;

bias_align u_bias (
    .bias_data(bias_data),
    .bias_shift(bias_shift),
    .bias32(bias32)
);

accumulator32 u_accumulator (
    .clk(clk),
    .rst_n(rst_n),
    .bias_load(bias_load),
    .bias32(bias32),
    .partial_sum(partial_sum),
    .psum_valid(psum_valid),
    .acc32(acc32)
);

register_en #(.WIDTH(32)) u_result (
    .clk(clk),
    .rst_n(rst_n),
    .en(result_load),
    .data_in(acc32),
    .data_out(result32)
);

postprocess_lane u_postprocess (
    .result32(result32),
    .relu_en(relu_en),
    .output_shift(output_shift),
    .output8(output8)
);

endmodule
