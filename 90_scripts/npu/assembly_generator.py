"""Operation emitters; x5 image, x6 result record, x7 loop; x1..4 scratch."""
from memory_builder import BANKS
def emit_gemm(o,m):
    p=m['ops'][o['id']]
    cfg=(int(o['relu'])<<11)|(o['out_shift']<<6)|(o['bias_shift']&63)
    return [f'SETADDR SRC0_BASE,{BANKS[o["src"]]}',f'SETADDR SRC1_BASE,{BANKS["W0"]+4*p["weight_word"]}',
            f'SETADDR DST_BASE,{BANKS[o["dst"]]}',f'SETADDR BIAS_BASE,{BANKS["Bias"]+4*p["bias_word"]}',
            f'SETADDR GEMM_DIM,{(1<<20)|(o["n"]<<10)|o["k"]}',f'SETI GEMM_CFG,{cfg}','EXEC GEMM']
def emit_arg(o,m): return [f'SETADDR ARG_SRC,{BANKS[o["src"]]}',f'SETI ARG_LEN,{o["length"]}','EXEC ARGMAX,x1']
ASSEMBLY_OPS={'gemm':emit_gemm,'argmax':emit_arg}
def generate(s,m):
    lines=['# NPU v2: weights once, one reset/start/END, image loop']
    for bank in ('W0','W1','W2','W3','Bias'):
        r=m['regions'][bank]
        lines += [f'LI x1,{r["base"]}',f'LI x2,{BANKS[bank]}',f'LI x3,{r["bytes"]}','LOAD x1,x2,x3']
    lines += [f'LI x5,{m["regions"]["images"]["base"]}',f'LI x6,{m["regions"]["results"]["base"]}',f'LI x7,{len(s.sample_ids)}','image_loop:',
              'ADDI x1,x5,0',f'LI x2,{BANKS["A"]}','LI x3,784','LOAD x1,x2,x3']
    for o in s.ops:
        lines+=ASSEMBLY_OPS[o['op']](o,m)
        if o['id'] in m['fields']:
            f=m['fields'][o['id']]
            if f['offset']>2047: raise ValueError('record immediate')
            if o['op']=='gemm':
                lines += [f'LI x1,{BANKS[o["dst"]]}',f'ADDI x2,x6,{f["offset"]}',f'LI x3,{f["bytes"]}','STORE x1,x2,x3']
            else: lines += [f'SW x1,{f["offset"]}(x6)']
    stride=m['record_stride']
    lines += ['ADDI x5,x5,784',f'ADDI x6,x6,{stride}','ADDI x7,x7,-1','BNE x7,x0,image_loop','END']
    return '\n'.join(lines)+'\n'
