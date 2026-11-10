////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : unpack_int8x4
// Description : Unpack a word; lane zero is bits [7:0].
// Status      : structural wiring; leaf behavior pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module unpack_int8x4 (
    input  logic        [31:0]  word_in,

    output logic signed [7:0]   data_out [0:3]
);

for (genvar lane = 0; lane < 4; lane++) begin : g_unpack
    assign data_out[lane] = word_in[lane*8 +: 8];
end

endmodule
