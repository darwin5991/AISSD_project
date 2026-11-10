`timescale 1ns / 1ps
`default_nettype none

// Pure scoreboard: all stimulus/expectations/masks are precomputed in Python.
module mlp_top_tester #(
    parameter integer TB_CLOCK_PERIOD_NS = 10,
    parameter integer TB_RESET_CYCLES = 3,
    parameter integer TB_START_WAIT_CYCLES = 1,
    parameter bit TB_INITIAL_CLK = 1'b0
) (
    input wire clk, rst_n,
    output logic start,
    output logic tb_en,
    output logic tb_we,
    output logic [19:0] tb_addr,
    output logic [31:0] tb_wdata,
    input wire busy,
    input wire done,
    input wire [3:0] prediction,
    input wire [31:0] tb_rdata,
    input wire probe_out_we,
    input wire [6:0] probe_out_addr,
    input wire probe_buf_sel,
    input wire [31:0] probe_out_data
);
    `include "mlp_top_tb_data.vh"

    integer vector_index = -1;
    integer vectors_checked = 0;
    integer checks = 0, masked = 0, errors = 0;
    integer signal_checks [0:7];
    bit finished = 1'b0;

    task automatic summary(input string result);
        $display("[SUMMARY] module=mlp_top result=%s vectors=%0d/%0d checks=%0d masked=%0d errors=%0d time=%0t",
                 result, vectors_checked, NVEC, checks, masked, errors, $time);
    endtask

    task automatic abort_test(input string reason);
        errors++;
        finished = 1'b1;
        $display("[FAIL] module=mlp_top vector=%0d time=%0t reason=%s", vector_index, $time, reason);
        summary("FAIL");
        $fatal(1, "Top verification failed");
    endtask

    task automatic validate_data(input string signal_name,
                                 input logic [31:0] expected, input logic mask);
        if ((mask !== 1'b0) && (mask !== 1'b1))
            abort_test($sformatf("invalid mask: %s", signal_name));
        if ((mask === 1'b1) && ((^expected) === 1'bx))
            abort_test($sformatf("undefined expected value: %s", signal_name));
    endtask

    task automatic compare_signal(input integer index, input string signal_name,
                                  input integer width, input logic [31:0] actual,
                                  input logic [31:0] expected, input logic mask);
        if (mask === 1'b1) begin
            checks++;
            signal_checks[index]++;
            if (actual !== expected) begin
                $display("[MISMATCH] module=mlp_top vector=%0d cycle=%0d time=%0t signal=%s width=%0d actual=0x%0h expected=0x%0h",
                         vector_index, FIRST_VECTOR_CYCLE + vector_index, $time,
                         signal_name, width, actual, expected);
                abort_test("output mismatch");
            end
        end else masked++;
    endtask

    task automatic validate_configuration;
        if ((TOP_DATA_FORMAT_VERSION !== 1) || ((^SAMPLE_ID) === 1'bx) ||
            (SAMPLE_ID < 0) || (SAMPLE_ID > 9) || (NVEC !== 265015) ||
            (INIT_WORDS !== 117607) || (FINAL_WORDS !== 324) ||
            (START_VECTOR !== 2*INIT_WORDS+1) || (FINAL_READ_BEGIN !== START_VECTOR+29475) ||
            (NVEC !== FINAL_READ_BEGIN+FINAL_WORDS+1) ||
            (EXPECTED_PREDICTION < 0) || (EXPECTED_PREDICTION > 9))
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
        if (($bits(tb_start[0]) != $bits(start)) ||
            ($bits(tb_tb_en[0]) != $bits(tb_en)) ||
            ($bits(tb_tb_we[0]) != $bits(tb_we)) ||
            ($bits(tb_tb_addr[0]) != $bits(tb_addr)) ||
            ($bits(tb_tb_wdata[0]) != $bits(tb_wdata)) ||
            ($bits(tb_exp_busy[0]) != $bits(busy)) ||
            ($bits(tb_mask_busy[0]) != 1) ||
            ($bits(tb_exp_done[0]) != $bits(done)) ||
            ($bits(tb_mask_done[0]) != 1) ||
            ($bits(tb_exp_prediction[0]) != $bits(prediction)) ||
            ($bits(tb_mask_prediction[0]) != 1) ||
            ($bits(tb_exp_tb_rdata[0]) != $bits(tb_rdata)) ||
            ($bits(tb_mask_tb_rdata[0]) != 1) ||
            ($bits(tb_exp_probe_out_we[0]) != $bits(probe_out_we)) ||
            ($bits(tb_mask_probe_out_we[0]) != 1) ||
            ($bits(tb_exp_probe_out_addr[0]) != $bits(probe_out_addr)) ||
            ($bits(tb_mask_probe_out_addr[0]) != 1) ||
            ($bits(tb_exp_probe_buf_sel[0]) != $bits(probe_buf_sel)) ||
            ($bits(tb_mask_probe_buf_sel[0]) != 1) ||
            ($bits(tb_exp_probe_out_data[0]) != $bits(probe_out_data)) ||
            ($bits(tb_mask_probe_out_data[0]) != 1))
            abort_test("header/port width mismatch");
    endtask

    initial begin
        start = '0;
        tb_en = '0;
        tb_we = '0;
        tb_addr = '0;
        tb_wdata = '0;
        for (integer s = 0; s < 8; s++) signal_checks[s] = 0;
        @(posedge rst_n);
        validate_configuration();
        for (vector_index = 0; vector_index < NVEC; vector_index++) begin
            if (((^tb_start[vector_index]) === 1'bx) ||
                ((^tb_tb_en[vector_index]) === 1'bx) ||
                ((^tb_tb_we[vector_index]) === 1'bx) ||
                ((^tb_tb_addr[vector_index]) === 1'bx) ||
                ((^tb_tb_wdata[vector_index]) === 1'bx))
                abort_test("undefined stimulus");
            validate_data("busy", tb_exp_busy[vector_index], tb_mask_busy[vector_index]);
            validate_data("done", tb_exp_done[vector_index], tb_mask_done[vector_index]);
            validate_data("prediction", tb_exp_prediction[vector_index], tb_mask_prediction[vector_index]);
            validate_data("tb_rdata", tb_exp_tb_rdata[vector_index], tb_mask_tb_rdata[vector_index]);
            validate_data("probe_out_we", tb_exp_probe_out_we[vector_index], tb_mask_probe_out_we[vector_index]);
            validate_data("probe_out_addr", tb_exp_probe_out_addr[vector_index], tb_mask_probe_out_addr[vector_index]);
            validate_data("probe_buf_sel", tb_exp_probe_buf_sel[vector_index], tb_mask_probe_buf_sel[vector_index]);
            validate_data("probe_out_data", tb_exp_probe_out_data[vector_index], tb_mask_probe_out_data[vector_index]);
        end
        vector_index = -1;
        $display("[INFO] module=mlp_top scope=top_full_rtl sample=%0d vectors=%0d prediction=%0d",
                 SAMPLE_ID, NVEC, EXPECTED_PREDICTION);
        $display("[INFO] init_write/read=%0d layer_writes=163 final_read=%0d", INIT_WORDS, FINAL_WORDS);
        repeat (START_WAIT_CYCLES) @(negedge clk);
        if ($time != FIRST_VECTOR_CYCLE * CLOCK_PERIOD_NS)
            abort_test("first vector timing mismatch");
        for (vector_index = 0; vector_index < NVEC; vector_index++) begin
            if (rst_n !== 1'b1) abort_test("unexpected reset");
            compare_signal(0, "busy", 1, busy, tb_exp_busy[vector_index], tb_mask_busy[vector_index]);
            compare_signal(1, "done", 1, done, tb_exp_done[vector_index], tb_mask_done[vector_index]);
            compare_signal(2, "prediction", 4, prediction, tb_exp_prediction[vector_index], tb_mask_prediction[vector_index]);
            compare_signal(3, "tb_rdata", 32, tb_rdata, tb_exp_tb_rdata[vector_index], tb_mask_tb_rdata[vector_index]);
            compare_signal(4, "probe_out_we", 1, probe_out_we, tb_exp_probe_out_we[vector_index], tb_mask_probe_out_we[vector_index]);
            compare_signal(5, "probe_out_addr", 7, probe_out_addr, tb_exp_probe_out_addr[vector_index], tb_mask_probe_out_addr[vector_index]);
            compare_signal(6, "probe_buf_sel", 1, probe_buf_sel, tb_exp_probe_buf_sel[vector_index], tb_mask_probe_buf_sel[vector_index]);
            compare_signal(7, "probe_out_data", 32, probe_out_data, tb_exp_probe_out_data[vector_index], tb_mask_probe_out_data[vector_index]);
            vectors_checked++;
            // Complete every comparison before changing inputs at this edge.
            start = tb_start[vector_index];
            tb_en = tb_tb_en[vector_index];
            tb_we = tb_tb_we[vector_index];
            tb_addr = tb_tb_addr[vector_index];
            tb_wdata = tb_tb_wdata[vector_index];
            if (vector_index < NVEC-1) @(negedge clk);
        end
        if ((vectors_checked != NVEC) || (checks == 0) || (errors != 0))
            abort_test("incomplete verification");
        for (integer s = 0; s < 8; s++)
            if (signal_checks[s] == 0) abort_test($sformatf("output %0d was never compared", s));
        finished = 1'b1;
        summary("PASS");
        $finish;
    end

    final begin
        if (!finished) begin
            $display("[FAIL] module=mlp_top vector=%0d time=%0t reason=simulation ended before verification completed",
                     vector_index, $time);
            $display("[SUMMARY] module=mlp_top result=FAIL vectors=%0d/%0d checks=%0d masked=%0d errors=%0d",
                     vectors_checked, NVEC, checks, masked, errors+1);
        end
    end
endmodule
`default_nettype wire
