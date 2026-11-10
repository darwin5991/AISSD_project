`timescale 1ns / 1ps
// SIMULATION ONLY: selected instead of 04_rtl/memory/memory_wrapper.sv.
// Implements the port contract with behavioral storage; not a BRAM implementation.
module memory_wrapper (
    input logic clk, rst_n,
    input logic tb_en, tb_we,
    input logic [19:0] tb_addr,
    input logic [31:0] tb_wdata,
    output logic [31:0] tb_rdata,
    input logic busy, buf_sel,
    input logic [7:0] in_addr,
    input logic in_en,
    output logic [31:0] in_data,
    input logic [6:0] out_addr,
    input logic out_we,
    input logic [31:0] out_data,
    input logic [14:0] weight_addr,
    input logic weight_en,
    output logic [31:0] weight_data [0:3],
    input logic [7:0] bias_addr,
    input logic bias_en,
    output logic [31:0] bias_data
);
    logic [31:0] buffer_a [0:195];
    logic [31:0] buffer_b [0:127];
    logic [31:0] weights [0:3][0:29279];
    logic [31:0] biases [0:162];

    // Checks restrict this simulation model to the already specified legal inputs.
    // They do not define production RTL behavior for unsupported addresses.
    task automatic legal_address(input integer memory_id, input integer address);
        case (memory_id)
            0: if (address < 0 || address >= 196) $fatal(1, "memory model: A address out of range");
            1: if (address < 0 || address >= 128) $fatal(1, "memory model: B address out of range");
            2, 3, 4, 5: if (address < 0 || address >= 29280) $fatal(1, "memory model: weight address out of range");
            6: if (address < 0 || address >= 163) $fatal(1, "memory model: bias address out of range");
            default: $fatal(1, "memory model: unsupported region");
        endcase
    endtask

    function automatic logic [31:0] read_word(input integer memory_id, input integer address);
        case (memory_id)
            0: read_word = buffer_a[address];
            1: read_word = buffer_b[address];
            2, 3, 4, 5: read_word = weights[memory_id-2][address];
            6: read_word = biases[address];
            default: read_word = 'x;
        endcase
    endfunction

    task automatic write_word(input integer memory_id, input integer address, input logic [31:0] value);
        case (memory_id)
            0: buffer_a[address] <= value;
            1: buffer_b[address] <= value;
            2, 3, 4, 5: weights[memory_id-2][address] <= value;
            6: biases[address] <= value;
        endcase
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Stored contents survive reset. Only read-output registers clear.
            tb_rdata <= 32'd0;
            in_data <= 32'd0;
            bias_data <= 32'd0;
            for (integer bank = 0; bank < 4; bank++) weight_data[bank] <= 32'd0;
        end else if (!busy) begin
            if (tb_en) begin
                if (tb_addr[1:0] !== 2'b00 || $isunknown(tb_addr))
                    $fatal(1, "memory model: TB address must be known and word aligned");
                legal_address(tb_addr[19:17], tb_addr[16:2]);
                if (tb_we)
                    write_word(tb_addr[19:17], tb_addr[16:2], tb_wdata);
                else
                    tb_rdata <= read_word(tb_addr[19:17], tb_addr[16:2]);
            end
        end else begin
            if (tb_en) $fatal(1, "memory model: TB access while busy is outside the scenario");
            if (in_en) begin
                legal_address(buf_sel ? 1 : 0, in_addr);
                in_data <= read_word(buf_sel ? 1 : 0, in_addr);
            end
            if (out_we) begin
                legal_address(buf_sel ? 0 : 1, out_addr);
                write_word(buf_sel ? 0 : 1, out_addr, out_data);
            end
            if (weight_en) begin
                legal_address(2, weight_addr);
                for (integer bank = 0; bank < 4; bank++)
                    weight_data[bank] <= weights[bank][weight_addr];
            end
            if (bias_en) begin
                legal_address(6, bias_addr);
                bias_data <= biases[bias_addr];
            end
        end
    end
endmodule
