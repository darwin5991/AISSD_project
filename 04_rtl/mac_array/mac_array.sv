////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : mac_array
// Last update : 2026.11.10
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : Registered INT8 operands, 16 multipliers and four adder trees
// Status      : three-stage MAC implemented; verification pending
// Reference   : architecture.md, sections 6.1, 6.2, 6.4 and 7.3
////////////////////////////////////////////////////////////////////////////////
//
// input[4], weight[4][4] -> [operands/reg] -> [products/reg] -> [trees/reg] -> psum[4]
// Lane j: partial_sum[j] = sum(input_data[k] * weight_data[j][k]).
// Tree: (p0+p1)+(p2+p3); no register between the two adder levels.
//
// Products and all sums use signed INT32.
// input_valid follows three register stages to psum_valid.
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

logic signed [7:0] input_reg [0:3];
logic signed [7:0] weight_reg [0:3] [0:3];

// Capture the common input once; all four output lanes use the same sample.
// Operands advance even when input_valid is zero, matching the valid bubbles.
for (genvar k = 0; k < 4; k++) begin : g_input
    register_en #(.WIDTH(8)) u_input (
        .clk(clk),
        .rst_n(rst_n),
        .en(1'b1),
        .data_in(input_data[k]),
        .data_out(input_reg[k])
    );
end

for (genvar lane = 0; lane < 4; lane++) begin : g_dot_product
    for (genvar k = 0; k < 4; k++) begin : g_weight
        register_en #(.WIDTH(8)) u_weight (
            .clk(clk),
            .rst_n(rst_n),
            .en(1'b1),
            .data_in(weight_data[lane][k]),
            .data_out(weight_reg[lane][k])
        );
    end

    // The existing product and partial-sum registers remain in dot_product4.
    dot_product4 u_dot_product (
        .clk(clk),
        .rst_n(rst_n),
        .input_data(input_reg),
        .weight_data(weight_reg[lane]),
        .partial_sum(partial_sum[lane])
    );
end

delay_line #(.WIDTH(1), .DEPTH(3)) u_valid (
    .clk(clk),
    .rst_n(rst_n),
    .data_in(input_valid),
    .data_out(psum_valid)
);

endmodule
