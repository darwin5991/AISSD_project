////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : mac_array
// Last update : 2026.11.06
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : 16 signed INT8 multipliers and four balanced adder trees
// Status      : structural wiring and arithmetic implemented; verification pending
// Reference   : architecture.md, sections 6.1, 6.2, 6.4 and 7.3
////////////////////////////////////////////////////////////////////////////////
//
// input[4], weight[4][4] -> [products/reg] -> [adder trees/reg] -> psum[4]
// Lane j: partial_sum[j] = sum(input_data[k] * weight_data[j][k]).
// Tree: (p0+p1)+(p2+p3); no register between the two adder levels.
//
// Products and all sums use signed INT32.
// input_valid follows two register stages to psum_valid.
// Data advances every clock; invalid inputs insert bubbles.
// Bias and running accumulation belong to accumulator_postprocess.
// rst_n asynchronously clears registers.
////////////////////////////////////////////////////////////////////////////////

module mac_array (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                input_valid,
    input  logic signed [7:0]   input_data [0:3],
    input  logic signed [7:0]   weight_data [0:3] [0:3],

    output logic signed [31:0]  partial_sum [0:3],
    output logic                psum_valid
);

for (genvar lane = 0; lane < 4; lane++) begin : g_dot_product
    dot_product4 u_dot_product (
        .clk(clk),
        .rst_n(rst_n),
        .input_data(input_data),
        .weight_data(weight_data[lane]),
        .partial_sum(partial_sum[lane])
    );
end

delay_line #(.WIDTH(1), .DEPTH(2)) u_valid (
    .clk(clk),
    .rst_n(rst_n),
    .data_in(input_valid),
    .data_out(psum_valid)
);

endmodule
