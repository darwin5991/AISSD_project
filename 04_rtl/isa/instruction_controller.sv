// Blocking scalar controller: request R, capture R+1, execute R+2.
// Status/error are internal state for Phase 1 diagnostics; no CSR bank is present.
module instruction_controller #(
    parameter logic [32:0] IMEM_BYTES = npu_isa_pkg::DEFAULT_IMEM_BYTES
) (
    input logic clk, rst_n, start,
    output logic busy, done, fault,
    output logic imem_en,
    output logic [31:0] imem_addr,
    input logic [31:0] imem_rdata,
    output logic [31:0] status,
    output logic [7:0] error_code
);
    import npu_isa_pkg::*;
    typedef enum logic [2:0] {
        IDLE, FETCH_REQ, FETCH_WAIT, EXECUTE, HALTED, FAULT_HALT
    } state_t;
    state_t state;
    logic [31:0] pc, instruction;
    scalar_op_t operation;
    logic [4:0] rd, rs1, rs2;
    logic [31:0] immediate, rs1_data, rs2_data, alu_result;
    logic [32:0] next_pc;
    logic writes_rd, register_write;
    logic [7:0] decode_error, fetch_error, next_pc_error;
    localparam logic [33:0] IMEM_END =
        {2'b00, IMEM_BASE} + {1'b0, IMEM_BYTES};

    function automatic logic [7:0] check_pc(input logic [32:0] address);
        if (address[1:0] != 2'b00)
            check_pc = ERR_MISALIGNED;
        else if (address[32] || (address[31:0] < IMEM_BASE) ||
                 ({1'b0, address} + 34'd4 > IMEM_END))
            check_pc = ERR_MEMORY_BOUNDS;
        else
            check_pc = ERR_OK;
    endfunction

    instruction_decoder u_decoder (
        .instruction(instruction), .operation(operation),
        .rd(rd), .rs1(rs1), .rs2(rs2), .immediate(immediate),
        .writes_rd(writes_rd), .error_code(decode_error)
    );
    register_file u_register_file (
        .clk(clk), .rst_n(rst_n),
        .rs1_addr(rs1[2:0]), .rs2_addr(rs2[2:0]),
        .rs1_data(rs1_data), .rs2_data(rs2_data),
        .write_en(register_write), .write_addr(rd[2:0]),
        .write_data(alu_result)
    );
    scalar_alu u_alu (
        .operation(operation), .lhs(rs1_data), .rhs(rs2_data),
        .immediate(immediate), .pc(pc), .result(alu_result), .next_pc(next_pc)
    );
    assign fetch_error = check_pc({1'b0, pc});
    assign next_pc_error = check_pc(next_pc);
    assign imem_addr = pc;
    assign imem_en = rst_n && (state == FETCH_REQ) && (fetch_error == ERR_OK);
    assign busy = (state == FETCH_REQ) || (state == FETCH_WAIT) || (state == EXECUTE);
    assign fault = (state == FAULT_HALT);
    // No architectural write occurs on decode/target failure (including JAL link).
    assign register_write = rst_n && (state == EXECUTE) &&
        (decode_error == ERR_OK) && (operation != OP_END) &&
        (next_pc_error == ERR_OK) && writes_rd;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            pc <= IMEM_BASE;
            instruction <= 32'd0;
            done <= 1'b0;
            status <= STATUS_RUNNING;
            error_code <= ERR_OK;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (start) begin
                    pc <= IMEM_BASE;
                    state <= FETCH_REQ;
                end
                FETCH_REQ: begin
                    if (fetch_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= fetch_error;
                    end else
                        state <= FETCH_WAIT;
                end
                FETCH_WAIT: begin
                    instruction <= imem_rdata;
                    state <= EXECUTE;
                end
                EXECUTE: begin
                    if (decode_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= decode_error;
                    end else if (operation == OP_END) begin
                        state <= HALTED;
                        status <= STATUS_END;
                        done <= 1'b1;
                    end else if (next_pc_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= next_pc_error;
                    end else begin
                        pc <= next_pc[31:0];
                        state <= FETCH_REQ;
                    end
                end
                HALTED: begin end
                FAULT_HALT: begin end
                default: begin
                    state <= FAULT_HALT;
                    status <= STATUS_ERROR;
                    error_code <= ERR_ILLEGAL_ENCODING;
                end
            endcase
        end
    end
endmodule
