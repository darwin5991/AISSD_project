`timescale 1ns / 1ps
`default_nettype none

// Standalone real MAC hierarchy; no Control/Memory or behavioral MAC model.
module tb_mac_array;
    localparam integer TB_CLOCK_PERIOD_NS = 10;
    localparam integer TB_RESET_CYCLES = 3;
    localparam integer TB_START_WAIT_CYCLES = 1;
    localparam bit TB_INITIAL_CLK = 1'b0;
    logic clk = TB_INITIAL_CLK;
    logic rst_n = 1'b0;

    wire input_valid;
    wire signed [7:0] input_data [0:3];
    wire signed [7:0] weight_data [0:3][0:3];
    wire signed [31:0] partial_sum [0:3];
    wire psum_valid;

    always #(TB_CLOCK_PERIOD_NS / 2.0) clk = ~clk;
    initial begin
        $timeformat(-9, 0, " ns", 10);
        repeat (TB_RESET_CYCLES) @(negedge clk);
        rst_n <= 1'b1;
    end

    mac_array u_dut (
        .clk(clk), .rst_n(rst_n),
        .input_valid(input_valid), .input_data(input_data), .weight_data(weight_data),
        .partial_sum(partial_sum), .psum_valid(psum_valid)
    );

    mac_array_tester #(
        .TB_CLOCK_PERIOD_NS(TB_CLOCK_PERIOD_NS), .TB_RESET_CYCLES(TB_RESET_CYCLES),
        .TB_START_WAIT_CYCLES(TB_START_WAIT_CYCLES), .TB_INITIAL_CLK(TB_INITIAL_CLK)
    ) u_tester (
        .clk(clk), .rst_n(rst_n),
        .input_valid(input_valid), .input_data(input_data), .weight_data(weight_data),
        .partial_sum(partial_sum), .psum_valid(psum_valid)
    );

    initial begin
        repeat (u_tester.TIMEOUT_CYCLES) @(negedge clk);
        u_tester.abort_test("timeout");
    end

    // Inputs/expectations come only from the pre-generated header. No probes or waves.
endmodule
`default_nettype wire
