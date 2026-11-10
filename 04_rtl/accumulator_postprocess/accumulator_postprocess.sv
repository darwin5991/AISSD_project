////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : accumulator_postprocess
// Last update : 2026.11.10
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : four INT32 accumulators with bias and INT8 postprocessing
// Status      : datapath implemented; standalone verification pending
// Reference   : architecture.md, sections 2, 6.2, 6.4 and 7.4
////////////////////////////////////////////////////////////////////////////////
//
// bias8 -> sign extend/align -> acc32 <- partial_sum (psum_valid)
// acc32 --result_load--> result32 -> ReLU/shift/saturate -> packed output
//
// bias_load initializes acc32; bias_shift = accumulator F - bias F.
// Positive bias_shift shifts left; negative shifts arithmetically right.
// bias_load and psum_valid must not overlap.
// result_load may coincide with bias_load to save the previous result.
// Postprocessing is combinational: optional ReLU, arithmetic right shift,
// then clamp to [-128,127]. Lane 0 occupies output_data[7:0].
// CU writes on the next edge with ReLU/shift settings held stable.
// rst_n asynchronously clears accumulator and result registers.
////////////////////////////////////////////////////////////////////////////////

module accumulator_postprocess (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                bias_load,
    input  logic signed [7:0]   bias_data [0:3],
    input  logic signed [5:0]   bias_shift,

    input  logic signed [31:0]  partial_sum [0:3],
    input  logic                psum_valid,

    input  logic                result_load,
    input  logic                relu_en,
    input  logic        [4:0]   output_shift,
    output logic        [31:0]  output_data
);

logic signed [7:0] output_bytes [0:3];

for (genvar lane = 0; lane < 4; lane++) begin : g_accumulator
    accumulator_lane u_lane (
        .clk(clk),
        .rst_n(rst_n),
        .bias_load(bias_load),
        .bias_data(bias_data[lane]),
        .bias_shift(bias_shift),
        .partial_sum(partial_sum[lane]),
        .psum_valid(psum_valid),
        .result_load(result_load),
        .relu_en(relu_en),
        .output_shift(output_shift),
        .output8(output_bytes[lane])
    );
end

pack_int8x4 u_pack (
    .data_in(output_bytes),
    .word_out(output_data)
);

endmodule
