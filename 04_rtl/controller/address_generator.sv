////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : address_generator
// Description : Calculate core word addresses from layer settings and MLP counters.
// Status      : combinational word address arithmetic implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module address_generator (
    input  logic        [7:0]   input_words,
    input  logic        [14:0]  weight_base,
    input  logic        [7:0]   bias_base,

    input  logic        [7:0]   input_word,
    input  logic        [6:0]   output_group,

    output logic        [7:0]   in_addr,
    output logic        [14:0]  weight_addr,
    output logic        [7:0]   bias_addr
);

logic [14:0] group_offset;

assign group_offset = output_group * input_words;
assign in_addr = input_word;
assign weight_addr = weight_base + group_offset + input_word;
assign bias_addr = bias_base + output_group;

endmodule
