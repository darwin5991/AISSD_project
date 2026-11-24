"""External-only ISA/engine smoke; expected values determined before simulation."""
from pathlib import Path
import argparse,json,uuid
from assembler import assemble,write_hex
from simulator import ROOT,compile_sim,simulate

def run_case(name,asm,expected,data=None,build=None):
    run=ROOT/'07_runs/npu'/f'{name}_{uuid.uuid4().hex[:10]}'
    for sub in ('input','output','logs'): (run/sub).mkdir(parents=True)
    words=assemble(asm);base=0x10001000
    init=[0]*1024+[0xa5a5a5a5]*len(expected)
    for addr,value in (data or {}).items():init[(addr-0x10000000)//4]=value
    (run/'input/program.asm').write_text(asm);write_hex(run/'input/imem.hex',words);write_hex(run/'input/dmem.hex',init)
    (run/'expected.json').write_text(json.dumps(expected))
    simulate(build,run,len(words),len(init),base,len(expected))
    lines=(run/'output/results.hex').read_text().splitlines()
    actual=[int(x,16) for x in lines]
    (run/'comparison.json').write_text(json.dumps(dict(expected=expected,actual=actual,passed=actual==expected),indent=2))
    if actual!=expected:raise AssertionError(str(run)+' '+str(actual)+' expected '+str(expected))
    print(name,'PASS',len(expected),'words',run)
    return run

def scalar(build):
    a=['LI x6,0x10001000'];e=[]
    def save(code,val):
        a.extend(code.splitlines());a.append(f'SW x1,{4*len(e)}(x6)');e.append(val&0xffffffff)
    save('LUI x1,0x12345',0x12345000)
    save('LI x2,-1\nADDI x3,x0,1\nADD x1,x2,x3',0)
    save('ADDI x1,x2,-2',0xfffffffd)
    save('LI x2,0x5678\nLI x3,0x1234\nAND x1,x2,x3',0x1230)
    save('OR x1,x2,x3',0x567c)
    save('ANDI x1,x2,0x7f',0x78)
    save('ORI x1,x0,-2048',0xfffff800)
    save('LI x2,0x80000001\nSLLI x1,x2,1',2)
    save('SRLI x1,x2,31',1)
    save('ADDI x0,x2,2\nADD x1,x0,x0',0)
    save('LI x2,0x10000000\nLI x3,0x87654321\nSW x3,4(x2)\nLW x1,4(x2)',0x87654321)
    save('SETI GEMM_DIM,-1\nCSRR x1,GEMM_DIM',0x1fffff)
    save('LI x2,0x12345abc\nCSRW GEMM_CFG,x2\nCSRR x1,GEMM_CFG',0xabc)
    save('SETI ARG_LEN,-2\nCSRR x1,ARG_LEN',14)
    save('SETI SRC0_BASE,-4096\nCSRR x1,SRC0_BASE',0xfffff000)
    save('CSRR x1,STATUS',0)
    save('TSTART\nADDI x1,x0,3\nTSTOP\nCSRR x1,PERF_COUNT',0)
    a+=['LI x1,0','LI x2,3','loop: ADDI x1,x1,1','BNE x1,x2,loop','BEQ x1,x2,taken','ADDI x1,x0,99','taken: BEQ x1,x0,bad','BNE x1,x2,bad',f'SW x1,{len(e)*4}(x6)'];e.append(3)
    # Link expected from actual expanded PC, independently checked by subsequent arithmetic.
    a+=['JAL x3,link','bad: ADDI x1,x0,99','link: ADDI x1,x3,0',f'SW x1,{len(e)*4}(x6)','END']
    words=assemble('\n'.join(a));jal_pc=next(i*4 for i,w in enumerate(words) if w&127==0x6f);e.append(jal_pc+4)
    return run_case('scalar','\n'.join(a),e,build=build)
def dma(build):
    a=['LI x6,0x10001000'];e=[];data={}
    for bank,offset in [(0,780),(1,508),(2,117108),(3,117108),(4,117108),(5,117108),(6,640)]:
        count=1 if bank<2 else 3
        pattern=[(0x807f00ff+bank*0x10203+i*0x1234567)&0xffffffff for i in range(count)]
        for i,w in enumerate(pattern):data[0x10000000+bank*16+i*4]=w
        a+=['TSTART',f'LI x1,{0x10000000+bank*16}',f'LI x2,{0x80000000+bank*0x20000+offset}',f'LI x3,{count*4}',
            'LOAD x1,x2,x3','ADDI x1,x2,0',f'ADDI x2,x6,{len(e)*4}','STORE x1,x2,x3','TSTOP','CSRR x1,PERF_COUNT',f'SW x1,{(len(e)+count)*4}(x6)']
        e+=pattern+[2*(count+2)]
    a+=['END'];return run_case('dma','\n'.join(a),e,data,build)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('gate',choices=['scalar','dma']);p.add_argument('--build');args=p.parse_args()
    b=Path(args.build) if args.build else compile_sim(ROOT/'99_build'/('npu_'+args.gate+'_'+uuid.uuid4().hex[:8]),'dma' if args.gate=='dma' else False)
    {'scalar':scalar,'dma':dma}[args.gate](b)
