////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : signed_compare8
// Description : Strict signed comparison a > b; ties return false.
// Status      : strict signed comparison implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module signed_compare8 (
    input  logic signed [7:0]   a,
    input  logic signed [7:0]   b,

    output logic                greater
);

assign greater = ($signed(a) > $signed(b));

endmodule
