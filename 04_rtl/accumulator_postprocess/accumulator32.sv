////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : accumulator32
// Description : One accumulator: addition, update selection and enabled register.
// Status      : accumulation path implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module accumulator32 (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                bias_load,
    input  logic signed [31:0]  bias32,

    input  logic                psum_valid,
    input  logic signed [31:0]  partial_sum,

    output logic signed [31:0]  acc32
);

logic signed [31:0] sum32;
logic signed [31:0] next_value;
logic write_en;

signed_adder32 u_add (
    .a(acc32),
    .b(partial_sum),
    .sum(sum32)
);

accumulator_update u_update (
    .bias_load(bias_load),
    .psum_valid(psum_valid),
    .bias32(bias32),
    .sum32(sum32),
    .write_en(write_en),
    .next_value(next_value)
);

register_en #(.WIDTH(32)) u_accumulator (
    .clk(clk),
    .rst_n(rst_n),
    .en(write_en),
    .data_in(next_value),
    .data_out(acc32)
);

endmodule
