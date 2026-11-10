////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : memory_port_mux
// Description : Select one memory's TB path while idle or core path while busy.
// Status      : combinational access selection implemented; RTL verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module memory_port_mux (
    input  logic                busy,

    input  logic                tb_en,
    input  logic                tb_we,
    input  logic        [14:0]  tb_addr,
    input  logic        [31:0]  tb_wdata,

    input  logic                core_en,
    input  logic                core_we,
    input  logic        [14:0]  core_addr,
    input  logic        [31:0]  core_wdata,

    output logic                ram_en,
    output logic                ram_we,
    output logic        [14:0]  ram_addr,
    output logic        [31:0]  ram_wdata
);

// Each RAM performs an operation only when the selected path asserts ram_en.
assign ram_en = busy ? core_en : tb_en;
assign ram_we = busy ? core_we : tb_we;
assign ram_addr = busy ? core_addr : tb_addr;
assign ram_wdata = busy ? core_wdata : tb_wdata;

endmodule
