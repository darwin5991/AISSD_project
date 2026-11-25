LI x6,0x10001000
LUI x1,0x12345
SW x1,0(x6)
LI x2,-1
ADDI x3,x0,1
ADD x1,x2,x3
SW x1,4(x6)
ADDI x1,x2,-2
SW x1,8(x6)
LI x2,0x5678
LI x3,0x1234
AND x1,x2,x3
SW x1,12(x6)
OR x1,x2,x3
SW x1,16(x6)
ANDI x1,x2,0x7f
SW x1,20(x6)
ORI x1,x0,-2048
SW x1,24(x6)
LI x2,0x80000001
SLLI x1,x2,1
SW x1,28(x6)
SRLI x1,x2,31
SW x1,32(x6)
ADDI x0,x2,2
ADD x1,x0,x0
SW x1,36(x6)
LI x2,0x10000000
LI x3,0x87654321
SW x3,4(x2)
LW x1,4(x2)
SW x1,40(x6)
SETI GEMM_DIM,-1
CSRR x1,GEMM_DIM
SW x1,44(x6)
LI x2,0x12345abc
CSRW GEMM_CFG,x2
CSRR x1,GEMM_CFG
SW x1,48(x6)
SETI ARG_LEN,-2
CSRR x1,ARG_LEN
SW x1,52(x6)
SETI SRC0_BASE,-4096
CSRR x1,SRC0_BASE
SW x1,56(x6)
CSRR x1,STATUS
SW x1,60(x6)
TSTART
ADDI x1,x0,3
TSTOP
CSRR x1,PERF_COUNT
SW x1,64(x6)
LI x1,0
LI x2,3
loop: ADDI x1,x1,1
BNE x1,x2,loop
BEQ x1,x2,taken
ADDI x1,x0,99
taken: BEQ x1,x0,bad
BNE x1,x2,bad
SW x1,68(x6)
JAL x3,link
bad: ADDI x1,x0,99
link: ADDI x1,x3,0
SW x1,72(x6)
END