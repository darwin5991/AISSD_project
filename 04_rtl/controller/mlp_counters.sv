////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : mlp_counters
// Description : Three MLP counters driven solely by Control unit update commands.
// Status      : enabled counter composition implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module mlp_counters (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                layer_clear,
    input  logic                layer_advance,

    input  logic                input_clear,
    input  logic                input_advance,

    input  logic                group_clear,
    input  logic                group_advance,

    output logic        [1:0]   layer_index,
    output logic        [7:0]   input_word,
    output logic        [6:0]   output_group
);

counter_en #(.WIDTH(2)) u_layer (
    .clk(clk),
    .rst_n(rst_n),
    .clear(layer_clear),
    .advance(layer_advance),
    .value(layer_index)
);

counter_en #(.WIDTH(8)) u_input (
    .clk(clk),
    .rst_n(rst_n),
    .clear(input_clear),
    .advance(input_advance),
    .value(input_word)
);

counter_en #(.WIDTH(7)) u_group (
    .clk(clk),
    .rst_n(rst_n),
    .clear(group_clear),
    .advance(group_advance),
    .value(output_group)
);

endmodule
