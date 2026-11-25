# MNIST 1000 ARGMAX verification

**PASS - actual XSim inference on all 1000 samples.** 2026-11-26, branch `npu-v2/20261125`. The earlier 10000-image run remains cancelled and its artifacts are preserved. This report covers only test IDs 0..999, not the entire 10000-image dataset.

## Run conditions

Original checkpoint/quantization, 784 -> 512 -> 128 -> 10 MLP. One program loads W0-W3 and bias once, then loops over 1000 images sequentially, with one reset, one accepted Start pulse and one END. Only ARGMAX uint32 results are stored in external DMEM. No FC1/FC2/FC3 output STORE, TSTART/TSTOP or waveform generation. No RTL, ISA, CSR, reference arithmetic or model/data changes.

The new dedicated `tb_npu_argmax_progress.sv` observes only external DMEM writes, checks their sequential result addresses and emits completed/total every 25 results. Its sidecar log is written/closed at each update so progress is readable while XSim is running. Progress reports completed result writes, not completed Python comparisons. The two original external memory models and all 39 RTL sources are unchanged; the original top TB is also unchanged. This dedicated TB uses a single Start pulse and verifies END/busy/halt controls. The external DMEM model still requires every result word be written exactly once.

A five-image actual precheck passed before the 1000-image run. Its interval tail (0 then 5) tests the final partial progress interval, and the main run tests all 40 full intervals. This precheck does not substitute for any of the 1000 requested inferences.

| Capacity/check | Actual |
|---|---:|
| IMEM words / capacity | 90 /16384 |
| DMEM initialized bytes / capacity | 1257132 /16777216 |
| Watchdog cycles | 50200000 |
| Wall timeout seconds | 3600 |
| Result byte range | 0x10131F0C through 0x10132EAB |
| Result words | 1000 |
| Progress sidecar records (including 0) | 41 |

Environment: Windows 11, existing Conda `aissd` (Python3.11.16, NumPy2.4.6, PyTorch2.11.0+cu128), native XSim 2025.2. Original checkpoint SHA256 `aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd`; dataset hashes match the prior V5 package and are preserved in manifest/integrity evidence. Existing normalization `(pixel/255-0.1307)/0.3081`, signed INT8 formats, shifts, ReLU and saturation remain unchanged.

## Python comparison

The unchanged independent NumPy INT8 Reference consumes the same immutable quantized inputs/parameters; it does not use packed addresses, generated instructions or DUT outputs. The unchanged strict comparator checks the actual external DMEM dump against Reference, using full uint32 ARGMAX values and no masks/tolerances.

| Model | Correct | Incorrect | Total | Accuracy |
|---|---:|---:|---:|---:|
| Python INT8 Reference | 991 | 9 | 1000 | 99.10% |
| RTL NPU | 991 | 9 | 1000 | 99.10% |

**ARGMAX match: 1000/1000 (100%), mismatches: 0.** No missing results, duplicate writes, invalid-format/X/Z values or out-of-range indices. IDs are exactly0..999, ordered and unique. All dump words were externally written exactly once; the monitor additionally checks output order. No diagnostic rerun, expected-value edit or RTL repair was needed. Python FP32 was not rerun for this scoped INT8/RTL implementation comparison; the cancelled 10000-run FP32 data remains separate.

## Actual commands and timing

Executed from repository root:

```powershell
conda run --no-capture-output -n aissd python 90_scripts/npu/run_argmax_progress.py --count 5 --timeout 1200
conda run --no-capture-output -n aissd python 90_scripts/npu/run_argmax_progress.py --count 1000 --build 99_build/npu_argmax_progress_dda93806 --timeout 3600
```

For a fresh build, omit `--build`. The driver uses the existing generator, runner and comparator. A reused snapshot must pass every source-hash check before simulation.

Actual main XSim invocation wall time: **656.739618 s (10.946 min)**. Driver generation/simulation/comparison time: **657.547834 s**. These are software runtime measurements. Timer is disabled; no per-image PERF_COUNT timing was measured. Theoretical 100 MHz DMA+GEMM active-engine sum, using Test1-verified dimensions, is 117293 + 1000*(29461+198) = 29776293 cycles =0.29776293 s; this excludes IC/scalar/ARGMAX execution and is not total hardware program latency.

## Evidence and integrity

- Raw run: `07_runs/npu/mnist_1000_argmax_progress_20261126_020901_8b1df2`.
- Live/completed progress: run `output/results.hex.progress` (0,25,...,1000).
- Actual output: run `output/results.hex`; Python arrays: `reference.npz`; per-image comparison: `predictions.csv`; strict comparison: `comparison.json`; final summary: `verification_summary.json`.
- Actual ASM/IMEM/DMEM, scenario, manifest, quantized parameters, simulator source hashes, execution plan and logs are preserved in the same unique ignored run directory.
- Launcher log: `99_build/additional_20261126/mnist_1000.log`; native tool args/exit JSON: build `simulate_mnist_1000_argmax_progress_20261126_020901_8b1df2.log.command.json`.
- Five-image precheck: `07_runs/npu/mnist_5_argmax_progress_20261126_020827_5f2366`; launcher `99_build/additional_20261126/progress_tb_5.log`.
- Compact committed evidence: `evidence/additional_20261126/mnist_1000_predictions.csv`, `mnist_1000_summary.json`, `mnist_1000_integrity.json`. Summary hashes refer to the original raw-run files.
- Final audit/report command: `conda run --no-capture-output -n aissd python 99_build/additional_20261126/finish_1000.py`; log `99_build/additional_20261126/integrity_1000.log`.

Integrity checks reassemble the program to exact IMEM, verify immutable input/reference/program hashes, native exit 0/NPU_EXTERNAL_PASS, all 1000 outputs and 41 progress records, original checkpoint/IDX hashes, all 42 compiled source hashes, all 39 routed RTL hashes, and unchanged original tracked RTL/TB/model/software/run files against 7a8d7fc. Main remains 2e89b8e994982094a36172a3fd2f65d4a9edaff7. Only new TB/driver/evidence and documentation records are added. No synthesis, implementation, power analysis or push. Earlier uncommitted documentation corrections and the stopped 10000-run records are preserved.
