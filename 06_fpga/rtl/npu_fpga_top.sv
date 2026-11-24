// FPGA boundary: start is accepted only after the synchronized core reset releases.
module npu_fpga_top(
    input logic clk,rst_n,start,
    output wire busy,done,fault,imem_en,
    output wire [31:0] imem_addr,
    input logic [31:0] imem_rdata,
    output wire dmem_en,dmem_we,
    output wire [31:0] dmem_addr,dmem_wdata,
    input logic [31:0] dmem_rdata
);
    wire core_rst_n;
    npu_reset_sync u_reset(.clk(clk),.async_rst_n(rst_n),.core_rst_n(core_rst_n));
    npu_top u_npu(
        .clk(clk),.rst_n(core_rst_n),.start(start && core_rst_n),
        .busy(busy),.done(done),.fault(fault),
        .imem_en(imem_en),.imem_addr(imem_addr),.imem_rdata(imem_rdata),
        .dmem_en(dmem_en),.dmem_we(dmem_we),.dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata),.dmem_rdata(dmem_rdata));
endmodule
