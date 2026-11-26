module perf_timer(input logic clk,rst_n,tstart,tstop,dma_active,gemm_active,
    output logic [31:0] count,output logic overflow);
logic armed;
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin count<=0; overflow<=0; armed<=0; end
    else if(tstart) begin count<=0; overflow<=0; armed<=1; end
    else begin
        if(tstop) armed<=0;
        if(armed && (dma_active || gemm_active)) begin
            count<=count+1'b1;
            if(&count) overflow<=1;
        end
    end
end
endmodule
