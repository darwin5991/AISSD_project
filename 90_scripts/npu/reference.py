"""Independent integer arrays: no addresses, packed memories or DUT inputs."""
import numpy as np
def wrap32(x): return (np.asarray(x,dtype=np.int64)&0xffffffff).astype(np.uint32).view(np.int32)
def gemm(x,w,b,bias_shift,out_shift,relu):
    b=np.asarray(b,dtype=np.int64)
    bias=wrap32(b<<bias_shift if bias_shift>=0 else b>>-bias_shift)
    acc=wrap32(np.asarray(x,dtype=np.int64)@np.asarray(w,dtype=np.int64).T+bias.astype(np.int64))
    return np.clip((np.maximum(acc,0) if relu else acc)>>out_shift,-128,127).astype(np.int8)
def argmax(x,length): return np.argmax(np.asarray(x,dtype=np.int8)[...,:length],axis=-1).astype(np.uint32)
def ref_gemm(o,buffers,data):
    y=gemm(buffers[o['src']],data[o['id']+'_w'],data[o['id']+'_b'],o['bias_shift'],o['out_shift'],o['relu'])
    buffers[o['dst']]=y
    return np.pad(y,((0,0),(0,(-o['n'])%4)))
def ref_arg(o,buffers,data): return argmax(buffers[o['src']],o['length'])
REFERENCE_OPS={'gemm':ref_gemm,'argmax':ref_arg}
def generate(s,data):
    buffers={'A':data['input']}; results={'sample_ids':np.array(s.sample_ids),'labels':data['labels']}
    for o in s.ops: results[o['id']]=REFERENCE_OPS[o['op']](o,buffers,data)
    return results
