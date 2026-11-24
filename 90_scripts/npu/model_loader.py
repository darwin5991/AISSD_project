"""Read-only baseline model/IDX adapter; identical baseline quantization."""
import sys, hashlib
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'03_model'))
from src.layer_view import LayerViewer
from src.quantization import encode,Fxp8

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(s):
    if s.checkpoint!='03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth': raise ValueError('unsupported checkpoint')
    cp=ROOT/s.checkpoint
    if sha(cp)!='aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd': raise ValueError('checkpoint hash')
    viewer=LayerViewer(); data={}; labels=[]; images=[]
    for i in s.sample_ids:
        pixels,label=viewer._read_sample(i)
        images.append(encode((pixels/255-viewer.mean)/viewer.std,Fxp8(True,5)).numpy().reshape(-1)); labels.append(label)
    data['input']=np.array(images,dtype=np.int8); data['labels']=np.array(labels,dtype=np.int32)
    for i in range(3):
        layer=getattr(viewer.model,f'fc{i+1}')
        data[f'fc{i+1}_w']=encode(layer.weight.detach(),Fxp8(True,7)).numpy()
        data[f'fc{i+1}_b']=encode(layer.bias.detach(),Fxp8(True,(9,8,7)[i])).numpy()
    return data,dict(checkpoint_sha256=sha(cp),dataset_sha256={p.name:sha(p) for p in viewer.data_root.glob('t10k-*-ubyte')})
