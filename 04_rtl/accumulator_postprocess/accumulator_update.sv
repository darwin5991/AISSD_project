////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : accumulator_update
// Description : Accumulator register enable and bias/sum selection.
// Status      : combinational arithmetic implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// bias_load and psum_valid must not overlap; no state or timing here.

module accumulator_update (
    input  logic                bias_load,
    input  logic                psum_valid,

    input  logic signed [31:0]  bias32,
    input  logic signed [31:0]  sum32,

    output logic                write_en,
    output logic signed [31:0]  next_value
);

assign write_en = bias_load | psum_valid;

always_comb begin
    case ({bias_load, psum_valid})
        2'b00: next_value = 32'sd0; // Register is disabled; retain its state.
        2'b10: next_value = bias32;
        2'b01: next_value = sum32;
        // Unsupported overlap/unknown control: no specified selection priority.
        default: next_value = 'x;
    endcase
end

endmodule
