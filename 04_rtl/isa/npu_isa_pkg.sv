package npu_isa_pkg;
    typedef enum logic [3:0] {IDLE,IF_REQ,IF_CAPTURE,ID,EX,MEM_START,MEM_WAIT,WB,HALTED} ic_state_t;
    typedef enum logic [3:0] {A_ADD,A_AND,A_OR,A_SLL,A_SRL,A_LUI} alu_t;
    typedef enum logic [1:0] {B_NONE,B_EQ,B_NE,B_JAL} branch_t;
    typedef enum logic [1:0] {M_NONE,M_LW,M_SW} mem_t;
    typedef enum logic [2:0] {N_NONE,N_LOAD,N_STORE,N_GEMM,N_ARG} npu_t;
    typedef enum logic [1:0] {C_NONE,C_READ,C_WRITE,C_SET} csr_t;
    typedef enum logic [1:0] {S_NONE,S_START,S_STOP,S_END} sys_t;
    typedef struct packed {
        alu_t alu_op; logic alu_src_a,alu_src_b; branch_t branch_op;
        mem_t mem_op; csr_t csr_op; npu_t npu_op; sys_t sys_op;
        logic reg_write; logic [2:0] wb_sel;
    } control_t;
    typedef struct packed {
        logic [31:0] pc,rs1_data,rs2_data,rs3_data,imm;
        logic [2:0] rd; logic [11:0] csr_addr; control_t c;
    } id_ex_t;
    typedef struct packed {
        logic [31:0] result,pc_next; logic [2:0] rd; logic reg_write;
        logic [2:0] wb_sel; mem_t mem_op; npu_t npu_op; csr_t csr_op;
        logic [11:0] csr_addr; logic [31:0] csr_wdata; sys_t sys_op;
        logic [31:0] src,dst,len;
    } ex_mem_t;
    typedef struct packed {logic [31:0] result,pc_next; logic [2:0] rd; logic reg_write;} mem_wb_t;
endpackage
