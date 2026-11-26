// Dedicated argmax-only external-memory testbench; no DUT hierarchy access.
`timescale 1ns/1ps
module tb_npu_argmax_progress;
logic clk=0,rst_n=0,start=0,busy,done,imem_en,dmem_en,dmem_we;
logic [31:0] imem_addr,imem_rdata,dmem_addr,dmem_wdata,dmem_rdata;
integer limit,cycles=0,result_base,result_words,completed=0,progress_fd;
string output_name,progress_name;
always #5 clk=~clk;
npu_top dut(.*);
external_imem imem(.clk(clk),.en(imem_en),.addr(imem_addr),.rdata(imem_rdata));
external_dmem dmem(.clk(clk),.en(dmem_en),.we(dmem_we),.addr(dmem_addr),.wdata(dmem_wdata),.rdata(dmem_rdata));
task record_progress;
    begin
        // Open/close makes completed external writes visible during run-all.
        progress_fd=$fopen(progress_name,"a");
        if(!progress_fd) $fatal(1,"progress open");
        $fdisplay(progress_fd,"completed=%0d total=%0d",completed,result_words);
        $fclose(progress_fd);
        $display("NPU_PROGRESS completed=%0d total=%0d",completed,result_words);
    end
endtask
initial begin
    if(!$value$plusargs("LIMIT=%d",limit) ||
       !$value$plusargs("DUMP_BASE=%d",result_base) ||
       !$value$plusargs("DUMP_WORDS=%d",result_words) ||
       !$value$plusargs("OUTPUT=%s",output_name)) $fatal(1,"progress TB args");
    progress_name={output_name,".progress"};
    progress_fd=$fopen(progress_name,"w");
    if(!progress_fd) $fatal(1,"progress create");
    $fclose(progress_fd);
    record_progress();
    repeat(4) @(negedge clk); rst_n=1;
    @(negedge clk);start=1;@(negedge clk);start=0;
    wait(done); @(negedge clk);
    if(busy || completed!=result_words) $fatal(1,"completion/count");
    dmem.dump_results();
    @(negedge clk); if(done || busy || imem_en || dmem_en) $fatal(1,"halt controls");
    $display("NPU_EXTERNAL_PASS"); $finish;
end
always @(posedge clk) begin
    cycles<=cycles+1;
    if(cycles>limit) $fatal(1,"watchdog");
    if(dmem_en && dmem_we) begin
        // Observe only external writes. This program writes ARGMAX records only.
        if(completed>=result_words || dmem_addr!==result_base+completed*4)
            $fatal(1,"unexpected result address/order");
        completed=completed+1;
        if(completed%25==0 || completed==result_words) record_progress();
    end
end
endmodule
