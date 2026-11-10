"""Prepare standalone MAC vectors from an existing MNIST sample-0 golden run.

    python project/03_model/golden/mac_array_golden.py --source-run <run-dir>

Requires NumPy. Replays the whole Top operand flow in Python, then drains the
three-stage MAC pipeline. Never runs inference, Control/Memory RTL or xsim.
See project/00_docs/verification/mac_array.md.
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
import memory_wrapper_golden as memory
import mlp_top_golden as top


PROJECT = control.PROJECT
HEADER_NAME = "mac_array_tb_data.vh"
FORMAT_VERSION = 1
PIPELINE_DEPTH = control.MAC_PIPELINE_DEPTH
INPUT_DATA = tuple(f"input_data_lane{k}" for k in range(4))
WEIGHT_DATA = tuple(tuple(f"weight_data_lane{g}_input{k}" for k in range(4)) for g in range(4))
PARTIAL_SUM = tuple(f"partial_sum_lane{g}" for g in range(4))
INPUTS = {"input_valid": (1, False), **{name: (8, True) for name in INPUT_DATA},
          **{name: (8, True) for row in WEIGHT_DATA for name in row}}
OUTPUTS = {**{name: (32, True) for name in PARTIAL_SUM}, "psum_valid": (1, False)}


def checked32(values, label):
    values = np.asarray(values, dtype=np.int64)
    control.require(np.all((values >= -(1 << 31)) & (values < (1 << 31))),
                    f"Signed int32 range exceeded: {label}")
    return values


def unpack_word(word):
    """The first signed INT8 is in [7:0], independent of host byte order."""
    result = []
    for k in range(4):
        byte = (int(word) >> (8 * k)) & 255
        result.append(byte - 256 if byte >= 128 else byte)
    return result


def load_source(source_run):
    # The shared loader validates the complete saved memory map/packing, hashes,
    # quantization, layer chain and final retained buffers before any output write.
    source = memory.load_source(source_run)
    layers = {}
    with np.load(source["directory"] / "golden.npz", allow_pickle=False) as archive:
        for layer in control.LAYERS:
            values = archive[f"{layer.name}_psum32"].copy()
            control.require(values.dtype == np.dtype("int32") and
                            values.shape == (layer.groups, layer.n, 4),
                            f"Invalid saved partial sums: {layer.name}")
            checked32(values, f"saved {layer.name} partial sums")
            relative = f"expected/{layer.name}_psum32.hex"
            path = source["directory"] / relative
            control.require(control.sha256(path) == source["manifest"]["files_sha256"].get(relative),
                            f"Source partial-sum HEX hash mismatch: {relative}")
            lines = path.read_text(encoding="ascii").splitlines()
            control.require(len(lines) == values.size and
                            all(re.fullmatch(r"[0-9a-fA-F]{8}", line) for line in lines),
                            f"Invalid partial-sum HEX layout: {relative}")
            words = np.array([int(line, 16) for line in lines], dtype=np.int64)
            signed = np.where(words >= (1 << 31), words - (1 << 32), words)
            control.require(np.array_equal(signed, values.reshape(-1)),
                            f"Partial-sum HEX/NPZ mismatch: {layer.name}")
            layers[layer.name] = {
                "input8": archive[f"{layer.name}_input8"].copy(),
                "weight8": archive[f"{layer.name}_weight8"].copy(),
                "psum32": values.astype(np.int64),
            }
    source["mac_layers"] = layers
    return source


def top_buffer_selection(timing):
    """Concrete normal Top routing, including cycles unused by Control tests.

    The standalone Memory stimulus uses zero placeholders for unobserved Control
    selections. Those are not literal Top MAC operands: layer preparation changes
    the combinational input mux, and the existing Control LUT keeps its ARGMAX B
    selection after completion until a new start/reset. No new start is tested.
    """
    selection = np.zeros(timing["nvec"], dtype=np.int64)
    core = timing["core_begin"]
    schedules = timing["control_schedule"]["layers"]
    for layer, schedule in zip(control.LAYERS, schedules):
        begin = core if layer.name == "fc1" else core + schedule["first_read"] - 1
        selection[begin:core + schedule["last_store"] + 1] = layer.buf_sel
    selection[core + schedules[-1]["last_store"] + 1:] = 1
    return selection


def build_stimulus(source):
    accesses, memory_timing = memory.build_stimulus(source)
    trace_count = memory_timing["nvec"]
    nvec = trace_count + PIPELINE_DEPTH
    selection = top_buffer_selection(memory_timing)
    active_buffers = (accesses["in_en"] | accesses["out_we"]) != 0
    control.require(np.array_equal(selection[active_buffers], accesses["buf_sel"][active_buffers]),
                    "Top routing disagrees with scheduled buffer accesses")
    stim = {name: np.zeros(nvec, dtype=np.int64) for name in INPUTS}
    # MAC consumes a BRAM read at the next rising edge, not at the read edge.
    stim["input_valid"][1:trace_count] = accesses["weight_en"][:-1]
    reference = memory.MemoryReference()
    initial = memory.split_initial(source)

    for vector in range(trace_count):
        # Snapshot existing BRAM read registers with the CURRENT Top selection.
        # Then advance Memory at the following rising edge. Using the newly read
        # word here instead would incorrectly remove the BRAM-to-MAC clock delay.
        for name, value in zip(INPUT_DATA, unpack_word(reference.read_outputs[int(selection[vector])])):
            stim[name][vector] = value
        for bank, names in enumerate(WEIGHT_DATA):
            for name, value in zip(names, unpack_word(reference.read_outputs[bank + 2])):
                stim[name][vector] = value
        if vector == memory_timing["initial_read_begin"]:
            for region, values in enumerate(initial):
                control.require(np.all(reference.written[region]) and
                                np.array_equal(reference.words[region], values),
                                f"Initialization replay differs: {memory.MEMORIES[region][0]}")
        if vector < trace_count - 1:
            reference.clock({name: int(values[vector]) for name, values in accesses.items()})

    control.require(np.array_equal(np.concatenate(reference.words[:2]), source["final_data"]),
                    "Final replayed A/B memories differ from saved golden")
    for region in range(2, len(memory.MEMORIES)):
        control.require(np.array_equal(reference.words[region], initial[region]),
                        f"Read-only memory changed: {memory.MEMORIES[region][0]}")
    # No further memory requests: operands hold their last Top values while the
    # final three comparisons drain the last target input. No new valid work enters.
    for name in INPUTS:
        if name != "input_valid":
            stim[name][trace_count:] = stim[name][trace_count - 1]
    first_vector = memory_timing["first_vector_cycle"]
    timing = {
        "nvec": nvec, "trace_vectors": trace_count, "pipeline_depth": PIPELINE_DEPTH,
        "clock_period_ns": memory_timing["clock_period_ns"],
        "reset_cycles": memory_timing["reset_cycles"],
        "start_wait_cycles": memory_timing["start_wait_cycles"],
        "first_vector_cycle": first_vector, "expected_cycles": first_vector + nvec - 1,
        "timeout_cycles": first_vector + nvec - 1 + 100,
        "init_words": memory_timing["init_words"],
        "initial_read_begin": memory_timing["initial_read_begin"],
        "core_begin": memory_timing["core_begin"],
        "argmax_read_begin": memory_timing["argmax_read_begin"],
        "final_read_begin": memory_timing["final_read_begin"],
        "final_words": memory_timing["final_words"], "drain_begin": trace_count,
        "last_target_vector": trace_count - 1, "last_compare_vector": nvec - 1,
        "control_schedule": memory_timing["control_schedule"],
        "buffer_selection": "layer preparation routing; B from ARGMAX preparation through final reads",
    }
    control.require((trace_count, nvec, timing["expected_cycles"], timing["timeout_cycles"]) ==
                    (265018, 265021, 265024, 265124), "MAC timeline differs from the approved scenario")
    return stim, timing


def calculate_partial_sums(stim):
    inputs = np.stack([stim[name] for name in INPUT_DATA], axis=1)
    weights = np.stack([np.stack([stim[name] for name in row], axis=1) for row in WEIGHT_DATA], axis=1)
    products = checked32(inputs[:, None, :] * weights, "sign-extended products")
    pair01 = checked32(products[:, :, 0] + products[:, :, 1], "adder level 1: p0+p1")
    pair23 = checked32(products[:, :, 2] + products[:, :, 3], "adder level 1: p2+p3")
    return checked32(pair01 + pair23, "adder level 2")


def validate_vectors(source, stim, expected, masks, partial, timing):
    nvec = timing["nvec"]
    control.require(stim.keys() == INPUTS.keys() and expected.keys() == OUTPUTS.keys() and
                    masks.keys() == OUTPUTS.keys(), "Vector signal set differs from the MAC ports")
    for values, ports in ((stim, INPUTS), (expected, OUTPUTS)):
        for name, (width, signed) in ports.items():
            low = -(1 << (width - 1)) if signed else 0
            high = (1 << (width - int(signed))) - 1
            control.require(values[name].shape == (nvec,) and
                            np.issubdtype(values[name].dtype, np.integer) and
                            np.all((values[name] >= low) & (values[name] <= high)),
                            f"Invalid vector shape, integer type or bit width: {name}")
    for name, mask in masks.items():
        control.require(mask.shape == (nvec,) and np.all(mask == 1),
                        f"Defined output was excluded from comparison: {name}")
        control.require(np.all(expected[name][:PIPELINE_DEPTH] == 0),
                        f"Incorrect reset/pipeline-fill output: {name}")
    for name in INPUTS:
        control.require(stim[name][0] == 0, f"Incorrect first input after reset: {name}")
    control.require(int(stim["input_valid"].sum()) == 29280 and
                    int(expected["psum_valid"].sum()) == 29280,
                    "Wrong number of valid inputs or output responses")
    control.require(np.array_equal(expected["psum_valid"][PIPELINE_DEPTH:],
                                   stim["input_valid"][:-PIPELINE_DEPTH]), "Valid delay differs from three stages")
    control.require(not np.any(stim["input_valid"][timing["drain_begin"]:]), "New valid work in pipeline drain")
    planned_valid = np.zeros(nvec, dtype=np.int64)
    schedules = timing["control_schedule"]["layers"]
    for layer, schedule in zip(control.LAYERS, schedules):
        reads = (timing["core_begin"] + schedule["first_read"]
                 + np.arange(layer.groups)[:, None] * (layer.n + 1) + np.arange(layer.n)).reshape(-1)
        samples = reads + 1
        planned_valid[samples] = 1
        saved = source["mac_layers"][layer.name]
        for k, name in enumerate(INPUT_DATA):
            wanted = np.tile(saved["input8"].reshape(layer.n, 4)[:, k], layer.groups)
            control.require(np.array_equal(stim[name][samples], wanted),
                            f"Saved input packing or BRAM delay differs: {layer.name}, input {k}")
        weights = saved["weight8"].reshape(layer.groups, 4, layer.n, 4).transpose(0, 2, 1, 3)
        weights = weights.reshape(-1, 4, 4)
        for g, names in enumerate(WEIGHT_DATA):
            for k, name in enumerate(names):
                control.require(np.array_equal(stim[name][samples], weights[:, g, k]),
                                f"Saved weight bank/lane packing differs: {layer.name}, lane {g}, input {k}")
        saved_partial = saved["psum32"].reshape(-1, 4)
        control.require(np.array_equal(partial[samples], saved_partial),
                        f"Recomputed MAC partial sums differ from saved golden: {layer.name}")
        for g, name in enumerate(PARTIAL_SUM):
            control.require(np.array_equal(expected[name][samples + PIPELINE_DEPTH], saved_partial[:, g]),
                            f"Delayed partial sums differ: {layer.name}, lane {g}")
    control.require(np.array_equal(stim["input_valid"], planned_valid), "Extra, missing or shifted valid cycles")
    for g, name in enumerate(PARTIAL_SUM):
        control.require(np.array_equal(expected[name][PIPELINE_DEPTH:], partial[:-PIPELINE_DEPTH, g]),
                        f"Partial-sum data delay differs: lane {g}")
        control.require(expected[name][-1] == partial[timing["last_target_vector"], g],
                        f"Final target input was not fully drained: lane {g}")


def build_vectors(source):
    stim, timing = build_stimulus(source)
    partial = calculate_partial_sums(stim)
    expected = {name: np.zeros(timing["nvec"], dtype=np.int64) for name in OUTPUTS}
    masks = {name: np.ones(timing["nvec"], dtype=np.uint8) for name in OUTPUTS}
    for g, name in enumerate(PARTIAL_SUM):
        expected[name][PIPELINE_DEPTH:] = partial[:-PIPELINE_DEPTH, g]
    expected["psum_valid"][PIPELINE_DEPTH:] = stim["input_valid"][:-PIPELINE_DEPTH]
    validate_vectors(source, stim, expected, masks, partial, timing)
    return stim, expected, masks, timing


def write_header(path, arrays, timing, run_id, source):
    ports = {**{f"tb_{name}": port for name, port in INPUTS.items()},
             **{f"tb_exp_{name}": port for name, port in OUTPUTS.items()},
             **{f"tb_mask_{name}": (1, False) for name in OUTPUTS}}
    params = {
        "MAC_DATA_FORMAT_VERSION": FORMAT_VERSION, "NVEC": timing["nvec"], "SAMPLE_ID": 0,
        "CLOCK_PERIOD_NS": timing["clock_period_ns"], "RESET_CYCLES": timing["reset_cycles"],
        "START_WAIT_CYCLES": timing["start_wait_cycles"], "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
        "FIRST_VECTOR_CYCLE": timing["first_vector_cycle"], "EXPECTED_CYCLES": timing["expected_cycles"],
        "TIMEOUT_CYCLES": timing["timeout_cycles"], "OUTPUT_COUNT": len(OUTPUTS),
        "TRACE_VECTORS": timing["trace_vectors"], "PIPELINE_DEPTH": PIPELINE_DEPTH,
        "INIT_WORDS": timing["init_words"], "INITIAL_READ_BEGIN": timing["initial_read_begin"],
        "CORE_BEGIN": timing["core_begin"], "ARGMAX_READ_BEGIN": timing["argmax_read_begin"],
        "FINAL_READ_BEGIN": timing["final_read_begin"], "FINAL_WORDS": timing["final_words"],
        "DRAIN_BEGIN": timing["drain_begin"], "VALID_INPUTS": 29280,
    }
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"// Auto-generated by mac_array_golden.py; DO NOT EDIT.\n// Run: {run_id}\n")
        stream.write(f"// Source run: {source['directory'].name}\n// Source NPZ SHA-256: {source['npz_sha256']}\n")
        stream.write("// Compare exp[k] BEFORE driving stim[k] at falling edges; stim[k] responds at k+3.\n")
        stream.write("// Masks: 1=compare whole signal, 0=exclude. Weight order: [output lane][input].\n")
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
    stim, expected, masks, timing = build_vectors(source)
    arrays = control.all_arrays(stim, expected, masks)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out = Path(output_dir).resolve() if output_dir else PROJECT / "07_runs" / f"mac_array_golden_{stamp}"
    header = Path(header_path).resolve() if header_path else PROJECT / "05_tb/mac_array" / HEADER_NAME
    control.require(not out.exists(), f"Output run already exists: {out}")
    control.require(not source["directory"].is_relative_to(out) and
                    not out.is_relative_to(source["directory"]) and
                    not header.is_relative_to(source["directory"]) and not header.is_relative_to(out),
                    "Source, run archive and published header paths must not overlap")
    (out / "vectors").mkdir(parents=True, exist_ok=False)
    saved_header = out / "vectors" / HEADER_NAME
    write_header(saved_header, arrays, timing, out.name, source)
    npz_path = out / "vectors/mac_array_vectors.npz"
    np.savez_compressed(npz_path, **arrays)
    with np.load(npz_path, allow_pickle=False) as restored:
        control.require(set(restored.files) == set(arrays) and
                        all(np.array_equal(restored[name], value) for name, value in arrays.items()),
                        "Saved MAC vector NPZ readback differs")
    (out / "source_manifest.json").write_bytes(source["manifest_bytes"])
    source_hashes = {}
    source_paths = [Path(__file__), Path(control.__file__), Path(memory.__file__), Path(top.__file__),
                    PROJECT / "00_docs/architecture.md", PROJECT / "00_docs/mac_input_pipeline.md",
                    PROJECT / "00_docs/modules/mac_array.md",
                    PROJECT / "00_docs/verification/mac_array.md", PROJECT / "00_docs/modules/memory_wrapper.md",
                    PROJECT / "00_docs/modules/control_unit.md", PROJECT / "00_docs/verification/mlp_top.md",
                    PROJECT / "04_rtl/controller/layer_config_lut.sv",
                    PROJECT / "04_rtl/controller/control_read_mux.sv",
                    PROJECT / "04_rtl/controller/read_issue_control.sv"]
    for path in source_paths:
        relative = path.relative_to(PROJECT)
        copied = out / "source_snapshot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied)
        source_hashes[relative.as_posix()] = control.sha256(copied)
    metrics = {
        "nvec": timing["nvec"], "trace_vectors": timing["trace_vectors"],
        "expected_cycles": timing["expected_cycles"], "timeout_cycles": timing["timeout_cycles"],
        "valid_inputs": int(stim["input_valid"].sum()), "valid_outputs": int(expected["psum_valid"].sum()),
        "expected_checks": sum(int(mask.sum()) for mask in masks.values()),
        "expected_masked": sum(int((mask == 0).sum()) for mask in masks.values()),
        "generation_checks_passed": True, "rtl_verified": False,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# MAC array golden\n\nSource: `{control.display_path(source['directory'])}`; MNIST test sample 0.\n\n"
        f"{timing['trace_vectors']} Top operand snapshots plus three drain comparisons = {timing['nvec']} vectors. "
        f"First comparison 40 ns; last {timing['expected_cycles'] * timing['clock_period_ns']} ns; "
        f"timeout {timing['timeout_cycles']} cycles.\n\n"
        "Replay initialization, initial readback, FC1/FC2/FC3, ARGMAX and final reads using the independent "
        "Python Memory model. Operands use the current Top buffer selection and existing BRAM read outputs; "
        "valid is the one-clock-delayed MLP read enable. No DUT state/output is sampled.\n\n"
        "Compute signed INT8 products, balanced INT32 tree and three register delays even when valid=0. "
        "All five outputs are compared on every vector. Valid operations are checked against the saved "
        "layer operands and partial-sum HEX/NPZ, including FC3 dummy lanes.\n\n"
        f"Published header: `{control.display_path(header)}`. Compare expected[k] before driving stimulus[k]; "
        "that stimulus produces a response at k+3. End after the last target response.\n\n"
        "vectors/ preserves the exact header/NPZ; source_snapshot/ and manifest.json preserve source/config/hash "
        "provenance. No inference, RTL simulation or waveform capture is performed. "
        "Generation checks do not establish RTL correctness.\n", encoding="utf-8")
    manifest = {
        "kind": "mac_array_golden", "format_version": FORMAT_VERSION, "sample_id": 0,
        "created_utc": datetime.now(timezone.utc).isoformat(), "git": control.git_provenance(),
        "source_run": control.display_path(source["directory"]), "source_run_id": source["directory"].name,
        "source_manifest_sha256": source["manifest_sha256"], "source_npz_sha256": source["npz_sha256"],
        "source_files_sha256": source["manifest"]["files_sha256"],
        "checkpoint_sha256": source["manifest"]["checkpoint_sha256"],
        "input_pixels_sha256": source["manifest"]["input_pixels_sha256"],
        "quantization": source["manifest"]["config"], "timing": timing,
        "inputs": INPUTS, "outputs": OUTPUTS,
        "port_bindings": {"input_valid": "input_valid", "psum_valid": "psum_valid",
                          **{name: f"input_data[{k}]" for k, name in enumerate(INPUT_DATA)},
                          **{name: f"weight_data[{g}][{k}]" for g, row in enumerate(WEIGHT_DATA)
                             for k, name in enumerate(row)},
                          **{name: f"partial_sum[{g}]" for g, name in enumerate(PARTIAL_SUM)}},
        "initial_clk": 0, "seed": None, "random_used": False, "fallback_random_seed": 42,
        "mask": "one bit per output/lane per vector; all defined MAC outputs compared, including valid=0",
        "vector_contract": "falling edge: compare expected[k], then drive stimulus[k]; MAC response at k+3",
        "verification_scope": "mac_array_standalone", "rtl_verified": False,
        "validation": "source memory/psum hashes and layout, Python memory replay, signed int32 tree, "
                      "saved valid operands/partial sums, all-cycle data/valid delay, NPZ round trip",
        "tb_header": control.display_path(header), "source_sha256": source_hashes,
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "files_sha256": {path.relative_to(out).as_posix(): control.sha256(path)
                         for path in sorted(out.rglob("*")) if path.is_file()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Publish only after a complete archive and successful generation checks.
    header.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".mac_array_data_", suffix=".tmp", dir=header.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copyfile(saved_header, temporary)
        control.require(control.sha256(temporary) == manifest["files_sha256"][f"vectors/{HEADER_NAME}"],
                        "Published MAC header hash differs from its archive")
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
    except (OSError, ValueError, KeyError, BadZipFile, EOFError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Saved: {out}\nPublished: {PROJECT / '05_tb/mac_array' / HEADER_NAME}")
    print("PASS: source/layout checks, MAC pipeline and saved partial sums, vector readback (not RTL verification)")


if __name__ == "__main__":
    main()
