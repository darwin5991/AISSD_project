////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : pipeline_control
// Description : Read scheduling and delayed metadata for MLP pipeline control.
// Status      : read schedule and delayed control events implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Delay taps drive destination enables before their sampling edge.
// For a read at R: MAC R+1, result capture R+4, output write R+5.

module pipeline_control (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                start,
    input  logic        [2:0]   state,
    input  logic        [1:0]   layer_index,

    input  logic        [7:0]   input_words,
    input  logic        [7:0]   output_groups,
    input  logic        [7:0]   input_word,
    input  logic        [6:0]   output_group,

    output logic                read_en,
    output logic                bias_read,
    output logic                mac_input_valid,

    output logic                bias_load,
    output logic                result_load,
    output logic                out_we,
    output logic        [6:0]   out_addr,

    output logic                prep_done,
    output logic                last_read,
    output logic                layer_stored,

    output logic                layer_clear,
    output logic                layer_advance,
    output logic                input_clear,
    output logic                input_advance,
    output logic                group_clear,
    output logic                group_advance
);

import control_state_pkg::*;

logic first_read;
logic last_input;
logic next_bias;
logic first_read_d1;
logic next_bias_d4;
logic mac_input_valid_raw;
logic result_load_raw;
logic out_we_raw;
logic layer_stored_raw;
logic bias_load_raw;
logic fault_hold;
logic metadata_rst_n;
logic controls_enabled;

// Immediately suppress events for unused encodings. A registered fault pulse
// then clears the metadata pipes before a subsequent start can use them.
// Normal state transitions do not pass through this reset-generation path.
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        fault_hold <= 1'b0;
    else
        fault_hold <= !state_is_valid(state);
end

assign metadata_rst_n = rst_n && !fault_hold;
assign controls_enabled = state_is_valid(state) && !fault_hold;
assign mac_input_valid = mac_input_valid_raw && controls_enabled;
assign result_load = result_load_raw && controls_enabled;
assign out_we = out_we_raw && controls_enabled;
assign layer_stored = layer_stored_raw && controls_enabled;
assign bias_load = bias_load_raw && controls_enabled;

read_issue_control u_issue (
    .clk(clk),
    .rst_n(rst_n),
    .start(start),
    .state(state),
    .layer_index(layer_index),
    .input_words(input_words),
    .output_groups(output_groups),
    .input_word(input_word),
    .output_group(output_group),
    .layer_stored(layer_stored),
    .read_en(read_en),
    .bias_read(bias_read),
    .first_read(first_read),
    .last_input(last_input),
    .last_read(last_read),
    .next_bias(next_bias),
    .prep_done(prep_done),
    .layer_clear(layer_clear),
    .layer_advance(layer_advance),
    .input_clear(input_clear),
    .input_advance(input_advance),
    .group_clear(group_clear),
    .group_advance(group_advance)
);

delay_line #(.WIDTH(1), .DEPTH(1)) u_mac_valid (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(read_en),
    .data_out(mac_input_valid_raw)
);

delay_line #(.WIDTH(1), .DEPTH(1)) u_first_bias (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(first_read),
    .data_out(first_read_d1)
);

delay_line #(.WIDTH(1), .DEPTH(4)) u_result_load (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(last_input),
    .data_out(result_load_raw)
);

delay_line #(.WIDTH(1), .DEPTH(4)) u_next_bias (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(next_bias),
    .data_out(next_bias_d4)
);

delay_line #(.WIDTH(1), .DEPTH(5)) u_output_write (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(last_input),
    .data_out(out_we_raw)
);

delay_line #(.WIDTH(7), .DEPTH(5)) u_output_address (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(output_group),
    .data_out(out_addr)
);

delay_line #(.WIDTH(1), .DEPTH(5)) u_layer_stored (
    .clk(clk),
    .rst_n(metadata_rst_n),
    .data_in(last_read),
    .data_out(layer_stored_raw)
);

pipeline_event_control u_bias_event (
    .first_read_d1(first_read_d1),
    .next_bias_d4(next_bias_d4),
    .bias_load(bias_load_raw)
);

endmodule
