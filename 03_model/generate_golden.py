"""Generate one-image RTL golden vectors using the approved architecture.

Run from any directory:
    python project/03_model/generate_golden.py --sample-id 0

Only this file is needed as an entry point. Existing model loading and
quantization code is reused. Each default run creates a separate directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import platform
from datetime import datetime

import numpy as np
import torch

from src.layer_view import LayerViewer
from src.quantization import IntegerMLP, make_config

# Approved initial formats: every stored operand/activation is signed 8-bit.
INPUT_FRAC = 5
WEIGHT_FRACS = (7, 7, 7)
OUTPUT_FRACS = (2, 2, 2)
BIAS_FRACS = (9, 8, 7)
SAMPLE_ID = 0
ROOT = Path(__file__).resolve().parents[2]


def checked32(value):
    value = np.asarray(value, dtype=np.int64)
    if np.any((value < -(2**31)) | (value > 2**31 - 1)):
        raise OverflowError("Golden arithmetic exceeds signed int32")
    return value.astype(np.int32)


def pack8(values):
    """First signed byte occupies bits [7:0] of each 32-bit word."""
    lanes = np.asarray(values, dtype=np.int64).reshape(-1, 4) & 255
    return np.bitwise_or.reduce(lanes.astype(np.uint32) << np.arange(0, 32, 8, dtype=np.uint32), axis=1)


def write_hex(path, values):
    """One 32-bit word per line, compatible with testbench $readmemh."""
    path.parent.mkdir(parents=True, exist_ok=True)
    words = np.asarray(values).astype(np.uint32).reshape(-1)
    path.write_text("".join(f"{int(word):08x}\n" for word in words), encoding="ascii")
    # Verify actual saved text, including negative two's-complement words.
    saved = np.array([int(line, 16) for line in path.read_text(encoding="ascii").splitlines()], dtype=np.uint32)
    if not np.array_equal(saved, words):
        raise AssertionError(f"HEX round trip failed: {path}")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@torch.inference_mode()
def generate_golden(sample_id=SAMPLE_ID, output_dir=None):
    viewer = LayerViewer()
    pixels, label = viewer._read_sample(sample_id)
    x = (pixels / 255.0 - viewer.mean) / viewer.std
    cfg = make_config(
        input_frac=INPUT_FRAC, weight_frac=WEIGHT_FRACS,
        output_frac=OUTPUT_FRACS, bias_frac=BIAS_FRACS,
        input_signed=True, hidden_signed=True, output_signed=True,
        output_rounding="truncate",
    )
    params = {k: v.detach().cpu().numpy() for k, v in viewer.model.state_dict().items()}
    result = IntegerMLP(params, torch.device("cpu")).forward(x, cfg, trace=True, verify_cpu=True)
    traces = result["trace"]
    arrays = {
        "pixels_uint8": pixels.numpy().astype(np.uint8).reshape(28, 28),
        "input_fp32": x.numpy().reshape(-1),
        "input8": traces["input"]["q"].numpy().reshape(-1),
    }
    memories = {
        "buffer_a": pack8(arrays["input8"]),
        "buffer_b": np.zeros(128, dtype=np.uint32),
    }
    expected = {}
    bank_parts = [[] for _ in range(4)]
    bias_parts, layer_info = [], []
    weight_base = bias_base = 0
    qinput = arrays["input8"]
    h = x
    for i, name in enumerate(("fc1", "fc2", "fc3")):
        trace = traces[name]
        actual_outputs, inputs = trace["weight8"].shape
        padded_outputs = ((actual_outputs + 3) // 4) * 4
        padding = padded_outputs - actual_outputs
        w = np.pad(trace["weight8"].numpy(), ((0, padding), (0, 0)))
        b8 = np.pad(trace["bias8"].numpy(), (0, padding))
        b32 = np.pad(trace["bias32"].numpy(), (0, padding))
        qoutput = np.pad(trace["q"].numpy().reshape(-1), (0, padding))
        input_words, tiles = inputs // 4, padded_outputs // 4

        # All products and both balanced adder-tree levels are checked int32.
        products = checked32(w.reshape(padded_outputs, input_words, 4).astype(np.int64)
                             * qinput.reshape(1, input_words, 4).astype(np.int64))
        pair01 = checked32(products[:, :, 0].astype(np.int64) + products[:, :, 1])
        pair23 = checked32(products[:, :, 2].astype(np.int64) + products[:, :, 3])
        partial = checked32(pair01.astype(np.int64) + pair23)
        # Prefix 0 is the initial aligned bias; prefix k+1 includes psum k.
        acc = checked32(np.concatenate(
            (b32[:, None], b32[:, None].astype(np.int64) + partial.astype(np.int64).cumsum(axis=1)),
            axis=1,
        ))
        reference_acc = np.pad(trace["acc32"].numpy().reshape(-1), (0, padding))
        if not np.array_equal(acc[:, -1], reference_acc):
            raise AssertionError(f"{name}: four-product accumulation differs from IntegerMLP")

        source_frac = (INPUT_FRAC if i == 0 else OUTPUT_FRACS[i-1]) + WEIGHT_FRACS[i]
        activated = np.maximum(acc[:, -1], 0) if i < 2 else acc[:, -1]
        restored_output = (activated >> (source_frac - OUTPUT_FRACS[i])).clip(-128, 127).astype(np.int8)
        if not np.array_equal(restored_output, qoutput):
            raise AssertionError(f"{name}: integer output shift/saturation mismatch")

        # [tile, input word, output lane] matches bank 0..3 and CU issue order.
        psum_order = partial.reshape(tiles, 4, input_words).transpose(0, 2, 1)
        acc_order = acc.reshape(tiles, 4, input_words + 1).transpose(0, 2, 1)
        for bank in range(4):
            bank_parts[bank].append(pack8(w[bank::4].reshape(-1)))
        bias_parts.append(pack8(b8))
        expected[f"{name}_output"] = pack8(qoutput)
        expected[f"{name}_bias32"] = b32
        expected[f"{name}_psum32"] = psum_order
        expected[f"{name}_acc32"] = acc_order
        arrays.update({
            f"{name}_input8": qinput.copy(),
            f"{name}_weight8": w,
            f"{name}_bias8": b8,
            f"{name}_bias32": b32,
            f"{name}_output8": qoutput,
            f"{name}_psum32": psum_order,
            f"{name}_acc32": acc_order,
        })
        h = getattr(viewer.model, name)(h)
        if i < 2:
            h = torch.relu(h)
        arrays[f"{name}_fp32"] = h.numpy().reshape(-1)
        layer_info.append({
            "layer": name, "inputs": inputs, "outputs": actual_outputs,
            "padded_outputs": padded_outputs, "input_words": input_words, "output_tiles": tiles,
            "weight_base_word": weight_base, "bias_base_word": bias_base,
            "input_frac": source_frac - WEIGHT_FRACS[i], "weight_frac": WEIGHT_FRACS[i],
            "bias_frac": BIAS_FRACS[i], "acc_frac": source_frac, "output_frac": OUTPUT_FRACS[i],
            "bias_shift": source_frac - BIAS_FRACS[i], "output_shift": source_frac - OUTPUT_FRACS[i],
            "relu": i < 2, "input_buffer": "B" if i == 1 else "A",
            "output_buffer": "A" if i == 1 else "B",
        })
        weight_base += tiles * input_words
        bias_base += tiles
        qinput = qoutput[:actual_outputs]

    for bank in range(4):
        memories[f"weight_bank{bank}"] = np.concatenate(bank_parts[bank])
    memories["bias"] = np.concatenate(bias_parts)
    depths = {"buffer_a": 196, "buffer_b": 128, **{f"weight_bank{i}": 29280 for i in range(4)}, "bias": 163}
    if {name: len(words) for name, words in memories.items()} != depths:
        raise AssertionError("Memory depth differs from architecture.md")
    final_a, final_b = memories["buffer_a"].copy(), memories["buffer_b"].copy()
    final_b[:128] = expected["fc1_output"]
    final_a[:32] = expected["fc2_output"]
    final_b[:3] = expected["fc3_output"]
    expected.update(buffer_a_final=final_a, buffer_b_final=final_b)
    arrays.update(buffer_a_initial=memories["buffer_a"], buffer_b_initial=memories["buffer_b"],
                  buffer_a_final=final_a, buffer_b_final=final_b)

    # Sequential signed argmax: compare only ten real logits; keep first on ties.
    logits = arrays["fc3_output8"][:10]
    prediction = 0
    for index in range(1, 10):
        if int(logits[index]) > int(logits[prediction]):
            prediction = index
    if prediction != int(result["q"].argmax(1)[0]):
        raise AssertionError("Sequential signed argmax mismatch")
    expected["prediction"] = np.array([prediction], dtype=np.uint32)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = Path(output_dir).resolve() if output_dir else ROOT / f"project/07_runs/golden_sample_{sample_id:05d}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    for name, words in memories.items():
        write_hex(out / "memory" / f"{name}.hex", words)
    for name, values in expected.items():
        write_hex(out / "expected" / f"{name}.hex", values)
    np.savez_compressed(out / "golden.npz", **arrays)
    with np.load(out / "golden.npz", allow_pickle=False) as saved:
        for key, value in arrays.items():
            if not np.array_equal(saved[key], value):
                raise AssertionError(f"NPZ round trip failed: {key}")
    checkpoint = ROOT / "project/03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth"
    source_paths = [Path(__file__), *[Path(__file__).parent / "src" / name
                                   for name in ("layer_view.py", "quantization.py", "models.py")]]
    manifest = {
        "sample_id": sample_id, "label": label, "prediction": prediction,
        "fp32_prediction": int(h.argmax(1)[0]), "config": cfg.as_dict(), "layers": layer_info,
        "preprocessing": {"mean": viewer.mean, "std": viewer.std, "formula": "(pixel / 255 - mean) / std"},
        "checkpoint_sha256": sha256(checkpoint),
        "input_pixels_sha256": hashlib.sha256(arrays["pixels_uint8"].tobytes()).hexdigest(),
        "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in source_paths},
        "rounding": {"offline_input_weight_bias": "nearest ties-to-even",
                     "output": "arithmetic right shift (floor), then signed int8 saturation"},
        "packing": "first byte in bits [7:0]; one 32-bit hex word per line",
        "weight_layout": "layer -> output tile -> input word; bank=output lane; byte=input lane",
        "psum32_layout": "[output_tile, input_word, output_lane]; C-order flatten in HEX",
        "acc32_layout": "[output_tile, prefix, output_lane]; prefix 0=bias, prefix k+1 includes psum k",
        "fc3_padding": "outputs 10 and 11 have zero weights/bias/output; excluded from argmax",
        "argmax": "signed comparison over indices 0..9; ties keep the lowest index",
        "memory": {name: {"file": f"memory/{name}.hex", "words": len(words),
                          "tb_base_byte": f"0x{index * 0x20000:05X}"}
                   for index, (name, words) in enumerate(memories.items())},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__},
        "files_sha256": {str(p.relative_to(out)).replace("\\", "/"): sha256(p)
                         for p in sorted(out.rglob("*")) if p.is_file()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        "# One-image MLP RTL golden\n\n"
        f"MNIST test sample {sample_id}; label={label}; signed-int8 prediction={prediction}.\n\n"
        "- memory/: TB initialization, one 32-bit word per line. Address = manifest base + 4 * line index.\n"
        "- expected/fcN_output.hex: packed layer output words (FC3 includes two zero dummy bytes).\n"
        "- expected/fcN_bias32.hex: aligned bias, one signed int32 value per line.\n"
        "- expected/fcN_psum32.hex: four-product sums, tile -> input word -> output lane.\n"
        "- expected/fcN_acc32.hex: same order with N+1 prefixes; prefix 0 is aligned bias.\n"
        "- expected/buffer_*_final.hex: complete buffers after FC3, including retained prior data.\n"
        "- expected/prediction.hex: one 32-bit word containing the expected class index.\n"
        "- golden.npz: named NumPy arrays with shapes retained; all FC3 integer arrays include dummy rows.\n"
        "- manifest.json: formats, shifts, addresses, packing, source/data hashes.\n\n"
        "HEX negative values use two's complement. Partial sums and accumulator prefixes are int32.\n"
        "This is arithmetic reference data, not a cycle schedule. Buffer B starts with explicit TB-written zeros; "
        "hardware reset must not clear BRAM. FC2 overwrites only A words 0..31; FC3 overwrites only B words 0..2.\n",
        encoding="utf-8",
    )
    print(f"Saved: {out}")
    print(f"sample={sample_id} | label={label} | FP32={manifest['fp32_prediction']} | INT8={prediction}")
    print("PASS: CPU integer reference, four-product accumulation, signed argmax, HEX/NPZ readback")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", type=int, default=SAMPLE_ID, help="MNIST test image index (0..9999)")
    parser.add_argument("--output-dir", type=Path, help="New output directory; default is a separate timestamped run")
    args = parser.parse_args()
    generate_golden(args.sample_id, args.output_dir)


if __name__ == "__main__":
    main()
