////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : sign_extend8_to32
// Description : Extend signed INT8 to signed INT32.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module sign_extend8_to32 (
    input  logic signed [7:0]   data_in,

    output logic signed [31:0]  data_out
);

assign data_out = {{24{data_in[7]}}, data_in};

endmodule
