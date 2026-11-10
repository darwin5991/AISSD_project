`timescale 1ns / 1ps
`default_nettype none


// Vector player only: all arithmetic expectations come from Python.
module accumulator_postprocess_tester #(
    parameter integer TB_CLOCK_PERIOD_NS = 10,
    parameter integer TB_RESET_CYCLES = 3,
    parameter integer TB_START_WAIT_CYCLES = 1,
    parameter bit TB_INITIAL_CLK = 1'b0
) (
    input wire clk, rst_n,
    output logic bias_load,
    output logic signed [7:0] bias_data [0:3],
    output logic signed [5:0] bias_shift,
    output logic signed [31:0] partial_sum [0:3],
    output logic psum_valid,
    output logic result_load,
    output logic relu_en,
    output logic [4:0] output_shift,
    input wire [31:0] output_data
);
    `include "accumulator_postprocess_tb_data.vh"

    localparam integer SIGNAL_COUNT = 1;
    integer vector_index = -1;
    integer vectors_checked = 0, stimulus_vectors_driven = 0;
    integer checks = 0, masked = 0, errors = 0;
    integer planned_checks = 0;
    integer planned_bias_loads = 0, planned_sums = 0, planned_result_loads = 0;
    integer planned_overlaps = 0;
    integer bias_loads_driven = 0, sums_driven = 0, result_loads_driven = 0;
    integer overlaps_driven = 0;
    bit finished = 1'b0;

    task automatic summary(input string result);
        $display("[SUMMARY] module=accumulator_postprocess result=%s vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                 result, vectors_checked, NVEC, checks, masked, errors, $time);
    endtask

    task automatic abort_test(input string reason);
        errors++;
        finished = 1'b1;
        $display("[FAIL] module=accumulator_postprocess vector=%0d time=%0t reason=%s",
                 vector_index, $time, reason);
        summary("FAIL");
        $fatal(1, "Accumulator/postprocess verification failed");
    endtask

    task automatic validate_configuration;
        if ((ACC_DATA_FORMAT_VERSION !== 1) || (SAMPLE_ID !== 0) ||
            (OUTPUT_COUNT !== SIGNAL_COUNT) || (NVEC !== 265016) ||
            (TRACE_VECTORS !== 265015) || (RESPONSE_LATENCY !== 1) ||
            (MAC_PIPELINE_DEPTH !== 2) || (INIT_WORDS !== 117607) ||
            (INITIAL_READ_BEGIN !== INIT_WORDS) || (CORE_BEGIN !== 2*INIT_WORDS+1) ||
            (ARGMAX_READ_BEGIN !== CORE_BEGIN+29460) ||
            (ARGMAX_SETTINGS_BEGIN !== CORE_BEGIN+29459) ||
            (FINAL_READ_BEGIN !== CORE_BEGIN+29475) || (FINAL_WORDS !== 324) ||
            (TRACE_VECTORS !== FINAL_READ_BEGIN+FINAL_WORDS+1) ||
            (DRAIN_BEGIN !== TRACE_VECTORS) || (NVEC !== TRACE_VECTORS+RESPONSE_LATENCY) ||
            (BIAS_LOADS !== 163) || (VALID_SUMS !== 29280) ||
            (RESULT_LOADS !== 163) || (OVERLAPPED_LOADS !== 160))
            abort_test("unsupported header format, sample or phase lengths");
        if ((TIME_UNIT_NS !== 1) || (TIME_PRECISION_PS !== 1) ||
            (TB_CLOCK_PERIOD_NS !== 10) || (TB_RESET_CYCLES !== 3) ||
            (TB_START_WAIT_CYCLES !== 1) || (TB_INITIAL_CLK !== 1'b0) ||
            (CLOCK_PERIOD_NS !== TB_CLOCK_PERIOD_NS) || (RESET_CYCLES !== TB_RESET_CYCLES) ||
            (START_WAIT_CYCLES !== TB_START_WAIT_CYCLES) || (INITIAL_CLK !== TB_INITIAL_CLK) ||
            (FIRST_VECTOR_CYCLE !== RESET_CYCLES+START_WAIT_CYCLES) ||
            (EXPECTED_CYCLES !== 265019) || (TIMEOUT_CYCLES !== 265119) ||
            (EXPECTED_CYCLES !== FIRST_VECTOR_CYCLE+NVEC-1) ||
            (TIMEOUT_CYCLES !== EXPECTED_CYCLES+100))
            abort_test("TB/header timing mismatch");
        if (($size(bias_data) != 4) || ($size(partial_sum) != 4) ||
            ($bits(tb_bias_load[0]) != $bits(bias_load)) ||
            ($bits(tb_bias_data_lane0[0]) != $bits(bias_data[0])) ||
            ($bits(tb_bias_data_lane1[0]) != $bits(bias_data[1])) ||
            ($bits(tb_bias_data_lane2[0]) != $bits(bias_data[2])) ||
            ($bits(tb_bias_data_lane3[0]) != $bits(bias_data[3])) ||
            ($bits(tb_bias_shift[0]) != $bits(bias_shift)) ||
            ($bits(tb_partial_sum_lane0[0]) != $bits(partial_sum[0])) ||
            ($bits(tb_partial_sum_lane1[0]) != $bits(partial_sum[1])) ||
            ($bits(tb_partial_sum_lane2[0]) != $bits(partial_sum[2])) ||
            ($bits(tb_partial_sum_lane3[0]) != $bits(partial_sum[3])) ||
            ($bits(tb_psum_valid[0]) != $bits(psum_valid)) ||
            ($bits(tb_result_load[0]) != $bits(result_load)) ||
            ($bits(tb_relu_en[0]) != $bits(relu_en)) ||
            ($bits(tb_output_shift[0]) != $bits(output_shift)) ||
            ($bits(tb_exp_output_data[0]) != $bits(output_data)) ||
            ($bits(tb_mask_output_data[0]) != 1))
            abort_test("header/port width or lane dimensions mismatch");
        if (($size(tb_bias_load) != NVEC) ||
            ($size(tb_bias_data_lane0) != NVEC) || ($size(tb_bias_data_lane1) != NVEC) ||
            ($size(tb_bias_data_lane2) != NVEC) || ($size(tb_bias_data_lane3) != NVEC) ||
            ($size(tb_bias_shift) != NVEC) ||
            ($size(tb_partial_sum_lane0) != NVEC) || ($size(tb_partial_sum_lane1) != NVEC) ||
            ($size(tb_partial_sum_lane2) != NVEC) || ($size(tb_partial_sum_lane3) != NVEC) ||
            ($size(tb_psum_valid) != NVEC) || ($size(tb_result_load) != NVEC) ||
            ($size(tb_relu_en) != NVEC) || ($size(tb_output_shift) != NVEC) ||
            ($size(tb_exp_output_data) != NVEC) || ($size(tb_mask_output_data) != NVEC))
            abort_test("missing vectors or inconsistent array lengths");
    endtask

    task automatic validate_vector(input integer index);
        if ((^{tb_bias_load[index],
               tb_bias_data_lane0[index], tb_bias_data_lane1[index],
               tb_bias_data_lane2[index], tb_bias_data_lane3[index], tb_bias_shift[index],
               tb_partial_sum_lane0[index], tb_partial_sum_lane1[index],
               tb_partial_sum_lane2[index], tb_partial_sum_lane3[index],
               tb_psum_valid[index], tb_result_load[index],
               tb_relu_en[index], tb_output_shift[index]}) === 1'bx)
            abort_test("undefined stimulus");
        if (tb_mask_output_data[index] !== 1'b1)
            abort_test("defined output_data has an invalid/excluding mask");
        if ((^tb_exp_output_data[index]) === 1'bx)
            abort_test("undefined output_data expectation");
        planned_checks++;
        if ((tb_bias_load[index] === 1'b1) && (tb_psum_valid[index] === 1'b1))
            abort_test("bias load overlaps a valid partial sum");
        if ((index == 0) && (tb_exp_output_data[index] !== 32'd0))
            abort_test("invalid reset expectation");
        if ((index < CORE_BEGIN) || (index >= ARGMAX_SETTINGS_BEGIN)) begin
            if ((tb_bias_load[index] !== 1'b0) || (tb_psum_valid[index] !== 1'b0) ||
                (tb_result_load[index] !== 1'b0))
                abort_test("new accumulator work outside the inference interval");
        end
        if (index >= ARGMAX_SETTINGS_BEGIN) begin
            if ((tb_bias_shift[index] !== 6'sd0) ||
                (tb_output_shift[index] !== 5'd0) || (tb_relu_en[index] !== 1'b0))
                abort_test("ARGMAX/completed Top numeric settings mismatch");
        end
        if (index >= TRACE_VECTORS-1) begin
            if ((tb_bias_load[index] !== 1'b0) || (tb_psum_valid[index] !== 1'b0) ||
                (tb_result_load[index] !== 1'b0))
                abort_test("new work at the end of Top replay");
        end
        if (index < TRACE_VECTORS) begin
            if (tb_bias_load[index] === 1'b1) planned_bias_loads++;
            if (tb_psum_valid[index] === 1'b1) planned_sums++;
            if (tb_result_load[index] === 1'b1) planned_result_loads++;
            if ((tb_bias_load[index] === 1'b1) && (tb_result_load[index] === 1'b1))
                planned_overlaps++;
        end
    endtask

    task automatic compare_output(input integer index);
        if (tb_mask_output_data[index] !== 1'b1)
            abort_test("defined output_data excluded during comparison");
        checks++;
        if (output_data !== tb_exp_output_data[index]) begin
            $display("[MISMATCH] module=accumulator_postprocess vector=%0d cycle=%0d time=%0t signal=output_data width=32 actual=0x%08h expected=0x%08h",
                     index, FIRST_VECTOR_CYCLE + index, $time,
                     output_data, tb_exp_output_data[index]);
            for (integer lane = 0; lane < 4; lane++) begin
                if (output_data[lane*8 +: 8] !== tb_exp_output_data[index][lane*8 +: 8])
                    $display("[MISMATCH] module=accumulator_postprocess vector=%0d cycle=%0d time=%0t signal=output_data lane=%0d actual=0x%02h expected=0x%02h actual_signed=%0d expected_signed=%0d",
                             index, FIRST_VECTOR_CYCLE + index, $time, lane,
                             output_data[lane*8 +: 8], tb_exp_output_data[index][lane*8 +: 8],
                             $signed(output_data[lane*8 +: 8]),
                             $signed(tb_exp_output_data[index][lane*8 +: 8]));
            end
            abort_test("output mismatch");
        end
    endtask

    task automatic drive_vector(input integer index);
        if ((index < 0) || (index >= TRACE_VECTORS))
            abort_test("attempt to drive a comparison-only vector");
        bias_load = tb_bias_load[index];
        bias_data[0] = tb_bias_data_lane0[index];
        bias_data[1] = tb_bias_data_lane1[index];
        bias_data[2] = tb_bias_data_lane2[index];
        bias_data[3] = tb_bias_data_lane3[index];
        bias_shift = tb_bias_shift[index];
        partial_sum[0] = tb_partial_sum_lane0[index];
        partial_sum[1] = tb_partial_sum_lane1[index];
        partial_sum[2] = tb_partial_sum_lane2[index];
        partial_sum[3] = tb_partial_sum_lane3[index];
        psum_valid = tb_psum_valid[index];
        result_load = tb_result_load[index];
        relu_en = tb_relu_en[index];
        output_shift = tb_output_shift[index];
        stimulus_vectors_driven++;
        if (bias_load === 1'b1) bias_loads_driven++;
        if (psum_valid === 1'b1) sums_driven++;
        if (result_load === 1'b1) result_loads_driven++;
        if ((bias_load === 1'b1) && (result_load === 1'b1)) overlaps_driven++;
    endtask

    initial begin
        bias_load = 1'b0;
        psum_valid = 1'b0;
        result_load = 1'b0;
        // Match the pre-start FC1 LUT; both register banks reset to zero.
        bias_shift = 6'sd3;
        relu_en = 1'b1;
        output_shift = 5'd10;
        for (integer lane = 0; lane < 4; lane++) begin
            bias_data[lane] = '0;
            partial_sum[lane] = '0;
        end
        @(posedge rst_n);
        validate_configuration();
        for (vector_index = 0; vector_index < NVEC; vector_index++)
            validate_vector(vector_index);
        if ((planned_checks != NVEC) || (planned_bias_loads != BIAS_LOADS) ||
            (planned_sums != VALID_SUMS) || (planned_result_loads != RESULT_LOADS) ||
            (planned_overlaps != OVERLAPPED_LOADS))
            abort_test("incomplete planned output or input-event coverage");
        vector_index = -1;
        $display("[INFO] module=accumulator_postprocess scope=accumulator_postprocess_standalone sample=%0d vectors=%0d outputs=%0d",
                 SAMPLE_ID, NVEC, OUTPUT_COUNT);
        $display("[INFO] trace_vectors=%0d final_compare_only=1 bias_loads=%0d valid_sums=%0d result_loads=%0d overlaps=%0d",
                 TRACE_VECTORS, BIAS_LOADS, VALID_SUMS, RESULT_LOADS, OVERLAPPED_LOADS);
        repeat (START_WAIT_CYCLES) @(negedge clk);
        if ($time != FIRST_VECTOR_CYCLE * CLOCK_PERIOD_NS)
            abort_test("first vector timing mismatch");
        for (vector_index = 0; vector_index < NVEC; vector_index++) begin
            if (rst_n !== 1'b1) abort_test("unexpected reset");
            compare_output(vector_index);
            vectors_checked++;
            // Compare all output bits before changing any input. The final
            // vector only checks the response to the last Top input.
            if (vector_index < TRACE_VECTORS) drive_vector(vector_index);
            if (vector_index < NVEC-1) @(negedge clk);
        end
        if ((vectors_checked != NVEC) || (checks != NVEC) || (checks != planned_checks) ||
            (masked != 0) || (errors != 0) || (stimulus_vectors_driven != TRACE_VECTORS) ||
            (bias_loads_driven != BIAS_LOADS) || (sums_driven != VALID_SUMS) ||
            (result_loads_driven != RESULT_LOADS) || (overlaps_driven != OVERLAPPED_LOADS) ||
            ($time != EXPECTED_CYCLES*CLOCK_PERIOD_NS))
            abort_test("incomplete verification or wrong final timing");
        finished = 1'b1;
        summary("PASS");
        $finish;
    end

    final begin
        if (!finished) begin
            $display("[FAIL] module=accumulator_postprocess vector=%0d time=%0t reason=simulation ended before verification completed",
                     vector_index, $time);
            $display("[SUMMARY] module=accumulator_postprocess result=FAIL vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                     vectors_checked, NVEC, checks, masked, errors+1, $time);
        end
    end
endmodule
`default_nettype wire
