"""Eight-bit fixed-point formats and the integer MLP reference path.

Storage: signed int8 weights; int8/uint8 activations; signed int32 accumulators.
Optional RTL rules: signed int8 bias aligned to int32; arithmetic output shift.
Defaults retain the original int32-bias / nearest-even analysis behavior.
Float64 GEMM accelerates exact integer operations only after a conservative
partial-sum bound proves that all sums fit signed int32. Sample paths are also
compared against CPU int64 matrix multiplication.
"""
from dataclasses import dataclass
from functools import lru_cache
from numbers import Integral
import torch

@dataclass(frozen=True)
class Fxp8:
    signed: bool
    frac: int

    def __post_init__(self):
        if not isinstance(self.signed, bool):
            raise TypeError('signed must be True or False')
        if not isinstance(self.frac, Integral) or not 0 <= self.frac <= 16:
            raise ValueError('Unsupported fractional bit count')

    @property
    def lo(self):
        return -128 if self.signed else 0

    @property
    def hi(self):
        return 127 if self.signed else 255

    @property
    def dtype(self):
        return torch.int8 if self.signed else torch.uint8

    @property
    def label(self):
        return f"{('S8' if self.signed else 'U8')}/F{self.frac}"

def encode(x, fmt):
    return torch.round(x.double() * 2.0 ** fmt.frac).clamp(fmt.lo, fmt.hi).to(fmt.dtype)

def decode(q, fmt):
    return q.double() * 2.0 ** (-fmt.frac)

def quant_stats(x, fmt):
    x = x.double()
    raw = torch.round(x * 2.0 ** fmt.frac)
    restored = decode(encode(x, fmt), fmt)
    error = restored - x
    return {'format': fmt.label, 'min_repr': fmt.lo * 2.0 ** (-fmt.frac), 'max_repr': fmt.hi * 2.0 ** (-fmt.frac), 'step': 2.0 ** (-fmt.frac), 'MAE': float(error.abs().mean()), 'MSE': float(error.square().mean()), 'max_error': float(error.abs().max()), 'outside_%': float(((x < fmt.lo * 2.0 ** (-fmt.frac)) | (x > fmt.hi * 2.0 ** (-fmt.frac))).double().mean() * 100), 'saturation_%': float(((raw < fmt.lo) | (raw > fmt.hi)).double().mean() * 100), 'zero_%': float((encode(x, fmt) == 0).double().mean() * 100)}

def requantize_codes(acc32, source_frac, target_fmt, rounding='nearest_even'):
    if rounding == 'nearest_even':
        return torch.round(acc32.double() * 2.0 ** (target_fmt.frac-source_frac))
    if rounding != 'truncate':
        raise ValueError('rounding must be nearest_even or truncate')
    shift = source_frac-target_fmt.frac
    if not 0 <= shift <= 31:
        raise ValueError('RTL output shift must be in 0..31')
    # Signed arithmetic shift: negative values round toward minus infinity.
    return acc32 >> shift


def requantize(acc32, source_frac, target_fmt, rounding='nearest_even'):
    codes = requantize_codes(acc32, source_frac, target_fmt, rounding)
    return codes.clamp(target_fmt.lo, target_fmt.hi).to(target_fmt.dtype)


def quantize_bias(bias, source_frac, bias_fmt=None):
    """Return aligned int32 bias and optional stored int8 bias.

    Offline FP32-to-int8 conversion keeps nearest-even rounding. Alignment
    widens before shifting and checks overflow before casting back to int32.
    """
    bias8 = None if bias_fmt is None else encode(bias, bias_fmt)
    if bias_fmt is None:
        aligned = torch.round(bias.double() * 2.0 ** source_frac)
    else:
        if not bias_fmt.signed:
            raise ValueError('Bias must be signed 8-bit')
        shift = source_frac-bias_fmt.frac
        if not -32 <= shift <= 31:
            raise ValueError('RTL bias shift must be in -32..31')
        wide = bias8.to(torch.int64)
        aligned = (wide << shift) if shift >= 0 else (wide >> -shift)
    if bool(((aligned < -(2**31)) | (aligned > 2**31-1)).any()):
        raise OverflowError('Aligned bias does not fit int32')
    return aligned.to(torch.int32), bias8

@dataclass(frozen=True)
class QuantConfig:
    input: Fxp8
    weights: tuple
    outputs: tuple
    biases: tuple = None
    output_rounding: str = 'nearest_even'

    def __post_init__(self):
        if len(self.weights) != 3 or len(self.outputs) != 3:
            raise ValueError('Exactly three weight and output formats are required')
        if any(not f.signed for f in self.weights):
            raise ValueError('Weights must always be signed 8-bit')
        if self.biases is not None and (len(self.biases) != 3 or any(not f.signed for f in self.biases)):
            raise ValueError('Exactly three signed 8-bit bias formats are required')
        if self.output_rounding not in ('nearest_even', 'truncate'):
            raise ValueError('output_rounding must be nearest_even or truncate')
        if self.output_rounding == 'truncate':
            if not self.input.signed or any(not f.signed for f in self.outputs):
                raise ValueError('RTL mode requires signed inputs and outputs')
            for inf, wf, of in zip((self.input, *self.outputs[:2]), self.weights, self.outputs):
                if not 0 <= inf.frac+wf.frac-of.frac <= 31:
                    raise ValueError('RTL output shift must be in 0..31')

    def label(self):
        label = '|'.join([self.input.label, 'W:' + ','.join((str(f.frac) for f in self.weights)), 'A:' + ','.join((f.label for f in self.outputs))])
        if self.biases is not None:
            label += '|B:' + ','.join(f.label for f in self.biases)
        if self.output_rounding != 'nearest_even':
            label += '|ASR'
        return label

    def as_dict(self):
        result = {'input': vars(self.input), 'weights': [vars(f) for f in self.weights], 'outputs': [vars(f) for f in self.outputs]}
        if self.biases is not None:
            result['biases'] = [vars(f) for f in self.biases]
        if self.output_rounding != 'nearest_even':
            result['output_rounding'] = self.output_rounding
        return result

def make_config(input_frac=4, weight_frac=4, output_frac=4, input_signed=True, hidden_signed=True, output_signed=True,
                bias_frac=None, output_rounding='nearest_even'):
    """Build a fixed 8-bit configuration; an int or three-item tuple selects F.

    Weight signedness is always True. hidden_signed accepts one bool or a
    two-item tuple. Choosing unsigned for negative inputs/logits is allowed
    for explicit diagnostics and uses saturation at zero.
    """

    def triple(value, name):
        values = (value,) * 3 if isinstance(value, Integral) else tuple(value)
        if len(values) != 3:
            raise ValueError(name + ' must be an int or a three-item tuple')
        return values
    w = triple(weight_frac, 'weight_frac')
    a = triple(output_frac, 'output_frac')
    h = (hidden_signed,) * 2 if isinstance(hidden_signed, bool) else tuple(hidden_signed)
    if len(h) != 2:
        raise ValueError('hidden_signed must be a bool or two-item tuple')
    return QuantConfig(Fxp8(input_signed, input_frac), tuple((Fxp8(True, f) for f in w)), (Fxp8(h[0], a[0]), Fxp8(h[1], a[1]), Fxp8(output_signed, a[2])),
                       None if bias_frac is None else tuple(Fxp8(True, f) for f in triple(bias_frac, 'bias_frac')),
                       output_rounding)

class IntegerMLP:

    def __init__(self, params, device):
        self.params = params
        self.device = device

    @lru_cache
    @torch.inference_mode()
    def prepare(self, cfg):
        packed = []
        input_fmt = cfg.input
        for idx, layer in enumerate(('fc1', 'fc2', 'fc3')):
            wf, of = (cfg.weights[idx], cfg.outputs[idx])
            w = encode(torch.as_tensor(self.params[layer + '.weight'], device=self.device), wf)
            raw_bias, _ = quantize_bias(
                torch.as_tensor(self.params[layer + '.bias'], device=self.device, dtype=torch.float64),
                input_fmt.frac + wf.frac, None if cfg.biases is None else cfg.biases[idx])
            packed.append((w, raw_bias.to(torch.int32), input_fmt, wf, of))
            input_fmt = of
        return packed

    @torch.inference_mode()
    def forward(self, x, cfg, trace=False, verify_cpu=False):
        q = encode(x, cfg.input)
        traces = {'input': {'q': q, 'restored': decode(q, cfg.input), 'format': cfg.input}}
        stats = []
        for idx, (w, b, inf, wf, of) in enumerate(self.prepare(cfg)):
            bound = q.double().abs().max() * w.double().abs().sum(1) + b.double().abs()
            if float(bound.max()) > 2 ** 31 - 1:
                raise OverflowError(f'FC{idx + 1} accumulator may overflow int32')
            acc_exact = q.double() @ w.double().T + b.double()
            acc32 = acc_exact.to(torch.int32)
            if verify_cpu:
                n = min(3, len(q))
                cpu_ref = q[:n].cpu().to(torch.int64) @ w.cpu().to(torch.int64).T + b.cpu().to(torch.int64)
                assert torch.equal(acc32[:n].cpu().to(torch.int64), cpu_ref), 'Integer matmul mismatch'
            source_frac = inf.frac + wf.frac
            real_before = acc32.double() * 2.0 ** (-source_frac)
            if idx < 2:
                real_before = real_before.clamp_min(0)
            raw_codes = requantize_codes(acc32.clamp_min(0) if idx < 2 else acc32, source_frac, of, cfg.output_rounding)
            q = raw_codes.clamp(of.lo, of.hi).to(of.dtype)
            restored = decode(q, of)
            stats.append({'layer': f'fc{idx + 1}', 'format': of.label, 'acc_abs_bound': float(bound.max()), 'saturation_%': float(((raw_codes < of.lo) | (raw_codes > of.hi)).double().mean() * 100), 'local_MSE': float((restored - real_before).square().mean())})
            if trace:
                traces[f'fc{idx + 1}'] = {'q': q, 'restored': restored, 'format': of, 'acc32': acc32, 'bias32': b, 'weight8': w, 'before_quant': real_before}
                if cfg.biases is not None:
                    traces[f'fc{idx + 1}']['bias8'] = encode(
                        torch.as_tensor(self.params[f'fc{idx + 1}.bias'], device=self.device), cfg.biases[idx])
        return {'q': q, 'logits': decode(q, cfg.outputs[-1]), 'trace': traces if trace else {}, 'stats': stats}
