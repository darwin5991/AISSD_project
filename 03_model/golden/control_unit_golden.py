"""Generate Control vectors from an existing one-image arithmetic golden run.

Run separately from xsim; this program never loads a checkpoint or runs RTL.
    python project/03_model/golden/control_unit_golden.py --source-run <run-dir>
Requires NumPy. See project/00_docs/verification/control_unit.md.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from zipfile import BadZipFile

import numpy as np


PROJECT = Path(__file__).resolve().parents[2]
REPOSITORY = PROJECT.parent
HEADER_NAME = "control_unit_tb_data.vh"
CLOCK_NS, RESET_CYCLES, START_WAIT_CYCLES = 10, 3, 1
FORMAT_VERSION = 1
# Read-edge offsets from the revised three-stage MAC specification.
MAC_PIPELINE_DEPTH = 3
MAC_INPUT_DELAY = 1
ACCUMULATION_DELAY = MAC_INPUT_DELAY + MAC_PIPELINE_DEPTH
RESULT_LOAD_DELAY = ACCUMULATION_DELAY + 1
OUTPUT_WRITE_DELAY = RESULT_LOAD_DELAY + 1
# Port order and widths come from control_unit.sv. No internal state encoding.
OUTPUTS = {
    "busy": (1, False), "done": (1, False), "prediction": (4, False),
    "buf_sel": (1, False), "in_addr": (8, False), "in_en": (1, False),
    "out_addr": (7, False), "out_we": (1, False),
    "weight_addr": (15, False), "weight_en": (1, False),
    "bias_addr": (8, False), "bias_en": (1, False),
    "mac_input_valid": (1, False), "bias_load": (1, False),
    "bias_shift": (6, True), "result_load": (1, False),
    "relu_en": (1, False), "output_shift": (5, False),
}
INPUTS = {"start": (1, False), "argmax_data": (32, False)}


@dataclass(frozen=True)
class Layer:
    name: str
    inputs: int
    outputs: int
    padded_outputs: int
    n: int
    groups: int
    weight_base: int
    bias_base: int
    bias_frac: int
    bias_shift: int
    output_shift: int
    relu: bool
    buf_sel: int


LAYERS = (
    Layer("fc1", 784, 512, 512, 196, 128, 0, 0, 9, 3, 10, True, 0),
    Layer("fc2", 512, 128, 128, 128, 32, 25088, 128, 8, 1, 7, True, 1),
    Layer("fc3", 128, 10, 12, 32, 3, 29184, 160, 7, 2, 7, False, 0),
)
EXPECTED_CONFIG = {
    "input": {"signed": True, "frac": 5},
    "weights": [{"signed": True, "frac": 7} for _ in LAYERS],
    "outputs": [{"signed": True, "frac": 2} for _ in LAYERS],
    "biases": [{"signed": True, "frac": x.bias_frac} for x in LAYERS],
    "output_rounding": "truncate",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_path(path):
    path = Path(path).resolve()
    return path.relative_to(REPOSITORY).as_posix() if path.is_relative_to(REPOSITORY) else str(path)


def load_source(source_run, *, allowed_sample_ids=(0,)):
    """Validate saved data; standalone callers retain sample 0 by default.

    Top explicitly opts into its approved sample IDs. This does not widen the
    Control/Memory/MAC/accumulator entry points that use the default policy.
    """
    source_run = Path(source_run).resolve()
    manifest_path, npz_path = source_run / "manifest.json", source_run / "golden.npz"
    for path in (manifest_path, npz_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing source data: {path}. Restore the original run, or manually run "
                "python project/03_model/generate_golden.py --sample-id <ID> first."
            )
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    allowed_sample_ids = tuple(allowed_sample_ids)
    require(bool(allowed_sample_ids) and
            all(type(value) is int and 0 <= value <= 9 for value in allowed_sample_ids),
            "Unsupported source sample-ID policy")
    sample_id = manifest.get("sample_id")
    require(type(sample_id) is int and sample_id in allowed_sample_ids,
            f"Unsupported source sample ID: {sample_id}; allowed IDs: {allowed_sample_ids}")
    require(manifest.get("config") == EXPECTED_CONFIG, "Source quantization config differs from the approved config")
    preprocessing = manifest.get("preprocessing", {})
    require(preprocessing.get("mean") == 0.1307 and preprocessing.get("std") == 0.3081,
            "Source preprocessing differs from the approved normalization")
    source_layers = manifest.get("layers", [])
    require(len(source_layers) == 3, "Source must describe all three FC layers")
    for layer, actual in zip(LAYERS, source_layers):
        expected = {
            "layer": layer.name, "inputs": layer.inputs, "outputs": layer.outputs,
            "padded_outputs": layer.padded_outputs, "input_words": layer.n,
            "output_tiles": layer.groups, "weight_base_word": layer.weight_base,
            "bias_base_word": layer.bias_base, "input_frac": 5 if layer.name == "fc1" else 2,
            "weight_frac": 7, "bias_frac": layer.bias_frac,
            "acc_frac": 12 if layer.name == "fc1" else 9, "output_frac": 2,
            "bias_shift": layer.bias_shift, "output_shift": layer.output_shift,
            "relu": layer.relu, "input_buffer": "B" if layer.buf_sel else "A",
            "output_buffer": "A" if layer.buf_sel else "B",
        }
        require(all(actual.get(key) == value for key, value in expected.items()),
                f"Source layer settings differ: {layer.name}")
    for key in ("checkpoint_sha256", "input_pixels_sha256"):
        require(isinstance(manifest.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", manifest[key]),
                f"Missing or invalid source provenance: {key}")
    npz_hash = sha256(npz_path)
    require(manifest.get("files_sha256", {}).get("golden.npz") == npz_hash,
            "Source golden.npz SHA-256 does not match its manifest")
    with np.load(npz_path, allow_pickle=False) as saved:
        require({"fc3_output8", "pixels_uint8"}.issubset(saved.files), "Missing FC3 or pixel array in golden.npz")
        logits = saved["fc3_output8"].copy()
        pixels = saved["pixels_uint8"]
        require(logits.shape == (12,) and logits.dtype == np.dtype("int8"),
                "fc3_output8 must contain 12 signed int8 values")
        require(pixels.shape == (28, 28) and pixels.dtype == np.dtype("uint8"),
                "pixels_uint8 must be a 28x28 uint8 image")
        require(hashlib.sha256(pixels.tobytes()).hexdigest() == manifest["input_pixels_sha256"],
                "Source pixel array hash differs from its manifest")
    require(np.all(logits[10:] == 0), "FC3 dummy outputs must both be zero")
    prediction = int(np.argmax(logits[:10]))  # Signed comparison; first index wins ties.
    require(type(manifest.get("prediction")) is int and manifest["prediction"] == prediction,
            "Source prediction differs from signed ARGMAX of the ten real FC3 outputs")
    return {
        "directory": source_run, "manifest": manifest, "manifest_bytes": manifest_bytes,
        "sample_id": sample_id,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "npz_sha256": npz_hash, "logits": logits, "prediction": prediction,
    }


def pack_word(values):
    return sum((int(value) & 255) << (8 * lane) for lane, value in enumerate(values))


def build_vectors(logits):
    """Construct the independent event schedule, indexed by falling-edge checks.

    Vector k is checked BEFORE stim[k] is driven. The following rising edge is
    S+k. An enable consumed at S+r is expected at vector r; a register updated
    by that edge is expected at vector r+1.
    """
    logits = np.asarray(logits)
    require(logits.shape == (12,) and logits.dtype == np.dtype("int8"), "Expected 12 signed int8 FC3 outputs")
    require(np.all(logits[10:] == 0), "FC3 dummy outputs must be zero")
    schedule, first = [], 2
    for layer in LAYERS:
        last = first + layer.groups * layer.n + layer.groups - 2
        schedule.append({"layer": layer.name, "first_read": first, "last_read": last, "last_store": last + OUTPUT_WRITE_DELAY})
        first = schedule[-1]["last_store"] + 2
    argmax_first = schedule[-1]["last_store"] + 2
    completion = argmax_first + 12
    nvec = completion + 3  # Includes done=1 and next-cycle done=0 checks.
    stim = {name: np.zeros(nvec, dtype=np.int64) for name in INPUTS}
    expected = {name: np.zeros(nvec, dtype=np.int64) for name in OUTPUTS}
    masks = {name: np.ones(nvec, dtype=np.uint8) for name in OUTPUTS}
    stim["start"][0] = 1
    expected["busy"][1:completion + 1] = 1
    expected["done"][completion + 1] = 1
    prediction = int(np.argmax(logits[:10]))
    expected["prediction"][completion + 1] = prediction
    masks["prediction"][:] = 0
    masks["prediction"][[0, completion + 1]] = 1

    for layer, timing in zip(LAYERS, schedule):
        # Next-layer LUT values are used after the previous final store.
        begin = 0 if layer.name == "fc1" else timing["first_read"] - 1
        stop = timing["last_store"] + 1
        for name, value in (("buf_sel", layer.buf_sel), ("bias_shift", layer.bias_shift),
                            ("output_shift", layer.output_shift), ("relu_en", int(layer.relu))):
            expected[name][begin:stop] = value
        expected["bias_load"][timing["first_read"] + 1] = 1
        for group in range(layer.groups):
            read_first = timing["first_read"] + group * (layer.n + 1)
            read_last = read_first + layer.n - 1
            reads = np.arange(read_first, read_last + 1)
            expected["in_en"][reads] = expected["weight_en"][reads] = 1
            expected["in_addr"][reads] = np.arange(layer.n)
            expected["weight_addr"][reads] = layer.weight_base + group * layer.n + np.arange(layer.n)
            expected["mac_input_valid"][reads + MAC_INPUT_DELAY] = 1
            expected["bias_en"][read_first] = 1
            expected["bias_addr"][read_first] = layer.bias_base + group
            expected["result_load"][read_last + RESULT_LOAD_DELAY] = 1
            if group + 1 < layer.groups:
                expected["bias_load"][read_last + RESULT_LOAD_DELAY] = 1
            expected["out_we"][read_last + OUTPUT_WRITE_DELAY] = 1
            expected["out_addr"][read_last + OUTPUT_WRITE_DELAY] = group

    # FC3's final write still uses FC3 settings. They are unused from PREP on.
    for name in ("bias_shift", "output_shift", "relu_en"):
        masks[name][schedule[-1]["last_store"] + 1:] = 0
    expected["buf_sel"][argmax_first:completion + 1] = 1
    masks["buf_sel"][schedule[-1]["last_store"] + 1:] = 0
    masks["buf_sel"][argmax_first:completion + 1] = 1
    for word in range(3):
        read = argmax_first + 5 * word
        expected["in_en"][read] = 1
        expected["in_addr"][read] = word
        # Updated after this falling edge's comparison; consumed at read+1.
        stim["argmax_data"][read + 1:] = pack_word(logits[4 * word:4 * word + 4])
    for address, enable in (("in_addr", "in_en"), ("out_addr", "out_we"),
                            ("weight_addr", "weight_en"), ("bias_addr", "bias_en")):
        masks[address] = expected[enable].astype(np.uint8)
    timing = {
        "layers": schedule, "argmax_first_read": argmax_first,
        "mac_pipeline_depth": MAC_PIPELINE_DEPTH,
        "completion_rising_edge": completion, "done_check_vector": completion + 1,
        "done_low_check_vector": completion + 2, "nvec": nvec,
        "clock_period_ns": CLOCK_NS, "reset_cycles": RESET_CYCLES,
        "start_wait_cycles": START_WAIT_CYCLES,
        "first_vector_cycle": RESET_CYCLES + START_WAIT_CYCLES,
        # clk starts at 0; final comparison ends at the last falling edge.
        "expected_cycles": RESET_CYCLES + START_WAIT_CYCLES + nvec - 1,
    }
    timing["timeout_cycles"] = timing["expected_cycles"] + 100
    validate_vectors(stim, expected, masks, timing)
    return stim, expected, masks, timing


def validate_vectors(stim, expected, masks, timing):
    nvec = timing["nvec"]
    require(nvec == 29478, "Schedule differs from the approved 29,478-vector scenario")
    for values, ports in ((stim, INPUTS), (expected, OUTPUTS)):
        require(values.keys() == ports.keys(), "Vector signal set differs from the port contract")
        for name, (width, signed) in ports.items():
            low, high = (-(1 << (width - 1)), (1 << (width - 1)) - 1) if signed else (0, (1 << width) - 1)
            require(values[name].shape == (nvec,) and np.all((values[name] >= low) & (values[name] <= high)),
                    f"Vector shape or bit width violation: {name}")
    require(masks.keys() == OUTPUTS.keys(), "Missing output comparison masks")
    for name, mask in masks.items():
        require(mask.shape == (nvec,) and np.all((mask == 0) | (mask == 1)), f"Invalid mask: {name}")
    counts = {"in_en": 29283, "weight_en": 29280, "mac_input_valid": 29280,
              "bias_en": 163, "bias_load": 163, "result_load": 163, "out_we": 163, "done": 1}
    for name, count in counts.items():
        require(int(expected[name].sum()) == count, f"Wrong event count: {name}")
    require(np.array_equal(expected["mac_input_valid"][1:], expected["weight_en"][:-1]),
            "MLP valid must be delayed one clock")
    # A read at R is captured by MAC at R+1 and accumulated at R+4.
    consumed = np.flatnonzero(expected["weight_en"]) + ACCUMULATION_DELAY
    require(not np.any(expected["bias_load"][consumed]), "Bias load overlaps a valid accumulator update")
    require(int(stim["start"].sum()) == 1 and stim["start"][0] == 1, "Start must be one clock")
    require(not np.any(stim["argmax_data"][:timing["argmax_first_read"] + 1]), "ARGMAX input must start at zero")


def all_arrays(stim, expected, masks):
    return {**{f"tb_{key}": value for key, value in stim.items()},
            **{f"tb_exp_{key}": value for key, value in expected.items()},
            **{f"tb_mask_{key}": value for key, value in masks.items()}}


def write_header(path, arrays, timing, run_id, source):
    """Compact initializers still create one complete array per signal."""
    ports = {**{f"tb_{name}": port for name, port in INPUTS.items()},
             **{f"tb_exp_{name}": port for name, port in OUTPUTS.items()},
             **{f"tb_mask_{name}": (1, False) for name in OUTPUTS}}
    def literal(value, width, signed):
        bits = int(value) & ((1 << width) - 1)
        marker = "'sh" if signed else "'h"
        return f"{width}{marker}{bits:0{(width + 3) // 4}x}"
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"// Auto-generated by control_unit_golden.py; DO NOT EDIT.\n// Run: {run_id}\n")
        stream.write(f"// Source run: {source['directory'].name}\n// Source NPZ SHA-256: {source['npz_sha256']}\n")
        stream.write("// Check exp[k] BEFORE driving stim[k] at the falling edge. Masks: 1=compare, 0=exclude.\n")
        params = {"CONTROL_DATA_FORMAT_VERSION": FORMAT_VERSION, "NVEC": timing["nvec"],
                  "SAMPLE_ID": 0, "CLOCK_PERIOD_NS": CLOCK_NS, "RESET_CYCLES": RESET_CYCLES,
                  "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
                  "START_WAIT_CYCLES": START_WAIT_CYCLES, "FIRST_VECTOR_CYCLE": timing["first_vector_cycle"],
                  "EXPECTED_CYCLES": timing["expected_cycles"], "TIMEOUT_CYCLES": timing["timeout_cycles"],
                  "EXPECTED_PREDICTION": source["prediction"]}
        for key, value in params.items():
            stream.write(f"localparam integer {key} = {value};\n")
        stream.write("localparam logic INITIAL_CLK = 1'b0;\n")
        for layer in LAYERS:
            for name, value in (("N", layer.n), ("GROUPS", layer.groups), ("WEIGHT_BASE", layer.weight_base),
                                ("BIAS_BASE", layer.bias_base), ("BIAS_SHIFT", layer.bias_shift),
                                ("OUTPUT_SHIFT", layer.output_shift), ("RELU", int(layer.relu))):
                stream.write(f"localparam integer {layer.name.upper()}_{name} = {value};\n")
        for name, (width, signed) in ports.items():
            suffix = (" signed" if signed else "") + (f" [{width-1}:0]" if width > 1 else "")
            stream.write(f"logic{suffix} {name} [0:NVEC-1];\n")
        stream.write("initial begin\n    for (integer i = 0; i < NVEC; i = i + 1) begin\n")
        for name, (width, signed) in ports.items():
            stream.write(f"        {name}[i] = {literal(0, width, signed)};\n")
        stream.write("    end\n")
        for name, values in arrays.items():
            width, signed = ports[name]
            changes = np.concatenate(([0], np.flatnonzero(values[1:] != values[:-1]) + 1, [len(values)]))
            stream.write(f"    // {name}\n")
            for begin, stop in zip(changes[:-1], changes[1:]):
                value = int(values[begin])
                if value == 0:
                    continue
                value_text = literal(value, width, signed)
                if stop - begin >= 4:
                    stream.write(f"    for (integer i = {begin}; i < {stop}; i = i + 1) {name}[i] = {value_text};\n")
                else:
                    for index in range(int(begin), int(stop)):
                        stream.write(f"    {name}[{index}] = {value_text};\n")
        stream.write("end\n")


def git_provenance():
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY,
                                capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=REPOSITORY,
                                capture_output=True, text=True, check=True).stdout
        return {"commit": commit, "dirty": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def generate(source_run, output_dir=None, header_path=None):
    source = load_source(source_run)
    stim, expected, masks, timing = build_vectors(source["logits"])
    arrays = all_arrays(stim, expected, masks)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out = Path(output_dir).resolve() if output_dir else PROJECT / "07_runs" / f"control_unit_golden_{stamp}"
    header = Path(header_path).resolve() if header_path else PROJECT / "05_tb/controller" / HEADER_NAME
    require(not out.exists(), f"Output run already exists: {out}")
    require(not source["directory"].is_relative_to(out), "Output cannot contain the source run")
    require(not header.is_relative_to(source["directory"]), "TB header cannot overwrite the source run")
    out.mkdir(parents=True, exist_ok=False)
    vectors_dir = out / "vectors"
    vectors_dir.mkdir()
    saved_header = vectors_dir / HEADER_NAME
    write_header(saved_header, arrays, timing, out.name, source)
    npz = vectors_dir / "control_unit_vectors.npz"
    np.savez_compressed(npz, **arrays)
    with np.load(npz, allow_pickle=False) as restored:
        require(set(restored.files) == set(arrays), "Saved vector signal set differs")
        for key, value in arrays.items():
            require(np.array_equal(restored[key], value), f"Saved vector round trip failed: {key}")
    (out / "source_manifest.json").write_bytes(source["manifest_bytes"])
    source_files = [Path(__file__), PROJECT / "00_docs/mac_input_pipeline.md",
                    PROJECT / "00_docs/verification/control_unit.md",
                    PROJECT / "00_docs/modules/control_unit.md", PROJECT / "00_docs/architecture.md"]
    source_hashes = {}
    for path in source_files:
        relative = path.relative_to(REPOSITORY)
        copied = out / "source_snapshot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied)
        source_hashes[relative.as_posix()] = sha256(copied)
    manifest = {
        "kind": "control_unit_golden", "format_version": FORMAT_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(), "sample_id": 0,
        "git": git_provenance(),
        "source_run": display_path(source["directory"]), "source_run_id": source["directory"].name,
        "source_manifest_sha256": source["manifest_sha256"], "source_npz_sha256": source["npz_sha256"],
        "checkpoint_sha256": source["manifest"]["checkpoint_sha256"],
        "input_pixels_sha256": source["manifest"]["input_pixels_sha256"],
        "prediction": source["prediction"], "timing": timing,
        "quantization": source["manifest"]["config"], "layers": [asdict(layer) for layer in LAYERS],
        "initial_clk": 0, "time_unit": "1ns", "time_precision": "1ps",
        "seed": None, "random_used": False, "fallback_random_seed": 42,
        "inputs": INPUTS, "outputs": OUTPUTS, "mask": "one bit per signal; 1=compare, 0=exclude",
        "vector_contract": "compare at falling edge k, then drive input k; following rising edge is S+k",
        "tb_header": display_path(header), "source_sha256": source_hashes,
        "files_sha256": {p.relative_to(out).as_posix(): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()},
        "validation": "schedule invariants and saved NPZ round trip; no RTL simulation",
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics = {"nvec": timing["nvec"], "prediction": source["prediction"],
               "expected_cycles": timing["expected_cycles"], "timeout_cycles": timing["timeout_cycles"],
               "event_counts": {key: int(expected[key].sum()) for key in
                                ("in_en", "weight_en", "bias_en", "bias_load", "result_load", "out_we", "done")},
               "generation_checks_passed": True, "rtl_verified": False}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# Control unit golden\n\nSource: `{display_path(source['directory'])}`; MNIST test sample 0.\n\n"
        f"{timing['nvec']} falling-edge vectors; signed prediction={source['prediction']}.\n\n"
        "- vectors/: archived SystemVerilog header and exact NumPy arrays.\n"
        "- source_manifest.json and source_snapshot/: source provenance and reproducible generator/specifications.\n"
        "- manifest.json / metrics.json: configuration, schedule, hashes and generation checks.\n\n"
        f"Published header: `{display_path(header)}`. Compare outputs before driving each vector.\n"
        "The final comparison is done=0 one cycle after completion. Clock starts low; reset is released "
        "after three cycles; vector 0 follows one waiting cycle.\n\n"
        "No checkpoint inference, xsim execution or waveform capture was performed. "
        "Generation checks do not establish RTL correctness.\n", encoding="utf-8")
    # Publish only a complete, validated run. replace() keeps an existing header intact until this point.
    header.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".control_unit_data_", suffix=".tmp", dir=header.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copyfile(saved_header, temporary)
        require(sha256(temporary) == manifest["files_sha256"][saved_header.relative_to(out).as_posix()],
                "Published header hash differs from the archived header")
        temporary.replace(header)
    finally:
        temporary.unlink(missing_ok=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True,
                        help="Existing generate_golden.py run containing golden.npz and manifest.json")
    parser.add_argument("--output-dir", type=Path, help="New output run directory; must not already exist")
    args = parser.parse_args()
    try:
        out = generate(args.source_run, args.output_dir)
    except (OSError, ValueError, KeyError, BadZipFile, EOFError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Saved: {out}\nPublished: {PROJECT / '05_tb/controller' / HEADER_NAME}")
    print("PASS: source/config hashes, schedule invariants and vector readback (not RTL verification)")


if __name__ == "__main__":
    main()
