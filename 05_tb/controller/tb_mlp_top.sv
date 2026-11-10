`timescale 1ns / 1ps
`default_nettype none

// Real Top + Control + Memory + MAC + accumulator/postprocess; no behavioral replacements.
module tb_mlp_top;
    localparam integer TB_CLOCK_PERIOD_NS = 10;
    localparam integer TB_RESET_CYCLES = 3;
    localparam integer TB_START_WAIT_CYCLES = 1;
    localparam bit TB_INITIAL_CLK = 1'b0;
    logic clk = TB_INITIAL_CLK;
    logic rst_n = 1'b0;
    wire start;
    wire tb_en;
    wire tb_we;
    wire [19:0] tb_addr;
    wire [31:0] tb_wdata;
    wire busy;
    wire done;
    wire [3:0] prediction;
    wire [31:0] tb_rdata;

    always #(TB_CLOCK_PERIOD_NS / 2.0) clk = ~clk;
    initial begin
        $timeformat(-9, 0, " ns", 10);
        repeat (TB_RESET_CYCLES) @(negedge clk);
        rst_n <= 1'b1;
    end

    mlp_top u_dut (
        .clk(clk), .rst_n(rst_n),
        .start(start),
        .tb_en(tb_en),
        .tb_we(tb_we),
        .tb_addr(tb_addr),
        .tb_wdata(tb_wdata),
        .busy(busy),
        .done(done),
        .prediction(prediction),
        .tb_rdata(tb_rdata)
    );

    mlp_top_tester #(
        .TB_CLOCK_PERIOD_NS(TB_CLOCK_PERIOD_NS), .TB_RESET_CYCLES(TB_RESET_CYCLES),
        .TB_START_WAIT_CYCLES(TB_START_WAIT_CYCLES), .TB_INITIAL_CLK(TB_INITIAL_CLK)
    ) u_tester (
        .clk(clk), .rst_n(rst_n),
        .start(start),
        .tb_en(tb_en),
        .tb_we(tb_we),
        .tb_addr(tb_addr),
        .tb_wdata(tb_wdata),
        .busy(busy),
        .done(done),
        .prediction(prediction),
        .tb_rdata(tb_rdata),
        .probe_out_we(u_dut.out_we),
        .probe_out_addr(u_dut.out_addr),
        .probe_buf_sel(u_dut.buf_sel),
        .probe_out_data(u_dut.out_word)
    );

    initial begin
        repeat (u_tester.TIMEOUT_CYCLES) @(negedge clk);
        u_tester.abort_test("timeout");
    end

    // Probes observe only write signals. No direct storage access or FSM probing.
    // No waveform logging.
endmodule
`default_nettype wire
