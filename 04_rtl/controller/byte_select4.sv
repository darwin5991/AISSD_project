////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : byte_select4
// Description : Select one signed byte from a packed word.
// Status      : packed signed-byte selection implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module byte_select4 (
    input  logic        [31:0]  word_in,
    input  logic        [1:0]   lane,

    output logic signed [7:0]   data_out
);

assign data_out = word_in[lane * 8 +: 8];

endmodule
