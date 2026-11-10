`timescale 1ns / 1ps
`default_nettype none

// All data expectations are precomputed in Python; no RAM reference model here.
module memory_wrapper_tester #(
    parameter integer TB_CLOCK_PERIOD_NS = 10,
    parameter integer TB_RESET_CYCLES = 3,
    parameter integer TB_START_WAIT_CYCLES = 1,
    parameter bit TB_INITIAL_CLK = 1'b0
) (
    input wire clk, rst_n,
    output logic tb_en, tb_we,
    output logic [19:0] tb_addr,
    output logic [31:0] tb_wdata,
    input wire [31:0] tb_rdata,
    output logic busy, buf_sel,
    output logic [7:0] in_addr,
    output logic in_en,
    input wire [31:0] in_data,
    output logic [6:0] out_addr,
    output logic out_we,
    output logic [31:0] out_data,
    output logic [14:0] weight_addr,
    output logic weight_en,
    input wire [31:0] weight_data [0:3],
    output logic [7:0] bias_addr,
    output logic bias_en,
    input wire [31:0] bias_data
);
    `include "memory_wrapper_tb_data.vh"

    localparam integer SIGNAL_COUNT = 7;
    integer vector_index = -1;
    integer vectors_checked = 0;
    integer checks = 0, masked = 0, errors = 0;
    integer planned_checks [0:SIGNAL_COUNT-1];
    integer signal_checks [0:SIGNAL_COUNT-1];
    integer planned_masked = 0;
    bit finished = 1'b0;

    task automatic summary(input string result);
        $display("[SUMMARY] module=memory_wrapper result=%s vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                 result, vectors_checked, NVEC, checks, masked, errors, $time);
    endtask

    task automatic abort_test(input string reason);
        errors++;
        finished = 1'b1;
        $display("[FAIL] module=memory_wrapper vector=%0d time=%0t reason=%s",
                 vector_index, $time, reason);
        summary("FAIL");
        $fatal(1, "Memory wrapper verification failed");
    endtask

    task automatic validate_data(input integer index, input string signal_name,
                                 input logic [31:0] expected, input logic mask);
        if ((mask !== 1'b0) && (mask !== 1'b1))
            abort_test($sformatf("invalid mask: %s", signal_name));
        if (mask === 1'b1) begin
            if ((^expected) === 1'bx)
                abort_test($sformatf("undefined expected value: %s", signal_name));
            planned_checks[index]++;
        end else planned_masked++;
    endtask

    task automatic compare_signal(input integer index, input string signal_name,
                                  input logic [31:0] actual,
                                  input logic [31:0] expected, input logic mask);
        if (mask === 1'b1) begin
            checks++;
            signal_checks[index]++;
            if (actual !== expected) begin
                // Array names include the bank index, e.g. weight_data[2].
                $display("[MISMATCH] module=memory_wrapper vector=%0d cycle=%0d time=%0t signal=%s width=32 actual=0x%08h expected=0x%08h",
                         vector_index, FIRST_VECTOR_CYCLE + vector_index, $time,
                         signal_name, actual, expected);
                abort_test("output mismatch");
            end
        end else if (mask === 1'b0) masked++;
        else abort_test($sformatf("invalid comparison mask: %s", signal_name));
    endtask

    task automatic validate_configuration;
        if ((MEMORY_DATA_FORMAT_VERSION !== 1) || (SAMPLE_ID !== 0) ||
            (OUTPUT_COUNT !== SIGNAL_COUNT) || (NVEC !== 265015) ||
            (INIT_WORDS !== 117607) || (FINAL_WORDS !== 324) ||
            (INITIAL_READ_BEGIN !== INIT_WORDS) || (CORE_BEGIN !== 2*INIT_WORDS+1) ||
            (ARGMAX_READ_BEGIN !== CORE_BEGIN+29460) ||
            (FINAL_READ_BEGIN !== CORE_BEGIN+29475) ||
            (NVEC !== FINAL_READ_BEGIN+FINAL_WORDS+1))
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
        if (($bits(tb_tb_en[0]) != $bits(tb_en)) ||
            ($bits(tb_tb_we[0]) != $bits(tb_we)) ||
            ($bits(tb_tb_addr[0]) != $bits(tb_addr)) ||
            ($bits(tb_tb_wdata[0]) != $bits(tb_wdata)) ||
            ($bits(tb_busy[0]) != $bits(busy)) ||
            ($bits(tb_buf_sel[0]) != $bits(buf_sel)) ||
            ($bits(tb_in_addr[0]) != $bits(in_addr)) ||
            ($bits(tb_in_en[0]) != $bits(in_en)) ||
            ($bits(tb_out_addr[0]) != $bits(out_addr)) ||
            ($bits(tb_out_we[0]) != $bits(out_we)) ||
            ($bits(tb_out_data[0]) != $bits(out_data)) ||
            ($bits(tb_weight_addr[0]) != $bits(weight_addr)) ||
            ($bits(tb_weight_en[0]) != $bits(weight_en)) ||
            ($bits(tb_bias_addr[0]) != $bits(bias_addr)) ||
            ($bits(tb_bias_en[0]) != $bits(bias_en)) ||
            ($bits(tb_exp_tb_rdata[0]) != $bits(tb_rdata)) ||
            ($bits(tb_exp_in_data[0]) != $bits(in_data)) ||
            ($bits(tb_exp_weight_data_bank0[0]) != $bits(weight_data[0])) ||
            ($bits(tb_exp_weight_data_bank1[0]) != $bits(weight_data[1])) ||
            ($bits(tb_exp_weight_data_bank2[0]) != $bits(weight_data[2])) ||
            ($bits(tb_exp_weight_data_bank3[0]) != $bits(weight_data[3])) ||
            ($bits(tb_exp_bias_data[0]) != $bits(bias_data)) ||
            ($bits(tb_mask_tb_rdata[0]) != 1) ||
            ($bits(tb_mask_in_data[0]) != 1) ||
            ($bits(tb_mask_weight_data_bank0[0]) != 1) ||
            ($bits(tb_mask_weight_data_bank1[0]) != 1) ||
            ($bits(tb_mask_weight_data_bank2[0]) != 1) ||
            ($bits(tb_mask_weight_data_bank3[0]) != 1) ||
            ($bits(tb_mask_bias_data[0]) != 1) || ($size(weight_data) != 4))
            abort_test("header/port width or bank count mismatch");
    endtask

    task automatic validate_vector(input integer index);
        if ((^{tb_tb_en[index], tb_tb_we[index], tb_tb_addr[index], tb_tb_wdata[index],
               tb_busy[index], tb_buf_sel[index], tb_in_addr[index], tb_in_en[index],
               tb_out_addr[index], tb_out_we[index], tb_out_data[index],
               tb_weight_addr[index], tb_weight_en[index], tb_bias_addr[index], tb_bias_en[index]}) === 1'bx)
            abort_test("undefined stimulus");
        if (tb_tb_en[index] && tb_busy[index]) abort_test("TB access overlaps busy");
        if (!tb_busy[index] && (tb_in_en[index] || tb_out_we[index] ||
                               tb_weight_en[index] || tb_bias_en[index]))
            abort_test("internal access outside busy");
        // Check the mask contract only; the expected read values come from Python.
        if (index == 0) begin
            if (tb_mask_tb_rdata[index] !== 1'b0) abort_test("unexpected initial TB response mask");
        end else if (tb_mask_tb_rdata[index] !==
                     (!tb_busy[index-1] && tb_tb_en[index-1] && !tb_tb_we[index-1]))
            abort_test("TB response mask is not delayed one clock");
        if ((tb_mask_in_data[index] !== 1'b1) ||
            (tb_mask_weight_data_bank0[index] !== 1'b1) ||
            (tb_mask_weight_data_bank1[index] !== 1'b1) ||
            (tb_mask_weight_data_bank2[index] !== 1'b1) ||
            (tb_mask_weight_data_bank3[index] !== 1'b1) ||
            (tb_mask_bias_data[index] !== 1'b1))
            abort_test("defined internal read output was excluded");
        validate_data(0, "tb_rdata", tb_exp_tb_rdata[index], tb_mask_tb_rdata[index]);
        validate_data(1, "in_data", tb_exp_in_data[index], tb_mask_in_data[index]);
        validate_data(2, "weight_data[0]", tb_exp_weight_data_bank0[index], tb_mask_weight_data_bank0[index]);
        validate_data(3, "weight_data[1]", tb_exp_weight_data_bank1[index], tb_mask_weight_data_bank1[index]);
        validate_data(4, "weight_data[2]", tb_exp_weight_data_bank2[index], tb_mask_weight_data_bank2[index]);
        validate_data(5, "weight_data[3]", tb_exp_weight_data_bank3[index], tb_mask_weight_data_bank3[index]);
        validate_data(6, "bias_data", tb_exp_bias_data[index], tb_mask_bias_data[index]);
    endtask

    task automatic drive_vector(input integer index);
        tb_en = tb_tb_en[index];
        tb_we = tb_tb_we[index];
        tb_addr = tb_tb_addr[index];
        tb_wdata = tb_tb_wdata[index];
        busy = tb_busy[index];
        buf_sel = tb_buf_sel[index];
        in_addr = tb_in_addr[index];
        in_en = tb_in_en[index];
        out_addr = tb_out_addr[index];
        out_we = tb_out_we[index];
        out_data = tb_out_data[index];
        weight_addr = tb_weight_addr[index];
        weight_en = tb_weight_en[index];
        bias_addr = tb_bias_addr[index];
        bias_en = tb_bias_en[index];
    endtask

    initial begin
        tb_en = '0;
        tb_we = '0;
        tb_addr = '0;
        tb_wdata = '0;
        busy = '0;
        buf_sel = '0;
        in_addr = '0;
        in_en = '0;
        out_addr = '0;
        out_we = '0;
        out_data = '0;
        weight_addr = '0;
        weight_en = '0;
        bias_addr = '0;
        bias_en = '0;
        for (integer s = 0; s < SIGNAL_COUNT; s++) begin
            planned_checks[s] = 0;
            signal_checks[s] = 0;
        end
        @(posedge rst_n);
        validate_configuration();
        for (vector_index = 0; vector_index < NVEC; vector_index++)
            validate_vector(vector_index);
        if ((planned_checks[0] != INIT_WORDS+FINAL_WORDS) ||
            (tb_mask_tb_rdata[NVEC-1] !== 1'b1))
            abort_test("incomplete TB read-response coverage");
        vector_index = -1;
        $display("[INFO] module=memory_wrapper scope=memory_wrapper_standalone sample=%0d vectors=%0d outputs=%0d",
                 SAMPLE_ID, NVEC, OUTPUT_COUNT);
        $display("[INFO] init_write/read=%0d layer_writes=163 final_read=%0d", INIT_WORDS, FINAL_WORDS);
        repeat (START_WAIT_CYCLES) @(negedge clk);
        if ($time != FIRST_VECTOR_CYCLE * CLOCK_PERIOD_NS)
            abort_test("first vector timing mismatch");
        for (vector_index = 0; vector_index < NVEC; vector_index++) begin
            if (rst_n !== 1'b1) abort_test("unexpected reset");
            compare_signal(0, "tb_rdata", tb_rdata, tb_exp_tb_rdata[vector_index], tb_mask_tb_rdata[vector_index]);
            compare_signal(1, "in_data", in_data, tb_exp_in_data[vector_index], tb_mask_in_data[vector_index]);
            compare_signal(2, "weight_data[0]", weight_data[0], tb_exp_weight_data_bank0[vector_index], tb_mask_weight_data_bank0[vector_index]);
            compare_signal(3, "weight_data[1]", weight_data[1], tb_exp_weight_data_bank1[vector_index], tb_mask_weight_data_bank1[vector_index]);
            compare_signal(4, "weight_data[2]", weight_data[2], tb_exp_weight_data_bank2[vector_index], tb_mask_weight_data_bank2[vector_index]);
            compare_signal(5, "weight_data[3]", weight_data[3], tb_exp_weight_data_bank3[vector_index], tb_mask_weight_data_bank3[vector_index]);
            compare_signal(6, "bias_data", bias_data, tb_exp_bias_data[vector_index], tb_mask_bias_data[vector_index]);
            vectors_checked++;
            // Finish all comparisons before changing any input at this edge.
            drive_vector(vector_index);
            if (vector_index < NVEC-1) @(negedge clk);
        end
        if ((vectors_checked != NVEC) || (checks == 0) || (errors != 0) ||
            (checks+masked != SIGNAL_COUNT*NVEC) || (masked != planned_masked) ||
            ($time != EXPECTED_CYCLES*CLOCK_PERIOD_NS))
            abort_test("incomplete verification or wrong final timing");
        for (integer s = 0; s < SIGNAL_COUNT; s++)
            if ((signal_checks[s] == 0) || (signal_checks[s] != planned_checks[s]))
                abort_test($sformatf("incomplete comparisons for output %0d", s));
        finished = 1'b1;
        summary("PASS");
        $finish;
    end

    final begin
        if (!finished) begin
            $display("[FAIL] module=memory_wrapper vector=%0d time=%0t reason=simulation ended before verification completed",
                     vector_index, $time);
            $display("[SUMMARY] module=memory_wrapper result=FAIL vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                     vectors_checked, NVEC, checks, masked, errors+1, $time);
        end
    end
endmodule
`default_nettype wire
