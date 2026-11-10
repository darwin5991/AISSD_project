////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : memory_wrapper
// Last update : 2026.11.09
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : single-port BRAM buffers, weight banks and bias memory
// Status      : memory leaf behavior implemented; RTL verification pending
// Reference   : architecture.md, sections 7.5, 8 and 9
////////////////////////////////////////////////////////////////////////////////
//
// Memory depth x width: A=196x32, B=128x32, W[0..3]=29280x32, bias=163x32.
// buf_sel=0: read A/write B; buf_sel=1: read B/write A.
// Weight banks share one read address and enable.
//
// Reads: one-clock latency. Writes: rising edge. No simultaneous R/W.
// TB access only while busy=0; TB uses byte addresses, core uses words.
// tb_addr: [19:17] memory, [16:2] word, [1:0]=00.
// First packed byte is in [7:0]; Top interprets it as signed INT8.
// Weight order: layer -> output group -> input word.
// FC3 stores 12 output bytes, including two zero dummy lanes.
// Reset clears non-memory registers; BRAM contents are retained.
////////////////////////////////////////////////////////////////////////////////

module memory_wrapper (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                tb_en,
    input  logic                tb_we,
    input  logic        [19:0]  tb_addr,
    input  logic        [31:0]  tb_wdata,
    output logic        [31:0]  tb_rdata,

    input  logic                busy,
    input  logic                buf_sel,

    input  logic        [7:0]   in_addr,
    input  logic                in_en,
    output logic        [31:0]  in_data,

    input  logic        [6:0]   out_addr,
    input  logic                out_we,
    input  logic        [31:0]  out_data,

    input  logic        [14:0]  weight_addr,
    input  logic                weight_en,
    output logic        [31:0]  weight_data [0:3],

    input  logic        [7:0]   bias_addr,
    input  logic                bias_en,
    output logic        [31:0]  bias_data
);

logic [2:0] tb_memory_select;
logic [14:0] tb_word_addr;
logic [6:0] tb_memory_en;

logic core_en [0:6];
logic core_we [0:6];
logic [14:0] core_addr [0:6];
logic [31:0] core_wdata [0:6];

logic ram_en [0:6];
logic ram_we [0:6];
logic [14:0] ram_addr [0:6];
logic [31:0] ram_wdata [0:6];
logic [31:0] ram_rdata [0:6];

logic [7:0] a_addr;
logic [7:0] b_addr;

tb_address_decoder u_tb_decode (
    .tb_en(tb_en),
    .tb_addr(tb_addr),
    .memory_select(tb_memory_select),
    .word_addr(tb_word_addr),
    .memory_en(tb_memory_en)
);

buffer_router u_buffers (
    .buf_sel(buf_sel),
    .in_addr(in_addr),
    .in_en(in_en),
    .in_data(in_data),
    .out_addr(out_addr),
    .out_we(out_we),
    .out_data(out_data),
    .a_rdata(ram_rdata[0]),
    .b_rdata(ram_rdata[1]),
    .a_en(core_en[0]),
    .a_we(core_we[0]),
    .a_addr(a_addr),
    .a_wdata(core_wdata[0]),
    .b_en(core_en[1]),
    .b_we(core_we[1]),
    .b_addr(b_addr),
    .b_wdata(core_wdata[1])
);

assign core_addr[0] = {7'd0, a_addr};
assign core_addr[1] = {7'd0, b_addr};

for (genvar bank = 0; bank < 4; bank++) begin : g_weight_ports
    assign core_en[bank+2] = weight_en;
    assign core_we[bank+2] = 1'b0;
    assign core_addr[bank+2] = weight_addr;
    assign core_wdata[bank+2] = 32'd0;
    assign weight_data[bank] = ram_rdata[bank+2];
end

assign core_en[6] = bias_en;
assign core_we[6] = 1'b0;
assign core_addr[6] = {7'd0, bias_addr};
assign core_wdata[6] = 32'd0;
assign bias_data = ram_rdata[6];

for (genvar memory = 0; memory < 7; memory++) begin : g_access
    memory_port_mux u_mux (
        .busy(busy),
        .tb_en(tb_memory_en[memory]),
        .tb_we(tb_we),
        .tb_addr(tb_word_addr),
        .tb_wdata(tb_wdata),
        .core_en(core_en[memory]),
        .core_we(core_we[memory]),
        .core_addr(core_addr[memory]),
        .core_wdata(core_wdata[memory]),
        .ram_en(ram_en[memory]),
        .ram_we(ram_we[memory]),
        .ram_addr(ram_addr[memory]),
        .ram_wdata(ram_wdata[memory])
    );
end

single_port_bram #(.DEPTH(196), .ADDR_WIDTH(8)) u_buffer_a (
    .clk(clk),
    .rst_n(rst_n),
    .en(ram_en[0]),
    .we(ram_we[0]),
    .addr(ram_addr[0][7:0]),
    .wdata(ram_wdata[0]),
    .rdata(ram_rdata[0])
);

single_port_bram #(.DEPTH(128), .ADDR_WIDTH(7)) u_buffer_b (
    .clk(clk),
    .rst_n(rst_n),
    .en(ram_en[1]),
    .we(ram_we[1]),
    .addr(ram_addr[1][6:0]),
    .wdata(ram_wdata[1]),
    .rdata(ram_rdata[1])
);

for (genvar bank = 0; bank < 4; bank++) begin : g_weight_rams
    single_port_bram #(.DEPTH(29280), .ADDR_WIDTH(15)) u_weight (
        .clk(clk),
        .rst_n(rst_n),
        .en(ram_en[bank+2]),
        .we(ram_we[bank+2]),
        .addr(ram_addr[bank+2]),
        .wdata(ram_wdata[bank+2]),
        .rdata(ram_rdata[bank+2])
    );
end

single_port_bram #(.DEPTH(163), .ADDR_WIDTH(8)) u_bias (
    .clk(clk),
    .rst_n(rst_n),
    .en(ram_en[6]),
    .we(ram_we[6]),
    .addr(ram_addr[6][7:0]),
    .wdata(ram_wdata[6]),
    .rdata(ram_rdata[6])
);

tb_read_mux u_tb_read (
    .clk(clk),
    .rst_n(rst_n),
    .busy(busy),
    .tb_en(tb_en),
    .tb_we(tb_we),
    .memory_select(tb_memory_select),
    .memory_rdata(ram_rdata),
    .tb_rdata(tb_rdata)
);

endmodule
