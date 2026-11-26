# Hardware architecture — target contract

## Top and hierarchy
```
external IMEM ────── instruction_controller ─── GPR / CSR / ALU / perf_timer
                             │ start / done / parameters
external DMEM ── dmem_port_mux ── DMA controller    GEMM controller    ARGMAX engine
                       │              │                 │                  │
                       └──────────────┴──── memory_wrapper (7 bank MUXs) ──┘
                                                   │  input + W[0:3] + bias
                                              unpack_int8x4 (instances)
                                                   │
                                                mac_array
                                                   │
                                           accumulator_postprocess
                                                   │ packed output → SRAM
```
Direct children of `npu_top`: `instruction_controller`, `dma_controller`, `gemm_controller`, `argmax_engine`, `dmem_port_mux`, `memory_wrapper`, `mac_array`, `accumulator_postprocess`, `unpack_int8x4` instances. GPR/CSR/ALU/decoder/perf timer inside IC. No extra GEMM engine wrapper enclosing datapath. No TB ports, fault, prediction or MMIO on new top.

| Direction | Signal | Width |
|---|---|---:|
| input | clk, rst_n, start | each 1 |
| output | busy, done | each 1 |
| output | imem_en | 1 |
| output | imem_addr | 32 |
| input | imem_rdata | 32 |
| output | dmem_en, dmem_we | each 1 |
| output | dmem_addr, dmem_wdata | each 32 |
| input | dmem_rdata | 32 |
All clocked on rising edge; active-low reset. External memory synchronous read: request before R, memory captures R, registered rdata valid after R, DUT consumes earliest R+1. Write commits at W, no response. Read data holds until next read. No ready/valid or variable latency. IMEM fetch only; DMEM single port shared scalar and DMA. Byte addresses; external model maps IMEM PC>>2 and DMEM (addr-0x10000000)>>2. SRAM uses independent single port banks, no simultaneous R/W within one bank.

## Instruction Controller: nine states
One instruction at a time, no overlapping IF/ID/EX/MEM/WB, no prefetch. IF/ID, ID/EX, EX/MEM, MEM/WB are stage registers not FSM states. Normal instructions bypass MEM. Every instruction commits at WB.
| State | Combinational action | Rising edge / next state |
|---|---|---|
| IDLE | no request, busy=0 | start accepted, PC=0 → IF_REQ |
| IF_REQ | imem_en=1, addr=PC | memory read → IF_CAPTURE |
| IF_CAPTURE | no request | IF/ID captures imem_rdata → ID |
| ID | decode fields, combinational 3 GPR reads, immediate and controls | capture ID/EX → EX |
| EX | ALU, branch decision/target, JAL link, LW/SW effective addr, CSR read/write value, DMA operands | capture EX/MEM → MEM_START for LW/SW/LOAD/STORE/EXEC; else WB |
| MEM_START | select port owners; one request (LW/SW) or one engine start pulse | SW: write commits, capture MEM/WB → WB; LW: request → MEM_WAIT; engines accept start/params → MEM_WAIT |
| MEM_WAIT | hold ownership, no repeated start/request; observe relevant rdata/done | LW: capture data next edge; engines: when done sampled capture result/metadata → WB; otherwise hold |
| WB | select EX/MEM or MEM/WB, commit GPR/CSR/PC/timer/END | ordinary: PC next → IF_REQ; END: done=1 → HALTED |
| HALTED | no request, busy=0 | done clears next edge; only reset exits; start ignored |
Busy high IF_REQ through WB. PC changes only at start initialization and WB (END may hold). End pulse is registered after END WB edge. x0 ignores writes. Use EX/MEM `mem_op/npu_op` to select WB source and awaited completion; no extra mem_result_sel or wait-type register. CSR read combinational in EX; do not commit architectural changes early. Branch compares latched operands; immediate sign extension per ISA; JAL old PC+4 link and separate PC next. For SW, effective address and store data available in EX/MEM; no GPR write.

### Stage register contracts
| Stage | Fields |
|---|---|
| IF/ID | instr[31:0]; PC stable until WB (capture PC in ID/EX) |
| ID/EX | pc32, rs1_data32, rs2_data32, rs3_data32, imm32, rd3, csr_addr12; separate control: alu_op (~4), alu_src_a1 (rs1/pc), alu_src_b1 (rs2/imm), branch_op2, mem_op2, csr_op2, npu_op3, sys_op2, reg_write1, wb_sel3 |
| EX/MEM | result32 (ALU/JAL link/CSR read/effective address), pc_next32, rd3, reg_write1, wb_sel3, mem_op2, npu_op3, csr_op2, csr_addr12, csr_wdata32, sys_op2, src32,dst32,len32 (DMA; src may also carry SW data) |
| MEM/WB | result32, pc_next32, rd3, reg_write1 |
Control encodings are implementation details: choose enumerations that cover necessary cases; branch_op distinguishes BEQ/BNE/JAL/none, npu_op DMA LOAD/STORE/GEMM/ARGMAX/none. Keep WB controls stable across wait. GPR x0 constant, 3 asynchronous reads, 1 synchronous WB write. No forwarding, hazard logic or pipeline overlap. Do not add unused fields/state. Data stage registers need not be reset when overwritten before use; controls must never cause a spurious request/commit.

### Clock-edge examples (edge R0 as indicated)
- ADD, top start accepted R0: IMEM read R1; IF/ID R2; ID/EX R3; EX/MEM R4; WB R5; next IMEM R6.
- LW with EX/MEM captured R0: external read R1; MEM/WB receives rdata R2; GPR/PC WB R3.
- SW with EX/MEM captured R0: DMEM write and MEM/WB R1; PC WB R2.
- NPU op with EX/MEM captured R0: start high during MEM_START, captured by engine R1; execute until final write/compare at E; engine done high after E for one full clock, active low; IC sees done at E+1, MEM/WB captured; WB E+2. Ownership held through E+1. ARGMAX result valid at E+1 sampling. All other commands wait, no new fetch until WB.

## Engine interface and SRAM ownership
- DMA start, src/dst/len[31:0], direction; local registers capture all on start edge, no extra state. DMA active/done. GEMM start plus SRC0/SRC1/DST/BIAS_BASE, GEMM_DIM[20:0], GEMM_CFG[11:0]; local registers capture on start edge. GEMM active/done. ARGMAX start plus ARG_SRC[31:0], ARG_LEN[3:0]; local registers capture on start edge, done and result[3:0]. ARGMAX active may exist locally, not connected to timer. No ready/ack/valid beyond specified protocol. Start only idle, held one cycle; done only after final committed operation, held one cycle. Engine idle afterward; result stable during done. No duplicate IC parameter snapshot for GEMM/ARGMAX.
- IC selects SRAM owner NONE/DMA/GEMM/ARGMAX, from MEM_START through completion acceptance (combinational from state/op or safe registered equivalent). No active arbitration, contention detection or address checks. `memory_wrapper` has bank-specific muxes (en,we,addr,wdata). DMA accesses a single addressed bank per request, ARGMAX A/B read, GEMM independent input A/B read, opposite output A/B write, W0..W3 common word address and read enable, Bias read. Weight/Bias must be writable by DMA. Read selector for DMA registered on read request edge, so returned data follows bank of that request; do not select using next request's live address. No extra RAM response register in wrapper. ARGMAX bank stable while active; appropriate latched selection. DMEM mux selects IC for LW/SW, DMA for LOAD/STORE; idle request disabled. Both clients can see shared rdata; only correct consumer samples. Ownership until done accepted.
- Keep `single_port_bram` inferred block RAM and its depth/port/registered output, `ram_decomp="area"` W banks. Existing async reset clears read output, not contents. A/B address paths support A's full 8-bit range, B 7-bit. GEMM output address path 8 bits after base added; group index 7 bits, group count 8 bits (128 representable); input word count/counter 8 bits (physical max 196; bubble value representable). Use bank ID addr[19:17], word addr[16:2]. Base role offsets established in local registers, can narrow physical addresses after capture. Preserve output group delay through R+6; not current group.

## DMA: 1 word/cycle pipeline
Fixed synchronous 32-bit word transfers between external DMEM and one SRAM bank. One start S captures src/dst/len/direction; active high after S. RUN issues N=len/4 reads on S+1..S+N. For read at R: source registered rdata after R; capture into DMA data register at R+1 with destination address/valid metadata; destination write at R+2 (read/response/write overlap across words). Advance cursor only on issued read, preserve associated destination until write. Drain valid pipeline; last write at S+N+2; done high and active low immediately after last write. No extra completion cycle in active or extra read. IDLE/RUN/DRAIN and done pulse (if DONE state used it is not active and produces no additional delay). N+2 active cycles; e.g. N=1 reads S+1, captures S+2, writes/done S+3. Both LOAD and STORE use same pipeline; source and destination are different memories. 400 MB/s steady state at 100MHz. No hardware validation of addresses/length. No arbitrary wait states.

## GEMM: preserve legacy pipeline
One GEMM per EXEC. `IDLE→PREP→RUN→DRAIN→IDLE` with done asserted on last write. Start S capture parameters, PREP after S, RUN after S+1, first read S+2. Q=K/4, G=ceil(N/4). Read Q consecutive words/group; one read-free cycle between groups, no unnecessary final group bubble. Bias read at first word each group. Input base+counter; weight cursor starts at W0 offset, increments on each read (instead of combinational group*Q where possible, Phase8 cursor is reference), shared across W0..3. Bias offset+group. Pipeline tags for result and next bias. Preserve all arithmetic and controls; do not replace with monolithic new computation.
| Edge relative to read R | Action |
|---|---|
| R | Input/Weight synchronous RAM read (bias on first input of group) |
| R+1 | operands registered in MAC, input valid; first group bias load on first read+1 |
| R+2 | products registered |
| R+3 | 4 adder-tree sums registered, psum_valid |
| R+4 | accumulators consume psum |
| last-input R+5 | result register captures old accumulator; next bias loaded if more groups |
| last-input R+6 | packed output writes; delayed group address; last group triggers done |
Bias preload for subsequent group uses prior group's last read+5 and already returned next bias; Q≥2 ensures legacy timing. Bias load and psum_valid never collide; result_load may coincide with bias_load. Reset clears valid metadata and accumulator registers per legacy; fresh bias initializes each group. Config held through final write. Signed INT8×INT8 products/32-bit trees; 16 multipliers (4 lanes ×4) and four partial sums. Preserve existing `mac_array` 3-stage valid and `accumulator_postprocess` result register and postprocess arithmetic. N not multiple of 4: software zero pads weights/bias; written pad lanes zero. No HW lane mask needed. Example expected active cycles S→last write for legacy schedule: first R=S+2, last R=S+2+G*Q+(G−1)−1, E=last R+6; use observed unit test to confirm timing. Keep fixed timing, not a new latency promise for whole program.

## ARGMAX
Independent start captures aligned source/length, resets local index/read phase; use legacy `argmax_unit`, tracker strict signed >, first element initialization, no tie replacement. Read one word at a time, registered output used next cycle, process each valid byte in order (one comparison/cycle); new read at each word boundary. Address base+4*(index>>2), lane index[1:0], final element LEN−1, not padding. Done after last comparison edge when result valid; no extra compare or GPR write until IC WB. Preserve legacy read/compare scheduling, adapt variable LEN and base, no separate fault state.

## Perf and reset
Timer armed AND (dma_active OR gemm_active) sampled at rising edge. Active becomes high after start S; final edge E still sees old active=1 and increments, then done=1/active=0; counts E−S exactly, excludes acceptance and next WB. TSTART clears/arms/clears sticky overflow, TSTOP disarms; both only at WB, no overlap. Count wraps, STATUS bit1 sticky. Count all DMA including STORE, no ARGMAX/scalar/fetch. No wall/overall cycle benchmark. Reset FSM/PC/GPR/CSR/timer/owners/valids/local control counters/flags to safe states; reset does not clear RAM arrays. Parameter/data stage registers may remain unreset if never used before valid capture. Preserve legacy MAC/accumulator resets; safe request defaults and invalid pipeline bits cleared. No additional reset/initial sequence. HALTED restarts only reset→start.
