////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : control_unit
// Last update : 2026.11.09
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : layer LUT, FSM, address/pipeline control and signed ARGMAX
// Status      : control hierarchy implemented; see verification results
// Reference   : architecture.md, sections 7.6 and 10..12
////////////////////////////////////////////////////////////////////////////////
//
// IDLE -> PREP -> RUN -> DRAIN -> PREP (next layer).
// After FC3, PREP -> ARGMAX -> IDLE.
//
// MLP counters: layer, input word, output group; input word N marks a gap.
// LUT: input lengths, groups, base addresses, shifts and ReLU selection.
// Initial FC1/2/3 shifts: bias=(+3,+1,+2), output=(10,7,7).
// CU schedules reads, mac_input_valid, bias_load, result_load and writes.
// MAC psum_valid directly enables accumulation in the datapath.
// ARGMAX rereads B: ten signed bytes, sequential compare, lowest-index tie.
// ARGMAX has its own counter; done pulses with prediction and busy=0.
// start is ignored while busy; rst_n asynchronously resets control state.
////////////////////////////////////////////////////////////////////////////////

module control_unit (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                start,
    output logic                busy,
    output logic                done,
    output logic        [3:0]   prediction,

    output logic                buf_sel,

    output logic        [7:0]   in_addr,
    output logic                in_en,
    input  logic        [31:0]  argmax_data,

    output logic        [6:0]   out_addr,
    output logic                out_we,

    output logic        [14:0]  weight_addr,
    output logic                weight_en,

    output logic        [7:0]   bias_addr,
    output logic                bias_en,

    output logic                mac_input_valid,

    output logic                bias_load,
    output logic signed [5:0]   bias_shift,

    output logic                result_load,
    output logic                relu_en,
    output logic        [4:0]   output_shift
);

logic [2:0] state;
logic [1:0] layer_index;
logic [7:0] input_word;
logic [6:0] output_group;

logic [7:0] input_words;
logic [7:0] output_groups;
logic [14:0] weight_base;
logic [7:0] bias_base;
logic layer_buf_sel;

logic layer_clear;
logic layer_advance;
logic input_clear;
logic input_advance;
logic group_clear;
logic group_advance;

logic prep_done;
logic last_read;
logic layer_stored;
logic mlp_read;
logic [7:0] mlp_in_addr;

logic [3:0] argmax_index;
logic [7:0] argmax_addr;
logic argmax_read;
logic argmax_initialize;
logic argmax_compare_en;
logic argmax_done;

layer_config_lut u_layer_config (
    .layer_index(layer_index),
    .input_words(input_words),
    .output_groups(output_groups),
    .weight_base(weight_base),
    .bias_base(bias_base),
    .buf_sel(layer_buf_sel),
    .bias_shift(bias_shift),
    .output_shift(output_shift),
    .relu_en(relu_en)
);

control_fsm u_fsm (
    .clk(clk),
    .rst_n(rst_n),
    .start(start),
    .layer_index(layer_index),
    .prep_done(prep_done),
    .last_read(last_read),
    .layer_stored(layer_stored),
    .argmax_done(argmax_done),
    .state(state),
    .busy(busy),
    .done(done)
);

mlp_counters u_counters (
    .clk(clk),
    .rst_n(rst_n),
    .layer_clear(layer_clear),
    .layer_advance(layer_advance),
    .input_clear(input_clear),
    .input_advance(input_advance),
    .group_clear(group_clear),
    .group_advance(group_advance),
    .layer_index(layer_index),
    .input_word(input_word),
    .output_group(output_group)
);

address_generator u_addresses (
    .input_words(input_words),
    .weight_base(weight_base),
    .bias_base(bias_base),
    .input_word(input_word),
    .output_group(output_group),
    .in_addr(mlp_in_addr),
    .weight_addr(weight_addr),
    .bias_addr(bias_addr)
);

pipeline_control u_pipeline (
    .clk(clk),
    .rst_n(rst_n),
    .start(start),
    .state(state),
    .layer_index(layer_index),
    .input_words(input_words),
    .output_groups(output_groups),
    .input_word(input_word),
    .output_group(output_group),
    .read_en(mlp_read),
    .bias_read(bias_en),
    .mac_input_valid(mac_input_valid),
    .bias_load(bias_load),
    .result_load(result_load),
    .out_we(out_we),
    .out_addr(out_addr),
    .prep_done(prep_done),
    .last_read(last_read),
    .layer_stored(layer_stored),
    .layer_clear(layer_clear),
    .layer_advance(layer_advance),
    .input_clear(input_clear),
    .input_advance(input_advance),
    .group_clear(group_clear),
    .group_advance(group_advance)
);

assign weight_en = mlp_read;

argmax_control u_argmax_control (
    .clk(clk),
    .rst_n(rst_n),
    .state(state),
    .class_index(argmax_index),
    .read_addr(argmax_addr),
    .read_en(argmax_read),
    .initialize(argmax_initialize),
    .compare_en(argmax_compare_en),
    .done(argmax_done)
);

argmax_unit u_argmax (
    .clk(clk),
    .rst_n(rst_n),
    .word_data(argmax_data),
    .class_index(argmax_index),
    .initialize(argmax_initialize),
    .compare_en(argmax_compare_en),
    .prediction(prediction)
);

control_read_mux u_read_mux (
    .state(state),
    .layer_buf_sel(layer_buf_sel),
    .mlp_addr(mlp_in_addr),
    .mlp_en(mlp_read),
    .argmax_addr(argmax_addr),
    .argmax_en(argmax_read),
    .buf_sel(buf_sel),
    .in_addr(in_addr),
    .in_en(in_en)
);

endmodule
