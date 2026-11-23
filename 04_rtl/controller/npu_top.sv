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
    instruction_controller #(.IMEM_BYTES(IMEM_BYTES)) u_instruction_controller (
        .clk(clk), .rst_n(rst_n), .start(start),
        .load_engine_active(1'b0), .gemm_engine_active(1'b0),
        .busy(busy), .done(done), .fault(fault),
        .imem_en(imem_en), .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .status(status), .error_code(error_code)
    );
    // No engines yet: qualified activity is tied low. No new public test ports.
    // DMEM/block transfer/SRAM/compute remain later phases.
    assign dmem_en = 1'b0;
    assign dmem_we = 1'b0;
    assign dmem_addr = 32'd0;
    assign dmem_wdata = 32'd0;
endmodule
