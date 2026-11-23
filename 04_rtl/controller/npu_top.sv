// Programmable NPU with scalar/block execution and independent CSR GEMM.
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
    logic gemm_start,gemm_active,gemm_done,gemm_fault;
    logic [7:0] gemm_config_error,gemm_error_code;
    wire [31:0] gemm_config [0:9];
    wire [6:0] gemm_en,gemm_we;
    wire [14:0] gemm_address [0:6];
    wire [31:0] gemm_wdata [0:6],gemm_rdata [0:6];
    gemm_engine u_gemm(.clk(clk),.rst_n(rst_n),.start(gemm_start),.config_words(gemm_config),
        .config_error(gemm_config_error),.active(gemm_active),.done(gemm_done),.fault(gemm_fault),
        .error_code(gemm_error_code),.ram_en(gemm_en),.ram_we(gemm_we),
        .ram_address(gemm_address),.ram_wdata(gemm_wdata),.ram_rdata(gemm_rdata));
    instruction_controller #(.IMEM_BYTES(IMEM_BYTES),.DMEM_BYTES(DMEM_BYTES)) u_instruction_controller (
        .clk(clk), .rst_n(rst_n), .start(start),
        .load_engine_active(1'b0), .gemm_engine_active(gemm_active),
        .gemm_start(gemm_start),.gemm_config(gemm_config),.gemm_done(gemm_done),
        .gemm_fault(gemm_fault),.gemm_config_error(gemm_config_error),.gemm_error_code(gemm_error_code),
        .busy(busy), .done(done), .fault(fault),
        .imem_en(imem_en), .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_en(dmem_en),.dmem_we(dmem_we),.dmem_addr(dmem_addr),
        .dmem_wdata(dmem_wdata),.dmem_rdata(dmem_rdata),
        .sram_en(sram_en),.sram_we(sram_we),.sram_address(sram_address),
        .sram_wdata(sram_wdata),.sram_rdata(sram_rdata),.sram_error(sram_error),
        .xfer_busy(xfer_busy),.xfer_load_active(xfer_load_active),
        .status(status), .error_code(error_code)
    );
    // Only one instruction owns SRAM; GEMM retains ownership through its final write.
    npu_memory_wrapper u_memory(
        .clk(clk),.rst_n(rst_n),
        .owner(gemm_active?npu_memory_pkg::OWNER_GEMM:(xfer_busy?npu_memory_pkg::OWNER_XFER:npu_memory_pkg::OWNER_NONE)),
        .xfer_en(sram_en),.xfer_we(sram_we),.xfer_address(sram_address),
        .xfer_wdata(sram_wdata),.xfer_rdata(sram_rdata),.xfer_error(sram_error),
        .gemm_en(gemm_en),.gemm_we(gemm_we),.gemm_address(gemm_address),
        .gemm_wdata(gemm_wdata),.gemm_rdata(gemm_rdata),
        .argmax_en(1'b0),.argmax_address(32'd0),.argmax_rdata(),.argmax_error());
endmodule
