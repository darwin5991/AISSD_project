////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : argmax_unit
// Description : Byte selection, signed comparison and maximum-record storage.
// Status      : signed byte comparison and record storage implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Class zero initializes the record; the CU supplies indices 0..9.

module argmax_unit (
    input  logic                clk,
    input  logic                rst_n,

    input  logic        [31:0]  word_data,
    input  logic        [3:0]   class_index,

    input  logic                initialize,
    input  logic                compare_en,

    output logic        [3:0]   prediction
);

logic signed [7:0] candidate;
logic signed [7:0] max_value;
logic greater;

byte_select4 u_select (
    .word_in(word_data),
    .lane(class_index[1:0]),
    .data_out(candidate)
);

signed_compare8 u_compare (
    .a(candidate),
    .b(max_value),
    .greater(greater)
);

argmax_tracker u_tracker (
    .clk(clk),
    .rst_n(rst_n),
    .initialize(initialize),
    .compare_en(compare_en),
    .greater(greater),
    .candidate(candidate),
    .candidate_index(class_index),
    .max_value(max_value),
    .best_index(prediction)
);

endmodule
