////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : relu32
// Description : Optional combinational ReLU.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module relu32 (
    input  logic signed [31:0]  data_in,
    input  logic                relu_en,

    output logic signed [31:0]  data_out
);

assign data_out = (relu_en && (data_in < 32'sd0)) ? 32'sd0 : data_in;

endmodule
