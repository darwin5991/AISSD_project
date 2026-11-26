# Programmable NPU v2 — final execution report

**Status: PASS — M0–M10 completed, 2026-11-25 (Asia/Seoul).**

## 1. Repository, source and environment

- Repository: `D:/Data/Local/Desktop/programing/AISSD/project` (all paths below relative to this root).
- Local branch: `npu-v2/20261125`.
- Baseline/main, unchanged: `2e89b8e994982094a36172a3fd2f65d4a9edaff7`.
- Final code commit: `0a94cce374539e78756e31cb910ab8553370dcc2`. A documentation-only final report commit follows; obtain its SHA with `git rev-parse HEAD`.
- Final RTL commit: `af165948b5ca65fc52ec4f36ccf2a2f32a354052`; no RTL edits after M4. All six functional scenarios and FPGA reports match the same 39 RTL file SHA256 values. Exact map: `99_build/npu_ooc_380ec37d39/source_hashes.json`, independently verified in `99_build/npu_m0/final_integrity.json`.
- M0–M10 local commits retained. No recovery branch, history rewrite, merge, push or network transfer. Phase8 was not merged. Tracked tree was clean at final code handoff; final documentation is committed after diff/review checks. Ignored build/model/data retained. No user files restored or cleanup performed.
- Windows 11; Conda `aissd`, Python 3.11.16 (`C:/Users/darwi/.conda/envs/aissd/python.exe`), NumPy 2.4.6, PyTorch 2.11.0+cu128. No environment/package changes.
- Vivado/XSim 2025.2 build6299465: `D:/AMDDesignTools/2025.2/Vivado/bin`. Native synthesis/implementation licenses actually acquired. Process-local XILINX_LOCAL_USER_DATA=no and APPDATA/TEMP/TMP under each ignored build directory.
- Checkpoint: `03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth`, 1,879,001 bytes; unchanged SHA256 `aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd`.
- Existing test IDX: `D:/Data/Local/Desktop/programing/AISSD/assignment1/data/mnist/MNIST/raw`. No downloads or data writes. Test IDX hashes before/after are in manifests/final_integrity.json. Normalization and quantization reuse baseline LayerViewer/encode, with input F5, W F7, bias F9/F8/F7, outputs F2, arithmetic output shift.
- Decisions/retry evidence: `08_decision_log.md`, `09_progress.md`. Existing preflight evidence reused rather than repeating synthetic license/tool tests.

Implementation: exact nine logical IC states, IF/ID→ID/EX→EX/MEM→MEM/WB registers, x0..x7, ten packed CSRs, 24 real instructions, WB architectural commits and END→HALTED. DMA, GEMM and ARGMAX capture their own parameters and run independently under IC ownership. Seven single-port SRAM banks retain depths/decomposition. New `npu_memory_wrapper` and `dmem_port_mux` replace legacy TB ownership only in the new hierarchy. `npu_top` directly instantiates unchanged unpackers, MAC and accumulator/postprocess; legacy source remains intact. No fault hardware, prefetch, extra arithmetic operator or extra datapath stage.

Python modules under `90_scripts/npu/` separate scenario, loader, independent NumPy integer reference, layout/packing, assembly emitters, assembler, external simulation, comparator and runner. Manifest hashes freeze input/reference/program artifacts. The reference never consumes DUT data or packed SRAM addresses.

## 2. Observed functional results

| Test | Actual result | Status | Evidence |
|---|---|---|---|
| Python foundations | 4/4 methods; 24 independent instruction encodings, LI/labels/packing/wrap/layout; baseline IDs0,1,7 all1956 layer bytes equal | PASS | `99_build/npu_m0/foundations_final.log` |
| Scalar ISA | 19/19 external words; arithmetic/logic/shift/wrap, x0, branches/JAL, LW/SW, CSR widths, halt pulse | PASS | `07_runs/npu/scalar_52cc5fe152` |
| DMA | 24/24 external words; all7 banks, single/multiword, final physical words, exact N+2 per transfer | PASS | `07_runs/npu/dma_9c0e67b2e2` |
| Small GEMM | 8/8 words; K8/12, N1/5/8, signed saturation/ReLU/padding, offsets/both directions, A outputword190 | PASS | `07_runs/npu/gemm_9f3f342382` |
| ARGMAX/timer | 12/12 words; signed/ties/LEN1,5,10; timer retains DMA count, clears at TSTART, excludes ARGMAX/scalar | PASS | `07_runs/npu/argmax_4105a01fb9` |
| Integrated small chain | 14/14 words; DMA→GEMM→STORE→ARGMAX, GEMM timer12/14/9 cycles | PASS | `07_runs/npu/chain_3de93df10a` |
| V1, ID0 | FC1 512/512, FC2 128/128, FC3 12/12 bytes; ARGMAX1/1 | PASS | run A below |
| V5, IDs0..4 | FC1 2560/2560, FC2 640/640, FC3 60/60 bytes; ARGMAX5/5 | PASS | run B |
| V20, IDs0..19 | ARGMAX20/20 | PASS | run C |
| V100, IDs0..99 | ARGMAX100/100 | PASS | run D |
| V200, IDs0..199 | ARGMAX200/200 | PASS | run E |
| V200F, same IDs0..199 | FC3 2400/2400 bytes incl400 zero pad bytes; ARGMAX200/200 | PASS | run F |
| Legacy MAC leaf | 265021/265021 vectors,1325105 checks,0 masked/0 errors | PASS | `07_runs/mac_array_xsim_20261124_174456_858512Z` |
| Legacy accumulator leaf | 265019/265019 vectors/checks,0 masked/0 errors | PASS | `07_runs/accumulator_postprocess_xsim_20261124_174456_858512Z` |
| 1000/10000 inference accuracy | User-run only; not launched | NOT RUN | commands below |

Five integrated smoke programs total77/77 words. Six mandatory model scenarios total6312 layer-byte comparisons and526 full uint32 index comparisons (2104 result words); zero mismatch. These totals include repeated samples across scenarios; there are200 unique mandatory MNIST IDs. FC3 comparison includes all12 physical bytes. Model/reference label matches were1/1,5/5,20/20,100/100,200/200,200/200, informational only; this is not full-test-set accuracy.

Each scenario uses one reset/start/END, one LOAD per weight bank and bias, and an assembly image loop. V20/V100/V200 store ARGMAX only; V200F stores FC3+ARGMAX. Every requested external DMEM result word was written exactly once, starting from A5A5A5A5 sentinel. New TB initializes/dumps only external IMEM/DMEM; no DUT hierarchy probing/forcing/internal SRAM initialization. Output files are dense `output/results.hex`, strictly checked for length/format/X/Z and exact values. No mismatch diagnostics were necessary; automatic failed-ID full-layer generation is implemented. No reference values, masks or timing conditions were adjusted to DUT results.

Timer wrap/sticky-overflow logic was reviewed; no forced internal state or billion-cycle overflow test was run. Old complete legacy controller/top regressions were not run; new external-only tests exercise the replacement controller/top, while both unchanged arithmetic leaves were independently regressed.

Run paths under `07_runs/npu/` (each contains manifest/scenario/reference/quantized/input/output/logs/comparison/summary):

| Run | Directory | reference.npz SHA256 |
|---|---|---|
| A | `mnist_1_fc1_fc2_fc3_argmax_20261125_024139_b33a42` | `66f6813155801caac5c5f216e574ebec9a5269291cc02fdff5a297af3cd5bb60` |
| B | `v5_20261125_024215_8631ca` | `26a0cab640a13594cca8b43f7e4b732d9a6712616ea244a3bfc656d1e8fd1260` |
| C | `v20_20261125_024243_a4c11b` | `49913d2cf7bc16056715ecb91205fdf85494a855f4aa5c7bb066d0c0ad1d8437` |
| D | `v100_20261125_024314_8859ab` | `c72cf4ea0f7bd02bc7b9b50a826b0367125f9ab8ccfd7169735aa28c9535e198` |
| E | `v200_20261125_024439_4aec3b` | `937256752c532ae1367e8276c7140ba64cc9cfd7736b41547833eacd105d4cca` |
| F | `v200f_20261125_024812_6bde90` | `937256752c532ae1367e8276c7140ba64cc9cfd7736b41547833eacd105d4cca` |

Model simulation build `99_build/npu_model_8cf69d59`; every reuse checks exact RTL/TB source hashes. Initial V1 source ad1a68c, then software/report commits only. Complete tool logs and commands are in the build/run directories; launcher logs `99_build/npu_m0/v1.log`, `v5.log`, `v20.log`, `v100.log`, `v200.log`, `v200f.log`. Manifest records git_head plus precommit toolchain/source hashes; final_integrity.json links all evidence, immutable hashes, common weight hashes and routed source identity.

## 3. Actual FPGA implementation and power

Top `npu_top`, `xc7a100tcsg324-1`, OOC,10.000ns npu_clk. External memory/TB excluded. Explicit39 RTL source files; no false/multicycle constraints. Nonproject synthesis with rebuilt hierarchy, opt_design/place_design/phys_opt_design/route_design default directives, maxThreads6; no seed sweep or RTL timing repair.

All FPGA artifacts: `99_build/npu_ooc_380ec37d39/`. Actual synthesis, route and power each exit0 with completion markers; per-tool command/exit JSON and console/Vivado logs retained. Source synthesis anchor e303caa, FPGA scripts committed5086240; power checker path normalization finalized0a94cce. No RTL change during FPGA work.

| Resource | Synth | Routed | Device capacity | Routed utilization |
|---|---:|---:|---:|---:|
| Slice LUT | 5075 | 4910 | 63400 | 7.74% |
| Flip-flop | 2180 | 2180 | 126800 | 1.72% |
| RAMB36E1 | 104 | 104 | 135 | 77.04% |
| RAMB18E1 | 11 | 11 | 270 | 4.07% |
| BRAM tile equivalents | 109.5 | 109.5 | 135 | 81.11% |
| DSP | 0 | 0 | 240 | 0% |
| Distributed RAM LUT | 0 | 0 | 19000 memory-capable LUT | 0% |

Eleven LUT SRLs are metadata/pipeline implementation, not SRAM replacement. All7 SRAM banks remain BRAM with prescribed depths and W area decomposition. Default synthesis maps unchanged8x8 multipliers to LUT logic; no forced DSP policy or arithmetic replacement.

| Timing/routing observation | Actual |
|---|---|
| Post-synth WNS/TNS | +2.058ns /0ns (informational) |
| Post-route setup WNS/TNS | **+0.312ns /0ns**,0/7923 failing endpoints |
| Post-route hold WHS/THS | **+0.145ns /0ns**,0/7923 failing endpoints |
| Pulse-width slack/failures | +4.020ns,0/2421 |
| Missing clocks / unconstrained internal endpoints | 0 /0 |
| Routable / fully routed nets | 7888 /7888 |
| Routing errors | 0 |

Worst setup: `u_gemm/output_shift_reg[4]` through legacy output shift/saturation and bank data mux to A BRAM `DIBDI[0]`; data9.363ns (logic2.666+route6.697),11 logic levels. Worst hold: IC EX/MEM len[26] to DMA remaining[24], data0.258ns. Reports contain20 worst setup and20 hold paths.

Scope: constrained internal paths pass under this OOC clock model. There are66 inputs/101 outputs without I/O delay. HD.CLK_SRC and HD.PARTPIN_LOCS are unset, so parent clock insertion/skew and boundary partial routing are not signed off. Clock period is unchanged; no timing exceptions hide paths. Board pins, external memory timing and asynchronous reset release/recovery/removal need parent/board integration. This is not whole-board timing signoff.

Synthesis/routed DRC each report43 warning entries: CFGBVS-1(1), REQP-1839/1840 async BRAM controls(20 each), CHECK-3(2 default report limits); no error-severity/fatal DRC. Warnings are preserved, not suppressed. Required legacy async reset and reset-retains-memory behavior remain intact; no invented configuration voltage was applied. OOC connectivity coverage warnings and removed unused inferred mux/control bits are retained in logs.

Power was run **last**, after six matching functional gates plus routed setup/hold/resource review. `routed_power.rpt`: total **0.115W**, dynamic0.026W, static0.089W, confidenceMedium, typical commercial, ambient25C/junction25.5C. No VCD/SAIF activity; vectorless/default propagation and enable assumptions, default250LFM/medium heatsink/medium12–15layer thermal model. BRAM dynamic estimate<0.001W illustrates the activity limitation. These are tool estimates, not measured inference/board power or energy; no numeric power acceptance threshold.

Important artifacts:

- `synth.dcp`, `routed.dcp` (routed SHA256 `6dae978d7a12b47d291aba90e776285423252f4077a78d11515ecee9bcb03631`).
- `synth_utilization.rpt`, `synth_utilization_hier.rpt`, `synth_timing_summary.rpt`, `synth_drc.rpt`.
- `routed_utilization.rpt`, `routed_utilization_hier.rpt`, `routed_timing_summary.rpt`, `routed_critical_setup.rpt`, `routed_critical_hold.rpt`, `routed_check_timing.rpt`, `routed_clocks.rpt`, `routed_drc.rpt`, `routed_route_status.rpt`, `routed_gate.json`.
- `routed_power.rpt`, `functional_and_route_pass.json`, `source_hashes.json`, `sources.txt`, stage command JSON/console logs/Vivado logs/journals.
- Compact checksums/status: `99_build/npu_m0/final_integrity.json`; actual read-only audit command `conda run -n aissd python 99_build/npu_m0/audit_final.py`, exit0, `final_audit.log`.

## 4. Reproduction from repository root

These are the actual required scenario commands (V1 used equivalent count/save arguments); adding a unique output directory is automatic. Reuse the recorded build with unchanged source, or omit --build to compile a new unique snapshot.

```powershell
conda run -n aissd python -m unittest discover -s 90_scripts/npu/tests -v
conda run -n aissd python 90_scripts/npu/smoke.py all
conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 1 --save fc1,fc2,fc3,argmax
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v5.json --build 99_build/npu_model_8cf69d59
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v20.json --build 99_build/npu_model_8cf69d59
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v100.json --build 99_build/npu_model_8cf69d59
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200.json --build 99_build/npu_model_8cf69d59
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200f.json --build 99_build/npu_model_8cf69d59
```

The original synth command creates a fresh unique build. The following implement/power commands are the exact executed build paths; to reproduce synthesis afresh, substitute its newly printed directory for later stages. Original evidence should be retained rather than overwritten by rerunning stages in the completed directory.

```powershell
conda run -n aissd python 90_scripts/npu/build_fpga.py synth
conda run -n aissd python 90_scripts/npu/build_fpga.py implement --run 99_build/npu_ooc_380ec37d39
conda run -n aissd python 90_scripts/npu/build_fpga.py power --run 99_build/npu_ooc_380ec37d39 --functional-runs 07_runs/npu/mnist_1_fc1_fc2_fc3_argmax_20261125_024139_b33a42 07_runs/npu/v5_20261125_024215_8631ca 07_runs/npu/v20_20261125_024243_a4c11b 07_runs/npu/v100_20261125_024314_8859ab 07_runs/npu/v200_20261125_024439_4aec3b 07_runs/npu/v200f_20261125_024812_6bde90
```

The Python FPGA wrapper records/executes `vivado.bat -mode batch -source 06_fpga/tcl/build_npu_ooc.tcl ... -tclargs <absolute-root> <absolute-build> <stage>` with repository-local environment. `synth_command.json`, `implement_command.json`, `power_command.json` contain exact absolute command arguments.

User-run large validation and explicit debug selection (prepared, not executed for1k/10k):

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 1000 --save argmax --timeout 3600
conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 10000 --save argmax --timeout 21600
conda run -n aissd python 90_scripts/npu/run_verification.py verify --ids 7,0,19 --save fc1,fc2,fc3,argmax
```

A software-only capacity/loop test allocated10000 image slots and ARGMAX outputs in8,349,132 DMEM bytes, <16MiB, with<128 IMEM words; it did not run10000-image inference or generate accuracy claims. Arbitrary ordered IDs and save selection are supported. Separate generate/assemble/simulate/compare commands, register conventions and module interfaces are documented in `90_scripts/npu/README.md`.

## 5. Repairs, limitations and handoff

Five substantive tooling repairs, zero functional/timing repairs, zero recovery branches. Early XSim launcher failures: unsupported -O option (two attempts), missing default timescale, Windows batch '=' tokenization. Final pre-power failure: path-separator mismatch in provenance dictionary; normalization retained exact39/39 source SHA checks across all six gates. All failing artifacts/logs preserved; no expected data or acceptance conditions changed. Full details and anchor commits are in08/09. No unresolved mandatory gate.

Deferred scope:1000/10000 actual accuracy runs, board/parent-clock/IO/reset-release integration, activity-based inference power and new operators/models beyond the supported loader. No overall Start→Done benchmark was requested/reported. No further optional experiments were launched after passing required gates. Original checkpoint/dataset and legacy datapath source preserved. **No push.**
