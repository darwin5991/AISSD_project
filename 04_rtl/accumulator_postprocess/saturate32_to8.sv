////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : saturate32_to8
// Description : Clamp signed INT32 to the signed INT8 range.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module saturate32_to8 (
    input  logic signed [31:0]  data_in,

    output logic signed [7:0]   data_out
);

assign data_out = (data_in > 32'sd127)  ? 8'sd127
                : (data_in < -32'sd128) ? 8'sh80
                : data_in[7:0];

endmodule
