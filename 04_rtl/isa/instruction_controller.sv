// Blocking scalar controller: request R, capture R+1, execute R+2.
// CSR/Timer commit shares scalar fault checks. Engine inputs are qualified activity.
module instruction_controller #(
    parameter logic [32:0] IMEM_BYTES = npu_isa_pkg::DEFAULT_IMEM_BYTES,
    parameter logic [32:0] DMEM_BYTES = npu_isa_pkg::DEFAULT_DMEM_BYTES
) (
    input logic clk, rst_n, start,
    input logic load_engine_active, gemm_engine_active,
    output logic gemm_start,
    output logic [31:0] gemm_config [0:9],
    input logic gemm_done,gemm_fault,
    input logic [7:0] gemm_config_error,gemm_error_code,
    output logic busy, done, fault,
    output logic imem_en,
    output logic [31:0] imem_addr,
    input logic [31:0] imem_rdata,
    output logic dmem_en,dmem_we,
    output logic [31:0] dmem_addr,dmem_wdata,
    input logic [31:0] dmem_rdata,
    output logic sram_en,sram_we,
    output logic [31:0] sram_address,sram_wdata,
    input logic [31:0] sram_rdata,
    input logic [7:0] sram_error,
    output logic xfer_busy,xfer_load_active,
    output logic [31:0] status,
    output logic [7:0] error_code
);
    import npu_isa_pkg::*;
    typedef enum logic [3:0] {
        IDLE, FETCH_REQ, FETCH_WAIT, EXECUTE, HALTED, FAULT_HALT, XFER_ARGS, XFER_WAIT, MEM_REQ, MEM_WAIT, GEMM_CHECK, GEMM_START, GEMM_WAIT, XFER_REJECT
    } state_t;
    state_t state;
    wire [31:0] gemm_settings [0:9];
    logic [31:0] gemm_next_pc;
    logic [7:0] gemm_next_pc_error,gemm_check_error;
    function automatic logic [2:0] memory_error_rank(input logic [7:0] code);
        case(code)
            ERR_MISALIGNED: memory_error_rank=0;
            ERR_INVALID_REGION: memory_error_rank=1;
            ERR_MEMORY_BOUNDS: memory_error_rank=2;
            ERR_INVALID_CONFIG: memory_error_rank=3;
            default: memory_error_rank=4;
        endcase
    endfunction
    function automatic logic [7:0] merge_memory_errors(input logic [7:0] first,second);
        if(first==ERR_OK) merge_memory_errors=second;
        else if(second==ERR_OK) merge_memory_errors=first;
        else merge_memory_errors=(memory_error_rank(first)<=memory_error_rank(second))?first:second;
    endfunction
    assign gemm_check_error=merge_memory_errors(gemm_next_pc_error,gemm_config_error);
    logic is_scalar_memory;
    logic [32:0] scalar_effective;
    logic [7:0] scalar_memory_error,scalar_check_error;
    logic [31:0] scalar_address,scalar_write_data,scalar_next_pc;
    logic xfer_dmem_en,xfer_dmem_we;
    logic [31:0] xfer_dmem_addr,xfer_dmem_wdata;
    localparam logic [33:0] DMEM_END =
        {2'b00,npu_isa_pkg::DMEM_BASE}+{1'b0,DMEM_BYTES};
    // Approved Phase 4 order: alignment, arithmetic wrap, region, capacity.
    function automatic logic [7:0] check_scalar_memory(input logic [32:0] address);
        if(address[1:0]!=0) check_scalar_memory=ERR_MISALIGNED;
        else if(address[32]) check_scalar_memory=ERR_MEMORY_BOUNDS;
        else if(address[31:28]!=4'h1) check_scalar_memory=ERR_INVALID_REGION;
        else if({1'b0,address}+34'd4>DMEM_END)
            check_scalar_memory=ERR_MEMORY_BOUNDS;
        else check_scalar_memory=ERR_OK;
    endfunction
    logic [31:0] pc, instruction;
    scalar_op_t operation;
    logic [4:0] rd, rs1, rs2;
    logic [31:0] transfer_src,transfer_dst,transfer_next_pc;
    logic transfer_done,transfer_fault,is_transfer;
    logic [7:0] transfer_fault_code;
    logic [7:0] transfer_pc_error,transfer_data_error,transfer_check_error,transfer_precheck_error;
    logic [2:0] rs2_read_address;
    logic [31:0] immediate, rs1_data, rs2_data, alu_result;
    logic [11:0] csr_address;
    logic [31:0] csr_read_data, csr_write_data, register_write_data;
    logic [31:0] perf_count;
    logic perf_overflow, timer_armed, timer_start, timer_stop;
    logic csr_access, csr_write_request, instruction_commit;
    logic [7:0] csr_error, execute_error;
    logic [32:0] next_pc;
    logic writes_rd, register_write;
    logic [7:0] decode_error, fetch_error, next_pc_error;
    localparam logic [33:0] IMEM_END =
        {2'b00, IMEM_BASE} + {1'b0, IMEM_BYTES};

    function automatic logic [7:0] check_pc(input logic [32:0] address);
        if (address[1:0] != 2'b00)
            check_pc = ERR_MISALIGNED;
        else if (address[32] || (address[31:0] < IMEM_BASE) ||
                 ({1'b0, address} + 34'd4 > IMEM_END))
            check_pc = ERR_MEMORY_BOUNDS;
        else
            check_pc = ERR_OK;
    endfunction

    instruction_decoder u_decoder (
        .instruction(instruction), .operation(operation),
        .rd(rd), .rs1(rs1), .rs2(rs2), .immediate(immediate),
        .writes_rd(writes_rd), .csr_address(csr_address), .error_code(decode_error)
    );
    register_file u_register_file (
        .clk(clk), .rst_n(rst_n),
        .rs1_addr(rs1[2:0]), .rs2_addr(rs2_read_address),
        .rs1_data(rs1_data), .rs2_data(rs2_data),
        .write_en(register_write), .write_addr(rd[2:0]),
        .write_data(register_write_data)
    );
    scalar_alu u_alu (
        .operation(operation), .lhs(rs1_data), .rhs(rs2_data),
        .immediate(immediate), .pc(pc), .result(alu_result), .next_pc(next_pc)
    );
    csr_file u_csr (
        .clk(clk), .rst_n(rst_n), .access_en(csr_access),
        .write_request(csr_write_request), .commit_en(instruction_commit),
        .address(csr_address), .write_data(csr_write_data),
        .read_data(csr_read_data), .access_error(csr_error), .gemm_settings(gemm_settings),
        .perf_count(perf_count), .perf_overflow(perf_overflow),
        .status(status), .error_code(error_code)
    );
    perf_timer u_timer (
        .clk(clk), .rst_n(rst_n), .timer_start(timer_start), .timer_stop(timer_stop),
        .load_active(load_engine_active || xfer_load_active), .gemm_active(gemm_engine_active),
        .count(perf_count), .overflow(perf_overflow), .armed(timer_armed)
    );
    block_transfer #(.DMEM_BYTES(DMEM_BYTES)) u_transfer(
        .clk(clk),.rst_n(rst_n),.start(rst_n && state==XFER_ARGS && transfer_check_error==ERR_OK),
        .is_store(operation==OP_STORE),.source_address(transfer_src),
        .destination_address(transfer_dst),.length_bytes(rs2_data),
        .busy(xfer_busy),.done(transfer_done),.fault(transfer_fault),
        .load_active(xfer_load_active),.error_code(transfer_fault_code),
        .dmem_en(xfer_dmem_en),.dmem_we(xfer_dmem_we),.dmem_addr(xfer_dmem_addr),
        .dmem_wdata(xfer_dmem_wdata),.dmem_rdata(dmem_rdata),
        .sram_en(sram_en),.sram_we(sram_we),.sram_address(sram_address),
        .sram_wdata(sram_wdata),.sram_rdata(sram_rdata),.sram_error(sram_error));
    assign transfer_data_error=npu_memory_pkg::transfer_error(transfer_src,transfer_dst,
        rs2_data,operation==OP_STORE,DMEM_BYTES);
    assign transfer_check_error=merge_memory_errors(transfer_pc_error,transfer_data_error);
    assign gemm_start=rst_n && state==GEMM_START;
    assign is_scalar_memory=(operation==OP_LW)||(operation==OP_SW);
    // Base is unsigned, immediate is signed. Keep carry/borrow before truncation.
    assign scalar_effective={1'b0,rs1_data}+{immediate[31],immediate};
    assign scalar_memory_error=check_scalar_memory(scalar_effective);
    assign scalar_check_error=merge_memory_errors(next_pc_error,scalar_memory_error);
    // Instruction-serial port ownership; no arbitration, buffering or latency change.
    always_comb begin
        dmem_en=1'b0;dmem_we=1'b0;dmem_addr=32'd0;dmem_wdata=32'd0;
        if(rst_n && state==MEM_REQ) begin
            dmem_en=1'b1;dmem_we=(operation==OP_SW);
            dmem_addr=scalar_address;dmem_wdata=scalar_write_data;
        end else if(rst_n && state==XFER_WAIT) begin
            dmem_en=xfer_dmem_en;dmem_we=xfer_dmem_we;
            dmem_addr=xfer_dmem_addr;dmem_wdata=xfer_dmem_wdata;
        end
    end
    assign is_transfer=(operation==OP_LOAD)||(operation==OP_STORE);
    assign rs2_read_address=(state==XFER_ARGS)?rd[2:0]:rs2[2:0];
    assign csr_access = rst_n && (state == EXECUTE) &&
        ((operation == OP_SETI) || (operation == OP_CSRW) || (operation == OP_CSRR));
    assign csr_write_request = (operation == OP_SETI) || (operation == OP_CSRW);
    assign csr_write_data = (operation == OP_SETI) ? immediate : rs1_data;
    assign register_write_data = (operation == OP_LW) ? dmem_rdata :
        ((operation == OP_CSRR) ? csr_read_data : alu_result);
    assign execute_error = (decode_error != ERR_OK) ? decode_error : csr_error;
    assign instruction_commit = rst_n && (state == EXECUTE) &&
        (execute_error == ERR_OK) && (operation != OP_END) &&
        !is_scalar_memory && operation!=OP_GEMM && (next_pc_error == ERR_OK);
    assign timer_start = instruction_commit && (operation == OP_TSTART);
    assign timer_stop = instruction_commit && (operation == OP_TSTOP);
    assign fetch_error = check_pc({1'b0, pc});
    assign next_pc_error = check_pc(next_pc);
    assign imem_addr = pc;
    assign imem_en = rst_n && (state == FETCH_REQ) && (fetch_error == ERR_OK);
    assign busy = (state == FETCH_REQ) || (state == FETCH_WAIT) || (state == EXECUTE) ||
        (state == XFER_ARGS) || (state == XFER_WAIT) ||
        (state == MEM_REQ) || (state == MEM_WAIT) ||
        (state == GEMM_CHECK) || (state == GEMM_START) || (state == GEMM_WAIT) ||
        (state == XFER_REJECT);
    assign fault = (state == FAULT_HALT);
    // No architectural write occurs on decode/target failure (including JAL link).
    assign register_write = (instruction_commit && writes_rd) ||
        (rst_n && state==MEM_WAIT && operation==OP_LW);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            pc <= IMEM_BASE;
            instruction <= 32'd0;
            transfer_src<=0;transfer_dst<=0;transfer_next_pc<=0;
            transfer_pc_error<=ERR_OK;transfer_precheck_error<=ERR_OK;
            scalar_address<=0;scalar_write_data<=0;scalar_next_pc<=0;
            gemm_next_pc<=0;gemm_next_pc_error<=ERR_OK;
            for(integer g=0;g<10;g++) gemm_config[g]<=0;
            done <= 1'b0;
            status <= STATUS_RUNNING;
            error_code <= ERR_OK;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (start) begin
                    pc <= IMEM_BASE;
                    state <= FETCH_REQ;
                end
                FETCH_REQ: begin
                    if (fetch_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= fetch_error;
                    end else
                        state <= FETCH_WAIT;
                end
                FETCH_WAIT: begin
                    instruction <= imem_rdata;
                    state <= EXECUTE;
                end
                EXECUTE: begin
                    if (execute_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= execute_error;
                    end else if (operation == OP_END) begin
                        state <= HALTED;
                        status <= STATUS_END;
                        done <= 1'b1;
                    end else if(operation==OP_GEMM) begin
                        // Snapshot first, then merge all memory/config errors by ISA priority.
                        for(integer g=0;g<10;g++) gemm_config[g]<=gemm_settings[g];
                        gemm_next_pc<=next_pc[31:0];gemm_next_pc_error<=next_pc_error;state<=GEMM_CHECK;
                    end else if(is_scalar_memory) begin
                        if(scalar_check_error!=ERR_OK) begin
                            state<=FAULT_HALT;status<=STATUS_ERROR;
                            error_code<=scalar_check_error;
                        end else begin
                            scalar_address<=scalar_effective[31:0];
                            scalar_write_data<=rs2_data;scalar_next_pc<=next_pc[31:0];
                            state<=MEM_REQ;
                        end
                    end else if(is_transfer) begin
                        transfer_src<=rs1_data;transfer_dst<=rs2_data;
                        transfer_next_pc<=next_pc[31:0];transfer_pc_error<=next_pc_error;state<=XFER_ARGS;
                    end else if (next_pc_error != ERR_OK) begin
                        state <= FAULT_HALT;
                        status <= STATUS_ERROR;
                        error_code <= next_pc_error;
                    end else begin
                        pc <= next_pc[31:0];
                        state <= FETCH_REQ;
                    end
                end
                // Read R is consumed at R+1. SW also completes after its write edge.
                MEM_REQ: state<=MEM_WAIT;
                MEM_WAIT: begin pc<=scalar_next_pc;state<=FETCH_REQ;end
                GEMM_CHECK: begin
                    if(gemm_check_error!=ERR_OK) begin
                        state<=FAULT_HALT;status<=STATUS_ERROR;error_code<=gemm_check_error;
                    end else state<=GEMM_START;
                end
                GEMM_START: state<=GEMM_WAIT;
                GEMM_WAIT: begin
                    if(gemm_fault) begin
                        state<=FAULT_HALT;status<=STATUS_ERROR;error_code<=gemm_error_code;
                    end else if(gemm_done) begin pc<=gemm_next_pc;state<=FETCH_REQ;end
                end
                XFER_ARGS: begin
                    // Third operand is available here; reject before any engine start.
                    transfer_precheck_error<=transfer_check_error;
                    if(transfer_check_error!=ERR_OK) state<=XFER_REJECT;
                    else state<=XFER_WAIT;
                end
                XFER_REJECT: begin
                    state<=FAULT_HALT;status<=STATUS_ERROR;error_code<=transfer_precheck_error;
                end
                XFER_WAIT: begin
                    if(transfer_fault) begin
                        state<=FAULT_HALT;status<=STATUS_ERROR;
                        error_code<=transfer_fault_code;
                    end else if(transfer_done) begin
                        pc<=transfer_next_pc;state<=FETCH_REQ;
                    end
                end
                HALTED: begin end
                FAULT_HALT: begin end
                default: begin
                    state <= FAULT_HALT;
                    status <= STATUS_ERROR;
                    error_code <= ERR_ILLEGAL_ENCODING;
                end
            endcase
        end
    end
endmodule
