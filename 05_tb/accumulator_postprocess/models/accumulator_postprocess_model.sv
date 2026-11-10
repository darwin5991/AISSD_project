`timescale 1ns / 1ps
// SIMULATION ONLY: behavioral arithmetic for Top connectivity/timing verification.
// This file is never selected as the production accumulator RTL.
module accumulator_postprocess (
    input logic clk, rst_n, bias_load,
    input logic signed [7:0] bias_data [0:3],
    input logic signed [5:0] bias_shift,
    input logic signed [31:0] partial_sum [0:3],
    input logic psum_valid, result_load, relu_en,
    input logic [4:0] output_shift,
    output logic [31:0] output_data
);
    logic signed [31:0] accumulator [0:3];
    logic signed [31:0] result [0:3];

    function automatic logic signed [31:0] aligned_bias(input logic signed [7:0] value,
                                                       input logic signed [5:0] shift);
        logic signed [31:0] extended;
        extended = value;
        aligned_bias = shift >= 0 ? (extended <<< shift) : (extended >>> -shift);
    endfunction

    function automatic logic [7:0] postprocess(input logic signed [31:0] value,
                                               input logic relu,
                                               input logic [4:0] shift);
        logic signed [31:0] adjusted;
        adjusted = (relu && value < 0) ? 32'sd0 : value;
        adjusted = adjusted >>> shift;
        if (adjusted > 32'sd127) postprocess = 8'h7f;
        else if (adjusted < -32'sd128) postprocess = 8'h80;
        else postprocess = adjusted[7:0];
    endfunction

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (integer lane = 0; lane < 4; lane++) begin
                accumulator[lane] <= 32'sd0;
                result[lane] <= 32'sd0;
            end
        end else begin
            if (bias_load && psum_valid)
                $fatal(1, "accumulator model: bias initialization overlaps a valid sum");
            for (integer lane = 0; lane < 4; lane++) begin
                if (result_load) result[lane] <= accumulator[lane];
                if (bias_load) accumulator[lane] <= aligned_bias(bias_data[lane], bias_shift);
                else if (psum_valid) accumulator[lane] <= accumulator[lane] + partial_sum[lane];
            end
        end
    end

    always_comb begin
        for (integer lane = 0; lane < 4; lane++)
            output_data[lane*8 +: 8] = postprocess(result[lane], relu_en, output_shift);
    end
endmodule
