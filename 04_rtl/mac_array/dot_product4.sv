////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : dot_product4
// Description : Four multipliers, product registers, adder tree and sum register.
// Status      : structural wiring and arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module dot_product4 (
    input  logic                clk,
    input  logic                rst_n,

    input  logic signed [7:0]   input_data [0:3],
    input  logic signed [7:0]   weight_data [0:3],

    output logic signed [31:0]  partial_sum
);

logic signed [31:0] product_comb [0:3];
logic signed [31:0] product_reg [0:3];
logic signed [31:0] sum_comb;

for (genvar lane = 0; lane < 4; lane++) begin : g_multiply
    signed_multiplier8 u_multiply (
        .a(input_data[lane]),
        .b(weight_data[lane]),
        .product(product_comb[lane])
    );

    register_en #(.WIDTH(32)) u_product (
        .clk(clk),
        .rst_n(rst_n),
        .en(1'b1),
        .data_in(product_comb[lane]),
        .data_out(product_reg[lane])
    );
end

adder_tree4 u_tree (
    .products(product_reg),
    .sum(sum_comb)
);

register_en #(.WIDTH(32)) u_partial_sum (
    .clk(clk),
    .rst_n(rst_n),
    .en(1'b1),
    .data_in(sum_comb),
    .data_out(partial_sum)
);

endmodule
