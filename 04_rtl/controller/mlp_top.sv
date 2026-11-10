////////////////////////////////////////////////////////////////////////////////
// Create Date : 2026.11.06
// Design Name : MLP end-to-end accelerator
// Module Name : mlp_top
// Last update : 2026.11.10
////////////////////////////////////////////////////////////////////////////////
// Hardware    : AMD/Xilinx Artix-7 XC7A100T-1CSG324C
// Description : top-level wiring for the end-to-end MNIST MLP
// Status      : structural wiring complete; full RTL integration verification pending
// Reference   : architecture.md, sections 7.1 and 7.2
////////////////////////////////////////////////////////////////////////////////
//
// Data: memory -> unpack INT8 -> MAC -> accumulator/postprocess -> memory.
// Control unit supplies addresses/timing and rereads FC3 data for ARGMAX.
// Model: 784 -> 512/ReLU -> 128/ReLU -> 10.
// Buffers: FC1 A->B, FC2 B->A, FC3 A->B; first byte is in [7:0].
//
// start: one-cycle request, accepted only while idle.
// busy covers inference and ARGMAX; done pulses with valid prediction.
// TB access: busy=0, 32-bit data, aligned 20-bit byte address.
// Clock: rising edge. Reset: asynchronous active-low.
////////////////////////////////////////////////////////////////////////////////

module mlp_top (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                start,
    output logic                busy,
    output logic                done,
    output logic        [3:0]   prediction,

    input  logic                tb_en,
    input  logic                tb_we,
    input  logic        [19:0]  tb_addr,
    input  logic        [31:0]  tb_wdata,
    output logic        [31:0]  tb_rdata
);

logic buf_sel;
logic [7:0] in_addr;
logic in_en;
logic [31:0] in_word;
logic [6:0] out_addr;
logic out_we;
logic [31:0] out_word;

logic [14:0] weight_addr;
logic weight_en;
logic [31:0] weight_words [0:3];
logic [7:0] bias_addr;
logic bias_en;
logic [31:0] bias_word;

logic input_valid;
logic signed [7:0] input_bytes [0:3];
logic signed [7:0] weight_bytes [0:3][0:3];
logic signed [31:0] partial_sum [0:3];
logic psum_valid;

logic bias_load;
logic signed [7:0] bias_bytes [0:3];
logic signed [5:0] bias_shift;
logic result_load;
logic relu_en;
logic [4:0] output_shift;

memory_wrapper u_memory (
    .clk(clk),
    .rst_n(rst_n),
    .tb_en(tb_en),
    .tb_we(tb_we),
    .tb_addr(tb_addr),
    .tb_wdata(tb_wdata),
    .tb_rdata(tb_rdata),
    .busy(busy),
    .buf_sel(buf_sel),
    .in_addr(in_addr),
    .in_en(in_en),
    .in_data(in_word),
    .out_addr(out_addr),
    .out_we(out_we),
    .out_data(out_word),
    .weight_addr(weight_addr),
    .weight_en(weight_en),
    .weight_data(weight_words),
    .bias_addr(bias_addr),
    .bias_en(bias_en),
    .bias_data(bias_word)
);

unpack_int8x4 u_input_unpack (
    .word_in(in_word),
    .data_out(input_bytes)
);

for (genvar bank = 0; bank < 4; bank++) begin : g_weight_unpack
    unpack_int8x4 u_unpack (
        .word_in(weight_words[bank]),
        .data_out(weight_bytes[bank])
    );
end

unpack_int8x4 u_bias_unpack (
    .word_in(bias_word),
    .data_out(bias_bytes)
);

mac_array u_mac (
    .clk(clk),
    .rst_n(rst_n),
    .input_valid(input_valid),
    .input_data(input_bytes),
    .weight_data(weight_bytes),
    .partial_sum(partial_sum),
    .psum_valid(psum_valid)
);

accumulator_postprocess u_accumulator (
    .clk(clk),
    .rst_n(rst_n),
    .bias_load(bias_load),
    .bias_data(bias_bytes),
    .bias_shift(bias_shift),
    .partial_sum(partial_sum),
    .psum_valid(psum_valid),
    .result_load(result_load),
    .relu_en(relu_en),
    .output_shift(output_shift),
    .output_data(out_word)
);

control_unit u_control (
    .clk(clk),
    .rst_n(rst_n),
    .start(start),
    .busy(busy),
    .done(done),
    .prediction(prediction),
    .buf_sel(buf_sel),
    .in_addr(in_addr),
    .in_en(in_en),
    .argmax_data(in_word),
    .out_addr(out_addr),
    .out_we(out_we),
    .weight_addr(weight_addr),
    .weight_en(weight_en),
    .bias_addr(bias_addr),
    .bias_en(bias_en),
    .mac_input_valid(input_valid),
    .bias_load(bias_load),
    .bias_shift(bias_shift),
    .result_load(result_load),
    .relu_en(relu_en),
    .output_shift(output_shift)
);

endmodule
