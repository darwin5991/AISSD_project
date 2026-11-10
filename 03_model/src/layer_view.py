"""Compact, single-image / single-layer float and int8 arithmetic inspection."""
from dataclasses import dataclass
from pathlib import Path
import struct
import numpy as np
import torch
from .models import MNISTMLP
from .quantization import Fxp8, encode, requantize, make_config, IntegerMLP, quantize_bias


def _vector(value):
    """One physical line; never wrap a four-element vector."""
    value = value.detach().cpu().numpy() if isinstance(value, torch.Tensor) else np.asarray(value)
    return np.array2string(value, precision=8, floatmode='fixed', suppress_small=False,
                          max_line_width=10000, separator=' ')


def _block(*lines):
    if not 1 <= len(lines) <= 2 or any(chr(10) in line for line in lines):
        raise ValueError('Each displayed block must contain one or two lines')
    print(*lines, sep=chr(10))
    print()


def _int32(value, name):
    if bool(((value < -(2**31)) | (value > 2**31 - 1)).any()):
        raise OverflowError(name + ' exceeds signed int32')
    return value.to(torch.int32)


class LayerViewer:
    """Load the checkpoint once and read exactly one MNIST image per selection."""

    def __init__(self, mean=0.1307, std=0.3081):
        if std <= 0:
            raise ValueError('std must be positive')
        root = Path(__file__).resolve().parents[3]
        self.mean, self.std = mean, std
        checkpoint = root/'project/03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth'
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
        state = state.get('model_state_dict', state.get('state_dict', state))
        self.model = MNISTMLP().cpu().eval()
        self.model.load_state_dict(state, strict=True)
        candidates = [root/'data/mnist/MNIST/raw', root/'assignment1/data/mnist/MNIST/raw',
                      root/'project/02_data/raw/MNIST/raw', root/'data/MNIST/raw']
        self.data_root = next((p for p in candidates if (p/'t10k-images-idx3-ubyte').is_file()
                               and (p/'t10k-labels-idx1-ubyte').is_file()), None)
        if self.data_root is None:
            raise FileNotFoundError('Uncompressed MNIST test IDX files not found')

    def _read_sample(self, sample_id):
        with (self.data_root/'t10k-images-idx3-ubyte').open('rb') as f:
            magic, count, rows, cols = struct.unpack('>IIII', f.read(16))
            if magic != 2051 or (rows, cols) != (28, 28):
                raise ValueError('Invalid MNIST image header')
            if not 0 <= sample_id < count:
                raise ValueError(f'sample_id must be in 0..{count-1}')
            f.seek(16 + sample_id * rows * cols)
            image = np.frombuffer(f.read(rows*cols), dtype=np.uint8).copy()
            if image.size != rows*cols:
                raise ValueError('Truncated image')
        with (self.data_root/'t10k-labels-idx1-ubyte').open('rb') as f:
            magic, labels = struct.unpack('>II', f.read(8))
            if magic != 2049 or labels != count:
                raise ValueError('Invalid MNIST labels')
            f.seek(8 + sample_id)
            label = f.read(1)
            if len(label) != 1:
                raise ValueError('Truncated label')
        return torch.from_numpy(image).float().reshape(1,784), label[0]

    @torch.inference_mode()
    def select(self, layer='fc1', sample_id=0, input_start=0, output_start=0):
        """Use FP32 upstream layers; quantize only the selected layer later."""
        if layer not in ('fc1','fc2','fc3'):
            raise ValueError('layer must be fc1, fc2, or fc3')
        image, label = self._read_sample(sample_id)
        x = (image/255.0 - self.mean)/self.std
        if layer in ('fc2','fc3'):
            x = torch.relu(self.model.fc1(x))
        if layer == 'fc3':
            x = torch.relu(self.model.fc2(x))
        linear = getattr(self.model, layer)
        if not 0 <= input_start <= linear.in_features-4:
            raise ValueError(f'input_start must be 0..{linear.in_features-4}')
        if not 0 <= output_start <= linear.out_features-2:
            raise ValueError(f'output_start must be 0..{linear.out_features-2}')
        return LayerSample(layer, sample_id, label, input_start, output_start,
                           x[0].clone(), linear.weight[output_start:output_start+2].clone(),
                           linear.bias[output_start:output_start+2].clone())


    @torch.inference_mode()
    def compare_random(self, input_frac=4, weight_fracs=(4,4,4), output_fracs=(4,4,4),
                       input_signed=True, hidden_signed=True, output_signed=True, seed=None,
                       bias_fracs=None, output_rounding='nearest_even'):
        """Compare FP32 and the complete quantized path on one random test image."""
        with (self.data_root/'t10k-images-idx3-ubyte').open('rb') as f:
            magic, count, rows, cols = struct.unpack('>IIII', f.read(16))
        if magic != 2051 or (rows,cols) != (28,28):
            raise ValueError('Invalid MNIST header')
        sample_id = int(np.random.default_rng(seed).integers(count))
        image, label = self._read_sample(sample_id)
        x = (image/255.0-self.mean)/self.std
        fp = {'input':x}
        h = x
        for i,name in enumerate(('fc1','fc2','fc3')):
            h = getattr(self.model,name)(h)
            if i < 2:
                h = torch.relu(h)
            fp[name] = h
        cfg = make_config(input_frac=input_frac, weight_frac=weight_fracs, output_frac=output_fracs,
                          input_signed=input_signed, hidden_signed=hidden_signed, output_signed=output_signed,
                          bias_frac=bias_fracs, output_rounding=output_rounding)
        params = {k:v.detach().cpu().numpy() for k,v in self.model.state_dict().items()}
        engine = IntegerMLP(params,torch.device('cpu'))
        quantized = engine.forward(x,cfg,trace=True,verify_cpu=True)
        restored = {name:entry['restored'] for name,entry in quantized['trace'].items()}
        fp_prediction = int(fp['fc3'].argmax(1)[0])
        q_prediction = int(restored['fc3'].argmax(1)[0])

        import matplotlib.pyplot as plt
        fig,ax = plt.subplots(figsize=(2.4,2.4))
        ax.imshow(image.reshape(28,28).numpy(),cmap='gray',vmin=0,vmax=255)
        ax.set_title(f'sample={sample_id}, label={label}')
        ax.axis('off')
        plt.tight_layout()
        plt.show()
        _block(f'sample={sample_id} | label={label} | FP32 prediction={fp_prediction} | FXP prediction={q_prediction}')
        # Four representative pixel intensities, rather than four background zeros.
        _, positions = np.unique(image[0].numpy(),return_index=True)
        pick = positions[np.linspace(0,len(positions)-1,min(4,len(positions)),dtype=int)]
        _block(f'input {pick.tolist()} FP32 = {_vector(x[0,pick])}',
               f'input {cfg.input.label} FXP = {_vector(restored["input"][0,pick])}')
        for i,name in enumerate(('fc1','fc2')):
            indices = fp[name][0].abs().topk(4).indices.sort().values
            _block(f'{name} {indices.tolist()} FP32 = {_vector(fp[name][0,indices])}',
                   f'{name} {cfg.outputs[i].label} FXP = {_vector(restored[name][0,indices])}')
        _block(f'FP32 logits [0:5] = {_vector(fp["fc3"][0,:5])}',
               f'FP32 logits [5:10] = {_vector(fp["fc3"][0,5:])}')
        _block(f'FXP {cfg.outputs[2].label} [0:5] = {_vector(restored["fc3"][0,:5])}',
               f'FXP {cfg.outputs[2].label} [5:10] = {_vector(restored["fc3"][0,5:])}')
        return {'sample_id':sample_id,'label':label,'config':cfg,'fp32':fp,
                'quantized':quantized,'dequantized':restored,
                'fp32_prediction':fp_prediction,'quantized_prediction':q_prediction}



    @torch.inference_mode()
    def evaluate_test(self, config=None, batch_size=512, device='auto'):
        """Compare FP32 and the chosen int8 format on the entire MNIST test set."""
        if not isinstance(batch_size,int) or batch_size < 1:
            raise ValueError('batch_size must be a positive integer')
        cfg = config or make_config(input_frac=5,weight_frac=(7,7,7),
                                    output_frac=(2,2,2),hidden_signed=False)
        device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device == 'auto' else device)
        with (self.data_root/'t10k-images-idx3-ubyte').open('rb') as f:
            magic,count,rows,cols = struct.unpack('>IIII',f.read(16))
            if magic != 2051 or count < 1 or (rows,cols) != (28,28):
                raise ValueError('Invalid MNIST image header')
            pixels = np.frombuffer(f.read(),dtype=np.uint8).copy()
            if pixels.size != count*784:
                raise ValueError('Invalid MNIST image payload size')
            pixels = pixels.reshape(count,784)
        with (self.data_root/'t10k-labels-idx1-ubyte').open('rb') as f:
            magic,labels_count = struct.unpack('>II',f.read(8))
            labels = np.frombuffer(f.read(),dtype=np.uint8).copy()
            if magic != 2049 or labels_count != count or labels.size != count:
                raise ValueError('Invalid MNIST label payload')
        model = MNISTMLP().to(device).eval()
        model.load_state_dict(self.model.state_dict(),strict=True)
        params = {k:v.detach().cpu().numpy() for k,v in self.model.state_dict().items()}
        engine = IntegerMLP(params,device)
        fp_correct = q_correct = changed = 0
        previous_tf32 = torch.backends.cuda.matmul.allow_tf32
        try:
            torch.backends.cuda.matmul.allow_tf32 = False
            for start in range(0,count,batch_size):
                stop = min(start+batch_size,count)
                x = torch.from_numpy(pixels[start:stop]).to(device,torch.float32)
                x = (x/255.0-self.mean)/self.std
                y = torch.from_numpy(labels[start:stop]).to(device,torch.int64)
                fp_pred = model(x).argmax(1)
                q_pred = engine.forward(x,cfg,verify_cpu=(start==0))['q'].argmax(1)
                fp_correct += int((fp_pred==y).sum())
                q_correct += int((q_pred==y).sum())
                changed += int((fp_pred!=q_pred).sum())
        finally:
            torch.backends.cuda.matmul.allow_tf32 = previous_tf32
        fp_accuracy,q_accuracy = 100*fp_correct/count,100*q_correct/count
        _block(f'MNIST test: {count} images | device={device}',cfg.label())
        _block(f'FP32      : {fp_accuracy:.2f}% ({fp_correct}/{count})',
               f'8-bit FXP : {q_accuracy:.2f}% ({q_correct}/{count})')
        _block(f'Difference (FXP - FP32): {q_accuracy-fp_accuracy:+.2f} percentage points',
               f'Predictions changed: {changed}/{count}')
        return {'count':count,'config':cfg,'fp32_correct':fp_correct,'quantized_correct':q_correct,
                'fp32_accuracy':fp_accuracy,'quantized_accuracy':q_accuracy,
                'difference_pp':q_accuracy-fp_accuracy,'predictions_changed':changed}



@dataclass
class LayerSample:
    layer: str
    sample_id: int
    label: int
    input_start: int
    output_start: int
    inputs: torch.Tensor
    weights: torch.Tensor
    bias: torch.Tensor

    @property
    def input_slice(self):
        return slice(self.input_start, self.input_start+4)

    def _print(self, inputs, weights, products, partials, full_sum, bias, linear, output,
               quantized=False, formats=None, stored_bias=None, bias_format=None):
        k, j = self.input_start, self.output_start
        kind = '8-bit FXP (real values)' if quantized else 'FP32'
        header = f'{self.layer} | sample={self.sample_id} (label={self.label}) | {kind}'
        if quantized:
            fi, fw, fo = formats
            bias_info = '' if bias_format is None else f'; bias={bias_format.label}'
            _block(header, f'input={fi.label}; weight={fw.label}; output={fo.label}; psum=S32/F{fi.frac+fw.frac}{bias_info}')
        else:
            _block(header)
        _block(f'input [{k}:{k+4}] = {_vector(inputs[self.input_slice])}')
        _block(*(f'weight [{j+r},{k}:{k+4}] = {_vector(weights[r,self.input_slice])}' for r in range(2)))
        _block(*(f'mul [{j+r}] = {_vector(products[r,self.input_slice])}  (input * weight)' for r in range(2)))
        tag = 'psum32' if quantized else 'psum'
        _block(*(f'{tag} [{j+r}] = {_vector(partials[r])}  (shown 4 only)' for r in range(2)))
        _block(f'full_sum{32 if quantized else ""} ({len(inputs)} inputs) = {_vector(full_sum)}')
        bias_line = f'bias{32 if quantized else ""} [{j}:{j+2}] = {_vector(bias)}'
        if stored_bias is None:
            _block(bias_line)
        else:
            _block(f'bias8 [{j}:{j+2}] = {_vector(stored_bias)}', bias_line)
        activation = 'ReLU -> ' if self.layer != 'fc3' else ''
        _block(f'{"acc32" if quantized else "linear"} = {_vector(linear)}  (full_sum + bias)',
               f'{"output8" if quantized else "output"} = {_vector(output)}  ({activation}{"requantize" if quantized else "layer output"})')

    @torch.inference_mode()
    def show_float(self):
        products = self.weights*self.inputs
        partials = products[:,self.input_slice].cumsum(1)
        full_sum = products.sum(1)
        linear = full_sum+self.bias
        output = torch.relu(linear) if self.layer != 'fc3' else linear
        self._print(self.inputs, self.weights, products, partials, full_sum, self.bias, linear, output)
        return {'input':self.inputs, 'weight':self.weights, 'products':products,
                'partial_sum':partials, 'full_sum':full_sum, 'bias':self.bias,
                'linear':linear, 'output':output}

    @torch.inference_mode()
    def show_quantized(self, input_frac=4, weight_frac=4, output_frac=4,
                       input_signed=True, output_signed=True, bias_frac=None,
                       output_rounding='nearest_even'):
        fi, fw, fo = Fxp8(input_signed,input_frac), Fxp8(True,weight_frac), Fxp8(output_signed,output_frac)
        # Reuse shared configuration validation, including signed RTL mode.
        make_config(input_frac=input_frac, weight_frac=weight_frac, output_frac=output_frac,
                    input_signed=input_signed, hidden_signed=output_signed, output_signed=output_signed,
                    bias_frac=bias_frac, output_rounding=output_rounding)
        bf = None if bias_frac is None else Fxp8(True,bias_frac)
        bias, bias8 = quantize_bias(self.bias, fi.frac+fw.frac, bf)
        qx, qw = encode(self.inputs,fi), encode(self.weights,fw)
        # Both operands are extended before multiplication, avoiding 8-bit overflow.
        products = qw.to(torch.int32)*qx.to(torch.int32)
        # int64 guards the entire prefix path, then verified results are stored as int32.
        prefixes = products.to(torch.int64).cumsum(1)
        _int32(prefixes, 'partial sum')
        _int32(prefixes+bias.to(torch.int64)[:,None], 'bias-initialized accumulator')
        partials = _int32(products[:,self.input_slice].to(torch.int64).cumsum(1), 'visible partial sum')
        full_sum = _int32(prefixes[:,-1], 'full sum')
        linear = _int32(full_sum.to(torch.int64)+bias.to(torch.int64), 'accumulator plus bias')
        activated = linear.clamp_min(0) if self.layer != 'fc3' else linear
        output = requantize(activated,fi.frac+fw.frac,fo,output_rounding)
        # Show represented real values; integer arithmetic above is unchanged.
        acc_scale = 2.0**-(fi.frac+fw.frac)
        real_values = {
            'input': qx.double()*2.0**-fi.frac,
            'weight': qw.double()*2.0**-fw.frac,
            'products': products.double()*acc_scale,
            'partial_sum': partials.double()*acc_scale,
            'full_sum': full_sum.double()*acc_scale,
            'bias': bias.double()*acc_scale,
            'linear': linear.double()*acc_scale,
            'output': output.double()*2.0**-fo.frac,
        }
        self._print(*(real_values[k] for k in ('input','weight','products','partial_sum',
                                              'full_sum','bias','linear','output')),
                    quantized=True,formats=(fi,fw,fo), bias_format=bf,
                    stored_bias=None if bias8 is None else bias8.double()*2.0**-bf.frac)
        return {'input':qx, 'weight':qw, 'products':products, 'partial_sum':partials,
                'full_sum':full_sum, 'bias':bias, 'linear':linear, 'output':output,
                'formats':(fi,fw,fo), 'dequantized':real_values, 'bias8':bias8, 'bias_format':bf}
