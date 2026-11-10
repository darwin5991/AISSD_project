`timescale 1ns / 1ps
`default_nettype none

// Read-only scoreboard: all stimulus, expectations and masks come from Python.
// A vector is checked BEFORE its input is driven at the same falling edge.
module control_unit_tester #(
    parameter integer TB_CLOCK_PERIOD_NS = 10,
    parameter integer TB_RESET_CYCLES = 3,
    parameter integer TB_START_WAIT_CYCLES = 1,
    parameter bit TB_INITIAL_CLK = 1'b0
) (
    input wire clk,
    input wire rst_n,
    output logic start,
    output logic [31:0] argmax_data,
    input wire busy,
    input wire done,
    input wire [3:0] prediction,
    input wire buf_sel,
    input wire [7:0] in_addr,
    input wire in_en,
    input wire [6:0] out_addr,
    input wire out_we,
    input wire [14:0] weight_addr,
    input wire weight_en,
    input wire [7:0] bias_addr,
    input wire bias_en,
    input wire mac_input_valid,
    input wire bias_load,
    input wire signed [5:0] bias_shift,
    input wire result_load,
    input wire relu_en,
    input wire [4:0] output_shift
);
    `include "control_unit_tb_data.vh"

    integer vector_index = -1;
    integer vectors_checked = 0;
    integer checks = 0;
    integer masked = 0;
    integer errors = 0;
    integer signal_checks [0:17];
    bit finished = 1'b0;

    task automatic summary(input string result);
        $display("[SUMMARY] module=control_unit result=%s vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                 result, vectors_checked, NVEC, checks, masked, errors, $time);
    endtask

    // Called by both the checker and the TB's global watchdog.
    task automatic abort_test(input string reason);
        errors = errors + 1;
        finished = 1'b1;
        $display("[FAIL] module=control_unit vector=%0d time=%0t reason=%s",
                 vector_index, $time, reason);
        summary("FAIL");
        $fatal(1, "control_unit verification failed");
    endtask

    task automatic validate_data(
        input string signal_name,
        input logic [31:0] expected,
        input logic mask
    );
        if ((mask !== 1'b0) && (mask !== 1'b1))
            abort_test($sformatf("invalid mask: %s at vector %0d", signal_name, vector_index));
        if ((mask === 1'b1) && ((^expected) === 1'bx))
            abort_test($sformatf("undefined expected value: %s at vector %0d", signal_name, vector_index));
    endtask

    task automatic compare_signal(
        input integer signal_index,
        input string signal_name,
        input integer width,
        input logic [31:0] actual,
        input logic [31:0] expected,
        input logic mask
    );
        if (mask === 1'b1) begin
            checks = checks + 1;
            signal_checks[signal_index] = signal_checks[signal_index] + 1;
            // Case inequality also rejects X/Z at every compared output.
            if (actual !== expected) begin
                $display("[MISMATCH] module=control_unit vector=%0d cycle=%0d time=%0t signal=%s width=%0d actual=0x%0h expected=0x%0h",
                         vector_index, FIRST_VECTOR_CYCLE + vector_index, $time,
                         signal_name, width, actual, expected);
                abort_test("output mismatch");
            end
        end else begin
            masked = masked + 1;
        end
    endtask

    task automatic validate_configuration;
        if ((CONTROL_DATA_FORMAT_VERSION !== 1) || (SAMPLE_ID !== 0) ||
            (NVEC !== 29478) || (EXPECTED_PREDICTION < 0) || (EXPECTED_PREDICTION > 9))
            abort_test("unsupported header format, sample or vector count");

        if ((TIME_UNIT_NS !== 1) || (TIME_PRECISION_PS !== 1) ||
            (TB_CLOCK_PERIOD_NS !== 10) || (TB_RESET_CYCLES !== 3) ||
            (TB_START_WAIT_CYCLES !== 1) || (TB_INITIAL_CLK !== 1'b0) ||
            (CLOCK_PERIOD_NS !== TB_CLOCK_PERIOD_NS) ||
            (RESET_CYCLES !== TB_RESET_CYCLES) ||
            (START_WAIT_CYCLES !== TB_START_WAIT_CYCLES) ||
            (INITIAL_CLK !== TB_INITIAL_CLK) ||
            (FIRST_VECTOR_CYCLE !== RESET_CYCLES + START_WAIT_CYCLES) ||
            (EXPECTED_CYCLES !== FIRST_VECTOR_CYCLE + NVEC - 1) ||
            (TIMEOUT_CYCLES !== EXPECTED_CYCLES + 100))
            abort_test("TB/header timing configuration mismatch");

        if ((FC1_N !== 196) || (FC1_GROUPS !== 128) ||
            (FC1_WEIGHT_BASE !== 0) || (FC1_BIAS_BASE !== 0) ||
            (FC1_BIAS_SHIFT !== 3) || (FC1_OUTPUT_SHIFT !== 10) || (FC1_RELU !== 1) ||
            (FC2_N !== 128) || (FC2_GROUPS !== 32) ||
            (FC2_WEIGHT_BASE !== 25088) || (FC2_BIAS_BASE !== 128) ||
            (FC2_BIAS_SHIFT !== 1) || (FC2_OUTPUT_SHIFT !== 7) || (FC2_RELU !== 1) ||
            (FC3_N !== 32) || (FC3_GROUPS !== 3) ||
            (FC3_WEIGHT_BASE !== 29184) || (FC3_BIAS_BASE !== 160) ||
            (FC3_BIAS_SHIFT !== 2) || (FC3_OUTPUT_SHIFT !== 7) || (FC3_RELU !== 0))
            abort_test("header layer configuration mismatch");

        if (($bits(tb_start[0]) != $bits(start)) ||
            ($bits(tb_argmax_data[0]) != $bits(argmax_data)) ||
            ($bits(tb_exp_busy[0]) != $bits(busy)) ||
            ($bits(tb_mask_busy[0]) != 1) ||
            ($bits(tb_exp_done[0]) != $bits(done)) ||
            ($bits(tb_mask_done[0]) != 1) ||
            ($bits(tb_exp_prediction[0]) != $bits(prediction)) ||
            ($bits(tb_mask_prediction[0]) != 1) ||
            ($bits(tb_exp_buf_sel[0]) != $bits(buf_sel)) ||
            ($bits(tb_mask_buf_sel[0]) != 1) ||
            ($bits(tb_exp_in_addr[0]) != $bits(in_addr)) ||
            ($bits(tb_mask_in_addr[0]) != 1) ||
            ($bits(tb_exp_in_en[0]) != $bits(in_en)) ||
            ($bits(tb_mask_in_en[0]) != 1) ||
            ($bits(tb_exp_out_addr[0]) != $bits(out_addr)) ||
            ($bits(tb_mask_out_addr[0]) != 1) ||
            ($bits(tb_exp_out_we[0]) != $bits(out_we)) ||
            ($bits(tb_mask_out_we[0]) != 1) ||
            ($bits(tb_exp_weight_addr[0]) != $bits(weight_addr)) ||
            ($bits(tb_mask_weight_addr[0]) != 1) ||
            ($bits(tb_exp_weight_en[0]) != $bits(weight_en)) ||
            ($bits(tb_mask_weight_en[0]) != 1) ||
            ($bits(tb_exp_bias_addr[0]) != $bits(bias_addr)) ||
            ($bits(tb_mask_bias_addr[0]) != 1) ||
            ($bits(tb_exp_bias_en[0]) != $bits(bias_en)) ||
            ($bits(tb_mask_bias_en[0]) != 1) ||
            ($bits(tb_exp_mac_input_valid[0]) != $bits(mac_input_valid)) ||
            ($bits(tb_mask_mac_input_valid[0]) != 1) ||
            ($bits(tb_exp_bias_load[0]) != $bits(bias_load)) ||
            ($bits(tb_mask_bias_load[0]) != 1) ||
            ($bits(tb_exp_bias_shift[0]) != $bits(bias_shift)) ||
            ($bits(tb_mask_bias_shift[0]) != 1) ||
            ($bits(tb_exp_result_load[0]) != $bits(result_load)) ||
            ($bits(tb_mask_result_load[0]) != 1) ||
            ($bits(tb_exp_relu_en[0]) != $bits(relu_en)) ||
            ($bits(tb_mask_relu_en[0]) != 1) ||
            ($bits(tb_exp_output_shift[0]) != $bits(output_shift)) ||
            ($bits(tb_mask_output_shift[0]) != 1))
            abort_test("header/port width mismatch");
    endtask

    initial begin : run_test
        start = 1'b0;
        argmax_data = 32'b0;
        for (integer s = 0; s < 18; s = s + 1)
            signal_checks[s] = 0;

        // Header initializers have completed by reset release (30 ns).
        @(posedge rst_n);
        validate_configuration();
        for (vector_index = 0; vector_index < NVEC; vector_index = vector_index + 1) begin
            if (((^tb_start[vector_index]) === 1'bx) ||
                ((^tb_argmax_data[vector_index]) === 1'bx))
                abort_test("undefined stimulus");
            validate_data("busy", tb_exp_busy[vector_index], tb_mask_busy[vector_index]);
            validate_data("done", tb_exp_done[vector_index], tb_mask_done[vector_index]);
            validate_data("prediction", tb_exp_prediction[vector_index], tb_mask_prediction[vector_index]);
            validate_data("buf_sel", tb_exp_buf_sel[vector_index], tb_mask_buf_sel[vector_index]);
            validate_data("in_addr", tb_exp_in_addr[vector_index], tb_mask_in_addr[vector_index]);
            validate_data("in_en", tb_exp_in_en[vector_index], tb_mask_in_en[vector_index]);
            validate_data("out_addr", tb_exp_out_addr[vector_index], tb_mask_out_addr[vector_index]);
            validate_data("out_we", tb_exp_out_we[vector_index], tb_mask_out_we[vector_index]);
            validate_data("weight_addr", tb_exp_weight_addr[vector_index], tb_mask_weight_addr[vector_index]);
            validate_data("weight_en", tb_exp_weight_en[vector_index], tb_mask_weight_en[vector_index]);
            validate_data("bias_addr", tb_exp_bias_addr[vector_index], tb_mask_bias_addr[vector_index]);
            validate_data("bias_en", tb_exp_bias_en[vector_index], tb_mask_bias_en[vector_index]);
            validate_data("mac_input_valid", tb_exp_mac_input_valid[vector_index], tb_mask_mac_input_valid[vector_index]);
            validate_data("bias_load", tb_exp_bias_load[vector_index], tb_mask_bias_load[vector_index]);
            validate_data("bias_shift", tb_exp_bias_shift[vector_index], tb_mask_bias_shift[vector_index]);
            validate_data("result_load", tb_exp_result_load[vector_index], tb_mask_result_load[vector_index]);
            validate_data("relu_en", tb_exp_relu_en[vector_index], tb_mask_relu_en[vector_index]);
            validate_data("output_shift", tb_exp_output_shift[vector_index], tb_mask_output_shift[vector_index]);
        end
        vector_index = -1;
        $display("[INFO] module=control_unit sample=%0d vectors=%0d expected_cycles=%0d timeout_cycles=%0d prediction=%0d",
                 SAMPLE_ID, NVEC, EXPECTED_CYCLES, TIMEOUT_CYCLES, EXPECTED_PREDICTION);

        // The first edge is 40 ns: one full cycle after reset release.
        repeat (START_WAIT_CYCLES) @(negedge clk);
        if ($time != FIRST_VECTOR_CYCLE * CLOCK_PERIOD_NS)
            abort_test("first vector is not aligned with the header schedule");

        for (vector_index = 0; vector_index < NVEC; vector_index = vector_index + 1) begin
            if (rst_n !== 1'b1)
                abort_test("unexpected reset during the normal inference scenario");

            compare_signal(0, "busy", 1, busy, tb_exp_busy[vector_index], tb_mask_busy[vector_index]);
            compare_signal(1, "done", 1, done, tb_exp_done[vector_index], tb_mask_done[vector_index]);
            compare_signal(2, "prediction", 4, prediction, tb_exp_prediction[vector_index], tb_mask_prediction[vector_index]);
            compare_signal(3, "buf_sel", 1, buf_sel, tb_exp_buf_sel[vector_index], tb_mask_buf_sel[vector_index]);
            compare_signal(4, "in_addr", 8, in_addr, tb_exp_in_addr[vector_index], tb_mask_in_addr[vector_index]);
            compare_signal(5, "in_en", 1, in_en, tb_exp_in_en[vector_index], tb_mask_in_en[vector_index]);
            compare_signal(6, "out_addr", 7, out_addr, tb_exp_out_addr[vector_index], tb_mask_out_addr[vector_index]);
            compare_signal(7, "out_we", 1, out_we, tb_exp_out_we[vector_index], tb_mask_out_we[vector_index]);
            compare_signal(8, "weight_addr", 15, weight_addr, tb_exp_weight_addr[vector_index], tb_mask_weight_addr[vector_index]);
            compare_signal(9, "weight_en", 1, weight_en, tb_exp_weight_en[vector_index], tb_mask_weight_en[vector_index]);
            compare_signal(10, "bias_addr", 8, bias_addr, tb_exp_bias_addr[vector_index], tb_mask_bias_addr[vector_index]);
            compare_signal(11, "bias_en", 1, bias_en, tb_exp_bias_en[vector_index], tb_mask_bias_en[vector_index]);
            compare_signal(12, "mac_input_valid", 1, mac_input_valid, tb_exp_mac_input_valid[vector_index], tb_mask_mac_input_valid[vector_index]);
            compare_signal(13, "bias_load", 1, bias_load, tb_exp_bias_load[vector_index], tb_mask_bias_load[vector_index]);
            compare_signal(14, "bias_shift", 6, bias_shift, tb_exp_bias_shift[vector_index], tb_mask_bias_shift[vector_index]);
            compare_signal(15, "result_load", 1, result_load, tb_exp_result_load[vector_index], tb_mask_result_load[vector_index]);
            compare_signal(16, "relu_en", 1, relu_en, tb_exp_relu_en[vector_index], tb_mask_relu_en[vector_index]);
            compare_signal(17, "output_shift", 5, output_shift, tb_exp_output_shift[vector_index], tb_mask_output_shift[vector_index]);
            vectors_checked = vectors_checked + 1;

            // Only reach stimulus after every output comparison has succeeded.
            start = tb_start[vector_index];
            argmax_data = tb_argmax_data[vector_index];
            if (vector_index < NVEC - 1)
                @(negedge clk);
        end

        if ((vectors_checked != NVEC) || (checks == 0) || (errors != 0))
            abort_test("incomplete verification");
        for (integer s = 0; s < 18; s = s + 1)
            if (signal_checks[s] == 0)
                abort_test($sformatf("output %0d was never compared", s));

        finished = 1'b1;
        summary("PASS");
        $finish;
    end

    // An external early $finish must never look like a successful test.
    final begin
        if (!finished) begin
            $display("[FAIL] module=control_unit vector=%0d time=%0t reason=simulation ended before verification completed",
                     vector_index, $time);
            $display("[SUMMARY] module=control_unit result=FAIL vectors=%0d/%0d checks=%0d masked=%0d errors=%0d",
                     vectors_checked, NVEC, checks, masked, errors + 1);
        end
    end
endmodule
`default_nettype wire
