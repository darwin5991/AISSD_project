////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : argmax_update
// Description : Select the next {index,value} record, retaining earlier ties.
// Status      : maximum-record update selection implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module argmax_update (
    input  logic                initialize,
    input  logic                compare_en,
    input  logic                greater,

    input  logic        [11:0]  current_record,
    input  logic        [11:0]  candidate_record,

    output logic                write_en,
    output logic        [11:0]  next_record
);

always_comb begin
    write_en = 1'b0;
    next_record = current_record;
    if (initialize || (compare_en && greater)) begin
        write_en = 1'b1;
        next_record = candidate_record;
    end
end

endmodule
