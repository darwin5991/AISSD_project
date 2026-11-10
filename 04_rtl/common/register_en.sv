////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : register_en
// Description : Enabled register with asynchronous active-low zero reset.
// Status      : enabled register implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module register_en #(
    parameter integer WIDTH = 32
) (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                en,

    input  logic        [WIDTH-1:0] data_in,
    output logic        [WIDTH-1:0] data_out
);

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        data_out <= '0;
    else if (en)
        data_out <= data_in;
end

endmodule
