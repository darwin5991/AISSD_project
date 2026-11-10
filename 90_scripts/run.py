"""Compile and simulate one selected module/TB using pre-generated test data.

    python project/90_scripts/run.py --list
    python project/90_scripts/run.py control_unit
    python project/90_scripts/run.py tb_control_unit

Uses Python's standard library. Never generates golden data or records waves.
Exit codes: 0=verified PASS, 1=RTL/tester FAIL, 2=preparation/tool error.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


PROJECT = Path(__file__).resolve().parents[1]
TARGETS_FILE = Path("90_scripts/sim_targets.json")
SUMMARY = re.compile(
    r"^\[SUMMARY\] module=(\w+) result=(PASS|FAIL) "
    r"vectors=(\d+)/(\d+) checks=(\d+) masked=(\d+) errors=(\d+)"
    r"(?: time=(\d+) ns)?\s*$", re.MULTILINE,
)
ERROR_LINE = re.compile(r"^(?:\[FAIL\]|\[MISMATCH\]|ERROR:|FATAL_ERROR:|Fatal:|FATAL:)", re.MULTILINE)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_targets(project=PROJECT):
    targets = json.loads((Path(project) / TARGETS_FILE).read_text(encoding="utf-8"))
    if not isinstance(targets, dict) or not targets:
        raise ValueError("No simulation targets configured")
    aliases = set()
    for name, target in targets.items():
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"Invalid target name: {name}")
        for field in ("module", "tb"):
            if not re.fullmatch(r"[A-Za-z_]\w*", target[field]):
                raise ValueError(f"Invalid {field} name for {name}")
        names = {name, target["module"], target["tb"]}
        if aliases & names:
            raise ValueError(f"Ambiguous module/TB alias: {name}")
        aliases.update(names)
        target["name"] = name
    return targets


def select_target(targets, name):
    for key, target in targets.items():
        if name in (key, target["module"], target["tb"]):
            return target
    raise ValueError(f"Unknown module/TB: {name}; use --list")


def source_files(project, target):
    project = Path(project).resolve()
    sources = []
    for pattern in target["sources"]:
        matches = sorted(project.glob(pattern))
        if not matches:
            raise FileNotFoundError(f"Missing source for {target['name']}: {pattern}")
        for path in matches:
            if not path.resolve().is_relative_to(project) or not path.is_file():
                raise ValueError(f"Invalid source path: {path}")
            relative = path.relative_to(project)
            if relative not in sources:
                sources.append(relative)
    if not sources:
        raise ValueError("Target has no source files")
    return sources


def validate_sample_id(sample_id, target):
    """Top may opt into samples 0..9; all standalone targets stay at sample 0."""
    allowed = target.get("sample_ids", [0])
    if (not isinstance(allowed, list) or not allowed or
            any(type(value) is not int or not 0 <= value <= 9 for value in allowed) or
            len(set(allowed)) != len(allowed)):
        raise ValueError("Unsupported target sample-ID policy")
    if target.get("module") != "mlp_top" and allowed != [0]:
        raise ValueError("Standalone targets support only sample 0")
    if type(sample_id) is not int or sample_id not in allowed:
        raise ValueError(f"Unsupported sample ID {sample_id} for {target.get('module')}; allowed IDs: {allowed}")


def prepare_data(project, target, data_run=None):
    """Resolve the header's named run, not the latest run; validate its bytes."""
    project = Path(project)
    header_relative = Path(target["header"])
    header = project / header_relative
    if not header.resolve().is_relative_to(project.resolve()):
        raise ValueError("TB header must be inside the project")
    prefix = header.read_text(encoding="utf-8")
    named_run = re.search(r"^// Run: (.+)$", prefix, re.MULTILINE)
    if not named_run:
        raise ValueError("Header has no generation run ID; manually generate the selected module's data")
    run_id = named_run[1].strip()
    if run_id in (".", "..") or any(c in run_id for c in "/\\"):
        raise ValueError("Invalid header run ID")
    directory = Path(data_run).resolve() if data_run else project / "07_runs" / run_id
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if directory.name != run_id or manifest.get("kind") != target["data_kind"]:
        raise ValueError("Header and selected module's data manifest refer to different runs")
    validate_sample_id(manifest.get("sample_id"), target)
    digest = sha256(header)
    archive_key = target.get("header_archive", f"vectors/{header_relative.name}")
    if manifest["files_sha256"].get(archive_key) != digest:
        raise ValueError("TB header SHA-256 differs from its generation manifest")
    timing = manifest["timing"]
    metadata = {
        "SAMPLE_ID": manifest["sample_id"], "NVEC": timing["nvec"],
        "CLOCK_PERIOD_NS": timing["clock_period_ns"], "RESET_CYCLES": timing["reset_cycles"],
        "EXPECTED_CYCLES": timing["expected_cycles"], "TIMEOUT_CYCLES": timing["timeout_cycles"],
        "TIME_UNIT_NS": 1, "TIME_PRECISION_PS": 1,
    }
    for header_name, timing_name in (("START_WAIT_CYCLES", "start_wait_cycles"),
                                     ("FIRST_VECTOR_CYCLE", "first_vector_cycle")):
        if timing_name in timing:
            metadata[header_name] = timing[timing_name]
    if "prediction" in manifest:
        metadata["EXPECTED_PREDICTION"] = manifest["prediction"]
    if target.get("format_parameter"):
        metadata[target["format_parameter"]] = manifest["format_version"]
    for key, value in metadata.items():
        match = re.search(rf"^localparam integer {re.escape(key)} = (\d+);$", prefix, re.MULTILINE)
        if type(value) is not int or not match or int(match[1]) != value:
            raise ValueError(f"Header/manifest configuration mismatch: {key}")
    for key, value in target.get("expected_parameters", {}).items():
        match = re.search(rf"^localparam integer {re.escape(key)} = (-?\d+);$", prefix, re.MULTILINE)
        if type(value) is not int or not match or int(match[1]) != value:
            raise ValueError(f"Unsupported {target['name']} parameter: {key}; "
                             "manually regenerate this target's data for the current specification")
    if (manifest["format_version"] != 1
            or timing["nvec"] <= 0 or timing["clock_period_ns"] != 10
            or timing["reset_cycles"] != 3 or timing["expected_cycles"] <= 0
            or timing["timeout_cycles"] != timing["expected_cycles"] + 100
            or not manifest["outputs"]):
        raise ValueError("Unsupported simulation data configuration")
    if "output_count" in target and len(manifest["outputs"]) != target["output_count"]:
        raise ValueError("Manifest output count differs from the selected target")
    source_files(project, target)
    return directory, manifest_path, manifest, digest


def find_tools(vivado_bin=None):
    tools = {}
    for name in ("xvlog", "xelab", "xsim"):
        if vivado_bin:
            path = Path(vivado_bin) / (name + (".bat" if os.name == "nt" else ""))
        else:
            found = shutil.which(name)
            path = Path(found) if found else None
        if path is None or not path.is_file():
            raise FileNotFoundError(f"{name} not found; use --vivado-bin <Vivado/bin>")
        tools[name] = path.resolve()
    return tools


def write_options(path, arguments):
    # Options files avoid cmd.exe reparsing source paths or '=' in arguments.
    def quote(value):
        value = str(value).replace("\\", "/")
        if any(c in value for c in '\n\r"'):
            raise ValueError("Invalid simulator argument")
        return f'"{value}"' if any(c.isspace() for c in value) else value
    Path(path).write_text("\n".join(quote(arg) for arg in arguments) + "\n", encoding="utf-8")


def stop_process(process):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        process.kill()
    process.wait()


def run_stage(name, tool, arguments, build, logs, timeout, stages):
    options = build / f"{name}.args"
    write_options(options, arguments)
    command = [str(tool), "-f", options.name]
    log = logs / f"{name}.log"
    record = {"stage": name, "command": command, "arguments": list(map(str, arguments)),
              "cwd": str(build), "log": str(log), "return_code": None}
    stages.append(record)
    start = time.monotonic()
    print(f"[{name.upper()}]", flush=True)
    try:
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(command, cwd=build, stdout=stream, stderr=subprocess.STDOUT)
            try:
                record["return_code"] = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                stop_process(process)
                record["terminated"] = True
                raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - start, 3)
    text = log.read_text(encoding="utf-8", errors="replace")
    version = re.search(r"(?:Vivado Simulator v|xsim v)([\w.]+)", text)
    if version:
        record["version"] = version[1]
    return record["return_code"], text


def judge_simulation(text, return_code, timing, output_count, module):
    """Do not accept xsim's zero exit code as evidence of verification."""
    matches = list(SUMMARY.finditer(text))
    if len(matches) != 1:
        return False, "missing or duplicate tester summary", None
    match = matches[0]
    actual_module, result, completed, total, checks, masked, errors, ended = match.groups()
    values = dict(zip(("vectors_checked", "vectors", "checks", "masked", "errors"),
                      map(int, (completed, total, checks, masked, errors))))
    if ended is not None:
        values["simulation_time_ns"] = int(ended)
    if actual_module != module:
        return False, f"tester summary is for {actual_module}, expected {module}", values
    if result != "PASS" or ERROR_LINE.search(text):
        return False, "tester reported a failure", values
    if return_code != 0:
        return False, f"xsim returned {return_code}", values
    if (int(completed) != timing["nvec"] or int(total) != timing["nvec"]
            or int(checks) <= 0 or int(errors) != 0
            or int(checks) + int(masked) != timing["nvec"] * output_count
            or ended is None or int(ended) != timing["expected_cycles"] * timing["clock_period_ns"]):
        return False, "incomplete or inconsistent verification counts/time", values
    return True, "all scheduled output comparisons completed", values


def git_state(project):
    try:
        def git(*args):
            return subprocess.run(["git", *args], cwd=project, capture_output=True,
                                  text=True, check=True).stdout.strip()
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def verification_result(target, passed):
    """A modeled simulation PASS cannot establish all-module RTL correctness."""
    modeled = target.get("modeled_modules", [])
    scope = target.get("verification_scope", "module_rtl")
    return {"simulation_passed": passed, "rtl_verified": passed and not modeled,
            "verification_scope": scope, "modeled_modules": modeled,
            "top_with_models_verified": passed and scope == "top_with_behavioral_models"}


def run(args):
    target = args.target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    run_id = f"{target['name']}_xsim_{stamp}"
    out, build = PROJECT / "07_runs" / run_id, PROJECT / "99_build" / run_id
    provenance = git_state(PROJECT)
    out.mkdir(parents=True, exist_ok=False)
    logs = out / "logs"
    logs.mkdir()
    build.mkdir(parents=True, exist_ok=False)
    record = {"kind": "xsim", "module": target["module"], "tb": target["tb"],
              "target": target, "run_id": run_id,
              "created_utc": datetime.now(timezone.utc).isoformat(), "git": provenance,
              "python": sys.version, "waveform_recording": False, "automatic_generation": False,
              "build_dir": str(build), "stages": []}
    metrics = {"status": "ERROR", "reason": "execution did not complete",
               **verification_result(target, False)}
    exit_code = 2
    print(f"[RUN] {out}", flush=True)
    print(f"[SCOPE] {metrics['verification_scope']}; modeled={','.join(metrics['modeled_modules']) or 'none'}", flush=True)
    try:
        directory, data_manifest, data, header_hash = prepare_data(PROJECT, target, args.data_run)
        record["sample_id"] = data["sample_id"]
        metrics["sample_id"] = data["sample_id"]
        tools = find_tools(args.vivado_bin)
        record.update(data_run=str(directory), data_manifest_sha256=sha256(data_manifest),
                      header_sha256=header_hash, source_run=data.get("source_run"),
                      source_npz_sha256=data.get("source_npz_sha256"), timing=data["timing"],
                      tools={key: str(value) for key, value in tools.items()})
        shutil.copyfile(data_manifest, out / "data_manifest.json")
        snapshot = out / "source_snapshot"
        hashes = {}
        sources = source_files(PROJECT, target)
        header = Path(target["header"])
        for relative in (*sources, header, Path("90_scripts/run.py"), TARGETS_FILE):
            copied = snapshot / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, copied)
            hashes[relative.as_posix()] = sha256(copied)
        if hashes[header.as_posix()] != header_hash:
            raise ValueError("Header changed during preparation; rerun after generation completes")
        record["source_sha256"] = hashes
        include_dirs = {header.parent, *(path.parent for path in sources)}
        compile_args = ["-sv"]
        for directory in sorted(include_dirs):
            compile_args.extend(["-i", (snapshot / directory).as_posix()])
        compile_args.extend([*((snapshot / path).as_posix() for path in sources), "-log", "xvlog.log"])
        snapshot_name = f"{target['tb']}_sim"
        elab_args = [f"work.{target['tb']}", "-s", snapshot_name, "-debug", "off",
                     "-timescale", "1ns/1ps", "-log", "xelab.log"]
        sim_args = [snapshot_name, "-R", "-onerror", "quit", "-onfinish", "quit", "-log", "xsim.log"]
        for name, tool_name, arguments in (("compile", "xvlog", compile_args),
                                           ("elaborate", "xelab", elab_args),
                                           ("simulate", "xsim", sim_args)):
            code, text = run_stage(name, tools[tool_name], arguments, build, logs,
                                   args.wall_timeout, record["stages"])
            if name != "simulate":
                if code != 0 or ERROR_LINE.search(text):
                    print("\n".join(text.splitlines()[-12:]), flush=True)
                    raise ValueError(f"{name} failed; see logs/{name}.log")
                continue
            for line in text.splitlines():
                if line.startswith(("[INFO]", "[MISMATCH]", "[FAIL]", "[SUMMARY]", "Fatal:")):
                    print(line, flush=True)
            passed, reason, counts = judge_simulation(text, code, data["timing"], len(data["outputs"]), target["module"])
            metrics.update(status="PASS" if passed else "FAIL", reason=reason,
                           tester=counts, **verification_result(target, passed))
            exit_code = 0 if passed else 1
    except KeyboardInterrupt:
        metrics["reason"] = "interrupted by user"
        exit_code = 130
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        metrics["reason"] = str(error)
    finally:
        record["result"] = metrics["status"]
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_json(out / "manifest.json", record)
        save_json(out / "metrics.json", metrics)
        (out / "README.md").write_text(
            f"# {target['name']} xsim\n\nTB: `{target['tb']}`. Result: **{metrics['status']}**. {metrics['reason']}\n\n"
            f"Scope: `{metrics['verification_scope']}`. Modeled modules: {', '.join(metrics['modeled_modules']) or 'none'}. "
            f"Full selected-module RTL verified: {metrics['rtl_verified']}.\n\n"
            f"Sample ID: {metrics.get('sample_id', 'unavailable')}.\n\n"
            "- manifest.json: source/data hashes, tools, commands and stage exit codes.\n"
            "- metrics.json: final verdict and tester comparison counts.\n"
            "- logs/: complete compile, elaboration and simulation text output.\n"
            "- source_snapshot/: the exact source and header compiled for this run.\n"
            f"- Build directory: `{build}`.\n\n"
            "No golden generation or waveform recording was performed.\n", encoding="utf-8")
        print(f"[RESULT] {metrics['status']}: {metrics['reason']}", flush=True)
        print(f"[LOGS] {logs}", flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="Module name or TB name (one target per invocation)")
    parser.add_argument("--list", action="store_true", help="List configured modules/TBs without running tools")
    parser.add_argument("--vivado-bin", type=Path, help="Vivado bin directory; default: search PATH")
    parser.add_argument("--data-run", type=Path, help="Generation run matching the fixed TB header; default: header's run ID")
    parser.add_argument("--wall-timeout", type=float, default=300,
                        help="Wall-clock seconds allowed per tool stage (default: 300); TB has its own cycle timeout")
    args = parser.parse_args()
    try:
        targets = load_targets()
        if args.list:
            for name, target in targets.items():
                tb_present = any(re.search(rf"\bmodule\s+{re.escape(target['tb'])}\b", path.read_text(encoding="utf-8"))
                                 for path in (PROJECT / "05_tb").rglob("*.sv"))
                status = "TB present" if tb_present else "TB not written"
                print(f"{name:26} {target['tb']:29} {status}")
            return 0
        if args.target is None:
            parser.error("select one module/TB; use --list to see available names")
        args.target = select_target(targets, args.target)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    if not 0 < args.wall_timeout < float("inf"):
        parser.error("--wall-timeout must be positive and finite")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
