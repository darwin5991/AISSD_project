////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : tb_read_mux
// Description : Capture the TB read selection and select the returning RAM word.
// Status      : registered read selection implemented; RTL verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Latch the selector only; no extra data register beyond RAM read latency.

module tb_read_mux (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                busy,
    input  logic                tb_en,
    input  logic                tb_we,
    input  logic        [2:0]   memory_select,

    input  logic        [31:0]  memory_rdata [0:6],

    output logic        [31:0]  tb_rdata
);

logic [2:0] read_memory_select;

// Capture selection on the same edge that updates the selected BRAM's read
// register. Registering tb_rdata here would introduce an extra read cycle.
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        read_memory_select <= 3'd0;
    else if (!busy && tb_en && !tb_we)
        read_memory_select <= memory_select;
end

// The contract guarantees tb_rdata only for the one-clock TB read response.
assign tb_rdata = memory_rdata[read_memory_select];

endmodule
