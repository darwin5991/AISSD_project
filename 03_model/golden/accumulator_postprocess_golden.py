"""Prepare standalone accumulator/postprocess vectors from saved sample-0 data.

    python project/03_model/golden/accumulator_postprocess_golden.py --source-run <run-dir>

Run manually, separately from xsim. Reuses the Python Control/Memory/MAC
references; never runs inference or RTL. See the accumulator verification spec.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import shutil
import tempfile
from zipfile import BadZipFile

import numpy as np

import control_unit_golden as control
import mac_array_golden as mac
import memory_wrapper_golden as memory
import mlp_top_golden as top


PROJECT = control.PROJECT
HEADER_NAME = "accumulator_postprocess_tb_data.vh"
FORMAT_VERSION = 1
RESPONSE_LATENCY = 1
BIAS_DATA = tuple(f"bias_data_lane{lane}" for lane in range(4))
PARTIAL_SUM = tuple(f"partial_sum_lane{lane}" for lane in range(4))
INPUTS = {
    "bias_load": (1, False), **{name: (8, True) for name in BIAS_DATA},
    "bias_shift": (6, True), **{name: (32, True) for name in PARTIAL_SUM},
    "psum_valid": (1, False), "result_load": (1, False),
    "relu_en": (1, False), "output_shift": (5, False),
}
OUTPUTS = {"output_data": (32, False)}
CONTROLS = ("bias_load", "result_load")
SETTINGS = ("bias_shift", "output_shift", "relu_en")


def load_source(source_run):
    # The shared loaders check sample/configuration, memory packing, hashes,
    # layer chaining, dummy operands and saved MAC partial sums without writing.
    source = mac.load_source(source_run)
    layers = {}
    with np.load(source["directory"] / "golden.npz", allow_pickle=False) as saved:
        for layer in control.LAYERS:
            data = {}
            shapes = {"bias8": (layer.padded_outputs,),
                      "bias32": (layer.padded_outputs,),
                      "acc32": (layer.groups, layer.n + 1, 4),
                      "output8": (layer.padded_outputs,)}
            for suffix, shape in shapes.items():
                value = saved[f"{layer.name}_{suffix}"].copy()
                dtype = np.dtype("int8" if suffix in ("bias8", "output8") else "int32")
                control.require(value.shape == shape and value.dtype == dtype,
                                f"Invalid saved array: {layer.name}_{suffix}")
                data[suffix] = value.astype(np.int64)
                if suffix in ("bias32", "acc32"):
                    mac.checked32(value, f"saved {layer.name}_{suffix}")
                    relative = f"expected/{layer.name}_{suffix}.hex"
                    path = source["directory"] / relative
                    control.require(control.sha256(path) == source["manifest"]["files_sha256"].get(relative),
                                    f"Source HEX hash mismatch: {relative}")
                    lines = path.read_text(encoding="ascii").splitlines()
                    control.require(len(lines) == value.size and
                                    all(re.fullmatch(r"[0-9a-fA-F]{8}", line) for line in lines),
                                    f"Invalid signed INT32 HEX layout: {relative}")
                    words = np.array([int(line, 16) for line in lines], dtype=np.int64)
                    signed = np.where(words >= (1 << 31), words - (1 << 32), words)
                    control.require(np.array_equal(signed, value.reshape(-1)),
                                    f"HEX/NPZ mismatch: {relative}")
            data["psum32"] = source["mac_layers"][layer.name]["psum32"]
            if layer.name == "fc3":
                control.require(np.all(data["bias8"][10:] == 0) and
                                np.all(data["bias32"][10:] == 0) and
                                np.all(data["acc32"][-1, :, 2:] == 0),
                                "FC3 dummy bias/accumulation must stay zero")
            layers[layer.name] = data
    source["accumulator_layers"] = layers
    return source


def build_stimulus(source):
    # These references return arrays in memory only. They do not generate run
    # folders, publish headers, launch a simulator or load a model checkpoint.
    _, memory_outputs, _, base_timing = memory.build_vectors(source)
    _, mac_outputs, _, mac_timing = mac.build_vectors(source)
    _, ctl, ctl_masks, ctl_timing = control.build_vectors(source["logits"])
    trace_count = base_timing["nvec"]
    control.require(mac_timing["trace_vectors"] == trace_count and
                    mac_timing["control_schedule"] == ctl_timing == base_timing["control_schedule"],
                    "Reference timelines disagree")
    nvec = trace_count + RESPONSE_LATENCY
    stim = {name: np.zeros(nvec, dtype=np.int64) for name in INPUTS}
    core = base_timing["core_begin"]
    core_slice = slice(core, core + ctl_timing["nvec"])
    for name in CONTROLS:
        stim[name][core_slice] = ctl[name]
    # Supply the bias read register BEFORE the next rising edge, just as Top
    # unpacks it. This includes TB reads and read-register holds when load=0.
    words = memory_outputs["bias_data"]
    for lane, name in enumerate(BIAS_DATA):
        byte = (words >> (8 * lane)) & 255
        stim[name][:trace_count] = np.where(byte >= 128, byte - 256, byte)
    for name in (*PARTIAL_SUM, "psum_valid"):
        stim[name][:trace_count] = mac_outputs[name][:trace_count]

    # The LUT selects FC1 before start. Later settings change at PREP, one
    # vector after the previous last write. ARGMAX and subsequent IDLE keep
    # layer index 3, whose numeric settings are all zero. Do not copy masked
    # Control placeholder values as though their meaning had been specified.
    for layer, schedule in zip(control.LAYERS, ctl_timing["layers"]):
        begin = 0 if layer.name == "fc1" else core + schedule["first_read"] - 1
        end = core + schedule["last_store"] + 1
        for name, value in (("bias_shift", layer.bias_shift),
                            ("output_shift", layer.output_shift), ("relu_en", int(layer.relu))):
            stim[name][begin:end] = value
    for name in SETTINGS:
        defined = ctl_masks[name] == 1
        control.require(np.array_equal(stim[name][core_slice][defined], ctl[name][defined]),
                        f"Concrete Top settings disagree with Control: {name}")
    # The extra vector is comparison-only. Its array entries describe the
    # held inputs for metadata/readback, not another stimulus to drive.
    for name in INPUTS:
        stim[name][trace_count:] = stim[name][trace_count - 1]
    first = base_timing["first_vector_cycle"]
    timing = dict(base_timing, nvec=nvec, trace_vectors=trace_count,
                  response_latency=RESPONSE_LATENCY, mac_pipeline_depth=mac.PIPELINE_DEPTH,
                  drain_begin=trace_count, last_target_vector=trace_count - 1,
                  last_compare_vector=nvec - 1, expected_cycles=first + nvec - 1,
                  timeout_cycles=first + nvec - 1 + 100,
                  argmax_settings_begin=core + ctl_timing["layers"][-1]["last_store"] + 1)
    control.require((trace_count, nvec, timing["expected_cycles"], timing["timeout_cycles"]) ==
                    (265018, 265019, 265022, 265122),
                    "Accumulator timeline differs from the approved scenario")
    return stim, timing


def aligned_bias(values, shift):
    values = np.asarray(values, dtype=np.int64)
    shift = int(shift)
    control.require(-32 <= shift <= 31, "Bias shift exceeds its signed 6-bit port")
    aligned = values << shift if shift >= 0 else values >> -shift
    # Reject a source/scenario outside INT32; do not invent overflow semantics.
    return mac.checked32(aligned, "aligned bias")


def build_expected(stim, timing):
    nvec = timing["nvec"]
    acc = np.zeros((nvec, 4), dtype=np.int64)
    result = np.zeros_like(acc)
    bias = np.stack([stim[name] for name in BIAS_DATA], axis=1)
    partial = np.stack([stim[name] for name in PARTIAL_SUM], axis=1)
    for vector in range(nvec - 1):
        control.require(not (stim["bias_load"][vector] and stim["psum_valid"][vector]),
                        f"Bias load overlaps valid accumulation at vector {vector}")
        # Capture OLD accumulator state, independently of this edge's update.
        result[vector + 1] = acc[vector] if stim["result_load"][vector] else result[vector]
        if stim["bias_load"][vector]:
            acc[vector + 1] = aligned_bias(bias[vector], stim["bias_shift"][vector])
        elif stim["psum_valid"][vector]:
            acc[vector + 1] = mac.checked32(acc[vector] + partial[vector],
                                            f"accumulation at vector {vector}")
        else:
            acc[vector + 1] = acc[vector]
    # Comparison k precedes driving settings[k], so it uses settings[k-1].
    # Initial LUT settings are FC1; reset has cleared both register banks.
    held_relu = np.r_[int(control.LAYERS[0].relu), stim["relu_en"][:-1]]
    held_shift = np.r_[control.LAYERS[0].output_shift, stim["output_shift"][:-1]]
    activated = np.where(held_relu[:, None] != 0, np.maximum(result, 0), result)
    shifted = activated >> held_shift[:, None]
    expected = {"output_data": top.packed(np.clip(shifted, -128, 127))}
    masks = {"output_data": np.ones(nvec, dtype=np.uint8)}
    return expected, masks, acc, result


def validate_vectors(source, stim, expected, masks, timing, acc, result):
    nvec = timing["nvec"]
    control.require(stim.keys() == INPUTS.keys() and expected.keys() == OUTPUTS.keys() and
                    masks.keys() == OUTPUTS.keys(), "Accumulator vector signal set differs")
    for arrays, ports in ((stim, INPUTS), (expected, OUTPUTS)):
        for name, (width, signed) in ports.items():
            low = -(1 << (width - 1)) if signed else 0
            high = (1 << (width - int(signed))) - 1
            values = arrays[name]
            control.require(values.shape == (nvec,) and np.issubdtype(values.dtype, np.integer) and
                            np.all((values >= low) & (values <= high)),
                            f"Invalid vector shape, integer type or bit width: {name}")
    control.require(masks["output_data"].shape == (nvec,) and np.all(masks["output_data"] == 1),
                    "Defined external output was excluded")
    control.require(expected["output_data"][0] == 0 and np.all(acc[0] == 0) and np.all(result[0] == 0),
                    "Incorrect reset state")
    planned = {name: np.zeros(nvec, dtype=np.int64) for name in (*CONTROLS, "psum_valid")}
    bias = np.stack([stim[name] for name in BIAS_DATA], axis=1)
    partial = np.stack([stim[name] for name in PARTIAL_SUM], axis=1)
    for layer, schedule in zip(control.LAYERS, timing["control_schedule"]["layers"]):
        first = timing["core_begin"] + schedule["first_read"]
        group_first = first + np.arange(layer.groups) * (layer.n + 1)
        reads = group_first[:, None] + np.arange(layer.n)
        sums = reads + control.ACCUMULATION_DELAY
        captures = reads[:, -1] + control.RESULT_LOAD_DELAY
        # Preserve the first bias read + 1; subsequent biases load with the
        # previous group's result capture, one cycle before the next first sum.
        loads = np.concatenate(([first + 1], captures[:-1]))
        planned["bias_load"][loads] = 1
        planned["psum_valid"][sums.reshape(-1)] = 1
        planned["result_load"][captures] = 1
        saved = source["accumulator_layers"][layer.name]
        label = layer.name
        control.require(np.array_equal(bias[loads], saved["bias8"].reshape(-1, 4)),
                        f"Bias stream/BRAM delay differs from saved bias8: {label}")
        aligned = aligned_bias(bias[loads], layer.bias_shift)
        control.require(np.array_equal(aligned, saved["bias32"].reshape(-1, 4)) and
                        np.array_equal(acc[loads + 1], saved["acc32"][:, 0]),
                        f"Aligned bias or initialization differs: {label}")
        control.require(np.all(stim["bias_shift"][loads] == layer.bias_shift),
                        f"Bias alignment setting differs: {label}")
        control.require(np.array_equal(partial[sums.reshape(-1)], saved["psum32"].reshape(-1, 4)),
                        f"Valid partial-sum stream differs: {label}")
        control.require(np.array_equal(acc[(sums + 1).reshape(-1)],
                                       saved["acc32"][:, 1:].reshape(-1, 4)),
                        f"Accumulation prefixes differ: {label}")
        control.require(np.array_equal(result[captures + 1], saved["acc32"][:, -1]),
                        f"Result capture did not preserve the completed accumulator: {label}")
        control.require(np.array_equal(expected["output_data"][captures + 1],
                                       source["layer_words"][label]),
                        f"Postprocessed layer output differs: {label}")
        for name, value in (("output_shift", layer.output_shift), ("relu_en", int(layer.relu))):
            control.require(np.all(stim[name][captures] == value),
                            f"Result capture/write setting differs: {label}, {name}")
    for name, values in planned.items():
        control.require(np.array_equal(stim[name], values),
                        f"Extra, missing or shifted accumulator event: {name}")
    counts = {"bias_load": 163, "result_load": 163, "psum_valid": 29280}
    for name, count in counts.items():
        control.require(int(stim[name].sum()) == count, f"Unexpected event count: {name}")
    control.require(int(np.count_nonzero(stim["bias_load"] & stim["result_load"])) == 160,
                    "Missing result-capture/next-bias overlap")
    zero_begin = timing["argmax_settings_begin"]
    for name in SETTINGS:
        control.require(np.all(stim[name][zero_begin:] == 0),
                        f"ARGMAX/completed Top LUT settings differ: {name}")
    final_acc = source["accumulator_layers"]["fc3"]["acc32"][-1, -1]
    final_word = int(top.packed(np.clip(final_acc, -128, 127))[0])
    control.require(np.all(expected["output_data"][zero_begin + 1:] == final_word),
                    "ARGMAX/final-read postprocessing must use retained results with shift=0")
    for name in (*CONTROLS, "psum_valid"):
        control.require(not np.any(stim[name][timing["last_target_vector"]:]),
                        "New work at the end of Top replay")
    control.require(expected["output_data"][-1] == expected["output_data"][-2],
                    "Last target input did not retain the output through the final comparison")


def build_vectors(source):
    stim, timing = build_stimulus(source)
    expected, masks, acc, result = build_expected(stim, timing)
    validate_vectors(source, stim, expected, masks, timing, acc, result)
    # Internal Python traces are generation checks, never DUT probes or TB outputs.
    return stim, expected, masks, timing


def write_header(path, arrays, timing, run_id, source):
    ports = {**{f"tb_{name}": port for name, port in INPUTS.items()},
             **{f"tb_exp_{name}": port for name, port in OUTPUTS.items()},
             **{f"tb_mask_{name}": (1, False) for name in OUTPUTS}}
    params = {
        "ACC_DATA_FORMAT_VERSION": FORMAT_VERSION, "NVEC": timing["nvec"], "SAMPLE_ID": 0,
        "CLOCK_PERIOD_NS": timing["clock_period_ns"], "RESET_CYCLES": timing["reset_cycles"],
        "START_WAIT_CYCLES": timing["start_wait_cycles"], "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
        "FIRST_VECTOR_CYCLE": timing["first_vector_cycle"], "EXPECTED_CYCLES": timing["expected_cycles"],
        "TIMEOUT_CYCLES": timing["timeout_cycles"], "OUTPUT_COUNT": len(OUTPUTS),
        "TRACE_VECTORS": timing["trace_vectors"], "RESPONSE_LATENCY": RESPONSE_LATENCY,
        "MAC_PIPELINE_DEPTH": timing["mac_pipeline_depth"], "DRAIN_BEGIN": timing["drain_begin"],
        "INIT_WORDS": timing["init_words"], "INITIAL_READ_BEGIN": timing["initial_read_begin"],
        "CORE_BEGIN": timing["core_begin"], "ARGMAX_READ_BEGIN": timing["argmax_read_begin"],
        "ARGMAX_SETTINGS_BEGIN": timing["argmax_settings_begin"],
        "FINAL_READ_BEGIN": timing["final_read_begin"], "FINAL_WORDS": timing["final_words"],
        "BIAS_LOADS": 163, "VALID_SUMS": 29280, "RESULT_LOADS": 163, "OVERLAPPED_LOADS": 160,
    }
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"// Auto-generated by accumulator_postprocess_golden.py; DO NOT EDIT.\n// Run: {run_id}\n")
        stream.write(f"// Source run: {source['directory'].name}\n// Source NPZ SHA-256: {source['npz_sha256']}\n")
        stream.write("// Falling edge: compare exp[k], then drive stim[k]; response at k+1.\n")
        stream.write("// Last vector is comparison-only. Mask=1 compares the entire 32-bit output.\n")
        stream.write("// Signed bias/partial arrays use lane order 0..3; lane 0 packs into bits [7:0].\n")
        for name, value in params.items():
            stream.write(f"localparam integer {name} = {value};\n")
        stream.write("localparam logic INITIAL_CLK = 1'b0;\n")
        for name, (width, signed) in ports.items():
            suffix = (" signed" if signed else "") + (f" [{width - 1}:0]" if width > 1 else "")
            stream.write(f"logic{suffix} {name} [0:NVEC-1];\n")
        stream.write("initial begin\n    for (integer i = 0; i < NVEC; i++) begin\n")
        for name in ports:
            stream.write(f"        {name}[i] = '0;\n")
        stream.write("    end\n")
        for name, values in arrays.items():
            width, signed = ports[name]
            changes = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1, len(values)]
            for begin, end in zip(changes[:-1], changes[1:]):
                value = int(values[begin])
                if value == 0:
                    continue
                marker = "'sh" if signed else "'h"
                literal = f"{width}{marker}{value & ((1 << width) - 1):0{(width + 3) // 4}x}"
                if end - begin >= 4:
                    stream.write(f"    for (integer i = {begin}; i < {end}; i++) {name}[i] = {literal};\n")
                else:
                    for index in range(int(begin), int(end)):
                        stream.write(f"    {name}[{index}] = {literal};\n")
        stream.write("end\n")


def generate(source_run, output_dir=None, header_path=None):
    source = load_source(source_run)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out = (Path(output_dir).resolve() if output_dir else
           PROJECT / "07_runs" / f"accumulator_postprocess_golden_{stamp}")
    header = (Path(header_path).resolve() if header_path else
              PROJECT / "05_tb/accumulator_postprocess" / HEADER_NAME)
    control.require(not out.exists(), f"Output run already exists: {out}")
    control.require(not source["directory"].is_relative_to(out) and
                    not out.is_relative_to(source["directory"]) and
                    not header.is_relative_to(source["directory"]) and not header.is_relative_to(out) and
                    not header.is_relative_to(PROJECT / "07_runs"),
                    "Source, archived runs and published header paths must not overlap")
    stim, expected, masks, timing = build_vectors(source)
    arrays = control.all_arrays(stim, expected, masks)
    (out / "vectors").mkdir(parents=True, exist_ok=False)
    saved_header = out / "vectors" / HEADER_NAME
    write_header(saved_header, arrays, timing, out.name, source)
    npz_path = out / "vectors/accumulator_postprocess_vectors.npz"
    np.savez_compressed(npz_path, **arrays)
    with np.load(npz_path, allow_pickle=False) as restored:
        control.require(set(restored.files) == set(arrays) and
                        all(np.array_equal(restored[name], value) for name, value in arrays.items()),
                        "Saved accumulator vector NPZ readback differs")
    (out / "source_manifest.json").write_bytes(source["manifest_bytes"])
    source_hashes = {}
    source_paths = [
        Path(__file__), Path(control.__file__), Path(memory.__file__), Path(mac.__file__), Path(top.__file__),
        PROJECT / "00_docs/architecture.md", PROJECT / "00_docs/mac_input_pipeline.md",
        PROJECT / "00_docs/modules/accumulator_postprocess.md",
        PROJECT / "00_docs/verification/accumulator_postprocess.md",
        PROJECT / "00_docs/modules/control_unit.md", PROJECT / "00_docs/modules/memory_wrapper.md",
        PROJECT / "00_docs/modules/mac_array.md", PROJECT / "00_docs/verification/mac_array.md",
        PROJECT / "00_docs/verification/memory_wrapper.md", PROJECT / "00_docs/verification/mlp_top.md",
        PROJECT / "04_rtl/controller/layer_config_lut.sv",
        PROJECT / "04_rtl/controller/control_read_mux.sv", PROJECT / "04_rtl/controller/read_issue_control.sv",
    ]
    for path in source_paths:
        relative = path.relative_to(PROJECT)
        copied = out / "source_snapshot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied)
        source_hashes[relative.as_posix()] = control.sha256(copied)
    event_counts = {name: int(stim[name].sum()) for name in (*CONTROLS, "psum_valid")}
    event_counts["overlapped_loads"] = int(np.count_nonzero(stim["bias_load"] & stim["result_load"]))
    metrics = {
        "nvec": timing["nvec"], "trace_vectors": timing["trace_vectors"],
        "expected_cycles": timing["expected_cycles"], "timeout_cycles": timing["timeout_cycles"],
        "event_counts": event_counts, "expected_checks": int(masks["output_data"].sum()),
        "expected_masked": int(np.count_nonzero(masks["output_data"] == 0)),
        "generation_checks_passed": True, "rtl_verified": False,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# Accumulator/postprocess golden\n\nSource: {control.display_path(source['directory'])}; sample 0.\n\n"
        f"{timing['trace_vectors']} Top input snapshots plus one comparison = {timing['nvec']} vectors. "
        f"First comparison 40 ns; last {timing['expected_cycles'] * timing['clock_period_ns']} ns; "
        f"timeout {timing['timeout_cycles']} cycles.\n\n"
        "Replay initialization, readback, FC1/FC2/FC3, ARGMAX, completion and final A/B reads. "
        "Python Control/Memory/MAC references provide inputs even when inactive. "
        "Capture old accumulators before next-bias updates. ReLU/shift changes remain combinational, "
        "including the zero numeric LUT settings from ARGMAX preparation onward.\n\n"
        "Check bias alignment, every valid partial sum and accumulation prefix, saved results "
        "and all 163 packed layer outputs against the original data, including FC3 dummy lanes. "
        "Only the external 32-bit output_data is a DUT comparison signal; every mask is 1.\n\n"
        f"Published header: {control.display_path(header)}. Compare expected[k] before driving stimulus[k]; "
        "its response is checked at k+1. The final vector compares only; do not drive new work afterward.\n\n"
        "Archive vectors, original manifest, source snapshots and hashes separately from earlier runs. "
        "Generation checks do not establish RTL correctness. No inference, RTL simulation or waves.\n",
        encoding="utf-8")
    manifest = {
        "kind": "accumulator_postprocess_golden", "format_version": FORMAT_VERSION, "sample_id": 0,
        "created_utc": datetime.now(timezone.utc).isoformat(), "git": control.git_provenance(),
        "source_run": control.display_path(source["directory"]), "source_run_id": source["directory"].name,
        "source_manifest_sha256": source["manifest_sha256"], "source_npz_sha256": source["npz_sha256"],
        "source_files_sha256": source["manifest"]["files_sha256"],
        "checkpoint_sha256": source["manifest"]["checkpoint_sha256"],
        "input_pixels_sha256": source["manifest"]["input_pixels_sha256"],
        "quantization": source["manifest"]["config"], "timing": timing,
        "inputs": INPUTS, "outputs": OUTPUTS,
        "port_bindings": {**{name: name for name in (*CONTROLS, *SETTINGS, "psum_valid", "output_data")},
                          **{name: f"bias_data[{lane}]" for lane, name in enumerate(BIAS_DATA)},
                          **{name: f"partial_sum[{lane}]" for lane, name in enumerate(PARTIAL_SUM)}},
        "initial_clk": 0, "seed": None, "random_used": False, "fallback_random_seed": 42,
        "mask": "one bit per vector; all bits of external output_data compared on every vector",
        "vector_contract": "compare expected[k] before driving stimulus[k]; response at k+1; last vector compares only",
        "verification_scope": "accumulator_postprocess_standalone", "rtl_verified": False,
        "validation": "source hashes/layout, Python Memory/MAC replay, bias/psum/acc prefixes, "
                      "old-state result captures, layer outputs, ARGMAX settings, NPZ round trip",
        "tb_header": control.display_path(header), "source_sha256": source_hashes,
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "files_sha256": {path.relative_to(out).as_posix(): control.sha256(path)
                         for path in sorted(out.rglob("*")) if path.is_file()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Publish after generation checks and a complete, separately preserved run.
    header.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".accumulator_data_", suffix=".tmp", dir=header.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copyfile(saved_header, temporary)
        control.require(control.sha256(temporary) == manifest["files_sha256"][f"vectors/{HEADER_NAME}"],
                        "Published accumulator header hash differs from its archive")
        temporary.replace(header)
    finally:
        temporary.unlink(missing_ok=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True,
                        help="Existing sample-0 arithmetic golden run with manifest, NPZ and HEX files")
    parser.add_argument("--output-dir", type=Path, help="New output run directory; must not already exist")
    args = parser.parse_args()
    try:
        out = generate(args.source_run, args.output_dir)
    except (OSError, ValueError, KeyError, BadZipFile, EOFError, OverflowError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Saved: {out}\nPublished: {PROJECT / '05_tb/accumulator_postprocess' / HEADER_NAME}")
    print("PASS: generation checks and source arithmetic cross-checks (not RTL verification)")


if __name__ == "__main__":
    main()
