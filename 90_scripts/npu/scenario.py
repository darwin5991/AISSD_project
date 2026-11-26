"""Declarative ordered operations and sample selection."""
from dataclasses import dataclass, asdict, field
import json
from pathlib import Path

DEFAULT_OPS=[dict(id=f'fc{i+1}',op='gemm',k=k,n=n,src=s,dst=d,bias_shift=b,out_shift=o,relu=r)
             for i,(k,n,s,d,b,o,r) in enumerate([(784,512,'A','B',3,10,True),(512,128,'B','A',1,7,True),(128,10,'A','B',2,7,False)])]
DEFAULT_OPS += [dict(id='argmax',op='argmax',src='B',length=10)]
@dataclass
class Scenario:
    name: str
    sample_ids: list
    save_outputs: list
    ops: list=field(default_factory=lambda: [x.copy() for x in DEFAULT_OPS])
    checkpoint: str='03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth'
    timer: bool=False
    waveform: bool=False
    reuse_weights: bool=True
    def validate(self):
        if not self.sample_ids or any(type(i)!=int or not 0<=i<10000 for i in self.sample_ids): raise ValueError('sample IDs')
        if self.timer or self.waveform or not self.reuse_weights: raise ValueError('bulk uses timer/wave off and reused weights')
        names={o['id'] for o in self.ops}
        if len(names)!=len(self.ops) or not set(self.save_outputs)<=names: raise ValueError('operation IDs')
        for o in self.ops:
            if o['src'] not in ('A','B'): raise ValueError('source bank')
            if o['op']=='gemm':
                k,n=o['k'],o['n']
                if k<8 or k%4 or k>min(1020,784 if o['src']=='A' else 512) or not 1<=n<=512: raise ValueError('GEMM dimensions')
                if o['dst']!=('B' if o['src']=='A' else 'A') or ((n+3)//4)*4>(512 if o['dst']=='B' else 784): raise ValueError('destination')
                if not -32<=o['bias_shift']<=31 or not 0<=o['out_shift']<=31: raise ValueError('shift')
            elif o['op']!='argmax' or not 1<=o['length']<=10: raise ValueError('operation')
        return self
    def save(self,p): Path(p).write_text(json.dumps(asdict(self),indent=2)+'\n')
    @classmethod
    def load(cls,p): return cls(**json.loads(Path(p).read_text())).validate()
