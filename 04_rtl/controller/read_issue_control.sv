////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : read_issue_control
// Description : Central read issue, counter commands and pipeline event tagging.
// Status      : MLP read schedule and counter commands implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Event tags apply to actual reads; input_word=N supplies the tile gap.
// first_read initializes the first output group of a layer.
// next_bias tags a completed group that has a following group.

module read_issue_control (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                start,
    input  logic        [2:0]   state,
    input  logic        [1:0]   layer_index,

    input  logic        [7:0]   input_words,
    input  logic        [7:0]   output_groups,
    input  logic        [7:0]   input_word,
    input  logic        [6:0]   output_group,

    input  logic                layer_stored,

    output logic                read_en,
    output logic                bias_read,
    output logic                first_read,
    output logic                last_input,
    output logic                last_read,
    output logic                next_bias,

    output logic                prep_done,

    output logic                layer_clear,
    output logic                layer_advance,
    output logic                input_clear,
    output logic                input_advance,
    output logic                group_clear,
    output logic                group_advance
);

import control_state_pkg::*;

always_comb begin
    read_en = 1'b0;
    bias_read = 1'b0;
    first_read = 1'b0;
    last_input = 1'b0;
    last_read = 1'b0;
    next_bias = 1'b0;
    prep_done = 1'b0;
    layer_clear = 1'b0;
    layer_advance = 1'b0;
    input_clear = 1'b0;
    input_advance = 1'b0;
    group_clear = 1'b0;
    group_advance = 1'b0;

    case (state)
        IDLE: if (start) begin
            layer_clear = 1'b1;
            input_clear = 1'b1;
            group_clear = 1'b1;
        end
        PREP: begin
            input_clear = 1'b1;
            group_clear = 1'b1;
            prep_done = 1'b1;
        end
        RUN: begin
            if ((layer_index < 2'd3) && (input_words != 0) &&
                (output_groups != 0) && ({1'b0, output_group} < output_groups)) begin
                if (input_word < input_words) begin
                    read_en = 1'b1;
                    input_advance = 1'b1;
                    bias_read = (input_word == 0);
                    first_read = bias_read && (output_group == 0);
                    last_input = (input_word == input_words - 1'b1);
                    last_read = last_input && ({1'b0, output_group} == output_groups - 1'b1);
                    next_bias = last_input && !last_read;
                end else if (input_word == input_words) begin
                    // Exactly one read-free cycle between output groups.
                    input_clear = 1'b1;
                    group_advance = 1'b1;
                end
            end
        end
        DRAIN: if (layer_stored) layer_advance = 1'b1;
        ARGMAX: begin end
        default: begin
            // Re-enter IDLE with clean counters after an unused encoding.
            layer_clear = 1'b1;
            input_clear = 1'b1;
            group_clear = 1'b1;
        end
    endcase
end

endmodule
