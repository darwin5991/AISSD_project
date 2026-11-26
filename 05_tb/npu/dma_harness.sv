// M3 only. Final top adds actual independent GEMM/ARGMAX and unchanged datapath.
module npu_top(input logic clk,rst_n,start,output logic busy,done,imem_en,
    output logic [31:0] imem_addr,input logic [31:0] imem_rdata,
    output logic dmem_en,dmem_we,output logic [31:0] dmem_addr,dmem_wdata,input logic [31:0] dmem_rdata);
logic scalar_en,scalar_we,dma_start,dma_store,dma_done,dma_active;
logic [31:0] scalar_addr,scalar_wdata,dma_src,dma_dst,dma_len;
logic [1:0] owner;
logic de,dw,se,sw;logic [31:0] da,dd,sa,sd,sr;
instruction_controller u_ic(.clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
    .imem_en(imem_en),.imem_addr(imem_addr),.imem_rdata(imem_rdata),
    .scalar_en(scalar_en),.scalar_we(scalar_we),.scalar_addr(scalar_addr),.scalar_wdata(scalar_wdata),.dmem_rdata(dmem_rdata),
    .dma_start(dma_start),.dma_store(dma_store),.dma_src(dma_src),.dma_dst(dma_dst),.dma_len(dma_len),.owner(owner),
    .dma_done(dma_done),.dma_active(dma_active),.gemm_done(1'b0),.arg_done(1'b0),.gemm_active(1'b0),.arg_result(4'b0));
dma_controller u_dma(clk,rst_n,dma_start,dma_store,dma_src,dma_dst,dma_len,dma_active,dma_done,de,dw,da,dd,dmem_rdata,se,sw,sa,sd,sr);
dmem_port_mux u_mux(owner==1,scalar_en,scalar_we,scalar_addr,scalar_wdata,de,dw,da,dd,dmem_en,dmem_we,dmem_addr,dmem_wdata);
npu_memory_wrapper u_memory(.clk(clk),.rst_n(rst_n),.owner(owner),.dma_en(se),.dma_we(sw),.dma_addr(sa),.dma_wdata(sd),.dma_rdata(sr),
    .buf_sel(1'b0),.in_en(1'b0),.out_we(1'b0),.in_addr(8'b0),.out_addr(8'b0),.out_data(32'b0),
    .weight_en(1'b0),.weight_addr(15'b0),.bias_en(1'b0),.bias_addr(8'b0),.arg_bank(1'b0),.arg_en(1'b0),.arg_addr(8'b0));
endmodule
