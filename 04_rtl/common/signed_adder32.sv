////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : signed_adder32
// Description : One signed INT32 addition; no pipeline register.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module signed_adder32 (
    input  logic signed [31:0]  a,
    input  logic signed [31:0]  b,

    output logic signed [31:0]  sum
);

assign sum = a + b;

endmodule
