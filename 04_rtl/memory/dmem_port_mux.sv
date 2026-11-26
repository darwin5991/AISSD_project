module dmem_port_mux(input logic dma_owner,
    input logic scalar_en,scalar_we,input logic [31:0] scalar_addr,scalar_wdata,
    input logic dma_en,dma_we,input logic [31:0] dma_addr,dma_wdata,
    output logic en,we,output logic [31:0] addr,wdata);
assign en=dma_owner?dma_en:scalar_en;
assign we=dma_owner?dma_we:scalar_we;
assign addr=dma_owner?dma_addr:scalar_addr;
assign wdata=dma_owner?dma_wdata:scalar_wdata;
endmodule
