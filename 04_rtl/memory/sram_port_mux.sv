// One selected owner; no priority arbitration or queued/concurrent commands.
module sram_port_mux (
    input logic [1:0] owner,
    input logic xfer_en,xfer_we,
    input logic [14:0] xfer_addr,
    input logic [31:0] xfer_wdata,
    input logic gemm_en,gemm_we,
    input logic [14:0] gemm_addr,
    input logic [31:0] gemm_wdata,
    input logic argmax_en,
    input logic [14:0] argmax_addr,
    output logic ram_en,ram_we,
    output logic [14:0] ram_addr,
    output logic [31:0] ram_wdata
);
    import npu_memory_pkg::*;
    always_comb begin
        ram_en=0;ram_we=0;ram_addr=0;ram_wdata=0;
        case(owner)
            OWNER_XFER: begin
                ram_en=xfer_en;ram_we=xfer_we;ram_addr=xfer_addr;ram_wdata=xfer_wdata;
            end
            OWNER_GEMM: begin
                ram_en=gemm_en;ram_we=gemm_we;ram_addr=gemm_addr;ram_wdata=gemm_wdata;
            end
            OWNER_ARGMAX: begin ram_en=argmax_en;ram_addr=argmax_addr;end
            default: begin end
        endcase
    end
endmodule
