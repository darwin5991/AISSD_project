`timescale 1ns / 1ps
// SIMULATION ONLY: calculates from the actual connected signed operands.
// Two register stages match the interface latency; no golden data is read here.
module mac_array (
    input logic clk, rst_n, input_valid,
    input logic signed [7:0] input_data [0:3],
    input logic signed [7:0] weight_data [0:3][0:3],
    output logic signed [31:0] partial_sum [0:3],
    output logic psum_valid
);
    logic signed [31:0] products [0:3][0:3];
    logic valid_d1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_d1 <= 1'b0;
            psum_valid <= 1'b0;
            for (integer lane = 0; lane < 4; lane++) begin
                partial_sum[lane] <= 32'sd0;
                for (integer k = 0; k < 4; k++) products[lane][k] <= 32'sd0;
            end
        end else begin
            valid_d1 <= input_valid;
            psum_valid <= valid_d1;
            for (integer lane = 0; lane < 4; lane++) begin
                for (integer k = 0; k < 4; k++)
                    products[lane][k] <= $signed(input_data[k]) * $signed(weight_data[lane][k]);
                partial_sum[lane] <= (products[lane][0] + products[lane][1])
                                  + (products[lane][2] + products[lane][3]);
            end
        end
    end
endmodule
