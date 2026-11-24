"""Host-side preconditions for the trusted M=1 GEMM hardware profile.

Validate the complete configuration before emitting an EXEC/program fixture.
This does not add a hardware checker or analyze arbitrary hand-written binaries.
"""
BANKS=((0x80000000,196),(0x80020000,128),(0x80040000,29280),
       (0x80060000,29280),(0x80080000,29280),(0x800a0000,29280),(0x800c0000,163))

def validate_gemm_config(config):
    if len(config)!=10:
        raise ValueError("GEMM requires ten CSR settings")
    raw=[]
    for i,value in enumerate(config):
        if type(value) is not int or not (0<=value<=0xffffffff or i==7 and -32<=value<0):
            raise ValueError("GEMM settings must be complete 32-bit values")
        raw.append(value & 0xffffffff)
    src,weight,dst,bias,m,n,k,bs,shift,act=raw
    bs=bs-(1<<32) if bs & (1<<31) else bs
    if m!=1 or not 1<=n<=512 or k<8 or k%4:
        raise ValueError("GEMM supports M=1, N=1..512, K>=8 divisible by four; K=4 is unsupported")
    if not -32<=bs<=31 or not 0<=shift<=31 or act not in (0,1):
        raise ValueError("GEMM shift/activation out of supported range")
    if any(address%4 for address in raw[:4]):
        raise ValueError("GEMM byte addresses must be word aligned")
    def bank(address):
        return next((i for i,(base,_) in enumerate(BANKS) if base<=address<base+0x20000),None)
    sb,wb,db,bb=map(bank,(src,weight,dst,bias))
    if sb not in (0,1) or db not in (0,1) or sb==db or wb!=2 or bb!=6:
        raise ValueError("GEMM requires opposite A/B buffers, W0 group base and Bias region")
    groups=(n+3)//4
    for address,size,b in ((src,k,sb),(weight,k*groups,wb),(dst,4*groups,db),(bias,4*groups,bb)):
        base,depth=BANKS[b];end=address+size
        if address>=base+4*depth or end>base+4*depth or end>(1<<32):
            raise ValueError("GEMM allocation exceeds physical SRAM depth")
    return tuple(raw)
