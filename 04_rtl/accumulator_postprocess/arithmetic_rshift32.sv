////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : arithmetic_rshift32
// Description : Arithmetic output shift; negative values round down.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module arithmetic_rshift32 (
    input  logic signed [31:0]  data_in,
    input  logic        [4:0]   shift,

    output logic signed [31:0]  data_out
);

// The signed left operand preserves the sign and discards low bits.
assign data_out = data_in >>> shift;

endmodule
