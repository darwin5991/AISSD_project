////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : control_fsm
// Description : IDLE / PREP / RUN / DRAIN / ARGMAX state and execution status.
// Status      : five-state controller implemented
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Shared 3-bit encoding; unused states return to IDLE on the next clock.

module control_fsm (
    input  logic                clk,
    input  logic                rst_n,

    input  logic                start,
    input  logic        [1:0]   layer_index,

    input  logic                prep_done,
    input  logic                last_read,
    input  logic                layer_stored,
    input  logic                argmax_done,

    output logic        [2:0]   state,
    output logic                busy,
    output logic                done
);

import control_state_pkg::*;
logic [2:0] next_state;

always_comb begin
    next_state = state;
    case (state)
        IDLE: if (start) next_state = PREP;
        PREP: if (prep_done) begin
            if (layer_index == 2'd3)
                next_state = ARGMAX;
            else
                next_state = RUN;
        end
        RUN: if (last_read) next_state = DRAIN;
        DRAIN: if (layer_stored) next_state = PREP;
        ARGMAX: if (argmax_done) next_state = IDLE;
        default: next_state = IDLE;
    endcase
end

always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= IDLE;
        busy <= 1'b0;
        done <= 1'b0;
    end else begin
        state <= next_state;
        busy <= (next_state != IDLE);
        done <= (state == ARGMAX) && argmax_done;
    end
end

endmodule
