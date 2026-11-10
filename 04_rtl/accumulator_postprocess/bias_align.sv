////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : bias_align
// Description : Sign extension followed by bias-scale alignment.
// Status      : bias sign extension and alignment connected; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module bias_align (
    input  logic signed [7:0]   bias_data,
    input  logic signed [5:0]   bias_shift,

    output logic signed [31:0]  bias32
);

logic signed [31:0] extended_bias;

sign_extend8_to32 u_extend (
    .data_in(bias_data),
    .data_out(extended_bias)
);

signed_shifter32 u_shift (
    .data_in(extended_bias),
    .shift(bias_shift),
    .data_out(bias32)
);

endmodule
