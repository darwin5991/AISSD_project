////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : layer_config_lut
// Description : Layer lengths, memory bases, buffer role and numeric configuration.
// Status      : combinational layer configuration implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Layer 0..2 selects FC1..3; layer 3 prepares final-buffer ARGMAX.

module layer_config_lut (
    input  logic        [1:0]   layer_index,

    output logic        [7:0]   input_words,
    output logic        [7:0]   output_groups,

    output logic        [14:0]  weight_base,
    output logic        [7:0]   bias_base,
    output logic                buf_sel,

    output logic signed [5:0]   bias_shift,
    output logic        [4:0]   output_shift,
    output logic                relu_en
);

always_comb begin
    input_words = 8'd0;
    output_groups = 8'd0;
    weight_base = 15'd0;
    bias_base = 8'd0;
    buf_sel = 1'b0;
    bias_shift = 6'sd0;
    output_shift = 5'd0;
    relu_en = 1'b0;

    case (layer_index)
        2'd0: begin
            input_words = 8'd196;
            output_groups = 8'd128;
            bias_shift = 6'sd3;
            output_shift = 5'd10;
            relu_en = 1'b1;
        end
        2'd1: begin
            input_words = 8'd128;
            output_groups = 8'd32;
            weight_base = 15'd25088;
            bias_base = 8'd128;
            buf_sel = 1'b1;
            bias_shift = 6'sd1;
            output_shift = 5'd7;
            relu_en = 1'b1;
        end
        2'd2: begin
            input_words = 8'd32;
            output_groups = 8'd3;
            weight_base = 15'd29184;
            bias_base = 8'd160;
            bias_shift = 6'sd2;
            output_shift = 5'd7;
        end
        2'd3: buf_sel = 1'b1; // ARGMAX preparation: no FC reads.
        default: begin end
    endcase
end

endmodule
