`timescale 1ns / 1ps
// SIMULATION ONLY: calculates from the actual connected signed operands.
// Input/weight, product and sum stages match the revised three-stage contract.
// No golden data is read here. This model is not selected by the full-RTL target.
module mac_array (
    input logic clk, rst_n, input_valid,
    input logic signed [7:0] input_data [0:3],
    input logic signed [7:0] weight_data [0:3][0:3],
    output logic signed [31:0] partial_sum [0:3],
    output logic psum_valid
);
    logic signed [7:0] inputs_reg [0:3];
    logic signed [7:0] weights_reg [0:3][0:3];
    logic signed [31:0] products [0:3][0:3];
    logic valid_d1, valid_d2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_d1 <= 1'b0;
            valid_d2 <= 1'b0;
            psum_valid <= 1'b0;
            for (integer k = 0; k < 4; k++) inputs_reg[k] <= 8'sd0;
            for (integer lane = 0; lane < 4; lane++) begin
                partial_sum[lane] <= 32'sd0;
                for (integer k = 0; k < 4; k++) begin
                    weights_reg[lane][k] <= 8'sd0;
                    products[lane][k] <= 32'sd0;
                end
            end
        end else begin
            // Invalid bubbles advance through all data and valid stages too.
            valid_d1 <= input_valid;
            valid_d2 <= valid_d1;
            psum_valid <= valid_d2;
            for (integer k = 0; k < 4; k++) inputs_reg[k] <= input_data[k];
            for (integer lane = 0; lane < 4; lane++) begin
                for (integer k = 0; k < 4; k++) begin
                    weights_reg[lane][k] <= weight_data[lane][k];
                    products[lane][k] <= $signed(inputs_reg[k]) * $signed(weights_reg[lane][k]);
                end
                partial_sum[lane] <= (products[lane][0] + products[lane][1])
                                  + (products[lane][2] + products[lane][3]);
            end
        end
    end
endmodule
