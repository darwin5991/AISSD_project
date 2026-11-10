////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : single_port_bram
// Description : One single-port synchronous RAM; one-clock read latency.
// Status      : synchronous RAM behavior implemented; RTL/BRAM mapping pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Reset applies to read-data registers only, never to stored memory contents.

module single_port_bram #(
    parameter integer WIDTH = 32,
    parameter integer DEPTH = 196,
    parameter integer ADDR_WIDTH = 8
) (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                en,
    input  logic                we,
    input  logic        [ADDR_WIDTH-1:0] addr,
    input  logic        [WIDTH-1:0] wdata,

    output logic        [WIDTH-1:0] rdata
);

logic [WIDTH-1:0] memory [0:DEPTH-1];

// No initialization or reset assignment to stored words. Keep storage writes
// in a clock-only process; reset suppresses accesses, never clears the array.
always_ff @(posedge clk) begin
    if (rst_n && en && we)
        memory[addr] <= wdata;
end

// One registered read, with the specified asynchronous zero reset.
// No read during writes; both writes and disabled cycles retain rdata.
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        rdata <= '0;
    else if (en && !we)
        rdata <= memory[addr];
end

endmodule
