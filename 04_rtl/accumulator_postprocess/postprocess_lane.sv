////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : postprocess_lane
// Description : Combinational ReLU, arithmetic shift and INT8 saturation.
// Status      : ReLU/shift/saturation path implemented; verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module postprocess_lane (
    input  logic signed [31:0]  result32,

    input  logic                relu_en,
    input  logic        [4:0]   output_shift,

    output logic signed [7:0]   output8
);

logic signed [31:0] activated;
logic signed [31:0] shifted;

relu32 u_relu (
    .data_in(result32),
    .relu_en(relu_en),
    .data_out(activated)
);

arithmetic_rshift32 u_shift (
    .data_in(activated),
    .shift(output_shift),
    .data_out(shifted)
);

saturate32_to8 u_saturate (
    .data_in(shifted),
    .data_out(output8)
);

endmodule
