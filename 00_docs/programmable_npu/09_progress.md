# Progress — update continuously
## M0 actual preflight / 2026-11-25
- PASS: new branch `npu-v2/20261125` from exact baseline `2e89b8e994982094a36172a3fd2f65d4a9edaff7`; initial tracked worktree clean; user untracked docs/AGENTS/ZIP preserved. No push.
- Read AGENTS, all 00–07, baseline top, pipeline/read scheduler, MAC, accumulator, BRAM, ARGMAX, model/quantization and runner. No normative conflict identified.
- `conda run -n aissd python -c ...` exit 0: Python 3.11.16, NumPy 2.4.6, PyTorch 2.11.0+cu128, strict model load and sample0 label 7. Checkpoint 1879001 bytes SHA256 matches normative hash. Test IDX available via baseline LayerViewer (download not used).
- Evidence `99_build/npu_m0/environment.txt`; prior full tool/license preflight `99_build/preflight_5dd1565c7eba/evidence/report.txt`, git permission report `99_build/git_permission_recheck_fb3b7774df7d/report.txt`. D: free ~926 GiB. Vivado/XSim 2025.2 at D:/AMDDesignTools/2025.2/Vivado/bin, target xc7a100tcsg324-1.
- Implementation files planned: `90_scripts/npu/*`, `04_rtl/isa/*`, new engine files under controller, `npu_memory_wrapper`/DMEM mux, `04_rtl/npu_top.sv`, `05_tb/npu/*`, NPU XDC/Tcl. Commands will be recorded as executed. Next M1. Repairs 0; recovery branches 0.
The document author's original NOT RUN template is superseded by the observed gates below. Chronological evidence follows this table.

| Gate | Status | Commit/source version | Evidence path | Notes |
|---|---|---|---|---|
| M0 preflight | PASS | 2bc8d0b | 99_build/npu_m0/environment.txt | Original preflight reused |
| M1 toolchain foundations | PASS | 87a8b86 | 99_build/npu_m0/m1_tests.log | 4 tests; IDs0,1,7 golden equality |
| M2 scalar IC | PASS | 53dfa24 | 07_runs/npu/scalar_377ea75f5d | 19/19 words |
| M3 SRAM/DMA | PASS | 681be1b | 07_runs/npu/dma_e2a1db6f61 | 24/24 words, N+2 timer |
| M4 GEMM | PASS | af16594 | 07_runs/npu/gemm_913b7c97c7 | 8/8 words, R+6 schedule |
| M5 ARGMAX/timer/smoke | PASS | ad1a68c | 99_build/npu_m0/m5.log | Full top 77/77 words |
| M6 V1 | PASS | fb1aa35 | 07_runs/npu/mnist_1_fc1_fc2_fc3_argmax_20261125_024139_b33a42 | 652 bytes+1 index |
| M7 V5 | PASS | ab7f95d | 07_runs/npu/v5_20261125_024215_8631ca | 3260 bytes+5 indices |
| M7 V20 | PASS | ab7f95d | 07_runs/npu/v20_20261125_024243_a4c11b | 20/20 |
| M7 V100 | PASS | b29c8d0 | 07_runs/npu/v100_20261125_024314_8859ab | 100/100 |
| M7 V200 | PASS | 72f48a1 | 07_runs/npu/v200_20261125_024439_4aec3b | 200/200 |
| M7 V200F | PASS | 72f48a1 | 07_runs/npu/v200f_20261125_024812_6bde90 | 2400 bytes+200 indices |
| M8 synthesis | PASS | e303caa+FPGA hashes | 99_build/npu_ooc_380ec37d39 | Synth WNS2.058ns; BRAM109.5/135 |
| M9 post-route | PASS | 5086240 | 99_build/npu_ooc_380ec37d39/routed_gate.json | WNS0.312ns/WHS0.145ns; route7888/7888 |
| M10 power/report | NOT RUN | — | — | |

## Current checkpoint
- Branch/base: npu-v2/20261125 / 2e89b8e994982094a36172a3fd2f65d4a9edaff7
- Last passing milestone / commit: M9 post-route / see M9 gate commit
- Current action: M10 power and final report
- Retry attempts used / recovery branches used: 4 tool-launch repairs / 0
- Next gate: M10 power/report
- Blockers: none currently

## Log template
Date, gate, source SHA or diff hash, branch, files, exact commands, exit codes, result counts, log paths, issues, next steps. Append failure attempts as well as passes; never replace failing evidence with passing log. Update current checkpoint at each commit.

## M1 foundations PASS / 2026-11-25
- Anchor 2bc8d0b. Added modular scenario, baseline read-only loader, independent NumPy wrap32 reference, SRAM/DMEM layout, operation-based assembly generator and 24-instruction assembler.
- Command `conda run -n aissd python -m unittest discover -s 90_scripts/npu/tests -v`; Python exit 0, 4/4 unittest methods PASS. Evidence `99_build/npu_m0/m1_tests.log` (PowerShell formats unittest stderr but unittest result OK).
- 24 encoding cases plus LI boundaries/label expansion, signed packing/wrap, layout; existing generate_golden.py IDs 0,1,7 all-layer equality 1956 bytes, predicted [7,2,9]. Baseline outputs `99_build/baseline_golden_515a0fa671`, `baseline_golden_51dab8755a`, `baseline_golden_c526978256`.
- Source reviewed for independent reference and expected-value isolation. No model/data changes. Next M2; repairs 0.

## M2 scalar IC PASS / 2026-11-25
- Anchor 87a8b86; exact 9-state IC with IF/ID, ID/EX, EX/MEM, MEM/WB, low-3-bit GPR addressing, packed CSR storage, WB commits, timer. New external-memory-only TB; temporary scalar harness excluded from final synthesis.
- `conda run -n aissd python 90_scripts/npu/smoke.py scalar --build 99_build/npu_scalar_573340c9` exit 0. External DMEM 19/19 words equal; each result written once; END pulse/HALTED/restart ignored verified. Includes scalar arithmetic/logic/shift/wrap, LW/SW, packed CSR truncation/sign, x0, BEQ/BNE and JAL link.
- Evidence `07_runs/npu/scalar_377ea75f5d`, simulator hashes/logs `99_build/npu_scalar_573340c9`, launcher log `99_build/npu_m0/m2_args_repair.log`.
- Preserved tool failures: cf6d25d1 and a4fff9b0 unsupported xelab -O (first repair incorrectly changed argument; second removed unsupported switch); b01feb56 missing default timescale (fixed --timescale 1ns/1ps); scalar_8e0ac731d5 XSim batch '=' tokenization (fixed quoting complete key=value). No RTL result mismatch. Four substantive tool repairs total across three distinct blockers; no recovery branches. Next M3.

## M3 SRAM/DMA PASS / 2026-11-25
- Anchor 53dfa24; new per-bank owner mux, registered DMA read selector, unchanged 7 BRAM instances/depths/area decomposition. DMA RUN/DRAIN response/data/write pipeline, no extra active completion cycle. DMEM scalar/DMA mux.
- `conda run -n aissd python 90_scripts/npu/smoke.py dma` exit 0, external 24/24 words exact. All seven banks; A/B last physical word, W/Bias multiword ending at final physical word; LOAD+STORE timer exactly 2*(N+2) each case. No duplicated/omitted external result writes.
- Evidence `07_runs/npu/dma_e2a1db6f61`; log `99_build/npu_m0/m3.log`; exact source hashes in corresponding `99_build/npu_dma_*/source_hashes.json`. No new failures/repairs; total tool repairs 4, recovery 0. Next M4.

## M4 GEMM PASS / 2026-11-25
- Anchor 681be1b; final structural `npu_top` directly instantiates new IC/DMA/GEMM/ARGMAX/mux/wrapper and unchanged unpackers/MAC/accumulator. GEMM IDLE/PREP/RUN/DRAIN, start-local packed parameters, weight cursor, one group bubble, legacy delay taps 1/5/6 and delayed output group.
- `conda run -n aissd python 90_scripts/npu/smoke.py gemm` exit 0; 8/8 external words exact over K=8/12, N=5/8/1, both ping-pong directions, signed random operands, positive/negative bias shifts, saturation/ReLU, padded lanes, nonzero input/W/bias/output bases. A output word190 exercises full 8-bit path.
- GEMM timer observed through CSRR+SW equals G*Q+G+6 for all three cases (12,14,9). Results through STORE only. Evidence `07_runs/npu/gemm_913b7c97c7`; launcher `99_build/npu_m0/m4.log`. No arithmetic changes or result masks.
- ARGMAX engine wired but NOT YET GATED; M5 next. Repairs unchanged 4; recovery 0.

## M5 integrated smoke PASS / 2026-11-25
- Anchor af16594. `conda run -n aissd python 90_scripts/npu/smoke.py all` exit 0; final full top compiled once, five programs, 77/77 external words exact: scalar19, DMA24, GEMM8, ARGMAX12, chain14.
- `07_runs/npu/scalar_52cc5fe152`, `dma_9c0e67b2e2`, `gemm_9f3f342382`, `argmax_4105a01fb9`, `chain_3de93df10a`. Logs/source hashes under `99_build/npu_all_*`; launcher `99_build/npu_m0/m5.log`.
- ARGMAX signed/ties/length1,5,10, both banks/nonzero offsets, padding ignored; timer retains DMA count across ARGMAX, TSTART clears count, ARGMAX/scalar excluded. DMA→GEMM→STORE→ARGMAX integrated on three small configurations. Timer overflow sticky wrap implemented and reviewed; no forced state/billion-cycle run.
- All new validation uses external top buses and output memory only. Legacy leaf RTL byte-identical to baseline. No new failures; repairs4/recovery0. Next M6 V1 toolchain.

## M6 V1 PASS / 2026-11-25
- Anchor ad1a68c. Complete runner supports separate generate/simulate/compare and combined verify; assembler separate CLI. Immutable quantized/reference/program/input hashes, ordered sample IDs and per-range layout recorded in manifest. Comparator rejects format/unknown/length/hash mismatch and emits first mismatch address/raw/signed details; failed model comparisons automatically generate full-layer diagnostic program for failed original IDs. No observed mismatch.
- Command `conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 1 --save fc1,fc2,fc3,argmax` exit 0. Actual V1: FC1 512/512, FC2 128/128, FC3 12/12 including zero pads, ARGMAX1/1; each output word written once, one reset/start/END. Reference label match1/1.
- Evidence `07_runs/npu/mnist_1_fc1_fc2_fc3_argmax_20261125_024139_b33a42`, log `99_build/npu_m0/v1.log`, exact build/source hashes in run/logs/simulator_sources.json. Test source version RTL af16594 (unchanged through ad1a68c), precommit Python hashes in manifest.
- Committed declarative required scenario configs; generic --count/--ids/--save supports later 1000/10000. Repairs4/recovery0. Next M7 sequential gates.

## M7 V5 and V20 PASS / 2026-11-25
- Source fb1aa35, compiled full RTL source hash verification on reuse `99_build/npu_model_8cf69d59`.
- `conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v5.json --build 99_build/npu_model_8cf69d59`: exit0, FC1 2560/2560, FC2 640/640, FC3 60/60, ARGMAX5/5, zero mismatches. `07_runs/npu/v5_20261125_024215_8631ca`; launcher `99_build/npu_m0/v5.log`.
- Same command with `v20.json`: exit0 ARGMAX20/20, no intermediate stores. `07_runs/npu/v20_20261125_024243_a4c11b`; launcher `99_build/npu_m0/v20.log`.
- One weight-load set and image loop per scenario, all requested result words written once. No RTL changes or new repairs. Next V100/V200/V200F.

## M7 V100 PASS / 2026-11-25
- Source ab7f95d; command `conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v100.json --build 99_build/npu_model_8cf69d59`, exit0. ARGMAX100/100; output write counts exact. Evidence `07_runs/npu/v100_20261125_024314_8859ab`; launcher `99_build/npu_m0/v100.log`. No intermediate FC stores.
- Prepared OOC source/report scripts (not yet run, not gated). Runner watchdog cleanup strengthened to terminate only its owned Windows process tree on timeout and persist per-command args/exit code. Does not change RTL/reference/comparison; next required gate exercises launcher. Next V200. No new repair attempts.

## M7 V200 and legacy datapath PASS / 2026-11-25
- `conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200.json --build 99_build/npu_model_8cf69d59`, exit0, ARGMAX200/200. Source b29c8d0; unchanged RTL. Evidence `07_runs/npu/v200_20261125_024439_4aec3b`, `99_build/npu_m0/v200.log`.
- Legacy leaf regression commands: `conda run -n aissd python 90_scripts/run.py mac_array --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin` and same `accumulator_postprocess`, process-local environment dirs `99_build/npu_legacy_{mac,acc}_env`. Both exit0. MAC265021/265021 vectors,1325105 checks,0 masked/errors; accumulator265019/265019 vectors/checks,0 masked/errors. Artifacts `07_runs/mac_array_xsim_20261124_174456_858512Z`, `07_runs/accumulator_postprocess_xsim_20261124_174456_858512Z`; launcher logs npu_m0/legacy_mac.log,legacy_acc.log. Old complete controller/top regression not run (new external-only gates replace them); all legacy source unchanged.
- Final Python foundations rerun after operand-count validation and future capacity assertion: command same M1, `99_build/npu_m0/foundations_final.log`,4/4 PASS; baseline IDs0,1,7 all-layer equality. 10000-image allocation/program capacity ONLY tested:8349132 bytes, <128 IMEM words; no1000/10000 inference/reference accuracy run. Source additions do not alter any valid encoding.
- No functional failure/diagnostic needed. Total tool repairs4/recovery0. Next V200F.

## M7 V200F PASS / 2026-11-25
- Source72f48a1, unchanged RTL hashes. `conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200f.json --build 99_build/npu_model_8cf69d59` exit0. FC3 2400/2400 bytes including400 padding bytes; ARGMAX200/200; labels200/200 informational. Evidence `07_runs/npu/v200f_20261125_024812_6bde90`, `99_build/npu_m0/v200f.log`; per-tool args/exit0 recorded in build command JSON.
- All mandatory functional gates PASS; no functional/reference mismatch or diagnostic rerun. Final RTL unchanged from af16594. No timing/power claim yet. Next M8 actual synth.

## M8 synthesis PASS / 2026-11-25
- Source e303caa plus exact precommit FPGA driver/Tcl/XDC hashes in `99_build/npu_ooc_380ec37d39/source_hashes.json`. `conda run -n aissd python 90_scripts/npu/build_fpga.py synth` exit0, bare NPU_SYNTH_COMPLETE, actual synth.dcp and all reports produced. Native Vivado2025.2 license acquired.
- Synthesized npu_top, xc7a100tcsg324-1, OOC10ns, no exceptions. LUT5075/63400(8.00%), FF2180/126800(1.72%), RAMB36=104,RAMB18=11=>109.5/135tiles(81.11%); DSP0/240 (unchanged 8x8 multiply maps to LUTs under default synthesis). DistributedRAM0;11 LUT SRLs are pipeline metadata, not SRAM substitution. Hierarchy confirms all BRAM under u_memory; depths/decomposition retained.
- Synthesis timing only: WNS2.058ns/TNS0, WHS0.214ns/THS0;7923 setup/hold endpoints. No_clock0, unconstrained_internal_endpoints0. Boundary no_input_delay66/no_output_delay101; clk HD.CLK_SRC not specified in OOC. NOT a post-route pass.
- Synth DRC43 reported warnings, no errors: CFGBVS-1(1), CHECK-3(2 report limits), REQP-1839/1840(20 each, async reset/control into BRAM). Preserve required legacy async reset and report reset-release/IO scope; no suppressed warnings or invented board voltage. Benign unused inferred BRAM mux bits and EX/MEM wb_sel optimized; no latches.
- Reviewed actual `synth_utilization.rpt`, `synth_utilization_hier.rpt`, `synth_timing_summary.rpt`, `synth_drc.rpt`, `synth_check_timing.rpt`, console. Launcher `99_build/npu_m0/m8.log`; tool command/exit JSON in build. Next M9 opt/place/phys_opt/route; no new repair.

## M9 post-route PASS / 2026-11-25
- Source5086240, same RTL as functional gates (af16594). `conda run -n aissd python 90_scripts/npu/build_fpga.py implement --run 99_build/npu_ooc_380ec37d39` exit0; actual opt_design/place_design/phys_opt_design/route_design, routed.dcp, all reports, bare NPU_ROUTE_TIMING_COMPLETE.
- Routed WNS +0.312ns,TNS0,0/7923 setup endpoints failing; WHS+0.145ns,THS0,0/7923 hold endpoints failing; pulsewidth slack4.020ns,0/2421 failing. `routed_gate.json` also independently queries no negative setup/hold paths. check_timing: no_clock0,unconstrained_internal_endpoints0. 7888/7888 routable nets fully routed; routing errors0 (11111 logical nets,3223 no routing needed).
- Routed LUT4910/63400(7.74%),FF2180/126800(1.72%),RAMB36=104,RAMB18=11=>109.5/135tiles81.11%,DSP0/240. LUT distributedRAM0,SRL11. No resource overflow. Worst setup output_shift_reg[4]→postprocess shift/saturation/mux→A BRAM DIBDI[0],9.363ns data(2.666logic+6.697route),11 logic levels. No RTL optimization/recovery/re-run necessary; first route passed.
- Reports `99_build/npu_ooc_380ec37d39/routed_{timing_summary,critical_setup,critical_hold,route_status,utilization,utilization_hier,drc,clocks,check_timing}.rpt`. Launcher `99_build/npu_m0/m9.log`; command/exit0 JSON in build. DRC43 reported warnings as synth, default per-rule report limits noted; no error-severity DRC. OOC no_input_delay66/no_output_delay101, unset HD.CLK_SRC/HD.PARTPIN_LOCS and CFGBVS, async reset/control warnings retained; no board I/O/clock insertion/reset-release signoff claim. No false/multicycle paths, period remains10ns.
- Next M10 routed power last, then final evidence/hash/report/clean tracked worktree. Tool repairs4, timing repairs0, recovery0.
