////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : pipeline_event_control
// Description : Select first-read+1 or prior last-read+5 bias load events.
// Status      : bias-load event combination implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module pipeline_event_control (
    input  logic                first_read_d1,
    input  logic                next_bias_d5,

    output logic                bias_load
);

assign bias_load = first_read_d1 | next_bias_d5;

endmodule
