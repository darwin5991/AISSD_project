////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : pack_int8x4
// Description : Pack four signed bytes; lane zero is bits [7:0].
// Status      : combinational packing implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module pack_int8x4 (
    input  logic signed [7:0]   data_in [0:3],

    output logic        [31:0]  word_out
);

for (genvar lane = 0; lane < 4; lane++) begin : g_pack
    assign word_out[lane*8 +: 8] = data_in[lane];
end

endmodule
