"""Load the existing model once; reuse approved quantization and INT8 packing."""
import struct
import sys
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"03_model"))
from generate_golden import pack8, INPUT_FRAC, WEIGHT_FRACS, OUTPUT_FRACS, BIAS_FRACS
from src.layer_view import LayerViewer
from src.quantization import encode, make_config

def load_assets(count=200):
    if not 1 <= count <= 200:
        raise ValueError("Phase 7 is limited to first 1..200 MNIST images")
    viewer = LayerViewer()
    paths = [viewer.data_root/"t10k-images-idx3-ubyte",viewer.data_root/"t10k-labels-idx1-ubyte"]
    with paths[0].open("rb") as f:
        magic,total,rows,cols = struct.unpack(">IIII",f.read(16))
        if (magic,total,rows,cols)!=(2051,10000,28,28) or paths[0].stat().st_size!=16+total*784:
            raise ValueError("invalid complete MNIST test image IDX")
        pixels = np.frombuffer(f.read(count*784),dtype=np.uint8).copy().reshape(count,784)
    with paths[1].open("rb") as f:
        magic,total_labels = struct.unpack(">II",f.read(8))
        if magic!=2049 or total_labels!=total or paths[1].stat().st_size!=8+total:
            raise ValueError("invalid complete MNIST test label IDX")
        labels = np.frombuffer(f.read(count),dtype=np.uint8).copy()
    if np.any(labels>9):
        raise ValueError("invalid MNIST label")
    cfg = make_config(input_frac=INPUT_FRAC,weight_frac=WEIGHT_FRACS,
                      output_frac=OUTPUT_FRACS,bias_frac=BIAS_FRACS,
                      input_signed=True,hidden_signed=True,output_signed=True,
                      output_rounding="truncate")
    x = (torch.from_numpy(pixels).float()/255.0-viewer.mean)/viewer.std
    input8 = encode(x,cfg.input).numpy()
    weights,biases = [],[]
    banks = [[] for _ in range(4)]
    bias_parts = []
    for i,name in enumerate(("fc1","fc2","fc3")):
        layer = getattr(viewer.model,name)
        w = encode(layer.weight.detach(),cfg.weights[i]).numpy()
        b = encode(layer.bias.detach(),cfg.biases[i]).numpy()
        weights.append(w.copy());biases.append(b.copy())
        pad = (-len(b))%4
        wp = np.pad(w,((0,pad),(0,0)))
        bp = np.pad(b,(0,pad))
        for bank in range(4):
            packed = pack8(wp[bank::4].reshape(-1))
            # Inverse mapping proves every signed code/lane is represented.
            decoded = np.stack([((packed>>(8*j))&255).astype(np.uint8).view(np.int8)
                                for j in range(4)],axis=1).reshape(-1,w.shape[1])
            if not np.array_equal(decoded,wp[bank::4]):
                raise AssertionError("weight packing inverse mismatch")
            banks[bank].append(packed)
        bias_parts.append(pack8(bp))
    packed_banks = [np.concatenate(parts) for parts in banks]
    packed_bias = np.concatenate(bias_parts)
    if any(len(w)!=29280 for w in packed_banks) or len(packed_bias)!=163:
        raise ValueError("model does not fit existing SRAM profile")
    checkpoint = ROOT/"03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth"
    return dict(input8=input8,input_fp32=x,labels=labels,weights=weights,biases=biases,
                banks=packed_banks,bias=packed_bias,config=cfg,params={
                    k:v.detach().cpu().numpy() for k,v in viewer.model.state_dict().items()},
                paths=[checkpoint,*paths],preprocessing=dict(mean=viewer.mean,std=viewer.std,
                formula="(float32(pixel)/255 - mean)/std"),model_loads=1)
