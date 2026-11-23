// Count rising edges of qualified LOAD/GEMM activity, never generic busy.
module perf_timer (
    input logic clk, rst_n,
    input logic timer_start, timer_stop,
    input logic load_active, gemm_active,
    output logic [31:0] count,
    output logic overflow,
    output logic armed
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 32'd0;
            overflow <= 1'b0;
            armed <= 1'b0;
        end else if (timer_start) begin
            count <= 32'd0;
            overflow <= 1'b0;
            armed <= 1'b1;
        end else if (timer_stop) begin
            armed <= 1'b0;
        end else if (armed && (load_active || gemm_active)) begin
            count <= count + 32'd1;
            if (count == 32'hffff_ffff)
                overflow <= 1'b1;
        end
    end
endmodule
