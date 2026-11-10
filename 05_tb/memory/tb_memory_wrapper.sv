`timescale 1ns / 1ps
`default_nettype none

// Standalone real Memory RTL; the tester drives every access from Python vectors.
module tb_memory_wrapper;
    localparam integer TB_CLOCK_PERIOD_NS = 10;
    localparam integer TB_RESET_CYCLES = 3;
    localparam integer TB_START_WAIT_CYCLES = 1;
    localparam bit TB_INITIAL_CLK = 1'b0;
    logic clk = TB_INITIAL_CLK;
    logic rst_n = 1'b0;

    wire tb_en, tb_we;
    wire [19:0] tb_addr;
    wire [31:0] tb_wdata, tb_rdata;
    wire busy, buf_sel;
    wire [7:0] in_addr;
    wire in_en;
    wire [31:0] in_data;
    wire [6:0] out_addr;
    wire out_we;
    wire [31:0] out_data;
    wire [14:0] weight_addr;
    wire weight_en;
    wire [31:0] weight_data [0:3];
    wire [7:0] bias_addr;
    wire bias_en;
    wire [31:0] bias_data;

    always #(TB_CLOCK_PERIOD_NS / 2.0) clk = ~clk;
    initial begin
        $timeformat(-9, 0, " ns", 10);
        repeat (TB_RESET_CYCLES) @(negedge clk);
        rst_n <= 1'b1;
    end

    memory_wrapper u_dut (
        .clk(clk), .rst_n(rst_n),
        .tb_en(tb_en), .tb_we(tb_we), .tb_addr(tb_addr),
        .tb_wdata(tb_wdata), .tb_rdata(tb_rdata),
        .busy(busy), .buf_sel(buf_sel),
        .in_addr(in_addr), .in_en(in_en), .in_data(in_data),
        .out_addr(out_addr), .out_we(out_we), .out_data(out_data),
        .weight_addr(weight_addr), .weight_en(weight_en), .weight_data(weight_data),
        .bias_addr(bias_addr), .bias_en(bias_en), .bias_data(bias_data)
    );

    memory_wrapper_tester #(
        .TB_CLOCK_PERIOD_NS(TB_CLOCK_PERIOD_NS), .TB_RESET_CYCLES(TB_RESET_CYCLES),
        .TB_START_WAIT_CYCLES(TB_START_WAIT_CYCLES), .TB_INITIAL_CLK(TB_INITIAL_CLK)
    ) u_tester (
        .clk(clk), .rst_n(rst_n),
        .tb_en(tb_en), .tb_we(tb_we), .tb_addr(tb_addr),
        .tb_wdata(tb_wdata), .tb_rdata(tb_rdata),
        .busy(busy), .buf_sel(buf_sel),
        .in_addr(in_addr), .in_en(in_en), .in_data(in_data),
        .out_addr(out_addr), .out_we(out_we), .out_data(out_data),
        .weight_addr(weight_addr), .weight_en(weight_en), .weight_data(weight_data),
        .bias_addr(bias_addr), .bias_en(bias_en), .bias_data(bias_data)
    );

    initial begin
        repeat (u_tester.TIMEOUT_CYCLES) @(negedge clk);
        u_tester.abort_test("timeout");
    end

    // Port-only access. No direct BRAM initialization/probing or waveform logging.
endmodule
`default_nettype wire
