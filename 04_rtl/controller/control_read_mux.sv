////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : control_read_mux
// Description : Select MLP or ARGMAX access to the shared input-memory port.
// Status      : shared MLP/ARGMAX input-port selection implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////

module control_read_mux (
    input  logic        [2:0]   state,
    input  logic                layer_buf_sel,

    input  logic        [7:0]   mlp_addr,
    input  logic                mlp_en,

    input  logic        [7:0]   argmax_addr,
    input  logic                argmax_en,

    output logic                buf_sel,
    output logic        [7:0]   in_addr,
    output logic                in_en
);

import control_state_pkg::*;

always_comb begin
    buf_sel = layer_buf_sel;
    in_addr = mlp_addr;
    in_en = 1'b0;
    case (state)
        RUN: in_en = mlp_en;
        ARGMAX: begin
            buf_sel = 1'b1;
            in_addr = argmax_addr;
            in_en = argmax_en;
        end
        default: begin end
    endcase
end

endmodule
