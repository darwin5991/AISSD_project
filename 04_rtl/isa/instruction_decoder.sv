// Scalar, CSR/Timer and block instructions. Encoding errors precede operand errors.
module instruction_decoder (
    input logic [31:0] instruction,
    output npu_isa_pkg::scalar_op_t operation,
    output logic [4:0] rd, rs1, rs2,
    output logic [31:0] immediate,
    output logic [11:0] csr_address,
    output logic writes_rd,
    output logic [7:0] error_code
);
    import npu_isa_pkg::*;
    logic uses_rd, uses_rs1, uses_rs2; // LOAD/STORE use RD as read-only rs3.
    always_comb begin
        operation = OP_INVALID;
        rd = instruction[11:7];
        rs1 = instruction[19:15];
        rs2 = instruction[24:20];
        immediate = 32'd0;
        csr_address = instruction[31:20];
        writes_rd = 1'b0;
        uses_rd = 1'b0;
        uses_rs1 = 1'b0;
        uses_rs2 = 1'b0;
        error_code = ERR_OK;
        case (instruction[6:0])
            OPC_LUI: begin
                operation = OP_LUI;
                immediate = {instruction[31:12], 12'd0};
                uses_rd = 1'b1;
                writes_rd = 1'b1;
            end
            OPC_ADDI: begin
                if (instruction[14:12] != 3'b000)
                    error_code = ERR_ILLEGAL_ENCODING;
                operation = OP_ADDI;
                immediate = {{20{instruction[31]}}, instruction[31:20]};
                uses_rd = 1'b1;
                uses_rs1 = 1'b1;
                writes_rd = 1'b1;
            end
            OPC_LW: begin
                operation = OP_LW;
                if (instruction[14:12] != 3'b010)
                    error_code = ERR_ILLEGAL_ENCODING;
                immediate = {{20{instruction[31]}}, instruction[31:20]};
                uses_rd = 1'b1;
                uses_rs1 = 1'b1;
                writes_rd = 1'b1;
            end
            OPC_SW: begin
                operation = OP_SW;
                if (instruction[14:12] != 3'b010)
                    error_code = ERR_ILLEGAL_ENCODING;
                immediate = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};
                uses_rs1 = 1'b1;
                uses_rs2 = 1'b1;
            end
            OPC_ADD: begin
                if ((instruction[14:12] != 3'b000) ||
                    (instruction[31:25] != 7'd0))
                    error_code = ERR_ILLEGAL_ENCODING;
                operation = OP_ADD;
                uses_rd = 1'b1;
                uses_rs1 = 1'b1;
                uses_rs2 = 1'b1;
                writes_rd = 1'b1;
            end
            OPC_BRANCH: begin
                case (instruction[14:12])
                    3'b000: operation = OP_BEQ;
                    3'b001: operation = OP_BNE;
                    default: error_code = ERR_ILLEGAL_ENCODING;
                endcase
                immediate = {{19{instruction[31]}}, instruction[31],
                    instruction[7], instruction[30:25], instruction[11:8], 1'b0};
                uses_rs1 = 1'b1;
                uses_rs2 = 1'b1;
            end
            OPC_JAL: begin
                operation = OP_JAL;
                immediate = {{11{instruction[31]}}, instruction[31],
                    instruction[19:12], instruction[20], instruction[30:21], 1'b0};
                uses_rd = 1'b1;
                writes_rd = 1'b1;
            end
            OPC_SETI: begin
                operation = OP_SETI;
                csr_address = instruction[18:7];
                immediate = {{19{instruction[31]}}, instruction[31:19]};
            end
            OPC_CSR: begin
                case (instruction[14:12])
                    3'b001: begin
                        operation = OP_CSRW;
                        uses_rs1 = 1'b1;
                        if (instruction[11:7] != 5'd0)
                            error_code = ERR_ILLEGAL_ENCODING;
                    end
                    3'b010: begin
                        operation = OP_CSRR;
                        uses_rd = 1'b1;
                        writes_rd = 1'b1;
                        if (instruction[19:15] != 5'd0)
                            error_code = ERR_ILLEGAL_ENCODING;
                    end
                    default: error_code = ERR_ILLEGAL_ENCODING;
                endcase
            end
            OPC_NPU: begin
                if ((instruction[14:12]==3'b000 || instruction[14:12]==3'b001) &&
                    instruction[31:25]==7'd0) begin
                    operation=(instruction[14:12]==3'b000)?OP_LOAD:OP_STORE;
                    uses_rd=1'b1;uses_rs1=1'b1;uses_rs2=1'b1;
                end else if (instruction == INSN_END)
                    operation = OP_END;
                else if (instruction == INSN_TSTART)
                    operation = OP_TSTART;
                else if (instruction == INSN_TSTOP)
                    operation = OP_TSTOP;
                else
                    error_code = ERR_ILLEGAL_ENCODING;
            end
            default: error_code = ERR_INVALID_OPCODE;
        endcase
        // U/J/immediate bit positions are not register references.
        if (error_code == ERR_OK &&
            ((uses_rd && (rd >= 5'd8)) ||
             (uses_rs1 && (rs1 >= 5'd8)) ||
             (uses_rs2 && (rs2 >= 5'd8))))
            error_code = ERR_INVALID_GPR;
    end
endmodule
