////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : argmax_tracker
// Description : Store the current signed maximum and its class index.
// Status      : maximum-value/index record implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module argmax_tracker (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                initialize,
    input  logic                compare_en,
    input  logic                greater,

    input  logic signed [7:0]   candidate,
    input  logic        [3:0]   candidate_index,

    output logic signed [7:0]   max_value,
    output logic        [3:0]   best_index
);

logic [11:0] candidate_record;
logic [11:0] current_record;
logic [11:0] next_record;
logic write_en;

assign candidate_record = {candidate_index, candidate};
assign max_value = current_record[7:0];
assign best_index = current_record[11:8];

argmax_update u_update (
    .initialize(initialize),
    .compare_en(compare_en),
    .greater(greater),
    .current_record(current_record),
    .candidate_record(candidate_record),
    .write_en(write_en),
    .next_record(next_record)
);

register_en #(.WIDTH(12)) u_record (
    .clk(clk),
    .rst_n(rst_n),
    .en(write_en),
    .data_in(next_record),
    .data_out(current_record)
);

endmodule
