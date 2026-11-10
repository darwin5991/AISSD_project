"""Prepare Top vectors for approved sample IDs 0..9 from saved arithmetic golden.

    python project/03_model/golden/mlp_top_golden.py --source-run <golden-run>
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

PROJECT = control.PROJECT
HEADER_NAME = "mlp_top_tb_data.vh"
SUPPORTED_SAMPLE_IDS = tuple(range(10))
INPUTS = {"start": (1, False), "tb_en": (1, False), "tb_we": (1, False),
          "tb_addr": (20, False), "tb_wdata": (32, False)}
OUTPUTS = {"busy": (1, False), "done": (1, False), "prediction": (4, False),
           "tb_rdata": (32, False), "probe_out_we": (1, False),
           "probe_out_addr": (7, False), "probe_buf_sel": (1, False),
           "probe_out_data": (32, False)}
MEMORIES = (("buffer_a", 196), ("buffer_b", 128),
            *((f"weight_bank{i}", 29280) for i in range(4)), ("bias", 163))


def packed(values):
    values = np.asarray(values, dtype=np.int64).reshape(-1, 4) & 255
    return np.sum(values << np.arange(0, 32, 8), axis=1, dtype=np.int64)


def load_data(source_run, *, allowed_sample_ids=(0,)):
    # Memory/MAC/accumulator loaders also call this function; keep their default
    # sample-0 contract. Only generate() opts into the approved Top sample IDs.
    source = control.load_source(source_run, allowed_sample_ids=allowed_sample_ids)
    root, manifest = source["directory"], source["manifest"]
    with np.load(root / "golden.npz", allow_pickle=False) as archive:
        saved = {name: archive[name].copy() for name in archive.files}

    def read_hex(relative, expected):
        path = root / relative
        control.require(control.sha256(path) == manifest["files_sha256"].get(relative),
                        f"Source HEX hash mismatch: {relative}")
        lines = path.read_text(encoding="ascii").splitlines()
        control.require(all(re.fullmatch(r"[0-9a-fA-F]{8}", line) for line in lines),
                        f"Invalid 32-bit HEX: {relative}")
        actual = np.array([int(line, 16) for line in lines], dtype=np.int64)
        control.require(np.array_equal(actual, expected), f"HEX/NPZ layout mismatch: {relative}")
        return actual

    # Independently reconstruct the saved memory packing, not DUT outputs.
    memory = {"buffer_a": saved["buffer_a_initial"].astype(np.int64),
              "buffer_b": saved["buffer_b_initial"].astype(np.int64)}
    control.require(np.array_equal(memory["buffer_a"], packed(saved["input8"])), "Input packing differs")
    control.require(np.all(memory["buffer_b"] == 0), "Initial B must be zero")
    bias_words, layer_words = [], {}
    for layer in control.LAYERS:
        for suffix, shape in (("input8", (layer.inputs,)),
                              ("weight8", (layer.padded_outputs, layer.inputs)),
                              ("bias8", (layer.padded_outputs,)),
                              ("output8", (layer.padded_outputs,))):
            value = saved[f"{layer.name}_{suffix}"]
            control.require(value.shape == shape and value.dtype == np.dtype("int8"),
                            f"Invalid saved int8 array: {layer.name}_{suffix}")
        bias_words.append(packed(saved[f"{layer.name}_bias8"]))
        layer_words[layer.name] = read_hex(f"expected/{layer.name}_output.hex",
                                           packed(saved[f"{layer.name}_output8"]))
    control.require(np.array_equal(saved["fc1_input8"], saved["input8"]) and
                    np.array_equal(saved["fc2_input8"], saved["fc1_output8"]) and
                    np.array_equal(saved["fc3_input8"], saved["fc2_output8"]), "Broken saved layer chain")
    for bank in range(4):
        memory[f"weight_bank{bank}"] = np.concatenate([
            packed(saved[f"{layer.name}_weight8"][bank::4]) for layer in control.LAYERS])
    memory["bias"] = np.concatenate(bias_words)
    addresses, initial = [], []
    for region, (name, depth) in enumerate(MEMORIES):
        meta = manifest["memory"][name]
        control.require(meta == {"file": f"memory/{name}.hex", "words": depth,
                                 "tb_base_byte": f"0x{region * 0x20000:05X}"},
                        f"Memory map mismatch: {name}")
        values = read_hex(meta["file"], memory[name])
        control.require(len(values) == depth, f"Memory depth mismatch: {name}")
        initial.append(values)
        addresses.append(region * 0x20000 + 4 * np.arange(depth, dtype=np.int64))
    final_a, final_b = memory["buffer_a"].copy(), layer_words["fc1"].copy()
    final_a[:32] = layer_words["fc2"]
    final_b[:3] = layer_words["fc3"]
    for name, values in (("buffer_a", final_a), ("buffer_b", final_b)):
        control.require(np.array_equal(saved[f"{name}_final"], values), f"Final buffer retention mismatch: {name}")
        read_hex(f"expected/{name}_final.hex", values)
    read_hex("expected/prediction.hex", np.array([source["prediction"]]))
    source.update(init_data=np.concatenate(initial), init_addr=np.concatenate(addresses),
                  final_data=np.concatenate([final_a, final_b]),
                  final_addr=np.concatenate([addresses[0], addresses[1]]), layer_words=layer_words)
    return source


def build_vectors(source):
    _, ctl, _, ctl_timing = control.build_vectors(source["logits"])
    count = len(source["init_data"])
    start = 2 * count + 1
    final_begin = start + ctl_timing["nvec"]
    nvec = final_begin + len(source["final_data"]) + 1
    stim = {name: np.zeros(nvec, dtype=np.int64) for name in INPUTS}
    expected = {name: np.zeros(nvec, dtype=np.int64) for name in OUTPUTS}
    masks = {name: np.zeros(nvec, dtype=np.uint8) for name in OUTPUTS}
    stim["tb_en"][:2 * count] = 1
    stim["tb_we"][:count] = 1
    stim["tb_addr"][:count] = stim["tb_addr"][count:2 * count] = source["init_addr"]
    stim["tb_wdata"][:count] = source["init_data"]
    expected["tb_rdata"][count + 1:2 * count + 1] = source["init_data"]
    masks["tb_rdata"][count + 1:2 * count + 1] = 1
    stim["start"][start] = 1
    inference = slice(start, final_begin)
    for name in ("busy", "done"):
        expected[name][inference] = ctl[name]
    expected["probe_out_we"][inference] = ctl["out_we"]
    expected["probe_out_addr"][inference] = ctl["out_addr"]
    expected["probe_buf_sel"][inference] = ctl["buf_sel"]
    for name in ("busy", "done", "probe_out_we"):
        masks[name][:] = 1
    for name in ("probe_out_addr", "probe_buf_sel", "probe_out_data"):
        masks[name] = expected["probe_out_we"].astype(np.uint8)
    for layer, schedule in zip(control.LAYERS, ctl_timing["layers"]):
        writes = np.flatnonzero(ctl["out_we"][schedule["first_read"]:schedule["last_store"] + 1])
        writes += schedule["first_read"] + start
        control.require(len(writes) == layer.groups, f"Layer write count differs: {layer.name}")
        expected["probe_out_data"][writes] = source["layer_words"][layer.name]
    done_vector = start + ctl_timing["done_check_vector"]
    expected["prediction"][done_vector] = source["prediction"]
    masks["prediction"][[0, done_vector]] = 1
    final_count = len(source["final_data"])
    stim["tb_en"][final_begin:final_begin + final_count] = 1
    stim["tb_addr"][final_begin:final_begin + final_count] = source["final_addr"]
    expected["tb_rdata"][final_begin + 1:] = source["final_data"]
    masks["tb_rdata"][final_begin + 1:] = 1
    timing = {"nvec": nvec, "clock_period_ns": 10, "reset_cycles": 3,
              "start_wait_cycles": 1, "first_vector_cycle": 4,
              "expected_cycles": nvec + 3, "timeout_cycles": nvec + 103,
              "init_words": count, "initial_read_begin": count, "start_vector": start,
              "done_check_vector": done_vector, "final_read_begin": final_begin,
              "final_words": final_count, "control_schedule": ctl_timing}
    control.require((count, final_count, nvec) == (117607, 324, 265018), "Unexpected phase lengths")
    control.require(stim["start"].sum() == 1 and not np.any(stim["tb_en"][inference]), "TB/core access overlap")
    control.require(expected["probe_out_we"].sum() == 163 and expected["done"].sum() == 1,
                    "Unexpected inference event counts")
    for values, ports in ((stim, INPUTS), (expected, OUTPUTS)):
        for name, (width, _) in ports.items():
            control.require(values[name].shape == (nvec,) and
                            np.all((values[name] >= 0) & (values[name] < 1 << width)), f"Bad vector width: {name}")
    for name, mask in masks.items():
        control.require(np.all((mask == 0) | (mask == 1)) and np.any(mask), f"Invalid/all-excluded mask: {name}")
    return stim, expected, masks, timing


def write_header(path, arrays, timing, run_id, source):
    ports = {**{f"tb_{key}": value for key, value in INPUTS.items()},
             **{f"tb_exp_{key}": value for key, value in OUTPUTS.items()},
             **{f"tb_mask_{key}": (1, False) for key in OUTPUTS}}
    params = {"TOP_DATA_FORMAT_VERSION": 1, "NVEC": timing["nvec"], "SAMPLE_ID": source["sample_id"],
              "CLOCK_PERIOD_NS": 10, "RESET_CYCLES": 3, "START_WAIT_CYCLES": 1,
              "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
              "FIRST_VECTOR_CYCLE": 4, "EXPECTED_CYCLES": timing["expected_cycles"],
              "TIMEOUT_CYCLES": timing["timeout_cycles"], "EXPECTED_PREDICTION": source["prediction"],
              "INIT_WORDS": timing["init_words"], "START_VECTOR": timing["start_vector"],
              "FINAL_READ_BEGIN": timing["final_read_begin"], "FINAL_WORDS": timing["final_words"]}
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"// Auto-generated by mlp_top_golden.py; DO NOT EDIT.\n// Run: {run_id}\n")
        stream.write(f"// Source run: {source['directory'].name}\n// Source NPZ SHA-256: {source['npz_sha256']}\n")
        stream.write("// Compare exp[k] before driving stim[k], on falling edges. 1=compare, 0=exclude.\n")
        for name, value in params.items():
            stream.write(f"localparam integer {name} = {value};\n")
        stream.write("localparam logic INITIAL_CLK = 1'b0;\n")
        for name, (width, _) in ports.items():
            stream.write(f"logic [{width - 1}:0] {name} [0:NVEC-1];\n")
        stream.write("logic [31:0] tb_init_data [0:INIT_WORDS-1];\n")
        stream.write("logic [31:0] tb_final_data [0:FINAL_WORDS-1];\n")
        stream.write("logic [19:0] tb_init_addr [0:INIT_WORDS-1];\n")
        stream.write("logic [19:0] tb_final_addr [0:FINAL_WORDS-1];\ninitial begin\n")

        def emit(name, values, width):
            changes = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1, len(values)]
            for begin, end in zip(changes[:-1], changes[1:]):
                literal = f"{width}'h{int(values[begin]):x}"
                if end - begin >= 4:
                    stream.write(f"    for (integer i = {begin}; i < {end}; i++) {name}[i] = {literal};\n")
                else:
                    for index in range(int(begin), int(end)):
                        stream.write(f"    {name}[{index}] = {literal};\n")

        # Helpers prevent writing the 117,607 memory literals twice in the header.
        emit("tb_init_data", source["init_data"], 32)
        emit("tb_final_data", source["final_data"], 32)
        offset = 0
        for region, (_, depth) in enumerate(MEMORIES):
            stream.write(f"    for (integer i = 0; i < {depth}; i++) tb_init_addr[{offset}+i] = 20'h{region * 0x20000:x} + 4*i;\n")
            offset += depth
        stream.write("    for (integer i = 0; i < FINAL_WORDS; i++) tb_final_addr[i] = tb_init_addr[i];\n")
        stream.write("    for (integer i = 0; i < NVEC; i++) begin\n")
        for name in ports:
            stream.write(f"        {name}[i] = '0;\n")
        stream.write("    end\n")
        # Values for these three arrays are copied from the precomputed helpers.
        for name, values in arrays.items():
            if name not in ("tb_tb_addr", "tb_tb_wdata", "tb_exp_tb_rdata"):
                emit(name, values, ports[name][0])
        stream.write("    for (integer i = 0; i < INIT_WORDS; i++) begin\n"
                     "        tb_tb_addr[i] = tb_init_addr[i];\n"
                     "        tb_tb_addr[INIT_WORDS+i] = tb_init_addr[i];\n"
                     "        tb_tb_wdata[i] = tb_init_data[i];\n"
                     "        tb_exp_tb_rdata[INIT_WORDS+1+i] = tb_init_data[i];\n"
                     "    end\n"
                     "    for (integer i = 0; i < FINAL_WORDS; i++) begin\n"
                     "        tb_tb_addr[FINAL_READ_BEGIN+i] = tb_final_addr[i];\n"
                     "        tb_exp_tb_rdata[FINAL_READ_BEGIN+1+i] = tb_final_data[i];\n"
                     "    end\nend\n")


def generate(source_run, output_dir=None, header_path=None):
    source = load_data(source_run, allowed_sample_ids=SUPPORTED_SAMPLE_IDS)
    stim, expected, masks, timing = build_vectors(source)
    arrays = control.all_arrays(stim, expected, masks)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out = Path(output_dir).resolve() if output_dir else PROJECT / "07_runs" / f"mlp_top_golden_{stamp}"
    header = Path(header_path).resolve() if header_path else PROJECT / "05_tb/controller" / HEADER_NAME
    control.require(not out.exists(), f"Output exists: {out}")
    control.require(not source["directory"].is_relative_to(out) and
                    not header.is_relative_to(source["directory"]) and not header.is_relative_to(out),
                    "Output/header must not overwrite source or run archive")
    (out / "vectors").mkdir(parents=True)
    saved_header = out / "vectors" / HEADER_NAME
    write_header(saved_header, arrays, timing, out.name, source)
    npz = out / "vectors/mlp_top_vectors.npz"
    np.savez_compressed(npz, **arrays)
    with np.load(npz, allow_pickle=False) as restored:
        control.require(set(restored.files) == set(arrays) and
                        all(np.array_equal(restored[name], value) for name, value in arrays.items()),
                        "Saved vector NPZ readback differs")
    (out / "source_manifest.json").write_bytes(source["manifest_bytes"])
    snapshots = out / "source_snapshot"
    snapshots.mkdir()
    source_paths = [Path(__file__), Path(control.__file__), PROJECT / "00_docs/mac_input_pipeline.md",
                    PROJECT / "00_docs/modules/mlp_top.md",
                    PROJECT / "00_docs/verification/mlp_top.md"]
    source_hashes = {}
    for path in source_paths:
        relative = path.relative_to(PROJECT)
        target = snapshots / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        source_hashes[relative.as_posix()] = control.sha256(path)
    manifest = {"kind": "mlp_top_golden", "format_version": 1, "sample_id": source["sample_id"],
                "prediction": source["prediction"], "source_run": control.display_path(source["directory"]),
                "source_manifest_sha256": source["manifest_sha256"], "source_npz_sha256": source["npz_sha256"],
                "checkpoint_sha256": source["manifest"]["checkpoint_sha256"],
                "input_pixels_sha256": source["manifest"]["input_pixels_sha256"],
                "git": control.git_provenance(), "timing": timing, "inputs": INPUTS, "outputs": OUTPUTS,
                "quantization": source["manifest"]["config"], "source_sha256": source_hashes,
                "seed": None, "random_used": False, "fallback_random_seed": 42,
                "mask": "one bit per signal; 1=compare, 0=exclude",
                "vector_contract": "falling edge: compare expected[k], then drive stimulus[k]",
                "validation": "HEX hashes/layout, NPZ layer chain/final retention, schedule, saved vector roundtrip",
                "versions": {"python": platform.python_version(), "numpy": np.__version__},
                "files_sha256": {p.relative_to(out).as_posix(): control.sha256(p) for p in sorted(out.rglob("*")) if p.is_file()}}
    metrics = {"sample_id": source["sample_id"], "nvec": timing["nvec"], "prediction": source["prediction"],
               "initial_words_written": timing["init_words"], "initial_words_read": timing["init_words"],
               "final_words_read": timing["final_words"], "layer_words_checked": 163,
               "expected_checks": sum(int(mask.sum()) for mask in masks.values()),
               "generation_checks_passed": True, "rtl_verified": False}
    for name, value in (("manifest", manifest), ("metrics", metrics)):
        (out / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# Top golden\n\nSource: `{control.display_path(source['directory'])}`; sample {source['sample_id']}.\n\n"
        f"{timing['nvec']} falling-edge vectors: initialize/read all 117607 words, infer once, "
        "check 163 layer writes, read all final A/B 324 words.\n\n"
        "Arrays use actual saved arithmetic data; timing uses the independent Control schedule. "
        "No checkpoint inference, simulation or waveform capture. Generation PASS does not verify RTL.\n",
        encoding="utf-8")
    header.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=".mlp_top_data_", suffix=".tmp", dir=header.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        shutil.copyfile(saved_header, temporary)
        control.require(control.sha256(temporary) == manifest["files_sha256"][f"vectors/{HEADER_NAME}"],
                        "Published header hash differs")
        temporary.replace(header)
    finally:
        temporary.unlink(missing_ok=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True,
                        help="Existing arithmetic golden run for an approved MNIST test sample (0..9)")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        out = generate(args.source_run, args.output_dir)
    except (OSError, ValueError, KeyError, BadZipFile, EOFError) as error:
        parser.exit(1, f"ERROR: {error}\n")
    print(f"Saved: {out}\nPublished: {PROJECT / '05_tb/controller' / HEADER_NAME}")
    print("PASS: generation checks (not RTL verification)")


if __name__ == "__main__":
    main()
