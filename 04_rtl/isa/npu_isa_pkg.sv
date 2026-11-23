// Programmable NPU v1.0: scalar, CSR/Timer and block transfer constants.
package npu_isa_pkg;
    localparam logic [31:0] IMEM_BASE = 32'h0000_0000;
    localparam logic [31:0] DMEM_BASE = 32'h1000_0000;
    localparam logic [32:0] DEFAULT_IMEM_BYTES = 33'd65536;
    localparam logic [32:0] DEFAULT_DMEM_BYTES = 33'd16777216;

    localparam logic [6:0] OPC_LUI = 7'h37, OPC_ADDI = 7'h13,
        OPC_ADD = 7'h33, OPC_BRANCH = 7'h63, OPC_JAL = 7'h6f,
        OPC_LW = 7'h03, OPC_SW = 7'h23, OPC_CSR = 7'h73,
        OPC_SETI = 7'h0b, OPC_NPU = 7'h2b;
    localparam logic [31:0] INSN_END = 32'h0400_302b,
        INSN_GEMM = 32'h0000_202b,
        INSN_TSTART = 32'h0000_302b, INSN_TSTOP = 32'h0200_302b;
    localparam logic [11:0] CSR_SRC0_BASE = 12'h7c0,
        CSR_SRC1_BASE = 12'h7c1, CSR_DST_BASE = 12'h7c2,
        CSR_BIAS_BASE = 12'h7c3, CSR_M = 12'h7c4, CSR_N = 12'h7c5,
        CSR_K = 12'h7c6, CSR_BIAS_SHIFT = 12'h7c7,
        CSR_OUT_SHIFT = 12'h7c8, CSR_ACT_MODE = 12'h7c9,
        CSR_ARG_SRC = 12'h7e0, CSR_ARG_LEN = 12'h7e1,
        CSR_PERF_COUNT = 12'h7f0, CSR_PERF_OVERFLOW = 12'h7f1,
        CSR_STATUS = 12'h7f2, CSR_ERROR_CODE = 12'h7f3;

    localparam logic [7:0] ERR_OK = 8'h00, ERR_INVALID_OPCODE = 8'h01,
        ERR_INVALID_GPR = 8'h02, ERR_INVALID_CSR = 8'h03,
        ERR_INVALID_REGION = 8'h04, ERR_MISALIGNED = 8'h05,
        ERR_MEMORY_BOUNDS = 8'h06, ERR_INVALID_CONFIG = 8'h07,
        ERR_ILLEGAL_ENCODING = 8'h08;
    localparam logic [31:0] STATUS_RUNNING = 32'd0,
        STATUS_END = 32'd1, STATUS_ERROR = 32'd2;

    typedef enum logic [4:0] {
        OP_INVALID, OP_LUI, OP_ADDI, OP_ADD,
        OP_BEQ, OP_BNE, OP_JAL, OP_END,
        OP_SETI, OP_CSRW, OP_CSRR, OP_TSTART, OP_TSTOP, OP_LOAD, OP_STORE, OP_LW, OP_SW, OP_GEMM
    } scalar_op_t;
endpackage
