`timescale 1ns / 1ps
`default_nettype none

// Control-only testbench. Data generation and simulator invocation are separate.
module tb_control_unit;
    localparam integer TB_CLOCK_PERIOD_NS = 10;
    localparam integer TB_RESET_CYCLES = 3;
    localparam integer TB_START_WAIT_CYCLES = 1;
    localparam bit TB_INITIAL_CLK = 1'b0;

    logic clk = TB_INITIAL_CLK;
    logic rst_n = 1'b0;
    wire start;
    wire [31:0] argmax_data;
    wire busy;
    wire done;
    wire [3:0] prediction;
    wire buf_sel;
    wire [7:0] in_addr;
    wire in_en;
    wire [6:0] out_addr;
    wire out_we;
    wire [14:0] weight_addr;
    wire weight_en;
    wire [7:0] bias_addr;
    wire bias_en;
    wire mac_input_valid;
    wire bias_load;
    wire signed [5:0] bias_shift;
    wire result_load;
    wire relu_en;
    wire [4:0] output_shift;

    always #(TB_CLOCK_PERIOD_NS / 2.0) clk = ~clk;

    initial begin
        $timeformat(-9, 0, " ns", 10);
        repeat (TB_RESET_CYCLES) @(negedge clk);
        // NBA release keeps this edge distinct from the first tester edge.
        rst_n <= 1'b1;
    end

    control_unit u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .argmax_data(argmax_data),
        .busy(busy),
        .done(done),
        .prediction(prediction),
        .buf_sel(buf_sel),
        .in_addr(in_addr),
        .in_en(in_en),
        .out_addr(out_addr),
        .out_we(out_we),
        .weight_addr(weight_addr),
        .weight_en(weight_en),
        .bias_addr(bias_addr),
        .bias_en(bias_en),
        .mac_input_valid(mac_input_valid),
        .bias_load(bias_load),
        .bias_shift(bias_shift),
        .result_load(result_load),
        .relu_en(relu_en),
        .output_shift(output_shift)
    );

    control_unit_tester #(
        .TB_CLOCK_PERIOD_NS(TB_CLOCK_PERIOD_NS),
        .TB_RESET_CYCLES(TB_RESET_CYCLES),
        .TB_START_WAIT_CYCLES(TB_START_WAIT_CYCLES),
        .TB_INITIAL_CLK(TB_INITIAL_CLK)
    ) u_tester (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .argmax_data(argmax_data),
        .busy(busy),
        .done(done),
        .prediction(prediction),
        .buf_sel(buf_sel),
        .in_addr(in_addr),
        .in_en(in_en),
        .out_addr(out_addr),
        .out_we(out_we),
        .weight_addr(weight_addr),
        .weight_en(weight_en),
        .bias_addr(bias_addr),
        .bias_en(bias_en),
        .mac_input_valid(mac_input_valid),
        .bias_load(bias_load),
        .bias_shift(bias_shift),
        .result_load(result_load),
        .relu_en(relu_en),
        .output_shift(output_shift)
    );

    initial begin
        // Includes reset, waiting, every vector and the 100-cycle margin.
        repeat (u_tester.TIMEOUT_CYCLES) @(negedge clk);
        u_tester.abort_test("timeout");
    end

    // No waveform logging: simulation results are the tester's text summary.
endmodule
`default_nettype wire
