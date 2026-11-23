// v1 CSR storage. D-01: retain every RW bit; EXEC will validate configurations.
module csr_file (
    input logic clk, rst_n,
    input logic access_en, write_request, commit_en,
    input logic [11:0] address,
    input logic [31:0] write_data,
    output logic [31:0] read_data,
    output logic [7:0] access_error,
    input logic [31:0] perf_count,
    input logic perf_overflow,
    input logic [31:0] status,
    input logic [7:0] error_code
);
    import npu_isa_pkg::*;
    logic [31:0] settings [0:11];
    integer rw_index;
    logic known;
    always_comb begin
        rw_index = -1;
        case (address)
            CSR_SRC0_BASE: rw_index = 0;
            CSR_SRC1_BASE: rw_index = 1;
            CSR_DST_BASE: rw_index = 2;
            CSR_BIAS_BASE: rw_index = 3;
            CSR_M: rw_index = 4;
            CSR_N: rw_index = 5;
            CSR_K: rw_index = 6;
            CSR_BIAS_SHIFT: rw_index = 7;
            CSR_OUT_SHIFT: rw_index = 8;
            CSR_ACT_MODE: rw_index = 9;
            CSR_ARG_SRC: rw_index = 10;
            CSR_ARG_LEN: rw_index = 11;
            default: begin end
        endcase
        known = 1'b1;
        read_data = 32'd0;
        if (rw_index >= 0)
            read_data = settings[rw_index];
        else begin
            case (address)
                CSR_PERF_COUNT: read_data = perf_count;
                CSR_PERF_OVERFLOW: read_data = {31'd0, perf_overflow};
                CSR_STATUS: read_data = status;
                CSR_ERROR_CODE: read_data = {24'd0, error_code};
                default: known = 1'b0;
            endcase
        end
        access_error = ERR_OK;
        if (access_en && (!known || (write_request && (rw_index < 0))))
            access_error = ERR_INVALID_CSR;
    end
    // Access checking and commit are separate: a faulting instruction cannot write.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (integer i = 0; i < 12; i = i + 1)
                settings[i] <= 32'd0;
        end else if (access_en && write_request && commit_en &&
                     (access_error == ERR_OK) && (rw_index >= 0))
            settings[rw_index] <= write_data;
    end
endmodule
