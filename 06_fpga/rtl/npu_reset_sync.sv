// FPGA boundary reset only. Existing NPU/SRAM asynchronous reset contracts are unchanged.
module npu_reset_sync(
    input logic clk,
    input logic async_rst_n,
    output wire core_rst_n
);
    (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) logic [1:0] reset_pipe;
    always_ff @(posedge clk or negedge async_rst_n) begin
        if(!async_rst_n)reset_pipe<=2'b00;
        else reset_pipe<={reset_pipe[0],1'b1};
    end
    assign core_rst_n=reset_pipe[1];
endmodule
