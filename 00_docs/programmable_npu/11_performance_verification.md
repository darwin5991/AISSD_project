# Additional real-model performance verification

2026-11-26. **Test 1: PASS (actual XSim).** Anchor `7a8d7fc31ac6e1f293ae924fbf65f0555e688242`; branch `npu-v2/20261125`. Existing RTL, ISA, CSR, reference arithmetic, model and datasets unchanged.

## Conditions and method

Original 784?512?128?10 MLP, MNIST test IDs 0?4, baseline signed INT8 normalization/quantization. One program, one reset/start/END; W0?W3 and bias loaded once and reused for all five images. Five image bodies are explicitly emitted within this small program; the separate repeated-load helper uses a five-iteration loop. All FC1/FC2/FC3 outputs (including FC3 padding) and ARGMAX are saved.

Every target instruction has all operands and CSRs prepared before `TSTART; LOAD/STORE/EXEC GEMM; TSTOP; CSRR x4,PERF_COUNT`. A following `SW x4,...` writes the snapshot outside the interval. x4 is CSR/snapshot scratch; x1 is safe address scratch after each operation; x5/x6 retain input/result pointers. No internal DUT probes or forced signals. Timer slots are disjoint from inference results and initialized with A5A5A5A5.

The unchanged external DMEM model requires exactly one write to every dumped word. The inference simulation dumps 820 result words plus 40 timer words: 5 initial bank snapshots + 5?7 image snapshots. `combined_raw.hex` preserves the original contiguous dump; `results.hex` and `timers.hex` are lossless slices for comparison. The helper checks 25 independently recorded timer words. No missing/duplicate timer or inference result writes occurred.

Timer counts armed DMA or GEMM active cycles, including prep/drain, and excludes instruction fetch/decode, scalar work, CSR setup, IC overhead, ARGMAX, and TSTART/TSTOP instruction execution. These are engine times, not complete program latency.

## Independent cycle derivation

`C_DMA = B/4 + 2`: the controller issues L word reads and drains the response/write pipeline by two cycles (`04_rtl/controller/dma_controller.sv`). `C_GEMM = G?Q + G + 6`, with Q=K/4, G=ceil(N/4): PREP1 + GQ reads + (G?1) group bubbles + drain6 (`gemm_controller.sv`, architecture ?GEMM). `perf_timer.sv` samples active at each rising edge. Expected values were sealed into the manifest before simulation; no expectation was fitted to observations. Existing DMA smoke reports 6/10 cycles for paired one/three-word transfers; GEMM smoke reports 12/14/9 for its three small configurations.

## Bank LOAD measurements

| Operation | Bytes | Expected | Initial | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Min | Max | Mean | Population SD | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| W0 LOAD | 117120 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 0 | PASS |
| W1 LOAD | 117120 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 0 | PASS |
| W2 LOAD | 117120 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 0 | PASS |
| W3 LOAD | 117120 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 29282 | 0 | PASS |
| Bias LOAD | 652 | 165 | 165 | 165 | 165 | 165 | 165 | 165 | 165 | 165 | 165 | 0 | PASS |

Bank words: 29280 each; bias words:163. Initial model load total **117293 cycles = 1.17293 ms at 100 MHz**. Each of the five helper iterations matches the initial load set.

## Image measurements

| Operation | Expected | ID 0 | ID 1 | ID 2 | ID 3 | ID 4 | Min | Max | Mean | Population SD | Time at 100 MHz (?s) | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Input LOAD | 198 | 198 | 198 | 198 | 198 | 198 | 198 | 198 | 198 | 0 | 1.98 | PASS |
| FC1 GEMM | 25222 | 25222 | 25222 | 25222 | 25222 | 25222 | 25222 | 25222 | 25222 | 0 | 252.22 | PASS |
| FC1 STORE | 130 | 130 | 130 | 130 | 130 | 130 | 130 | 130 | 130 | 0 | 1.30 | PASS |
| FC2 GEMM | 4134 | 4134 | 4134 | 4134 | 4134 | 4134 | 4134 | 4134 | 4134 | 0 | 41.34 | PASS |
| FC2 STORE | 34 | 34 | 34 | 34 | 34 | 34 | 34 | 34 | 34 | 0 | 0.34 | PASS |
| FC3 GEMM | 105 | 105 | 105 | 105 | 105 | 105 | 105 | 105 | 105 | 0 | 1.05 | PASS |
| FC3 STORE | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 0 | 0.05 | PASS |

Input LOAD:784 B/196 words. Stores: FC1 512 B/128 words; FC2 128 B/32 words; FC3 **12 B/3 words**, including two zero padding bytes. Every measured delta from theory is zero. Observed cycles are identical across these five distinct images; fixed controller schedules support data-independent latency for these dimensions, although five images alone are not exhaustive evidence for every input.

| Scope | GEMM cycles | DMA cycles | DMA+GEMM cycles | Time at 100 MHz |
|---|---:|---:|---:|---:|
| Measured per image, with intermediate stores | 29461 | 367 | 29828 | 0.29828 ms |
| Measured five-image sum, excluding model load | 147305 | 1835 | 149140 | 1.49140 ms |
| Measured five images including initial model load | 147305 | 119128 | 266433 | 2.66433 ms |
| Ordinary argmax-only per image, theoretical | 29461 | 198 | 29659 | 0.29659 ms |
| Ordinary five images + initial load, theoretical | 147305 | 118283 | 265588 | 2.65588 ms |

Ordinary inference removes 169 intermediate STORE cycles/image. ARGMAX and scalar SW are outside the timer; these estimates exclude their execution and all IC overhead. The argmax-only mode was not separately timer-measured. The repeated-load helper measures 586465 total active cycles across five model load sets, separate from the normal program.

## MAC utilization

Sixteen logical INT8 multipliers execute each read cycle. Useful utilization = K?N/(16?measured GEMM cycles). Padding efficiency = useful/padded multiplies; schedule efficiency = padded ideal/measured cycles. Overhead includes PREP, bubbles and drain.

| Layer | K,N | Useful multiplies | Padded multiplies | Ideal useful cycles | Ideal padded cycles | Measured cycles | Useful utilization | Padding efficiency | Schedule efficiency | Overhead cycles |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fc1 | 784,512 | 401408 | 401408 | 25088 | 25088 | 25222 | 99.4687% | 100.0000% | 99.4687% | 134 |
| fc2 | 512,128 | 65536 | 65536 | 4096 | 4096 | 4134 | 99.0808% | 100.0000% | 99.0808% | 38 |
| fc3 | 128,10 | 1280 | 1536 | 80 | 96 | 105 | 76.1905% | 83.3333% | 91.4286% | 9 |

FC1 overhead:1+127+6=134; FC2:1+31+6=38; FC3:1+2+6=9. FC3 padding adds256 non-useful multiplies (16 ideal cycles); its 83.3333% padding efficiency and 91.4286% schedule efficiency multiply to76.1905% useful utilization. Logical multiplier count does not imply DSP mapping; the existing OOC reports are unchanged.

## Correctness and evidence

FC1 2560/2560 bytes, FC2 640/640 bytes, FC3 60/60 bytes including10 padding bytes, ARGMAX5/5 full uint32 values: **zero mismatches**. All 820 result words equal original V5 byte-for-byte (SHA256 `95ca4b970789c13398af7d82a7a2072b5a673cdc845f19bd5f2bf750cbc25d07`). All independent reference arrays also equal the original V5 arrays. No arithmetic/reference correction or diagnostic rerun was needed.

Executed from repository root:

```powershell
conda run --no-capture-output -n aissd python 90_scripts/npu/additional_verification.py performance --build 99_build/npu_model_8cf69d59 --timeout 1200
```

- Inference run: `07_runs/npu/performance_5_20261126_014729_3fbbfc`; simulator invocation wall time **9.352037 s**.
- Repeated-load run: `07_runs/npu/performance_weight_repeat_5_20261126_014739_7b8753`; simulator invocation wall time **4.714643 s**.
- These wall times include the native tool launcher/startup/dump and are distinct from the 100 MHz active-cycle estimates.
- Both raw run directories preserve scenario, manifest, assembly, IMEM/DMEM HEX, quantized/reference NPZ, original combined output, comparison, tool/source hashes, simulator logs and execution records. `measurement` in manifest explicitly enables supplemental instrumentation; the baseline scenario contract and bulk generator remain unchanged.
- Launcher log: `99_build/additional_20261126/performance.log`; exact native command/exit JSON and simulator logs: `99_build/npu_model_8cf69d59/simulate_performance*.log*`.
- Compact evidence: `evidence/additional_20261126/performance_per_image.csv`, `weight_load_per_run.csv`, `performance_analysis.json`.

Snapshot reuse verified every one of42 RTL/TB source hashes. Existing model SHA256 remains `aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd`; dataset hashes equal original V5. Builds/waves/synthesis/implementation/power were not regenerated. No RTL, ISA, CSR, baseline scripts or saved prior results changed.
