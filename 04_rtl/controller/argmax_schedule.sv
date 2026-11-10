////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : argmax_schedule
// Description : Central ARGMAX read/compare schedule; controls its dedicated counter.
// Status      : sequential signed-ARGMAX schedule implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// One RAM word is read before processing its bytes; final dummy lanes are skipped.
// No independent layer or MLP scheduling is performed here.

module argmax_schedule (
    input  logic                clk,
    input  logic                rst_n,

    input  logic        [2:0]   state,
    input  logic        [3:0]   class_index,

    output logic                index_clear,
    output logic                index_advance,

    output logic                read_en,
    output logic                initialize,
    output logic                compare_en,
    output logic                done
);

import control_state_pkg::*;
// This phase bit distinguishes the read of a word from processing its bytes.
// Class index remains the only ARGMAX counter; it holds during each read.
logic word_loaded;

always_comb begin
    index_clear = 1'b1;
    index_advance = 1'b0;
    read_en = 1'b0;
    initialize = 1'b0;
    compare_en = 1'b0;
    done = 1'b0;
    if (state == ARGMAX) begin
        index_clear = 1'b0;
        if (class_index <= 4'd9) begin
            if (!word_loaded) begin
                read_en = 1'b1;
            end else begin
                initialize = (class_index == 0);
                compare_en = (class_index != 0);
                index_advance = (class_index < 4'd9);
                done = (class_index == 4'd9);
            end
        end
    end
end

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        word_loaded <= 1'b0;
    else if (state == ARGMAX) begin
        if (read_en)
            word_loaded <= 1'b1;
        else if ((initialize || compare_en) && (class_index[1:0] == 2'd3))
            word_loaded <= 1'b0;
    end else
        word_loaded <= 1'b0;
end

endmodule
