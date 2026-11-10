////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : signed_shifter32
// Description : Bias alignment: positive shift left, negative arithmetic right.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module signed_shifter32 (
    input  logic signed [31:0]  data_in,
    input  logic signed [5:0]   shift,

    output logic signed [31:0]  data_out
);

logic signed [6:0] extended_shift;
logic        [6:0] right_amount;

// Widen before negation: signed 6-bit -32 must become shift amount +32.
assign extended_shift = {shift[5], shift};
assign right_amount = -extended_shift;
assign data_out = (shift >= 6'sd0)
                ? (data_in <<< shift)
                : (data_in >>> right_amount);

endmodule
