////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : buffer_router
// Description : Route the common input/output ports to ping-pong buffers A and B.
// Status      : combinational buffer routing implemented; RTL verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module buffer_router (
    input  logic                buf_sel,

    input  logic        [7:0]   in_addr,
    input  logic                in_en,
    output logic        [31:0]  in_data,

    input  logic        [6:0]   out_addr,
    input  logic                out_we,
    input  logic        [31:0]  out_data,

    input  logic        [31:0]  a_rdata,
    input  logic        [31:0]  b_rdata,

    output logic                a_en,
    output logic                a_we,
    output logic        [7:0]   a_addr,
    output logic        [31:0]  a_wdata,

    output logic                b_en,
    output logic                b_we,
    output logic        [7:0]   b_addr,
    output logic        [31:0]  b_wdata
);

// Input and output always use different single-port memories.
// The output word address is zero-extended to the common eight-bit route.
assign a_en = buf_sel ? out_we : in_en;
assign a_we = buf_sel ? out_we : 1'b0;
assign a_addr = buf_sel ? {1'b0, out_addr} : in_addr;
assign a_wdata = buf_sel ? out_data : 32'd0;

assign b_en = buf_sel ? in_en : out_we;
assign b_we = buf_sel ? 1'b0 : out_we;
assign b_addr = buf_sel ? in_addr : {1'b0, out_addr};
assign b_wdata = buf_sel ? 32'd0 : out_data;

// Select the BRAM read register even while in_en=0. A selection change may
// therefore change in_data without performing a new memory read.
assign in_data = buf_sel ? b_rdata : a_rdata;

endmodule
