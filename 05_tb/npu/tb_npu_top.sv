`timescale 1ns/1ps
module tb_npu_top;
logic clk=0,rst_n=0,start=0,busy,done,imem_en,dmem_en,dmem_we;
logic [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata;
integer limit,cycles=0;
always #5 clk=~clk;
`ifdef SCALAR_ONLY
scalar_harness dut(.*);
`else
npu_top dut(.*);
`endif
external_imem imem(.clk(clk),.en(imem_en),.addr(imem_addr),.rdata(imem_rdata));
external_dmem dmem(.clk(clk),.en(dmem_en),.we(dmem_we),.addr(dmem_addr),.wdata(dmem_wdata),.rdata(dmem_rdata));
initial begin
    if(!$value$plusargs("LIMIT=%d",limit)) $fatal(1,"LIMIT");
    repeat(4) @(negedge clk); rst_n=1; @(negedge clk);start=1;@(negedge clk);start=0;
    wait(done); @(negedge clk);
    if(busy) $fatal(1,"busy during done");
    dmem.dump_results();
    @(negedge clk); if(done || busy || imem_en || dmem_en) $fatal(1,"halt controls");
    start=1; repeat(3) @(negedge clk);
    if(done || busy || imem_en || dmem_en) $fatal(1,"halt restart");
    $display("NPU_EXTERNAL_PASS"); $finish;
end
always @(posedge clk) begin cycles<=cycles+1; if(cycles>limit) $fatal(1,"watchdog");end
endmodule
