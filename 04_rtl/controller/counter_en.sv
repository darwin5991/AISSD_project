////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : counter_en
// Description : Counter: clear to zero, otherwise advance on command.
// Status      : asynchronous-reset counter implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Counter policy is supplied by Control unit; no local scheduling.

module counter_en #(
    parameter integer WIDTH = 8
) (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                clear,
    input  logic                advance,

    output logic        [WIDTH-1:0] value
);

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        value <= '0;
    else if (clear)
        value <= '0;
    else if (advance)
        value <= value + 1'b1;
end

endmodule
