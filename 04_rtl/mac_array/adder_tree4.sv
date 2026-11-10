////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : adder_tree4
// Description : Balanced four-input INT32 sum without registers.
// Status      : structural wiring and arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module adder_tree4 (
    input  logic signed [31:0]  products [0:3],

    output logic signed [31:0]  sum
);

logic signed [31:0] pair_sum [0:1];

signed_adder32 u_pair01 (
    .a(products[0]),
    .b(products[1]),
    .sum(pair_sum[0])
);

signed_adder32 u_pair23 (
    .a(products[2]),
    .b(products[3]),
    .sum(pair_sum[1])
);

signed_adder32 u_final (
    .a(pair_sum[0]),
    .b(pair_sum[1]),
    .sum(sum)
);

endmodule
