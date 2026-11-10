"""Prepare standalone Memory vectors from saved MNIST sample-0 golden data.

    python project/03_model/golden/memory_wrapper_golden.py --source-run <run-dir>

Requires NumPy. Run separately from xsim; no inference or RTL is executed here.
See project/00_docs/verification/memory_wrapper.md for the vector contract.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import tempfile
from zipfile import BadZipFile

import numpy as np

import control_unit_golden as control
import mlp_top_golden as top


PROJECT = control.PROJECT
HEADER_NAME = "memory_wrapper_tb_data.vh"
FORMAT_VERSION = 1
MEMORIES = top.MEMORIES
INPUTS = {
    "tb_en": (1, False), "tb_we": (1, False),
    "tb_addr": (20, False), "tb_wdata": (32, False),
    "busy": (1, False), "buf_sel": (1, False),
    "in_addr": (8, False), "in_en": (1, False),
    "out_addr": (7, False), "out_we": (1, False), "out_data": (32, False),
    "weight_addr": (15, False), "weight_en": (1, False),
    "bias_addr": (8, False), "bias_en": (1, False),
}
WEIGHT_OUTPUTS = tuple(f"weight_data_bank{bank}" for bank in range(4))
OUTPUTS = {name: (32, False) for name in
           ("tb_rdata", "in_data", *WEIGHT_OUTPUTS, "bias_data")}
CORE_INPUTS = ("busy", "buf_sel", "in_addr", "in_en", "out_addr", "out_we",
               "weight_addr", "weight_en", "bias_addr", "bias_en")


def split_initial(source):
    """Return the seven source memories without inventing unwritten contents."""
    result, offset = [], 0
    for _, depth in MEMORIES:
        result.append(source["init_data"][offset:offset + depth])
        offset += depth
    control.require(offset == len(source["init_data"]), "Initial memory length differs")
    return result


def load_source(source_run):
    # Reuse the Top loader's hash/configuration, packing and layer-chain checks.
    # Importing it does not call generate(), load a checkpoint or run a simulator.
    source = top.load_data(source_run)
    initial = split_initial(source)
    fc3 = control.LAYERS[-1]
    dummy_begin = fc3.weight_base + (fc3.groups - 1) * fc3.n
    for bank in (2, 3):
        control.require(np.all(initial[bank + 2][dummy_begin:dummy_begin + fc3.n] == 0),
                        f"FC3 dummy weights must be zero in bank {bank}")
    control.require(int(initial[6][-1]) >> 16 == 0, "FC3 dummy biases must be zero")
    return source


def build_stimulus(source):
    """Use the same absolute phases as Top, with Control outputs as inputs.

    control.build_vectors() is a Python schedule derived from the specification;
    this does not instantiate or execute Control RTL. Disabled addresses and
    unused selections use that schedule's concrete values, not extra DUT rules.
    """
    _, ctl, _, ctl_timing = control.build_vectors(source["logits"])
    count, final_count = len(source["init_data"]), len(source["final_data"])
    core_begin = 2 * count + 1  # Keep Top's idle vector after initial readback.
    final_begin = core_begin + ctl_timing["nvec"]
    nvec = final_begin + final_count + 1  # Includes the final read response.
    stim = {name: np.zeros(nvec, dtype=np.int64) for name in INPUTS}
    stim["tb_en"][:2 * count] = 1
    stim["tb_we"][:count] = 1
    stim["tb_addr"][:count] = source["init_addr"]
    stim["tb_addr"][count:2 * count] = source["init_addr"]
    stim["tb_wdata"][:count] = source["init_data"]
    for name in CORE_INPUTS:
        stim[name][core_begin:final_begin] = ctl[name]
    for layer, schedule in zip(control.LAYERS, ctl_timing["layers"]):
        writes = (schedule["first_read"] + np.arange(layer.groups) * (layer.n + 1)
                  + layer.n - 1 + control.OUTPUT_WRITE_DELAY)
        control.require(np.all(ctl["out_we"][writes] == 1) and
                        np.array_equal(ctl["out_addr"][writes], np.arange(layer.groups)),
                        f"Output write schedule differs: {layer.name}")
        stim["out_data"][core_begin + writes] = source["layer_words"][layer.name]
    stim["tb_en"][final_begin:final_begin + final_count] = 1
    stim["tb_addr"][final_begin:final_begin + final_count] = source["final_addr"]
    first_vector = control.RESET_CYCLES + control.START_WAIT_CYCLES
    timing = {
        "nvec": nvec, "clock_period_ns": control.CLOCK_NS,
        "reset_cycles": control.RESET_CYCLES, "start_wait_cycles": control.START_WAIT_CYCLES,
        "first_vector_cycle": first_vector, "expected_cycles": first_vector + nvec - 1,
        "timeout_cycles": first_vector + nvec - 1 + 100,
        "init_words": count, "initial_read_begin": count, "core_begin": core_begin,
        "argmax_read_begin": core_begin + ctl_timing["argmax_first_read"],
        "final_read_begin": final_begin, "final_words": final_count,
        "last_response_vector": nvec - 1, "control_schedule": ctl_timing,
    }
    control.require((count, final_count, nvec) == (117607, 324, 265018),
                    "Memory phases differ from the approved Top schedule")
    for name, (width, _) in INPUTS.items():
        control.require(stim[name].shape == (nvec,) and
                        np.all((stim[name] >= 0) & (stim[name] < (1 << width))),
                        f"Invalid input shape or width: {name}")
    control.require(not np.any(stim["tb_en"] & stim["busy"]), "TB access overlaps busy")
    for name in ("in_en", "out_we", "weight_en", "bias_en"):
        control.require(not np.any(stim[name] & (1 - stim["busy"])),
                        f"Internal access outside busy: {name}")
    counts = {"in_en": 29283, "weight_en": 29280, "bias_en": 163, "out_we": 163}
    for name, count_expected in counts.items():
        control.require(int(stim[name].sum()) == count_expected, f"Wrong event count: {name}")
    control.require(int(stim["tb_en"].sum()) == 2 * count + final_count and
                    int(stim["tb_we"].sum()) == count, "Wrong TB access counts")
    return stim, timing


class MemoryReference:
    """Port-contract model with separate storage and read register per BRAM.

    Storage is unknown until explicitly written. Reset only establishes zero
    read registers; it is not represented as a memory fill operation.
    """

    def __init__(self):
        self.words = [np.empty(depth, dtype=np.int64) for _, depth in MEMORIES]
        self.written = [np.zeros(depth, dtype=np.bool_) for _, depth in MEMORIES]
        self.read_outputs = np.zeros(len(MEMORIES), dtype=np.int64)

    def address(self, memory, word):
        control.require(0 <= memory < len(MEMORIES), f"Unsupported memory region: {memory}")
        control.require(0 <= word < MEMORIES[memory][1],
                        f"Address outside {MEMORIES[memory][0]}: {word}")

    def read(self, memory, word):
        self.address(memory, word)
        control.require(self.written[memory][word],
                        f"Read before initialization: {MEMORIES[memory][0]}[{word}]")
        value = int(self.words[memory][word])
        self.read_outputs[memory] = value
        return value

    def write(self, memory, word, value):
        self.address(memory, word)
        self.words[memory][word] = value
        self.written[memory][word] = True
        # Writes do not update the BRAM's read-output register.

    def clock(self, inputs):
        """Process one rising edge; return a TB response only for a TB read."""
        if not inputs["busy"]:
            if inputs["tb_en"]:
                address = inputs["tb_addr"]
                control.require(address & 3 == 0, "Unaligned TB request")
                memory, word = address >> 17, (address >> 2) & 0x7fff
                if inputs["tb_we"]:
                    self.write(memory, word, inputs["tb_wdata"])
                else:
                    return self.read(memory, word)
        else:
            control.require(not inputs["tb_en"], "TB request while busy is outside the scenario")
            selection = inputs["buf_sel"]
            if inputs["in_en"]:
                self.read(selection, inputs["in_addr"])
            if inputs["out_we"]:
                self.write(1 - selection, inputs["out_addr"], inputs["out_data"])
            if inputs["weight_en"]:
                for bank in range(4):
                    self.read(bank + 2, inputs["weight_addr"])
            if inputs["bias_en"]:
                self.read(6, inputs["bias_addr"])
        return None


def build_expected(source, stim, timing):
    nvec = timing["nvec"]
    expected = {name: np.zeros(nvec, dtype=np.int64) for name in OUTPUTS}
    masks = {name: np.ones(nvec, dtype=np.uint8) for name in OUTPUTS}
    masks["tb_rdata"][:] = 0
    reference = MemoryReference()
    initial = split_initial(source)
    buffers = [initial[0].copy(), initial[1].copy()]
    checkpoints = {}
    for layer, schedule in zip(control.LAYERS, timing["control_schedule"]["layers"]):
        target = 1 - layer.buf_sel
        buffers[target][:layer.groups] = source["layer_words"][layer.name]
        checkpoints[timing["core_begin"] + schedule["last_store"] + 1] = (
            target, buffers[target].copy(), layer.name)

    held_selection, response = 0, None
    for vector in range(nvec):
        # These are the values BEFORE stim[vector] changes at this falling edge.
        expected["in_data"][vector] = reference.read_outputs[held_selection]
        expected["bias_data"][vector] = reference.read_outputs[6]
        for bank, name in enumerate(WEIGHT_OUTPUTS):
            expected[name][vector] = reference.read_outputs[bank + 2]
        if response is not None:
            expected["tb_rdata"][vector] = response
            masks["tb_rdata"][vector] = 1
        if vector == timing["initial_read_begin"]:
            for memory, values in enumerate(initial):
                control.require(np.all(reference.written[memory]) and
                                np.array_equal(reference.words[memory], values),
                                f"Initial memory writeback differs: {MEMORIES[memory][0]}")
        if vector in checkpoints:
            target, values, layer_name = checkpoints[vector]
            control.require(np.array_equal(reference.words[target], values),
                            f"Layer writeback/retention differs: {layer_name}")
        if vector < nvec - 1:
            inputs = {name: int(values[vector]) for name, values in stim.items()}
            response = reference.clock(inputs)
            held_selection = inputs["buf_sel"]

    control.require(np.array_equal(np.concatenate(reference.words[:2]), source["final_data"]),
                    "Replayed final A/B storage differs from source golden")
    for memory in range(2, len(MEMORIES)):
        control.require(np.array_equal(reference.words[memory], initial[memory]),
                        f"Read-only memory changed during inference: {MEMORIES[memory][0]}")
    return expected, masks


def validate_vectors(source, stim, expected, masks, timing):
    """Cross-check replay responses against saved golden, not DUT behavior."""
    nvec = timing["nvec"]
    for name, (width, _) in OUTPUTS.items():
        control.require(expected[name].shape == (nvec,) and
                        np.all((expected[name] >= 0) & (expected[name] < (1 << width))),
                        f"Invalid expected shape or width: {name}")
        mask = masks[name]
        control.require(mask.shape == (nvec,) and np.all((mask == 0) | (mask == 1)) and np.any(mask),
                        f"Invalid or all-excluded mask: {name}")
        if name != "tb_rdata":
            control.require(np.all(mask == 1), f"Defined read register was excluded: {name}")
            control.require(expected[name][0] == 0, f"Reset read output is not zero: {name}")
    requests = (stim["busy"] == 0) & (stim["tb_en"] == 1) & (stim["tb_we"] == 0)
    response_mask = np.zeros(nvec, dtype=np.uint8)
    response_mask[1:] = requests[:-1]
    control.require(np.array_equal(masks["tb_rdata"], response_mask), "TB response mask is misaligned")
    for begin, values in ((timing["initial_read_begin"], source["init_data"]),
                          (timing["final_read_begin"], source["final_data"])):
        control.require(np.array_equal(expected["tb_rdata"][begin + 1:begin + len(values) + 1], values),
                        "Replayed TB readback differs from source golden")
    initial = split_initial(source)
    layer_inputs = (initial[0], source["layer_words"]["fc1"], source["layer_words"]["fc2"])
    for layer, schedule, input_words in zip(
            control.LAYERS, timing["control_schedule"]["layers"], layer_inputs):
        first = timing["core_begin"] + schedule["first_read"]
        reads = (first + np.arange(layer.groups)[:, None] * (layer.n + 1)
                 + np.arange(layer.n)).reshape(-1)
        control.require(np.array_equal(expected["in_data"][reads + 1], np.tile(input_words, layer.groups)),
                        f"Internal input reads differ from saved layer inputs: {layer.name}")
        for bank, name in enumerate(WEIGHT_OUTPUTS):
            control.require(np.array_equal(expected[name][reads + 1],
                                           initial[bank + 2][stim["weight_addr"][reads]]),
                            f"Weight read responses differ: {layer.name}, bank {bank}")
        bias_reads = first + np.arange(layer.groups) * (layer.n + 1)
        control.require(np.array_equal(expected["bias_data"][bias_reads + 1],
                                       initial[6][stim["bias_addr"][bias_reads]]),
                        f"Bias read responses differ: {layer.name}")
    argmax_reads = timing["argmax_read_begin"] + 5 * np.arange(3)
    control.require(np.array_equal(expected["in_data"][argmax_reads + 1], source["layer_words"]["fc3"]),
                    "ARGMAX memory reads differ from FC3 words")
    control.require(requests[-1] == 0 and masks["tb_rdata"][-1] == 1 and
                    not any(values[-1] for values in stim.values()),
                    "Final vector must check the last response without another request")


def build_vectors(source):
    stim, timing = build_stimulus(source)
    expected, masks = build_expected(source, stim, timing)
    validate_vectors(source, stim, expected, masks, timing)
    return stim, expected, masks, timing


def write_header(path, arrays, timing, run_id, source):
    ports = {**{f"tb_{name}": port for name, port in INPUTS.items()},
             **{f"tb_exp_{name}": port for name, port in OUTPUTS.items()},
             **{f"tb_mask_{name}": (1, False) for name in OUTPUTS}}
    params = {
        "MEMORY_DATA_FORMAT_VERSION": FORMAT_VERSION, "NVEC": timing["nvec"], "SAMPLE_ID": 0,
        "CLOCK_PERIOD_NS": timing["clock_period_ns"], "RESET_CYCLES": timing["reset_cycles"],
        "START_WAIT_CYCLES": timing["start_wait_cycles"], "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
        "FIRST_VECTOR_CYCLE": timing["first_vector_cycle"], "EXPECTED_CYCLES": timing["expected_cycles"],
        "TIMEOUT_CYCLES": timing["timeout_cycles"], "OUTPUT_COUNT": len(OUTPUTS),
        "INIT_WORDS": timing["init_words"], "INITIAL_READ_BEGIN": timing["initial_read_begin"],
        "CORE_BEGIN": timing["core_begin"], "ARGMAX_READ_BEGIN": timing["argmax_read_begin"],
        "FINAL_READ_BEGIN": timing["final_read_begin"], "FINAL_WORDS": timing["final_words"],
    }
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"// Auto-generated by memory_wrapper_golden.py; DO NOT EDIT.\n// Run: {run_id}\n")
        stream.write(f"// Source run: {source['directory'].name}\n// Source NPZ SHA-256: {source['npz_sha256']}\n")
        stream.write("// Compare exp[k] BEFORE driving stim[k] at the falling edge. 1=compare, 0=exclude.\n")
        stream.write("// weight_data_bankN maps to DUT weight_data[N]; first packed byte is [7:0].\n")
        for name, value in params.items():
            stream.write(f"localparam integer {name} = {value};\n")
        stream.write("localparam logic INITIAL_CLK = 1'b0;\n")
        for name, (width, _) in ports.items():
            suffix = f" [{width - 1}:0]" if width > 1 else ""
            stream.write(f"logic{suffix} {name} [0:NVEC-1];\n")
        stream.write("initial begin\n    for (integer i = 0; i < NVEC; i++) begin\n")
        for name in ports:
            stream.write(f"        {name}[i] = '0;\n")
        stream.write("    end\n")
        for name, values in arrays.items():
            width, _ = ports[name]
            changes = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1, len(values)]
            for begin, end in zip(changes[:-1], changes[1:]):
                value = int(values[begin])
                if value == 0:
                    continue
                literal = f"{width}'h{value:x}"
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
    out = (Path(output_dir).resolve() if output_dir else
           PROJECT / "07_runs" / f"memory_wrapper_golden_{stamp}")
    header = Path(header_path).resolve() if header_path else PROJECT / "05_tb/memory" / HEADER_NAME
    control.require(not out.exists(), f"Output run already exists: {out}")
    control.require(not source["directory"].is_relative_to(out) and
                    not out.is_relative_to(source["directory"]) and
                    not header.is_relative_to(source["directory"]) and not header.is_relative_to(out),
                    "Source, run archive and published header paths must not overlap")
    (out / "vectors").mkdir(parents=True, exist_ok=False)
    saved_header = out / "vectors" / HEADER_NAME
    write_header(saved_header, arrays, timing, out.name, source)
    npz_path = out / "vectors/memory_wrapper_vectors.npz"
    np.savez_compressed(npz_path, **arrays)
    with np.load(npz_path, allow_pickle=False) as restored:
        control.require(set(restored.files) == set(arrays) and
                        all(np.array_equal(restored[name], values) for name, values in arrays.items()),
                        "Saved vector NPZ readback differs")
    (out / "source_manifest.json").write_bytes(source["manifest_bytes"])
    source_hashes = {}
    source_paths = [Path(__file__), Path(top.__file__), Path(control.__file__),
                    PROJECT / "00_docs/architecture.md", PROJECT / "00_docs/mac_input_pipeline.md",
                    PROJECT / "00_docs/modules/memory_wrapper.md",
                    PROJECT / "00_docs/verification/memory_wrapper.md"]
    for path in source_paths:
        relative = path.relative_to(PROJECT)
        copied = out / "source_snapshot" / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied)
        source_hashes[relative.as_posix()] = control.sha256(copied)
    event_counts = {name: int(stim[name].sum()) for name in ("in_en", "weight_en", "bias_en", "out_we")}
    metrics = {
        "nvec": timing["nvec"], "expected_cycles": timing["expected_cycles"],
        "timeout_cycles": timing["timeout_cycles"], "initial_words_written": timing["init_words"],
        "initial_words_read": timing["init_words"], "final_words_read": timing["final_words"],
        "event_counts": event_counts,
        "expected_checks": sum(int(mask.sum()) for mask in masks.values()),
        "expected_masked": sum(int((mask == 0).sum()) for mask in masks.values()),
        "generation_checks_passed": True, "rtl_verified": False,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# Memory wrapper golden\n\nSource: `{control.display_path(source['directory'])}`; MNIST test sample 0.\n\n"
        f"{timing['nvec']} falling-edge vectors; {timing['expected_cycles']} expected TB cycles, "
        f"timeout {timing['timeout_cycles']} cycles.\n\n"
        "Initialize/read all 117607 words, replay the normal FC1/FC2/FC3/ARGMAX memory schedule, "
        "then read all 324 final A/B words, including retained data. Tester directly drives busy/core ports.\n\n"
        "Compare every defined internal read output, including TB read updates, held values and "
        "buffer-selection changes. Compare tb_rdata only on one-clock TB read responses. "
        "Weight arrays named weight_data_bankN map to DUT weight_data[N].\n\n"
        f"Published header: `{control.display_path(header)}`. Each falling edge compares expected[k] "
        "before driving stimulus[k]. Vector 0 is at 40 ns; finish on the final read-response comparison.\n\n"
        "vectors/ stores the exact header/NPZ; source_snapshot/ stores the used sources/specifications; "
        "manifest.json records source/configuration/hash provenance. No inference, RTL simulation "
        "or waveform capture is performed. Generation checks do not establish RTL correctness.\n",
        encoding="utf-8")
    manifest = {
        "kind": "memory_wrapper_golden", "format_version": FORMAT_VERSION, "sample_id": 0,
        "created_utc": datetime.now(timezone.utc).isoformat(), "git": control.git_provenance(),
        "source_run": control.display_path(source["directory"]), "source_run_id": source["directory"].name,
        "source_manifest_sha256": source["manifest_sha256"], "source_npz_sha256": source["npz_sha256"],
        "source_files_sha256": source["manifest"]["files_sha256"],
        "checkpoint_sha256": source["manifest"]["checkpoint_sha256"],
        "input_pixels_sha256": source["manifest"]["input_pixels_sha256"],
        "quantization": source["manifest"]["config"], "timing": timing,
        "inputs": INPUTS, "outputs": OUTPUTS,
        "weight_output_ports": {name: f"weight_data[{bank}]" for bank, name in enumerate(WEIGHT_OUTPUTS)},
        "memory": source["manifest"]["memory"], "initial_clk": 0,
        "seed": None, "random_used": False, "fallback_random_seed": 42,
        "mask": "one bit per output/bank per vector; 1=compare, 0=exclude",
        "vector_contract": "falling edge: compare expected[k], then drive stimulus[k]; read response at k+1",
        "verification_scope": "memory_wrapper_standalone", "rtl_verified": False,
        "validation": "source hashes/layout, legal initialized accesses, per-memory read-register replay, "
                      "layer/final retention, saved read responses, schedule and NPZ round trip",
        "tb_header": control.display_path(header), "source_sha256": source_hashes,
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "files_sha256": {path.relative_to(out).as_posix(): control.sha256(path)
                         for path in sorted(out.rglob("*")) if path.is_file()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Keep an existing TB header until all generation checks and archival writes succeed.
    header.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".memory_wrapper_data_", suffix=".tmp",
                                         dir=header.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copyfile(saved_header, temporary)
        control.require(control.sha256(temporary) == manifest["files_sha256"][f"vectors/{HEADER_NAME}"],
                        "Published header hash differs from its archive")
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
    print(f"Saved: {out}\nPublished: {PROJECT / '05_tb/memory' / HEADER_NAME}")
    print("PASS: source/layout checks, memory replay, schedule and vector readback (not RTL verification)")


if __name__ == "__main__":
    main()
