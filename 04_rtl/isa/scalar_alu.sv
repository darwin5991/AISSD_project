module scalar_alu (
    input npu_isa_pkg::scalar_op_t operation,
    input logic [31:0] lhs, rhs, immediate, pc,
    output logic [31:0] result,
    output logic [32:0] next_pc
);
    import npu_isa_pkg::*;
    always_comb begin
        result = 32'd0;
        next_pc = {1'b0, pc} + 33'd4;
        case (operation)
            OP_LUI: result = immediate;
            OP_ADDI: result = lhs + immediate;
            OP_ADD: result = lhs + rhs;
            OP_BEQ: if (lhs == rhs)
                next_pc = {1'b0, pc} + {immediate[31], immediate};
            OP_BNE: if (lhs != rhs)
                next_pc = {1'b0, pc} + {immediate[31], immediate};
            OP_JAL: begin
                result = pc + 32'd4;
                next_pc = {1'b0, pc} + {immediate[31], immediate};
            end
            default: begin end
        endcase
    end
endmodule
