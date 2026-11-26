module instruction_decoder (
    input logic [31:0] instr,
    output npu_isa_pkg::control_t c,
    output logic [31:0] imm,
    output logic [11:0] csr_addr
);
import npu_isa_pkg::*;
always_comb begin
    c='0; c.alu_op=A_ADD; imm={{20{instr[31]}},instr[31:20]}; csr_addr=instr[31:20];
    case(instr[6:0])
        7'h37: begin c.alu_op=A_LUI; c.alu_src_b=1; c.reg_write=1; imm={instr[31:12],12'b0}; end
        7'h33: begin
            c.reg_write=1;
            case(instr[14:12])
                7: c.alu_op=A_AND;
                6: c.alu_op=A_OR;
                default: c.alu_op=A_ADD;
            endcase
        end
        7'h13: begin
            c.reg_write=1; c.alu_src_b=1;
            case(instr[14:12])
                7:c.alu_op=A_AND; 6:c.alu_op=A_OR; 1:c.alu_op=A_SLL; 5:c.alu_op=A_SRL;
                default:c.alu_op=A_ADD;
            endcase
        end
        7'h63: begin
            c.branch_op=(instr[14:12]==0)?B_EQ:B_NE;
            imm={{19{instr[31]}},instr[31],instr[7],instr[30:25],instr[11:8],1'b0};
        end
        7'h6f: begin
            c.branch_op=B_JAL; c.reg_write=1; c.wb_sel=1;
            imm={{11{instr[31]}},instr[31],instr[19:12],instr[20],instr[30:21],1'b0};
        end
        7'h03: begin c.mem_op=M_LW; c.alu_src_b=1; c.reg_write=1; c.wb_sel=3; end
        7'h23: begin c.mem_op=M_SW; c.alu_src_b=1; imm={{20{instr[31]}},instr[31:25],instr[11:7]}; end
        7'h73: begin
            if(instr[14:12]==1) c.csr_op=C_WRITE;
            else begin c.csr_op=C_READ; c.reg_write=1; c.wb_sel=2; end
        end
        7'h0b: begin c.csr_op=C_SET; csr_addr=instr[18:7]; imm={{19{instr[31]}},instr[31:19]}; end
        7'h2b: case(instr[14:12])
            0:c.npu_op=N_LOAD;
            1:c.npu_op=N_STORE;
            2:if(instr[31:25]==0) c.npu_op=N_GEMM;
              else begin c.npu_op=N_ARG; c.reg_write=1; c.wb_sel=3; end
            3:case(instr[31:25])
                0:c.sys_op=S_START; 1:c.sys_op=S_STOP; 2:c.sys_op=S_END;
                default:begin end
            endcase
            default:begin end
        endcase
        default:begin end
    endcase
end
endmodule
