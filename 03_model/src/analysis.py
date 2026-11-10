"""Notebook-facing API for model inspection, custom FXP experiments and search.

Model definition is copied from assignment1. Data normalization, evaluation,
and figure logic are the project-specific parts adapted from its MLP tools.
The notebook only sets parameters and invokes the methods below.
"""
from pathlib import Path
from dataclasses import replace
import csv
import hashlib
import html
import json
import platform
import time
import numpy as np
import matplotlib.pyplot as plt
import torch
from torchvision import datasets
from IPython.display import display, HTML
from .models import MNISTMLP
from .quantization import Fxp8, QuantConfig, IntegerMLP, encode, decode, quant_stats, requantize, make_config

def show_table(rows, columns=None, limit=None):
    rows = list(rows)
    if not rows:
        display(HTML('<p>No rows.</p>'))
        return
    columns = list(dict.fromkeys((k for r in rows for k in r))) if columns is None else list(columns)

    def fmt(v):
        return f'{v:.7g}' if isinstance(v, (float, np.floating)) else str(v)
    body = ''.join(('<tr>' + ''.join(('<td>' + html.escape(fmt(r.get(k, ''))) + '</td>' for k in columns)) + '</tr>' for r in rows[:limit]))
    display(HTML('<div style="overflow:auto;max-height:520px"><table><thead><tr>' + ''.join(('<th>' + html.escape(k) + '</th>' for k in columns)) + '</tr></thead><tbody>' + body + '</tbody></table></div>'))

def value_stats(name, t):
    v = t.detach().double()
    return {'tensor': name, 'shape': str(tuple(v.shape)), 'min': float(v.min()), 'max': float(v.max()), 'mean': float(v.mean()), 'std': float(v.std(unbiased=False)), 'negative_%': float((v < 0).double().mean() * 100)}

def rank(row):
    return (-row['accuracy_%'], row['logit_MSE'])

class MLPAnalysis:
    """High-level notebook API. Setup once, then run the visible analysis stages."""

    def __init__(self, seed=42, preprocessing='auto_calibration', calibration_per_digit=100, sample_count=10, batch_size=512, device='auto', data_root=None):
        if not 1 <= sample_count <= 10 or not 1 <= calibration_per_digit <= 500:
            raise ValueError('sample_count: 1..10; calibration_per_digit: 1..500')
        if batch_size < 1:
            raise ValueError('batch_size must be positive')
        self.root = Path(__file__).resolve().parents[3]
        self.project = self.root / 'project'
        self.checkpoint = self.project / '03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth'
        self.result_dir = self.project / '07_runs/mlp_int8_analysis'
        candidates = [self.root / 'data/mnist', self.root / 'assignment1/data/mnist', self.project / '02_data/raw', self.root / 'data']
        self.data_root = Path(data_root).resolve() if data_root else next((p for p in candidates if (p / 'MNIST/raw/train-images-idx3-ubyte').is_file()), None)
        if self.data_root is None:
            raise FileNotFoundError('MNIST raw files not found in ' + str(candidates))
        self.seed, self.preprocessing = (seed, preprocessing)
        self.calib_per_digit, self.sample_count, self.batch_size = (calibration_per_digit, sample_count, batch_size)
        self.device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device == 'auto' else device)
        self.weight_layer, self.weight_row, self.weight_columns = ('fc1', 0, slice(0, 16))
        self.results, self.format_search_rows = ([], [])
        self.best_configs, self.calibration_cache, self.manual_configs = ({}, {}, {})
        self.recommended_config, self.recommended_profile = (None, None)
        self.last_config = make_config()
        np.random.seed(seed)
        torch.manual_seed(seed)
        if self.device.type == 'cuda':
            torch.cuda.manual_seed_all(seed)
            torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.set_float32_matmul_precision('highest')
        np.set_printoptions(precision=7, suppress=True, linewidth=130)
        self._load_model()
        self.show_environment()

    def show_environment(self):
        show_table([{'Python': platform.python_version(), 'PyTorch': torch.__version__, 'NumPy': np.__version__, 'device': str(self.device)}])
        print('Checkpoint:', self.checkpoint.relative_to(self.root))
        print('MNIST:', self.data_root.relative_to(self.root))

    def _load_model(self):
        loaded = torch.load(self.checkpoint, map_location='cpu', weights_only=True)
        state = loaded.get('model_state_dict', loaded.get('state_dict', loaded))
        self.model = MNISTMLP().to(self.device)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        self.params = {k: v.detach().cpu().numpy().copy() for k, v in self.model.state_dict().items()}
        self.checkpoint_sha256 = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()
        self.quantizer = IntegerMLP(self.params, self.device)
        self.selected_weight = self.params['fc1.weight']

    def show_model(self):
        """Show the restored model and every parameter shape."""
        print(self.model)
        show_table([{'parameter': k, 'shape': str(v.shape), 'dtype': str(v.dtype), 'count': v.size} for k, v in self.params.items()])
        print('Total parameters:', sum((v.size for v in self.params.values())))
        print('SHA-256:', self.checkpoint_sha256)

    def load_data(self):
        """Compare preprocessing on train calibration and show a few inputs."""
        self.train_set = datasets.MNIST(self.data_root, train=True, download=False)
        self.test_set = datasets.MNIST(self.data_root, train=False, download=False)
        rng = np.random.default_rng(self.seed)
        self.calib_ids = np.concatenate([rng.choice(np.flatnonzero(self.train_set.targets.numpy() == d), self.calib_per_digit, replace=False) for d in range(10)])
        rng.shuffle(self.calib_ids)
        self.calib_unit = self.train_set.data[torch.as_tensor(self.calib_ids)].reshape(-1, 784).to(self.device, torch.float32) / 255.0
        self.calib_y = self.train_set.targets[torch.as_tensor(self.calib_ids)].to(self.device)
        self.preprocessors = {'unit_0_1': (0.0, 1.0), 'mnist_standard': (0.1307, 0.3081), 'minus1_plus1': (0.5, 0.5)}
        self.preprocess_rows = []
        with torch.inference_mode():
            for name, (mean, std) in self.preprocessors.items():
                values = (self.calib_unit - mean) / std
                logits = self.model(values)
                self.preprocess_rows.append({'preprocessing': name, 'calibration_accuracy_%': float((logits.argmax(1) == self.calib_y).double().mean() * 100), 'input_min': float(values.min()), 'input_max': float(values.max())})
        self.preprocess_selected = max(self.preprocess_rows, key=lambda r: r['calibration_accuracy_%'])['preprocessing'] if self.preprocessing == 'auto_calibration' else self.preprocessing
        if self.preprocess_selected not in self.preprocessors:
            raise ValueError('Unknown PREPROCESSING')
        self.input_mean, self.input_std = self.preprocessors[self.preprocess_selected]
        self.calib_x = (self.calib_unit - self.input_mean) / self.input_std
        self.input_is_nonnegative = bool(float(self.calib_x.min()) >= 0)
        self.test_unit = self.test_set.data.reshape(-1, 784).to(self.device, torch.float32) / 255.0
        self.test_x = (self.test_unit - self.input_mean) / self.input_std
        self.test_y = self.test_set.targets.to(self.device)
        self.sample_ids = np.array([int(torch.where(self.test_set.targets == d)[0][0]) for d in range(10)])[:self.sample_count]
        self.sample_x = self.test_x[torch.as_tensor(self.sample_ids, device=self.device)]
        self.sample_y = self.test_y[torch.as_tensor(self.sample_ids, device=self.device)]
        show_table(self.preprocess_rows)
        print('Selected using TRAIN calibration only:', self.preprocess_selected)
        print('Training preprocessing was not supplied; this is empirical selection, not proof of the original training configuration.')
        print('Normalized input can be negative:', not self.input_is_nonnegative)
        fig, axes = plt.subplots(1, len(self.sample_ids), figsize=(max(6, len(self.sample_ids) * 1.4), 2.1), squeeze=False)
        for ax, idx in zip(axes.flat, self.sample_ids):
            ax.imshow(self.test_set.data[idx], cmap='gray', vmin=0, vmax=255)
            ax.set_title(f'id={idx}, y={int(self.test_set.targets[idx])}')
            ax.axis('off')
        plt.tight_layout()
        plt.show()
        print('Calibration/train:', len(self.calib_ids), '| Final test:', len(self.test_set))
        print('Example normalized 28x28 patch (rows 8:16, columns 8:16):')
        print(self.sample_x[0].reshape(28, 28)[8:16, 8:16].cpu().numpy())
        raw_example = self.test_set.data[self.sample_ids[0]].flatten().numpy()
        active = np.flatnonzero(raw_example > 0)
        self.preview_pixels = np.unique(np.concatenate([np.flatnonzero(raw_example == 0)[:3], active[np.linspace(0, len(active) - 1, 9, dtype=int)]]))
        show_table([{'pixel_index': int(i), 'raw_uint8': int(raw_example[i]), 'unit_0_1': float(self.test_unit[self.sample_ids[0], i]), 'model_input': float(self.sample_x[0, i])} for i in self.preview_pixels])
        self.q44_signed = make_config()
        self.q44_unsigned = make_config(input_signed=not self.input_is_nonnegative, hidden_signed=False)

    @torch.inference_mode()
    def _fp_trace(self, x):
        z1 = self.model.fc1(x)
        a1 = torch.relu(z1)
        z2 = self.model.fc2(a1)
        a2 = torch.relu(z2)
        return {'input': x, 'fc1_pre_relu': z1, 'fc1': a1, 'fc2_pre_relu': z2, 'fc2': a2, 'fc3': self.model.fc3(a2)}

    @torch.inference_mode()
    def _fp_logits(self, x):
        return torch.cat([self.model(x[i:i + self.batch_size]) for i in range(0, len(x), self.batch_size)])

    def baseline(self):
        """Compute FP32 references and final test accuracy."""
        self.calib_fp = self._fp_trace(self.calib_x)
        self.sample_fp = self._fp_trace(self.sample_x)
        self.test_fp_logits = self._fp_logits(self.test_x)
        self.fp_test_accuracy = float((self.test_fp_logits.argmax(1) == self.test_y).double().mean() * 100)
        print(f'FP32 test accuracy: {self.fp_test_accuracy:.2f}%')
        show_table([value_stats(k, v) for k, v in self.calib_fp.items()])
        show_table([{'digit': d, 'test_count': int((self.test_y == d).sum()), 'accuracy_%': float((self.test_fp_logits.argmax(1)[self.test_y == d] == d).double().mean() * 100)} for d in range(10)])
        print('Example final logits:', self.sample_fp['fc3'][0].cpu().numpy())

    def show_weights(self, layer='fc1', row=0, columns=slice(0, 16)):
        """Inspect any row/slice of the complete NumPy weight arrays."""
        self.weight_layer, self.weight_row, self.weight_columns = (layer, row, columns)
        show_table([value_stats(k, torch.as_tensor(v)) for k, v in self.params.items()])
        self.selected_weight = self.params[f'{self.weight_layer}.weight']
        print(f'{self.weight_layer}.weight shape={self.selected_weight.shape}, row={self.weight_row}, columns={self.weight_columns}')
        print(self.selected_weight[self.weight_row, self.weight_columns])
        print(f'{self.weight_layer}.bias (first 16):', self.params[f'{self.weight_layer}.bias'][:16])
        print('Complete arrays: PARAMS["fc1.weight"], PARAMS["fc2.weight"], etc.')

    def show_distributions(self):
        fig, axes = plt.subplots(2, 4, figsize=(16, 6))
        for ax, name in zip(axes[0], ['fc1.weight', 'fc2.weight', 'fc3.weight', 'fc3.bias']):
            ax.hist(self.params[name].ravel(), bins=80, log=True)
            ax.set_title(name)
            ax.set_ylabel('count (log)')
        for ax, name in zip(axes[1], ['input', 'fc1', 'fc2', 'fc3']):
            ax.hist(self.calib_fp[name].detach().cpu().numpy().ravel(), bins=80, log=True)
            ax.set_title(name)
            ax.set_xlabel('FP32 value')
        plt.tight_layout()
        plt.show()
        show_table([{'tensor': k, 'p0': float(v.min()), 'p50': float(torch.quantile(v.double().flatten(), 0.5)), 'p99': float(torch.quantile(v.double().flatten(), 0.99)), 'p100': float(v.max()), 'zero_%': float((v == 0).double().mean() * 100)} for k, v in self.calib_fp.items() if k in ('input', 'fc1', 'fc2', 'fc3')])

    def check_quantizer(self):
        probe = torch.tensor([-9.0, -8.0, -0.09375, -0.03125, 0.0, 0.03125, 0.09375, 1.0, 7.9375, 8.0, 16.0])
        s4, u4 = (Fxp8(True, 4), Fxp8(False, 4))
        show_table([{'original': float(x), 'S8_F4_code': int(a), 'S8_F4_restored': float(b), 'U8_F4_code': int(c), 'U8_F4_restored': float(d)} for x, a, b, c, d in zip(probe, encode(probe, s4), decode(encode(probe, s4), s4), encode(probe, u4), decode(encode(probe, u4), u4))])
        assert encode(torch.tensor([-0.09375, -0.03125, 0.03125, 0.09375]), s4).tolist() == [-2, 0, 0, 2]
        assert encode(torch.tensor([-100.0, 100.0]), s4).tolist() == [-128, 127]
        assert encode(torch.tensor([-1.0, 100.0]), u4).tolist() == [0, 255]
        assert requantize(torch.tensor([-7, -5, -3, -1, 1, 3, 5, 7], dtype=torch.int32), 1, Fxp8(True, 0)).tolist() == [-4, -2, -2, 0, 0, 2, 2, 4]
        print('Boundary, saturation, and signed nearest-even checks: PASS')

    def show_input_quantization(self, cfg=None):
        cfg = cfg or self.last_config
        input_formats = list(dict.fromkeys([cfg.input] + [Fxp8(True, 4), Fxp8(True, 5), Fxp8(True, 6), Fxp8(False, 7), Fxp8(False, 8)]))
        show_table([quant_stats(self.calib_x, f) for f in input_formats])
        fig, axes = plt.subplots(2, len(input_formats) + 1, figsize=(16, 5), layout='constrained')
        original = self.sample_x[0].reshape(28, 28).cpu().numpy()
        lo, hi = (min(-0.5, float(original.min())), max(1.0, float(original.max())))
        axes[0, 0].imshow(original, cmap='gray', vmin=lo, vmax=hi)
        axes[0, 0].set_title('FP32 input')
        axes[1, 0].axis('off')
        for j, f in enumerate(input_formats, 1):
            restored = decode(encode(self.sample_x[0], f), f).reshape(28, 28).cpu().numpy()
            axes[0, j].imshow(restored, cmap='gray', vmin=lo, vmax=hi)
            axes[0, j].set_title(f.label)
            error_image = axes[1, j].imshow(restored - original, cmap='coolwarm', vmin=-0.5, vmax=0.5)
            axes[1, j].set_title('restored - FP32')
        for ax in axes.flat:
            ax.set_xticks([])
            ax.set_yticks([])
        fig.colorbar(error_image, ax=list(axes[1, 1:]), shrink=0.6, label='quantization error')
        plt.show()
        example_fmt = cfg.input
        example_q = encode(self.sample_x[0], example_fmt)
        show_table([{'pixel': int(i), 'original': float(self.sample_x[0, i]), 'code8': int(example_q[i]), 'bits': format(int(example_q[i]) & 255, '08b'), 'restored': float(decode(example_q[i], example_fmt))} for i in self.preview_pixels])
        print('Unsigned model-input quantization is diagnostic when normalization produces negative inputs.')

    def show_weight_quantization(self, cfg=None):
        cfg = cfg or self.last_config
        self.weight_rows = []
        for layer in ('fc1', 'fc2', 'fc3'):
            w = torch.as_tensor(self.params[layer + '.weight'], device=self.device)
            for frac in sorted({4, 5, 6, 7, cfg.weights[('fc1', 'fc2', 'fc3').index(layer)].frac}):
                self.weight_rows.append({'layer': layer, **quant_stats(w, Fxp8(True, frac))})
        show_table(self.weight_rows)
        w_preview = torch.as_tensor(self.selected_weight[self.weight_row, self.weight_columns], device=self.device)
        preview_columns = np.arange(self.selected_weight.shape[1])[self.weight_columns]
        show_table([{'column': int(preview_columns[i]), 'original': float(v), **{f'F{f}_code': int(encode(v, Fxp8(True, f))) for f in (4, 6, 7)}, **{f'F{f}_restored': float(decode(encode(v, Fxp8(True, f)), Fxp8(True, f))) for f in (4, 6, 7)}} for i, v in enumerate(w_preview)])
        current_format = cfg.weights[('fc1', 'fc2', 'fc3').index(self.weight_layer)]
        show_table([{'column': int(preview_columns[i]), 'original': float(v), 'current_format': current_format.label,
                     'current_code8': int(encode(v, current_format)), 'current_restored': float(decode(encode(v, current_format), current_format))}
                    for i, v in enumerate(w_preview)])
        fig, axes = plt.subplots(1, 3, figsize=(13, 3))
        for ax, layer in zip(axes, ('fc1', 'fc2', 'fc3')):
            rows = [r for r in self.weight_rows if r['layer'] == layer]
            ax.plot([int(r['format'].split('F')[1]) for r in rows], [r['MSE'] for r in rows], marker='o')
            ax.set_title(layer + ' weight')
            ax.set_xlabel('fractional bits')
            ax.set_ylabel('MSE')
            ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.show()

    def show_pipeline(self, cfg=None):
        cfg = cfg or self.last_config
        self.sample_q44 = self.quantizer.forward(self.sample_x, cfg, trace=True, verify_cpu=True)
        show_table(self.sample_q44['stats'])
        for name, entry in self.sample_q44['trace'].items():
            print(name, entry['format'].label, str(entry['q'].dtype), '| codes:', entry['q'][0, :12].cpu().numpy(), '| restored:', entry['restored'][0, :12].cpu().numpy())
        show_table([{'class': i, 'FP32_logit': float(self.sample_fp['fc3'][0, i]), 'code8': int(self.sample_q44['q'][0, i]), 'restored': float(self.sample_q44['logits'][0, i])} for i in range(10)])
        assert all((e['q'].dtype in (torch.int8, torch.uint8) for e in self.sample_q44['trace'].values()))
        print('CPU int64 equivalence and 8-bit stage dtype checks: PASS')

    @torch.inference_mode()
    def _assess(self, name, cfg, x, y, fp_reference, phase='calibration'):
        logits, stat_batches = ([], [])
        started = time.perf_counter()
        for i in range(0, len(x), self.batch_size):
            result = self.quantizer.forward(x[i:i + self.batch_size], cfg)
            logits.append(result['logits'])
            stat_batches.append((len(x[i:i + self.batch_size]), result['stats']))
        logits = torch.cat(logits)
        pred = logits.argmax(1)
        row = {'phase': phase, 'experiment': name, 'accuracy_%': float((pred == y).double().mean() * 100), 'prediction_changed_%': float((pred != fp_reference.argmax(1)).double().mean() * 100), 'logit_MSE': float((logits - fp_reference.double()).square().mean()), 'argmax_tie_%': float(((logits == logits.max(1, keepdim=True).values).sum(1) > 1).double().mean() * 100), 'config': cfg.label()}
        for idx in range(3):
            row[f'fc{idx + 1}_saturation_%'] = sum((n * s[idx]['saturation_%'] for n, s in stat_batches)) / len(x)
        row['seconds'] = time.perf_counter() - started
        return (row, logits)

    def compare_q44(self):
        for name, cfg in [('q44_signed', self.q44_signed), ('q44_unsigned_positive', self.q44_unsigned)]:
            row, _ = self._assess(name, cfg, self.calib_x, self.calib_y, self.calib_fp['fc3'])
            self.results.append(row)
        show_table([{'phase': 'calibration', 'experiment': 'FP32', 'accuracy_%': float((self.calib_fp['fc3'].argmax(1) == self.calib_y).double().mean() * 100)}, *self.results])
        print('Calibration scores only; final test comparison is shown in the final evaluation stage.')

    def _choose_format(self, name, x, signed):
        options = []
        for frac in range(8 if signed else 9):
            f = Fxp8(signed, frac)
            stats = {'tensor': name, **quant_stats(x, f)}
            self.format_search_rows.append(stats)
            options.append((stats['MSE'], stats['saturation_%'], frac, f))
        return min(options, key=lambda r: r[:3])[-1]

    def search_formats(self):
        self.format_search_rows = []
        weight_best = tuple((self._choose_format(layer + '.weight', torch.as_tensor(self.params[layer + '.weight'], device=self.device), True) for layer in ('fc1', 'fc2', 'fc3')))
        self.seeds = {}
        for positive_unsigned in (False, True):
            signed = not positive_unsigned
            inf = self._choose_format('input', self.calib_x, signed or not self.input_is_nonnegative)
            a1 = self._choose_format('fc1', self.calib_fp['fc1'], signed)
            a2 = self._choose_format('fc2', self.calib_fp['fc2'], signed)
            out = self._choose_format('fc3', self.calib_fp['fc3'], True)
            self.seeds['unsigned_positive' if positive_unsigned else 'signed'] = QuantConfig(inf, weight_best, (a1, a2, out))
        show_table([{'profile': name, 'initial_config': cfg.label()} for name, cfg in self.seeds.items()])
        fig, axes = plt.subplots(2, 4, figsize=(16, 6))
        for ax, name in zip(axes.flat, ['fc1.weight', 'fc2.weight', 'fc3.weight', 'input', 'fc1', 'fc2', 'fc3']):
            for signed, label in [(True, 'signed'), (False, 'unsigned')]:
                prefix = 'S8' if signed else 'U8'
                rows = [r for r in self.format_search_rows if r['tensor'] == name and r['format'].startswith(prefix)]
                by_f = {int(r['format'].split('F')[1]): r for r in rows}
                if by_f:
                    fs = sorted(by_f)
                    ax.semilogy(fs, [max(by_f[f]['MSE'], 1e-16) for f in fs], marker='o', label=label)
            ax.set_title(name)
            ax.set_xlabel('fractional bits')
            ax.set_ylabel('local MSE')
            ax.grid(alpha=0.3)
            if ax.lines:
                ax.legend()
        axes.flat[-1].axis('off')
        plt.tight_layout()
        plt.show()
        print('Complete local search records:', len(self.format_search_rows), '(variable: format_search_rows)')

    def _score_config(self, name, cfg):
        if cfg not in self.calibration_cache:
            row, _ = self._assess(name, cfg, self.calib_x, self.calib_y, self.calib_fp['fc3'])
            self.calibration_cache[cfg] = row
            self.results.append(row)
        return self.calibration_cache[cfg]

    def compare_auto(self):
        self.calibration_cache = {}
        self.best_configs = {}
        for profile, seed_cfg in self.seeds.items():
            best = seed_cfg
            best_row = self._score_config(profile + '_seed', best)
            for location in ('input', 0, 1, 2):
                current = best.input if location == 'input' else best.outputs[location]
                center = best
                fractions = sorted(set([max(0, current.frac - 1), current.frac, min(7 if current.signed else 8, current.frac + 1)]))
                for frac in fractions:
                    alternative = Fxp8(current.signed, frac)
                    if location == 'input':
                        candidate = replace(center, input=alternative)
                    else:
                        outputs = list(center.outputs)
                        outputs[location] = alternative
                        candidate = replace(center, outputs=tuple(outputs))
                    row = self._score_config(f'{profile}_refine_{location}_F{frac}', candidate)
                    if rank(row) < rank(best_row):
                        best, best_row = (candidate, row)
            self.best_configs[profile] = best
            print('Selected on calibration:', profile, best.label())
        best_unsigned = self.best_configs['unsigned_positive']
        self.unsigned_final = replace(best_unsigned, outputs=(*best_unsigned.outputs[:2], Fxp8(False, best_unsigned.outputs[2].frac)))
        diagnostic_row, _ = self._assess('unsigned_final_DIAGNOSTIC', self.unsigned_final, self.calib_x, self.calib_y, self.calib_fp['fc3'])
        self.results.append(diagnostic_row)
        self.unsigned_input = replace(best_unsigned, input=Fxp8(False, best_unsigned.input.frac))
        input_diagnostic_row, _ = self._assess('unsigned_input_DIAGNOSTIC', self.unsigned_input, self.calib_x, self.calib_y, self.calib_fp['fc3'])
        self.results.append(input_diagnostic_row)
        show_table([{'profile': name, **self._score_config(name, cfg)} for name, cfg in self.best_configs.items()] + [{'profile': 'unsigned final (diagnostic)', **diagnostic_row}, {'profile': 'unsigned input (diagnostic)', **input_diagnostic_row}])
        print('Configurations frozen before final test evaluation.')

    def evaluate_final(self):
        """Evaluate frozen automatic candidates and current manual settings on test."""
        self.final_configs = {'q44_signed': self.q44_signed, 'q44_unsigned_positive': self.q44_unsigned, 'selected_signed': self.best_configs['signed'], 'selected_unsigned_positive': self.best_configs['unsigned_positive'], 'unsigned_final_DIAGNOSTIC': self.unsigned_final, 'unsigned_input_DIAGNOSTIC': self.unsigned_input}
        self.final_configs.update(self.manual_configs)
        self.recommended_profile = min(self.best_configs, key=lambda name: rank(self._score_config(name, self.best_configs[name])))
        self.recommended_config = self.best_configs[self.recommended_profile]
        self.final_logits = {}
        self.final_rows = [{'phase': 'test', 'experiment': 'FP32', 'accuracy_%': self.fp_test_accuracy, 'prediction_changed_%': 0.0, 'logit_MSE': 0.0}]
        for name, cfg in self.final_configs.items():
            row, logits = self._assess(name, cfg, self.test_x, self.test_y, self.test_fp_logits, phase='test')
            row['drop_pp'] = self.fp_test_accuracy - row['accuracy_%']
            self.final_rows.append(row)
            self.final_logits[name] = logits
        self.results.extend(self.final_rows)
        show_table(self.final_rows)
        recommended_name = 'selected_' + self.recommended_profile
        self.chosen_logits = self.final_logits[recommended_name]
        self.chosen_pred = self.chosen_logits.argmax(1)
        print('Recommended by calibration:', self.recommended_profile, self.recommended_config.label())
        show_table([{'digit': d, 'FP32_accuracy_%': float((self.test_fp_logits.argmax(1)[self.test_y == d] == d).double().mean() * 100), 'INT8_accuracy_%': float((self.chosen_pred[self.test_y == d] == d).double().mean() * 100)} for d in range(10)])
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar([r['experiment'] for r in self.final_rows], [r['accuracy_%'] for r in self.final_rows])
        ax.set_ylabel('test accuracy (%)')
        ax.set_ylim(max(0, min((r['accuracy_%'] for r in self.final_rows)) - 2), 100)
        plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.show()
        fail_ids = torch.where((self.test_fp_logits.argmax(1) == self.test_y) & (self.chosen_pred != self.test_y))[0][:8].cpu().tolist()
        if fail_ids:
            fig, axes = plt.subplots(1, len(fail_ids), figsize=(max(6, len(fail_ids) * 1.8), 2.4), squeeze=False)
            for ax, idx in zip(axes.flat, fail_ids):
                ax.imshow(self.test_set.data[idx], cmap='gray')
                ax.set_title(f'id={idx}, true={int(self.test_y[idx])}\nFP={int(self.test_fp_logits[idx].argmax())}, Q={int(self.chosen_pred[idx])}')
                ax.axis('off')
            plt.tight_layout()
            plt.show()
            idx = fail_ids[0]
            show_table([{'sample_id': idx, 'class': d, 'FP32_logit': float(self.test_fp_logits[idx, d]), 'INT8_restored_logit': float(self.chosen_logits[idx, d])} for d in range(10)])
        else:
            print('No FP32-correct / quantized-wrong case.')
        for name, cfg in [('signed', self.best_configs['signed']), ('unsigned', self.best_configs['unsigned_positive'])]:
            verification = self.quantizer.forward(self.sample_x, cfg, trace=True, verify_cpu=True)
            assert all((e['q'].element_size() == 1 for e in verification['trace'].values()))
            assert all((w.dtype == torch.int8 and b.dtype == torch.int32 for w, b, *_ in self.quantizer.prepare(cfg)))
        print('Selected signed/unsigned CPU integer equivalence and all 8-bit stage checks: PASS')

    def run_experiment(self, cfg=None, name='manual', split='test'):
        """Run one editable 8-bit configuration; keep its row for final export."""
        cfg = cfg or make_config()
        if split not in ('calibration', 'test'):
            raise ValueError('split must be calibration or test')
        if not cfg.input.signed and (not self.input_is_nonnegative):
            print('Diagnostic: negative normalized inputs will saturate to zero.')
        if not cfg.outputs[-1].signed:
            print('Diagnostic: negative final logits will saturate to zero.')
        x, y, fp = (self.calib_x, self.calib_y, self.calib_fp['fc3']) if split == 'calibration' else (self.test_x, self.test_y, self.test_fp_logits)
        row, logits = self._assess(name, cfg, x, y, fp, phase=split)
        if split == 'test':
            row['drop_pp'] = self.fp_test_accuracy - row['accuracy_%']
        self.results = [r for r in self.results if (r['phase'], r['experiment']) != (split, name)]
        self.results.append(row)
        self.manual_configs[name] = cfg
        self.last_config = cfg
        show_table([row])
        return {'config': cfg, 'metrics': row, 'logits': logits}

    def save_results(self, cfg=None, name='manual', save=True, result_dir=None):
        """Export all weights and a few inputs/outputs for the explicitly selected format."""
        export_config = cfg or self.last_config
        export_name = name
        self.result_dir = Path(result_dir).resolve() if result_dir else self.result_dir
        recommended_samples = self.quantizer.forward(self.sample_x, export_config, trace=True, verify_cpu=True)
        arrays = {'original__' + k.replace('.', '__'): v for k, v in self.params.items()}
        for idx, (w, b, *_) in enumerate(self.quantizer.prepare(export_config), 1):
            arrays[f'quantized__fc{idx}__weight'] = w.cpu().numpy()
            arrays[f'quantized__fc{idx}__bias_int32'] = b.cpu().numpy()
        for name, entry in recommended_samples['trace'].items():
            arrays[f'sample__{name}__fp32'] = self.sample_fp[name].cpu().numpy()
            arrays[f'sample__{name}__code8'] = entry['q'].cpu().numpy()
            arrays[f'sample__{name}__restored'] = entry['restored'].cpu().numpy()
            if 'acc32' in entry:
                arrays[f'sample__{name}__acc32'] = entry['acc32'].cpu().numpy()
        arrays['sample__pixels_uint8'] = self.test_set.data[torch.as_tensor(self.sample_ids)].numpy()
        arrays['sample_ids'] = self.sample_ids
        arrays['sample_labels'] = self.sample_y.cpu().numpy()
        arrays['calibration_train_ids'] = self.calib_ids
        metadata = {'checkpoint_sha256': self.checkpoint_sha256, 'checkpoint': str(self.checkpoint.relative_to(self.root)), 'preprocessing': {'name': self.preprocess_selected, 'mean': self.input_mean, 'std': self.input_std, 'formula': '(pixel / 255 - mean) / std', 'selection': 'training calibration accuracy' if self.preprocessing == 'auto_calibration' else 'explicit user setting', 'candidates': self.preprocess_rows}, 'seed': self.seed, 'calibration_count': len(self.calib_ids), 'test_count': len(self.test_set), 'export_name': export_name, 'export_config': export_config.as_dict(), 'selection': 'explicit export configuration', 'rounding': 'nearest ties-to-even', 'overflow': 'saturate outputs; raise on int32 accumulator/bias overflow', 'bias': 'signed int32 at input_frac + weight_frac', 'versions': {'python': platform.python_version(), 'torch': torch.__version__, 'numpy': np.__version__}, 'device': str(self.device)}
        arrays['metadata_json'] = np.array(json.dumps(metadata, ensure_ascii=False))
        if save:
            self.result_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(self.result_dir / 'arrays.npz', **arrays)
            self.results = list({(r['phase'], r['experiment'], r.get('config', '')): r for r in self.results}.values())
            fields = list(dict.fromkeys((k for row in self.results for k in row)))
            with (self.result_dir / 'results.csv').open('w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(self.results)
            with np.load(self.result_dir / 'arrays.npz', allow_pickle=False) as saved:
                for key, value in arrays.items():
                    assert np.array_equal(saved[key], value), 'Saved array mismatch: ' + key
            print('Saved and verified:', self.result_dir / 'arrays.npz')
            print('Saved:', self.result_dir / 'results.csv')
        show_table([{'array': k, 'shape': str(v.shape), 'dtype': str(v.dtype)} for k, v in arrays.items() if k != 'metadata_json'])
        print('Load: saved = np.load(analysis.result_dir / "arrays.npz", allow_pickle=False)')
        print('All FC1 weights: saved["original__fc1__weight"]')
        print('Quantized FC1 weights: saved["quantized__fc1__weight"]')
