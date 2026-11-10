////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : signed_multiplier8
// Description : Signed INT8 multiplication, extended to INT32.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module signed_multiplier8 (
    input  logic signed [7:0]   a,
    input  logic signed [7:0]   b,

    output logic signed [31:0]  product
);

logic signed [15:0] product16;

assign product16 = a * b;
assign product = {{16{product16[15]}}, product16};

endmodule
