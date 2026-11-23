// Phase 2 scalar/CSR/Timer top. Legacy MLP datapath remains untouched.
module npu_top #(
    parameter logic [32:0] IMEM_BYTES = npu_isa_pkg::DEFAULT_IMEM_BYTES,
    parameter logic [32:0] DMEM_BYTES = npu_isa_pkg::DEFAULT_DMEM_BYTES
) (
    input logic clk, rst_n, start,
    output logic busy, done, fault,
    output logic imem_en,
    output logic [31:0] imem_addr,
    input logic [31:0] imem_rdata,
    output logic dmem_en, dmem_we,
    output logic [31:0] dmem_addr, dmem_wdata,
    input logic [31:0] dmem_rdata
);
    logic [31:0] status;
    logic [7:0] error_code;
    logic sram_en,sram_we,xfer_busy,xfer_load_active;
    logic [31:0] sram_address,sram_wdata,sram_rdata;
    logic [7:0] sram_error;
    wire [14:0] gemm_address [0:6];
    wire [31:0] gemm_wdata [0:6],gemm_rdata [0:6];
    for(genvar b=0;b<7;b++) begin:g_unused_compute_ports
        assign gemm_address[b]=0;assign gemm_wdata[b]=0;
    end
    instruction_controller #(.IMEM_BYTES(IMEM_BYTES),.DMEM_BYTES(DMEM_BYTES)) u_instruction_controller (
        .clk(clk), .rst_n(rst_n), .start(start),
        .load_engine_active(1'b0), .gemm_engine_active(1'b0),
        .busy(busy), .done(done), .fault(fault),
        .imem_en(imem_en), .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_en(dmem_en),.dmem_we(dmem_we),.dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata),.dmem_rdata(dmem_rdata),
        .sram_en(sram_en),.sram_we(sram_we),.sram_address(sram_address),
        .sram_wdata(sram_wdata),.sram_rdata(sram_rdata),.sram_error(sram_error),
        .xfer_busy(xfer_busy),.xfer_load_active(xfer_load_active),
        .status(status), .error_code(error_code)
    );
    // Owner choice is instruction-serial. No compute engine is instantiated here.
    npu_memory_wrapper u_memory(
        .clk(clk),.rst_n(rst_n),
        .owner(xfer_busy?npu_memory_pkg::OWNER_XFER:npu_memory_pkg::OWNER_NONE),
        .xfer_en(sram_en),.xfer_we(sram_we),.xfer_address(sram_address),
        .xfer_wdata(sram_wdata),.xfer_rdata(sram_rdata),.xfer_error(sram_error),
        .gemm_en(7'd0),.gemm_we(7'd0),.gemm_address(gemm_address),
        .gemm_wdata(gemm_wdata),.gemm_rdata(gemm_rdata),
        .argmax_en(1'b0),.argmax_address(32'd0),.argmax_rdata(),.argmax_error());
endmodule
