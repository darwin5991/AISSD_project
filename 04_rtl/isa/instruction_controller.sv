module instruction_controller(
    input logic clk,rst_n,start,output logic busy,done,
    output logic imem_en,output logic [31:0] imem_addr,input logic [31:0] imem_rdata,
    output logic scalar_en,scalar_we,output logic [31:0] scalar_addr,scalar_wdata,input logic [31:0] dmem_rdata,
    output logic dma_start,dma_store,gemm_start,arg_start,
    output logic [1:0] owner,
    output logic [31:0] dma_src,dma_dst,dma_len,
    input logic dma_done,gemm_done,arg_done,dma_active,gemm_active,input logic [3:0] arg_result,
    output logic [31:0] src0,src1,dst,bias,arg_src,
    output logic [20:0] dim,output logic [11:0] cfg,output logic [3:0] arg_len
);
import npu_isa_pkg::*;
ic_state_t state;
logic [31:0] pc,if_id;
id_ex_t id_ex; ex_mem_t ex_mem; mem_wb_t mem_wb;
control_t decoded;
logic [31:0] immediate,r1,r2,r3,alu_y,csr_rdata,count,wb_data;
logic [11:0] csr_addr;
logic overflow,awaited_done,use_mem_wb,rf_we;
instruction_decoder u_decode(if_id,decoded,immediate,csr_addr);
register_file u_gpr(.clk(clk),.rst_n(rst_n),.we(rf_we),.wa(use_mem_wb?mem_wb.rd:ex_mem.rd),
    .wd(wb_data),.ra(if_id[17:15]),.rb(if_id[22:20]),.rc(if_id[9:7]),.a(r1),.b(r2),.c(r3));
scalar_alu u_alu(.a(id_ex.c.alu_src_a?id_ex.pc:id_ex.rs1_data),.b(id_ex.c.alu_src_b?id_ex.imm:id_ex.rs2_data),.op(id_ex.c.alu_op),.y(alu_y));
csr_file u_csr(.clk(clk),.rst_n(rst_n),.we(state==WB && (ex_mem.csr_op==C_WRITE || ex_mem.csr_op==C_SET)),
    .waddr(ex_mem.csr_addr),.raddr(id_ex.csr_addr),.wdata(ex_mem.csr_wdata),.count(count),.halted(state==HALTED),.overflow(overflow),
    .rdata(csr_rdata),.src0(src0),.src1(src1),.dst(dst),.bias(bias),.arg_src(arg_src),.dim(dim),.cfg(cfg),.arg_len(arg_len));
perf_timer u_timer(.clk(clk),.rst_n(rst_n),.tstart(state==WB && ex_mem.sys_op==S_START),.tstop(state==WB && ex_mem.sys_op==S_STOP),
    .dma_active(dma_active),.gemm_active(gemm_active),.count(count),.overflow(overflow));
assign busy=(state!=IDLE && state!=HALTED);
assign imem_en=state==IF_REQ;
assign imem_addr=pc;
assign use_mem_wb=(ex_mem.mem_op!=M_NONE || ex_mem.npu_op!=N_NONE);
assign wb_data=use_mem_wb?mem_wb.result:ex_mem.result;
assign rf_we=state==WB && (use_mem_wb?mem_wb.reg_write:ex_mem.reg_write);
assign scalar_en=state==MEM_START && ex_mem.mem_op!=M_NONE;
assign scalar_we=ex_mem.mem_op==M_SW;
assign scalar_addr=ex_mem.result;
assign scalar_wdata=ex_mem.src;
assign dma_start=state==MEM_START && (ex_mem.npu_op==N_LOAD || ex_mem.npu_op==N_STORE);
assign dma_store=ex_mem.npu_op==N_STORE;
assign gemm_start=state==MEM_START && ex_mem.npu_op==N_GEMM;
assign arg_start=state==MEM_START && ex_mem.npu_op==N_ARG;
assign dma_src=ex_mem.src; assign dma_dst=ex_mem.dst; assign dma_len=ex_mem.len;
always_comb begin
    owner=0;
    if(state==MEM_START || state==MEM_WAIT) case(ex_mem.npu_op)
        N_LOAD,N_STORE:owner=1; N_GEMM:owner=2; N_ARG:owner=3; default:begin end
    endcase
    case(ex_mem.npu_op)
        N_LOAD,N_STORE:awaited_done=dma_done;N_GEMM:awaited_done=gemm_done;N_ARG:awaited_done=arg_done;default:awaited_done=0;
    endcase
end
always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin state<=IDLE;pc<=0;done<=0;id_ex.c<='0;ex_mem<='0;mem_wb.reg_write<=0;end
    else begin
        done<=0;
        case(state)
            IDLE:if(start) begin pc<=0;state<=IF_REQ;end
            IF_REQ:state<=IF_CAPTURE;
            IF_CAPTURE:begin if_id<=imem_rdata;state<=ID;end
            ID:begin
                id_ex.pc<=pc;id_ex.rs1_data<=r1;id_ex.rs2_data<=r2;id_ex.rs3_data<=r3;
                id_ex.imm<=immediate;id_ex.rd<=if_id[9:7];id_ex.csr_addr<=csr_addr;id_ex.c<=decoded;state<=EX;
            end
            EX:begin
                ex_mem.result <= (id_ex.c.wb_sel==1)?id_ex.pc+4:((id_ex.c.wb_sel==2)?csr_rdata:alu_y);
                ex_mem.pc_next<=id_ex.pc+4;
                if(id_ex.c.branch_op==B_JAL || (id_ex.c.branch_op==B_EQ && id_ex.rs1_data==id_ex.rs2_data) ||
                    (id_ex.c.branch_op==B_NE && id_ex.rs1_data!=id_ex.rs2_data)) ex_mem.pc_next<=id_ex.pc+id_ex.imm;
                ex_mem.rd<=id_ex.rd;ex_mem.reg_write<=id_ex.c.reg_write;ex_mem.wb_sel<=id_ex.c.wb_sel;
                ex_mem.mem_op<=id_ex.c.mem_op;ex_mem.npu_op<=id_ex.c.npu_op;ex_mem.csr_op<=id_ex.c.csr_op;
                ex_mem.csr_addr<=id_ex.csr_addr;ex_mem.csr_wdata<=id_ex.c.csr_op==C_SET?id_ex.imm:id_ex.rs1_data;
                ex_mem.sys_op<=id_ex.c.sys_op;
                ex_mem.src<=id_ex.c.mem_op==M_SW?id_ex.rs2_data:id_ex.rs1_data;
                ex_mem.dst<=id_ex.rs2_data;ex_mem.len<=id_ex.rs3_data;
                state<=(id_ex.c.mem_op!=M_NONE || id_ex.c.npu_op!=N_NONE)?MEM_START:WB;
            end
            MEM_START:begin
                if(ex_mem.mem_op==M_SW) begin
                    mem_wb.result<=ex_mem.result;mem_wb.pc_next<=ex_mem.pc_next;
                    mem_wb.rd<=ex_mem.rd;mem_wb.reg_write<=ex_mem.reg_write;state<=WB;
                end else state<=MEM_WAIT;
            end
            MEM_WAIT:if(ex_mem.mem_op==M_LW || awaited_done) begin
                mem_wb.result<=ex_mem.mem_op==M_LW?dmem_rdata:{28'b0,arg_result};
                mem_wb.pc_next<=ex_mem.pc_next;mem_wb.rd<=ex_mem.rd;mem_wb.reg_write<=ex_mem.reg_write;state<=WB;
            end
            WB:if(ex_mem.sys_op==S_END) begin done<=1;state<=HALTED;end
               else begin pc<=use_mem_wb?mem_wb.pc_next:ex_mem.pc_next;state<=IF_REQ;end
            HALTED:begin end
            default:begin end
        endcase
    end
end
endmodule
