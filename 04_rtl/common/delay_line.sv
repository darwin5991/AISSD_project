////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : delay_line
// Description : Free-running pipeline; reset clears every stage.
// Status      : free-running register pipeline implemented (DEPTH >= 1)
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module delay_line #(
    parameter integer WIDTH = 1,
    parameter integer DEPTH = 1
) (
    input  logic                clk,
    input  logic                rst_n,

    input  logic        [WIDTH-1:0] data_in,
    output logic        [WIDTH-1:0] data_out
);

logic [WIDTH-1:0] stages [0:DEPTH-1];

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        for (integer i = 0; i < DEPTH; i = i + 1)
            stages[i] <= '0;
    end else begin
        stages[0] <= data_in;
        for (integer i = 1; i < DEPTH; i = i + 1)
            stages[i] <= stages[i-1];
    end
end

assign data_out = stages[DEPTH-1];

endmodule
