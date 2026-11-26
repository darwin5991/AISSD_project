# ISA specification — programmable NPU v2
Normative; supersedes Phase8 where inconsistent. 32-bit instruction, little-endian packed bytes, 32-bit byte-address PC. Single in-order blocking instruction. Valid code/data assumed. No hardware illegal-opcode, register range, CSR permission, alignment, bounds, overflow-address, region/config fault or runtime error logic; behavior outside defined valid program domain unspecified. Assembler and Python validate legal inputs. Scalar arithmetic wraps mod 2^32.

## 1. Register and execution model
8 GPRs x0..x7, 32 bits; x0 always zero, writes ignored. Encode 5-bit register fields but valid values 0..7, hardware uses low 3 bits. PC reset/start 0; default next PC=PC+4; branch/JAL use current instruction PC, selected target must be 4-byte aligned and in IMEM (software precondition). Only WB updates architectural PC/GPR/CSR/timer. `END` pulses top done one clock, busy drops, HALTED until reset. Reset zeros architected registers, leaves SRAM contents. No external fault or prediction port. Status read during running returns HALTED=0; after END no more instructions execute.

## 2. Instruction list (24 real instructions)
All fields use normal RV32I encoding where stated, except custom below. `funct7` for shift immediates is upper imm[11:5]. `rs1/rs2/rd` legal register fields. `sext` sign-extends; SRLI logical zero-fill. No other RV32I instructions supported.

| Mnemonic | Opcode hex | funct3 | funct7 / format | Behavior |
|---|---|---|---|---|
| LUI rd,imm20 | 37 | — | U | rd=imm20<<12 |
| ADD rd,rs1,rs2 | 33 | 000 | 0000000 R | add |
| ADDI rd,rs1,imm12 | 13 | 000 | I | rs1+sext(imm12) |
| AND rd,rs1,rs2 | 33 | 111 | 0000000 R | bitwise AND |
| ANDI rd,rs1,imm12 | 13 | 111 | I | rs1 & sext(imm12) |
| OR rd,rs1,rs2 | 33 | 110 | 0000000 R | bitwise OR |
| ORI rd,rs1,imm12 | 13 | 110 | I | rs1 \| sext(imm12) |
| SLLI rd,rs1,shamt | 13 | 001 | 0000000 I | shift left 0..31 |
| SRLI rd,rs1,shamt | 13 | 101 | 0000000 I | logical right 0..31 |
| BEQ rs1,rs2,label | 63 | 000 | B | equal: PC+offset; else PC+4 |
| BNE rs1,rs2,label | 63 | 001 | B | not equal: PC+offset; else PC+4 |
| JAL rd,label | 6F | — | J | rd=PC+4; PC=PC+offset |
| LW rd,imm12(rs1) | 03 | 010 | I | rd=DMEM32[rs1+sext(imm12)] |
| SW rs2,imm12(rs1) | 23 | 010 | S | DMEM32[rs1+sext(imm12)]=rs2 |
| CSRW csr,rs1 | 73 | 001 | I rd=0 | write CSR |
| CSRR rd,csr | 73 | 010 | I rs1=0 | read CSR |
| SETI csr,imm13 | 0B | — | custom0 | CSR=sext(imm13), truncated to storage width |
| LOAD rs1,rs2,rs3 | 2B | 000 | f7=0 | DMEM→SRAM |
| STORE rs1,rs2,rs3 | 2B | 001 | f7=0 | SRAM→DMEM |
| EXEC GEMM | 2B | 010 | f7=0 | one GEMM, no GPR output |
| EXEC ARGMAX,rd | 2B | 010 | f7=1 | result index→rd |
| TSTART | 2B | 011 | f7=0 | count=0, overflow=0, arm |
| TSTOP | 2B | 011 | f7=1 | disarm, retain count and overflow |
| END | 2B | 011 | f7=2 | normal halt, done pulse |

### Field layouts
```
R [31:25] funct7 | [24:20] rs2 | [19:15] rs1 | [14:12] funct3 | [11:7] rd | [6:0] opcode
I [31:20] imm12  | [19:15] rs1 | [14:12] funct3 | [11:7] rd | [6:0] opcode
S [31:25] imm[11:5] | [24:20] rs2 | [19:15] rs1 | [14:12] funct3 | [11:7] imm[4:0] | opcode
B [31] imm[12] | [30:25] imm[10:5] | [24:20] rs2 | [19:15] rs1 | [14:12] funct3 | [11:8] imm[4:1] | [7] imm[11] | opcode
U [31:12] imm20 | [11:7] rd | opcode
J [31] imm[20] | [30:21] imm[10:1] | [20] imm[11] | [19:12] imm[19:12] | [11:7] rd | opcode
CUSTOM0 [31:19] signed imm13 | [18:7] csr12 | [6:0] 0x0B
CUSTOM1 [31:25] funct7 | [24:20] rs2 | [19:15] rs1 | [14:12] funct3 | [11:7] rd_or_rs3 | [6:0] 0x2B
```
B offset signed 13-bit and J offset signed 21-bit, bit0 implied 0; valid targets/offsets are multiples of 4. I/S immediates signed -2048..2047; SETI -4096..4095. For CSR, I imm field is unsigned CSR index, not ordinary signed immediate. For LOAD/STORE rs1=src byte address, rs2=dst byte address, rs3=length bytes; encoded in rd field; no GPR writes. For EXEC GEMM, rs1/rs2/rd=0; ARGMAX rs1/rs2=0; system unused fields=0. SW only external DMEM, no internal direct scalar writes. LOAD/STORE 4-byte aligned and length positive multiple of 4, stay in one actual SRAM bank. All addresses byte addresses, no wrap for memory accesses as a valid-program constraint.

### Pseudo instructions and assembly
`.equ NAME, VALUE`, `LI rd,32-bit constant` (signed low12 adjustment, use ADDI from x0 if fits; otherwise LUI and optional ADDI), `SETADDR csr,constant` (LI x4 then CSRW, explicitly clobbers x4). Labels resolve after pseudo expansion; case-insensitive mnemonic, register aliases r0..r7; comment syntax documented by assembler. Labels and symbols resolved in two passes. Refuse illegal source assembly/overflow/unsupported encoding in software, not RTL. Branch offsets from actual current PC. No pseudo instruction counted as real opcode.

### Independent encoding check vectors
| Assembly | Word hex |
|---|---|
| LW x5,4(x1) | 0040A283 |
| SW x2,-4(x1) | FE20AE23 |
| LOAD x1,x2,x3 | 002081AB |
| STORE x1,x2,x3 | 002091AB |
| EXEC GEMM | 0000202B |
| EXEC ARGMAX,x5 | 020022AB |
| TSTART | 0000302B |
| TSTOP | 0200302B |
| END | 0400302B |
| SETI GEMM_DIM,1 | 000BE20B |
| AND x3,x1,x2 | 0020F1B3 |
| OR x3,x1,x2 | 0020E1B3 |
| ANDI x3,x1,-1 | FFF0F193 |
| ORI x3,x1,1 | 0010E193 |
| SLLI x3,x1,4 | 00409193 |
| SRLI x3,x1,4 | 0040D193 |
SETI vector checks encoding only (1 is not a valid execution DIM). Check other instructions and pseudo/labels independently.

## 3. CSR map (10 implemented)
Read 32-bit zero-extended from packed storage, RW writes low implemented bits; RO read only in valid code, all RW reset zero. Unknown read unspecified (zero acceptable). No extra CSR/error registers. CSR writes and TSTART/TSTOP commit only at WB.
| Address | Name | Width | Access / field |
|---|---|---:|---|
| 7C0 | SRC0_BASE | 32 | RW input byte address A/B |
| 7C1 | SRC1_BASE | 32 | RW W0 byte base, same offset W1–W3 |
| 7C2 | DST_BASE | 32 | RW output byte address opposite buffer |
| 7C3 | BIAS_BASE | 32 | RW bias byte address |
| 7C4 | GEMM_DIM | 21 | RW K[9:0], N[19:10], M[20] (literal M=1) |
| 7C7 | GEMM_CFG | 12 | RW BIAS_SHIFT[5:0] signed two's complement, OUT_SHIFT[10:6] unsigned, ACT_MODE[11] 0 none/1 ReLU |
| 7E0 | ARG_SRC | 32 | RW A/B aligned byte base |
| 7E1 | ARG_LEN | 4 | RW element count 1..10 |
| 7F0 | PERF_COUNT | 32 | RO accumulated active cycles |
| 7F2 | STATUS | 2 | RO bit0 HALTED, bit1 PERF_OVERFLOW (sticky) |
`7C5,7C6,7C8,7C9,7F1,7F3` reserved in this spec, not old individual CSRs. All others unimplemented. `dim=(1<<20)|(N<<10)|K`; `cfg=(relu<<11)|(out_shift<<6)|(bias_shift & 63)`; BIAS_SHIFT -32..31 and OUT_SHIFT 0..31. M=1 only. No original 32-bit shadow for narrow fields. Controller captures execution parameters on its own start acceptance, not an extra IC snapshot state.

## 4. Memory map
| Region | Base | Size/depth |
|---|---|---|
| IMEM | 00000000 | 64 KiB / 16384 words (external TB) |
| DMEM | 10000000 | 16 MiB / 4194304 words (external TB) |
| A | 80000000 | 196×32 = 784 B |
| B | 80020000 | 128×32 = 512 B |
| W0 | 80040000 | 29280×32 = 117120 B |
| W1 | 80060000 | 29280×32 = 117120 B |
| W2 | 80080000 | 29280×32 = 117120 B |
| W3 | 800A0000 | 29280×32 = 117120 B |
| Bias | 800C0000 | 163×32 = 652 B |
| Reserved MMIO | F0000000 | not supported |
Actual SRAM total 470428 bytes, 117607 words. Bank ID addr[19:17], offset word addr[16:2]; narrower physical widths per bank (A=8, B=7, W=15, Bias=8). Holes in 128KiB windows not memory. Software ensures ranges, bank roles, no crossing, valid buffers. No TB maps external IMEM/DMEM into FPGA.

## 5. GEMM and ARGMAX
GEMM M=1, K≥8 multiple of 4, N=1..512. K≤1020 representable, **physical** input capacity/other bounds apply (A max 784, B max 512 before offset); input/output opposite A/B. `Q=K/4`, `G=ceil(N/4)`; each W bank stores G*Q words, bias and output G words. Input addresses `SRC0+4*i`; W bank j word `base_word+g*Q+i`; Bias `BIAS_BASE+4*g`; Output `DST_BASE+4*g` (g delayed). Lane j outputs row 4g+j; byte k input k+4i. Last group pad weights/bias with zero; output padding zero. INT8 signed x,w,b; bias align signed left (32-bit wrap) or arithmetic right; signed INT32 partial/accumulate wrap; optional ReLU; arithmetic shift right; signed saturation [-128,127]; byte0 low bits. No rounding beyond legacy arithmetic shift. ARGMAX signed INT8, L=1..10, aligned A/B start, first max on ties, ignore padding, index zero-extended. No automatic ARGMAX after GEMM.

## 6. Timer
32-bit wrapping count with sticky overflow on wrap; TSTART clears count and overflow and arms, TSTOP disarms and retains; reset clears. Count iff armed AND (DMA active including LOAD and STORE OR GEMM active). Preparation and drain included, IC, scalar, ARGMAX, idle and done acceptance excluded. CSRR PERF_COUNT then SW to DMEM when needed. See cycle definition in 02. No overall execution benchmark required.
