// Programmable NPU v2. External fixed-latency IMEM/DMEM; no internal TB ports.
module npu_top(input logic clk,rst_n,start,output logic busy,done,
    output logic imem_en,output logic [31:0] imem_addr,input logic [31:0] imem_rdata,
    output logic dmem_en,dmem_we,output logic [31:0] dmem_addr,dmem_wdata,input logic [31:0] dmem_rdata);
logic scalar_en,scalar_we,dma_start,dma_store,dma_done,dma_active,gemm_start,gemm_done,gemm_active,arg_start,arg_done;
logic [31:0] scalar_addr,scalar_wdata,dma_src,dma_dst,dma_len,src0,src1,dst,bias,arg_src;
logic [20:0] dim;logic [11:0] cfg;logic [3:0] arg_len,arg_result;logic [1:0] owner;
logic de,dw,se,sw;logic [31:0] da,dd,sa,sd,sr;
logic buf_sel,read_en,bias_en,mac_input_valid,bias_load,result_load,out_we,relu_en,ab,ae;
logic [7:0] in_addr,out_addr,bias_addr,aa;logic [14:0] weight_addr;
logic signed [5:0] bias_shift;logic [4:0] output_shift;
logic [31:0] in_word,out_word,bias_word,arg_word,weight_words[0:3];
logic signed [7:0] input_bytes[0:3],weight_bytes[0:3][0:3],bias_bytes[0:3];
logic signed [31:0] partial_sum[0:3];logic psum_valid;
instruction_controller u_ic(.clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
    .imem_en(imem_en),.imem_addr(imem_addr),.imem_rdata(imem_rdata),
    .scalar_en(scalar_en),.scalar_we(scalar_we),.scalar_addr(scalar_addr),.scalar_wdata(scalar_wdata),.dmem_rdata(dmem_rdata),
    .dma_start(dma_start),.dma_store(dma_store),.dma_src(dma_src),.dma_dst(dma_dst),.dma_len(dma_len),.owner(owner),
    .dma_done(dma_done),.dma_active(dma_active),.gemm_start(gemm_start),.gemm_done(gemm_done),.gemm_active(gemm_active),
    .arg_start(arg_start),.arg_done(arg_done),.arg_result(arg_result),.src0(src0),.src1(src1),.dst(dst),.bias(bias),
    .arg_src(arg_src),.dim(dim),.cfg(cfg),.arg_len(arg_len));
dma_controller u_dma(clk,rst_n,dma_start,dma_store,dma_src,dma_dst,dma_len,dma_active,dma_done,de,dw,da,dd,dmem_rdata,se,sw,sa,sd,sr);
dmem_port_mux u_dmem_mux(owner==1,scalar_en,scalar_we,scalar_addr,scalar_wdata,de,dw,da,dd,dmem_en,dmem_we,dmem_addr,dmem_wdata);
gemm_controller u_gemm(clk,rst_n,gemm_start,src0,src1,dst,bias,dim,cfg,gemm_active,gemm_done,buf_sel,read_en,bias_en,
    in_addr,out_addr,bias_addr,weight_addr,mac_input_valid,bias_load,result_load,out_we,bias_shift,output_shift,relu_en);
argmax_engine u_arg(clk,rst_n,arg_start,arg_src,arg_len,arg_done,arg_result,ab,ae,aa,arg_word);
npu_memory_wrapper u_memory(.clk(clk),.rst_n(rst_n),.owner(owner),.dma_en(se),.dma_we(sw),.dma_addr(sa),.dma_wdata(sd),.dma_rdata(sr),
    .buf_sel(buf_sel),.in_en(read_en),.out_we(out_we),.in_addr(in_addr),.out_addr(out_addr),.out_data(out_word),.in_data(in_word),
    .weight_en(read_en),.weight_addr(weight_addr),.weight_data(weight_words),.bias_en(bias_en),.bias_addr(bias_addr),.bias_data(bias_word),
    .arg_bank(ab),.arg_en(ae),.arg_addr(aa),.arg_data(arg_word));
unpack_int8x4 u_input(in_word,input_bytes);
unpack_int8x4 u_bias(bias_word,bias_bytes);
for(genvar j=0;j<4;j=j+1) begin:g_weight
    unpack_int8x4 u_unpack(weight_words[j],weight_bytes[j]);
end
mac_array u_mac(clk,rst_n,mac_input_valid,input_bytes,weight_bytes,partial_sum,psum_valid);
accumulator_postprocess u_accumulator(clk,rst_n,bias_load,bias_bytes,bias_shift,partial_sum,psum_valid,result_load,relu_en,output_shift,out_word);
endmodule
