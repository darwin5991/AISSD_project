// Temporary M2 harness. Never included in synthesis source list.
module scalar_harness(input logic clk,rst_n,start,output logic busy,done,imem_en,
    output logic [31:0] imem_addr,input logic [31:0] imem_rdata,
    output logic dmem_en,dmem_we,output logic [31:0] dmem_addr,dmem_wdata,input logic [31:0] dmem_rdata);
instruction_controller u_ic(.clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
    .imem_en(imem_en),.imem_addr(imem_addr),.imem_rdata(imem_rdata),
    .scalar_en(dmem_en),.scalar_we(dmem_we),.scalar_addr(dmem_addr),.scalar_wdata(dmem_wdata),.dmem_rdata(dmem_rdata),
    .dma_done(1'b0),.gemm_done(1'b0),.arg_done(1'b0),.dma_active(1'b0),.gemm_active(1'b0),.arg_result(4'b0));
endmodule
