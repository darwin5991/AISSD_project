// Shared RTL encoding. The five architectural states are unchanged.
package control_state_pkg;
    typedef enum logic [2:0] {
        IDLE   = 3'd0,
        PREP   = 3'd1,
        RUN    = 3'd2,
        DRAIN  = 3'd3,
        ARGMAX = 3'd4
    } control_state_t;

    function automatic logic state_is_valid(input logic [2:0] value);
        case (value)
            IDLE, PREP, RUN, DRAIN, ARGMAX: state_is_valid = 1'b1;
            default: state_is_valid = 1'b0;
        endcase
    endfunction
endpackage
