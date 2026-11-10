////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : argmax_control
// Description : ARGMAX-only counter and read/compare command distribution.
// Status      : ARGMAX counter and schedule implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module argmax_control (
    input  logic                clk,
    input  logic                rst_n,

    input  logic        [2:0]   state,

    output logic        [3:0]   class_index,
    output logic        [7:0]   read_addr,
    output logic                read_en,

    output logic                initialize,
    output logic                compare_en,
    output logic                done
);

logic index_clear;
logic index_advance;

assign read_addr = {6'd0, class_index[3:2]};

counter_en #(.WIDTH(4)) u_index (
    .clk(clk),
    .rst_n(rst_n),
    .clear(index_clear),
    .advance(index_advance),
    .value(class_index)
);

argmax_schedule u_schedule (
    .clk(clk),
    .rst_n(rst_n),
    .state(state),
    .class_index(class_index),
    .index_clear(index_clear),
    .index_advance(index_advance),
    .read_en(read_en),
    .initialize(initialize),
    .compare_en(compare_en),
    .done(done)
);

endmodule
