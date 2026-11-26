module scalar_alu(input logic [31:0] a,b,input npu_isa_pkg::alu_t op,output logic [31:0] y);
import npu_isa_pkg::*;
always_comb case(op)
    A_AND:y=a&b; A_OR:y=a|b; A_SLL:y=a<<b[4:0]; A_SRL:y=a>>b[4:0]; A_LUI:y=b;
    default:y=a+b;
endcase
endmodule
