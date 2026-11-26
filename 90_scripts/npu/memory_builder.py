"""SRAM-aware packing and aligned external allocation; no expected values."""
import numpy as np
from assembler import write_hex
BASE=0x10000000
BANKS={'A':0x80000000,'B':0x80020000,'W0':0x80040000,'W1':0x80060000,'W2':0x80080000,'W3':0x800a0000,'Bias':0x800c0000}
def pack8(v): return np.ascontiguousarray(v,dtype=np.int8).reshape(-1).view('<u4')
def unpack8(w): return np.asarray(w,dtype='<u4').view(np.int8)
def build(s,data):
    parts=[]; regions={}; offset=0
    def alloc(name,words):
        nonlocal offset
        words=np.asarray(words,dtype='<u4').reshape(-1)
        r=dict(base=BASE+offset,bytes=words.size*4,words=words.size)
        regions[name]=r; parts.append(words); offset+=r['bytes']; return r
    weights=[[] for _ in range(4)]; biases=[]; meta={}; wb=bb=0
    for o in s.ops:
        if o['op']!='gemm': continue
        k,n=o['k'],o['n']; g=(n+3)//4
        w=data[o['id']+'_w']; b=data[o['id']+'_b']
        if w.shape!=(n,k) or b.shape!=(n,): raise ValueError('parameter shape')
        w=np.pad(w,((0,4*g-n),(0,0))); b=np.pad(b,(0,4*g-n))
        for j in range(4): weights[j].append(pack8(w[j::4]))
        biases.append(pack8(b)); meta[o['id']]=dict(weight_word=wb,bias_word=bb)
        wb+=g*k//4; bb+=g
    if wb>29280 or bb>163: raise ValueError('weight/bias capacity')
    for j in range(4): alloc(f'W{j}',np.concatenate(weights[j]))
    alloc('Bias',np.concatenate(biases)); alloc('images',pack8(data['input']))
    fields={}; stride=0
    for o in s.ops:
        if o['id'] not in s.save_outputs: continue
        size=((o['n']+3)//4)*4 if o['op']=='gemm' else 4
        fields[o['id']]=dict(offset=stride,bytes=size,dtype='int8' if o['op']=='gemm' else 'uint32',logical=o.get('n',1))
        stride+=size
    alloc('results',np.full(len(s.sample_ids)*stride//4,0xa5a5a5a5,dtype=np.uint32))
    if offset>16*1024**2: raise ValueError('DMEM capacity')
    return np.concatenate(parts),dict(regions=regions,ops=meta,fields=fields,record_stride=stride,sample_ids=s.sample_ids,initial_words=offset//4,dump=dict(base=regions['results']['base'],words=regions['results']['words'],file='output/results.hex'))
