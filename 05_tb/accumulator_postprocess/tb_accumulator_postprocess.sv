`timescale 1ns / 1ps
`default_nettype none


// Standalone production hierarchy; inputs are precomputed Python vectors.
module tb_accumulator_postprocess;
    localparam integer TB_CLOCK_PERIOD_NS = 10;
    localparam integer TB_RESET_CYCLES = 3;
    localparam integer TB_START_WAIT_CYCLES = 1;
    localparam bit TB_INITIAL_CLK = 1'b0;
    logic clk = TB_INITIAL_CLK;
    logic rst_n = 1'b0;

    wire bias_load;
    wire signed [7:0] bias_data [0:3];
    wire signed [5:0] bias_shift;
    wire signed [31:0] partial_sum [0:3];
    wire psum_valid;
    wire result_load;
    wire relu_en;
    wire [4:0] output_shift;
    wire [31:0] output_data;

    always #(TB_CLOCK_PERIOD_NS / 2.0) clk = ~clk;
    initial begin
        $timeformat(-9, 0, " ns", 10);
        repeat (TB_RESET_CYCLES) @(negedge clk);
        rst_n <= 1'b1;
    end

    accumulator_postprocess u_dut (
        .clk(clk), .rst_n(rst_n),
        .bias_load(bias_load), .bias_data(bias_data), .bias_shift(bias_shift),
        .partial_sum(partial_sum), .psum_valid(psum_valid),
        .result_load(result_load), .relu_en(relu_en), .output_shift(output_shift),
        .output_data(output_data)
    );

    accumulator_postprocess_tester #(
        .TB_CLOCK_PERIOD_NS(TB_CLOCK_PERIOD_NS), .TB_RESET_CYCLES(TB_RESET_CYCLES),
        .TB_START_WAIT_CYCLES(TB_START_WAIT_CYCLES), .TB_INITIAL_CLK(TB_INITIAL_CLK)
    ) u_tester (
        .clk(clk), .rst_n(rst_n),
        .bias_load(bias_load), .bias_data(bias_data), .bias_shift(bias_shift),
        .partial_sum(partial_sum), .psum_valid(psum_valid),
        .result_load(result_load), .relu_en(relu_en), .output_shift(output_shift),
        .output_data(output_data)
    );

    initial begin
        repeat (u_tester.TIMEOUT_CYCLES) @(negedge clk);
        u_tester.abort_test("timeout");
    end

    // No internal DUT probes, behavioral replacements or waveform capture.
endmodule
`default_nettype wire
