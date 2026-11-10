`timescale 1ns / 1ps
`default_nettype none

// Pure vector player/scoreboard. Python supplies all partial sums and valid values.
module mac_array_tester #(
    parameter integer TB_CLOCK_PERIOD_NS = 10,
    parameter integer TB_RESET_CYCLES = 3,
    parameter integer TB_START_WAIT_CYCLES = 1,
    parameter bit TB_INITIAL_CLK = 1'b0
) (
    input wire clk, rst_n,
    output logic input_valid,
    output logic signed [7:0] input_data [0:3],
    output logic signed [7:0] weight_data [0:3][0:3],
    input wire signed [31:0] partial_sum [0:3],
    input wire psum_valid
);
    `include "mac_array_tb_data.vh"

    localparam integer SIGNAL_COUNT = 5;
    integer vector_index = -1;
    integer vectors_checked = 0;
    integer checks = 0, masked = 0, errors = 0;
    integer planned_checks [0:SIGNAL_COUNT-1];
    integer signal_checks [0:SIGNAL_COUNT-1];
    integer planned_valid_inputs = 0, planned_valid_outputs = 0;
    integer valid_inputs_driven = 0, valid_outputs_checked = 0;
    bit finished = 1'b0;

    task automatic summary(input string result);
        $display("[SUMMARY] module=mac_array result=%s vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                 result, vectors_checked, NVEC, checks, masked, errors, $time);
    endtask

    task automatic abort_test(input string reason);
        errors++;
        finished = 1'b1;
        $display("[FAIL] module=mac_array vector=%0d time=%0t reason=%s", vector_index, $time, reason);
        summary("FAIL");
        $fatal(1, "MAC array verification failed");
    endtask

    task automatic validate_data(input integer index, input string signal_name,
                                 input logic [31:0] expected, input logic mask);
        // Every MAC output is defined in this scenario, even when psum_valid=0.
        if (mask !== 1'b1)
            abort_test($sformatf("defined output has an invalid/excluding mask: %s", signal_name));
        if ((^expected) === 1'bx)
            abort_test($sformatf("undefined expected value: %s", signal_name));
        planned_checks[index]++;
    endtask

    task automatic compare_signal(input integer index, input string signal_name,
                                  input integer width, input logic [31:0] actual,
                                  input logic [31:0] expected, input logic mask);
        if (mask !== 1'b1)
            abort_test($sformatf("defined output excluded during comparison: %s", signal_name));
        checks++;
        signal_checks[index]++;
        if (actual !== expected) begin
            $display("[MISMATCH] module=mac_array vector=%0d cycle=%0d time=%0t signal=%s width=%0d actual=0x%08h expected=0x%08h actual_signed=%0d expected_signed=%0d",
                     vector_index, FIRST_VECTOR_CYCLE + vector_index, $time,
                     signal_name, width, actual, expected, $signed(actual), $signed(expected));
            abort_test("output mismatch");
        end
    endtask

    task automatic validate_configuration;
        if ((MAC_DATA_FORMAT_VERSION !== 1) || (SAMPLE_ID !== 0) ||
            (OUTPUT_COUNT !== SIGNAL_COUNT) || (NVEC !== 265021) ||
            (TRACE_VECTORS !== 265018) || (PIPELINE_DEPTH !== 3) ||
            (INIT_WORDS !== 117607) || (INITIAL_READ_BEGIN !== INIT_WORDS) ||
            (CORE_BEGIN !== 2*INIT_WORDS+1) || (ARGMAX_READ_BEGIN !== CORE_BEGIN+29463) ||
            (FINAL_READ_BEGIN !== CORE_BEGIN+29478) || (FINAL_WORDS !== 324) ||
            (TRACE_VECTORS !== FINAL_READ_BEGIN+FINAL_WORDS+1) ||
            (DRAIN_BEGIN !== TRACE_VECTORS) || (NVEC !== TRACE_VECTORS+PIPELINE_DEPTH) ||
            (VALID_INPUTS !== 29280))
            abort_test("unsupported header format, sample or phase lengths");
        if ((TIME_UNIT_NS !== 1) || (TIME_PRECISION_PS !== 1) ||
            (TB_CLOCK_PERIOD_NS !== 10) || (TB_RESET_CYCLES !== 3) ||
            (TB_START_WAIT_CYCLES !== 1) || (TB_INITIAL_CLK !== 1'b0) ||
            (CLOCK_PERIOD_NS !== TB_CLOCK_PERIOD_NS) || (RESET_CYCLES !== TB_RESET_CYCLES) ||
            (START_WAIT_CYCLES !== TB_START_WAIT_CYCLES) || (INITIAL_CLK !== TB_INITIAL_CLK) ||
            (FIRST_VECTOR_CYCLE !== RESET_CYCLES+START_WAIT_CYCLES) ||
            (EXPECTED_CYCLES !== FIRST_VECTOR_CYCLE+NVEC-1) ||
            (TIMEOUT_CYCLES !== EXPECTED_CYCLES+100))
            abort_test("TB/header timing mismatch");
        if (($size(input_data) != 4) || ($size(weight_data, 1) != 4) ||
            ($size(weight_data, 2) != 4) || ($size(partial_sum) != 4) ||
            ($bits(tb_input_valid[0]) != $bits(input_valid)) ||
            ($bits(tb_input_data_lane0[0]) != $bits(input_data[0])) ||
            ($bits(tb_input_data_lane1[0]) != $bits(input_data[1])) ||
            ($bits(tb_input_data_lane2[0]) != $bits(input_data[2])) ||
            ($bits(tb_input_data_lane3[0]) != $bits(input_data[3])) ||
            ($bits(tb_weight_data_lane0_input0[0]) != $bits(weight_data[0][0])) ||
            ($bits(tb_weight_data_lane0_input1[0]) != $bits(weight_data[0][1])) ||
            ($bits(tb_weight_data_lane0_input2[0]) != $bits(weight_data[0][2])) ||
            ($bits(tb_weight_data_lane0_input3[0]) != $bits(weight_data[0][3])) ||
            ($bits(tb_weight_data_lane1_input0[0]) != $bits(weight_data[1][0])) ||
            ($bits(tb_weight_data_lane1_input1[0]) != $bits(weight_data[1][1])) ||
            ($bits(tb_weight_data_lane1_input2[0]) != $bits(weight_data[1][2])) ||
            ($bits(tb_weight_data_lane1_input3[0]) != $bits(weight_data[1][3])) ||
            ($bits(tb_weight_data_lane2_input0[0]) != $bits(weight_data[2][0])) ||
            ($bits(tb_weight_data_lane2_input1[0]) != $bits(weight_data[2][1])) ||
            ($bits(tb_weight_data_lane2_input2[0]) != $bits(weight_data[2][2])) ||
            ($bits(tb_weight_data_lane2_input3[0]) != $bits(weight_data[2][3])) ||
            ($bits(tb_weight_data_lane3_input0[0]) != $bits(weight_data[3][0])) ||
            ($bits(tb_weight_data_lane3_input1[0]) != $bits(weight_data[3][1])) ||
            ($bits(tb_weight_data_lane3_input2[0]) != $bits(weight_data[3][2])) ||
            ($bits(tb_weight_data_lane3_input3[0]) != $bits(weight_data[3][3])) ||
            ($bits(tb_exp_partial_sum_lane0[0]) != $bits(partial_sum[0])) ||
            ($bits(tb_exp_partial_sum_lane1[0]) != $bits(partial_sum[1])) ||
            ($bits(tb_exp_partial_sum_lane2[0]) != $bits(partial_sum[2])) ||
            ($bits(tb_exp_partial_sum_lane3[0]) != $bits(partial_sum[3])) ||
            ($bits(tb_exp_psum_valid[0]) != $bits(psum_valid)) ||
            ($bits(tb_mask_partial_sum_lane0[0]) != 1) ||
            ($bits(tb_mask_partial_sum_lane1[0]) != 1) ||
            ($bits(tb_mask_partial_sum_lane2[0]) != 1) ||
            ($bits(tb_mask_partial_sum_lane3[0]) != 1) ||
            ($bits(tb_mask_psum_valid[0]) != 1))
            abort_test("header/port width or lane dimensions mismatch");
    endtask

    task automatic validate_vector(input integer index);
        if ((^{tb_input_valid[index],
               tb_input_data_lane0[index], tb_input_data_lane1[index],
               tb_input_data_lane2[index], tb_input_data_lane3[index],
               tb_weight_data_lane0_input0[index], tb_weight_data_lane0_input1[index],
               tb_weight_data_lane0_input2[index], tb_weight_data_lane0_input3[index],
               tb_weight_data_lane1_input0[index], tb_weight_data_lane1_input1[index],
               tb_weight_data_lane1_input2[index], tb_weight_data_lane1_input3[index],
               tb_weight_data_lane2_input0[index], tb_weight_data_lane2_input1[index],
               tb_weight_data_lane2_input2[index], tb_weight_data_lane2_input3[index],
               tb_weight_data_lane3_input0[index], tb_weight_data_lane3_input1[index],
               tb_weight_data_lane3_input2[index], tb_weight_data_lane3_input3[index]}) === 1'bx)
            abort_test("undefined stimulus");
        validate_data(0, "partial_sum[0]", tb_exp_partial_sum_lane0[index], tb_mask_partial_sum_lane0[index]);
        validate_data(1, "partial_sum[1]", tb_exp_partial_sum_lane1[index], tb_mask_partial_sum_lane1[index]);
        validate_data(2, "partial_sum[2]", tb_exp_partial_sum_lane2[index], tb_mask_partial_sum_lane2[index]);
        validate_data(3, "partial_sum[3]", tb_exp_partial_sum_lane3[index], tb_mask_partial_sum_lane3[index]);
        validate_data(4, "psum_valid", tb_exp_psum_valid[index], tb_mask_psum_valid[index]);
        if (index < PIPELINE_DEPTH) begin
            if ((tb_exp_partial_sum_lane0[index] !== 32'sd0) ||
                (tb_exp_partial_sum_lane1[index] !== 32'sd0) ||
                (tb_exp_partial_sum_lane2[index] !== 32'sd0) ||
                (tb_exp_partial_sum_lane3[index] !== 32'sd0) ||
                (tb_exp_psum_valid[index] !== 1'b0))
                abort_test("invalid reset/pipeline-fill expectations");
        end
        if ((index >= DRAIN_BEGIN) && (tb_input_valid[index] !== 1'b0))
            abort_test("new valid work in pipeline drain");
        if (tb_input_valid[index] === 1'b1) planned_valid_inputs++;
        if (tb_exp_psum_valid[index] === 1'b1) planned_valid_outputs++;
    endtask

    task automatic drive_vector(input integer index);
        input_valid = tb_input_valid[index];
        input_data[0] = tb_input_data_lane0[index];
        input_data[1] = tb_input_data_lane1[index];
        input_data[2] = tb_input_data_lane2[index];
        input_data[3] = tb_input_data_lane3[index];
        weight_data[0][0] = tb_weight_data_lane0_input0[index];
        weight_data[0][1] = tb_weight_data_lane0_input1[index];
        weight_data[0][2] = tb_weight_data_lane0_input2[index];
        weight_data[0][3] = tb_weight_data_lane0_input3[index];
        weight_data[1][0] = tb_weight_data_lane1_input0[index];
        weight_data[1][1] = tb_weight_data_lane1_input1[index];
        weight_data[1][2] = tb_weight_data_lane1_input2[index];
        weight_data[1][3] = tb_weight_data_lane1_input3[index];
        weight_data[2][0] = tb_weight_data_lane2_input0[index];
        weight_data[2][1] = tb_weight_data_lane2_input1[index];
        weight_data[2][2] = tb_weight_data_lane2_input2[index];
        weight_data[2][3] = tb_weight_data_lane2_input3[index];
        weight_data[3][0] = tb_weight_data_lane3_input0[index];
        weight_data[3][1] = tb_weight_data_lane3_input1[index];
        weight_data[3][2] = tb_weight_data_lane3_input2[index];
        weight_data[3][3] = tb_weight_data_lane3_input3[index];
        if (input_valid === 1'b1) valid_inputs_driven++;
    endtask

    initial begin
        input_valid = 1'b0;
        for (integer g = 0; g < 4; g++) begin
            input_data[g] = '0;
            for (integer k = 0; k < 4; k++) weight_data[g][k] = '0;
        end
        for (integer s = 0; s < SIGNAL_COUNT; s++) begin
            planned_checks[s] = 0;
            signal_checks[s] = 0;
        end
        @(posedge rst_n);
        validate_configuration();
        for (vector_index = 0; vector_index < NVEC; vector_index++)
            validate_vector(vector_index);
        if ((planned_valid_inputs != VALID_INPUTS) || (planned_valid_outputs != VALID_INPUTS))
            abort_test("incomplete input/output valid coverage");
        vector_index = -1;
        $display("[INFO] module=mac_array scope=mac_array_standalone sample=%0d vectors=%0d outputs=%0d",
                 SAMPLE_ID, NVEC, OUTPUT_COUNT);
        $display("[INFO] trace_vectors=%0d pipeline_depth=%0d valid_inputs=%0d compare_invalid_data=1",
                 TRACE_VECTORS, PIPELINE_DEPTH, VALID_INPUTS);
        repeat (START_WAIT_CYCLES) @(negedge clk);
        if ($time != FIRST_VECTOR_CYCLE * CLOCK_PERIOD_NS)
            abort_test("first vector timing mismatch");
        for (vector_index = 0; vector_index < NVEC; vector_index++) begin
            if (rst_n !== 1'b1) abort_test("unexpected reset");
            compare_signal(0, "partial_sum[0]", 32, partial_sum[0],
                           tb_exp_partial_sum_lane0[vector_index], tb_mask_partial_sum_lane0[vector_index]);
            compare_signal(1, "partial_sum[1]", 32, partial_sum[1],
                           tb_exp_partial_sum_lane1[vector_index], tb_mask_partial_sum_lane1[vector_index]);
            compare_signal(2, "partial_sum[2]", 32, partial_sum[2],
                           tb_exp_partial_sum_lane2[vector_index], tb_mask_partial_sum_lane2[vector_index]);
            compare_signal(3, "partial_sum[3]", 32, partial_sum[3],
                           tb_exp_partial_sum_lane3[vector_index], tb_mask_partial_sum_lane3[vector_index]);
            compare_signal(4, "psum_valid", 1, psum_valid,
                           tb_exp_psum_valid[vector_index], tb_mask_psum_valid[vector_index]);
            if (psum_valid === 1'b1) valid_outputs_checked++;
            vectors_checked++;
            // Finish every output comparison before changing any MAC operand.
            drive_vector(vector_index);
            if (vector_index < NVEC-1) @(negedge clk);
        end
        if ((vectors_checked != NVEC) || (checks != SIGNAL_COUNT*NVEC) ||
            (masked != 0) || (errors != 0) || (valid_inputs_driven != VALID_INPUTS) ||
            (valid_outputs_checked != VALID_INPUTS) ||
            ($time != EXPECTED_CYCLES*CLOCK_PERIOD_NS))
            abort_test("incomplete verification or wrong final timing");
        for (integer s = 0; s < SIGNAL_COUNT; s++)
            if ((signal_checks[s] != NVEC) || (signal_checks[s] != planned_checks[s]))
                abort_test($sformatf("incomplete comparisons for output %0d", s));
        finished = 1'b1;
        summary("PASS");
        $finish;
    end

    final begin
        if (!finished) begin
            $display("[FAIL] module=mac_array vector=%0d time=%0t reason=simulation ended before verification completed",
                     vector_index, $time);
            $display("[SUMMARY] module=mac_array result=FAIL vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                     vectors_checked, NVEC, checks, masked, errors+1, $time);
        end
    end
endmodule
`default_nettype wire
