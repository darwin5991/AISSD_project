# Progress — update continuously
## M0 actual preflight / 2026-11-25
- PASS: new branch `npu-v2/20261125` from exact baseline `2e89b8e994982094a36172a3fd2f65d4a9edaff7`; initial tracked worktree clean; user untracked docs/AGENTS/ZIP preserved. No push.
- Read AGENTS, all 00–07, baseline top, pipeline/read scheduler, MAC, accumulator, BRAM, ARGMAX, model/quantization and runner. No normative conflict identified.
- `conda run -n aissd python -c ...` exit 0: Python 3.11.16, NumPy 2.4.6, PyTorch 2.11.0+cu128, strict model load and sample0 label 7. Checkpoint 1879001 bytes SHA256 matches normative hash. Test IDX available via baseline LayerViewer (download not used).
- Evidence `99_build/npu_m0/environment.txt`; prior full tool/license preflight `99_build/preflight_5dd1565c7eba/evidence/report.txt`, git permission report `99_build/git_permission_recheck_fb3b7774df7d/report.txt`. D: free ~926 GiB. Vivado/XSim 2025.2 at D:/AMDDesignTools/2025.2/Vivado/bin, target xc7a100tcsg324-1.
- Implementation files planned: `90_scripts/npu/*`, `04_rtl/isa/*`, new engine files under controller, `npu_memory_wrapper`/DMEM mux, `04_rtl/npu_top.sv`, `05_tb/npu/*`, NPU XDC/Tcl. Commands will be recorded as executed. Next M1. Repairs 0; recovery branches 0.
Initial state: document package prepared; **all implementation and verification gates NOT RUN**. No new RTL/simulation/synthesis/route performed by document author. Codex fills actual records.

| Gate | Status | Commit/source version | Evidence path | Notes |
|---|---|---|---|---|
| M0 preflight | NOT RUN | — | — | |
| M1 toolchain foundations | NOT RUN | — | — | |
| M2 scalar IC | NOT RUN | — | — | |
| M3 SRAM/DMA | NOT RUN | — | — | |
| M4 GEMM | NOT RUN | — | — | |
| M5 ARGMAX/timer/smoke | NOT RUN | — | — | |
| M6 V1 | NOT RUN | — | — | |
| M7 V5 | NOT RUN | — | — | |
| M7 V20 | NOT RUN | — | — | |
| M7 V100 | NOT RUN | — | — | |
| M7 V200 | NOT RUN | — | — | |
| M7 V200F | NOT RUN | — | — | |
| M8 synthesis | NOT RUN | — | — | |
| M9 post-route | NOT RUN | — | — | |
| M10 power/report | NOT RUN | — | — | |

## Current checkpoint
- Branch/base:
- Last passing milestone / commit:
- Current action:
- Retry attempts used / recovery branches used:
- Next gate:
- Blockers:

## Log template
Date, gate, source SHA or diff hash, branch, files, exact commands, exit codes, result counts, log paths, issues, next steps. Append failure attempts as well as passes; never replace failing evidence with passing log. Update current checkpoint at each commit.

## M1 foundations PASS / 2026-11-25
- Anchor 2bc8d0b. Added modular scenario, baseline read-only loader, independent NumPy wrap32 reference, SRAM/DMEM layout, operation-based assembly generator and 24-instruction assembler.
- Command `conda run -n aissd python -m unittest discover -s 90_scripts/npu/tests -v`; Python exit 0, 4/4 unittest methods PASS. Evidence `99_build/npu_m0/m1_tests.log` (PowerShell formats unittest stderr but unittest result OK).
- 24 encoding cases plus LI boundaries/label expansion, signed packing/wrap, layout; existing generate_golden.py IDs 0,1,7 all-layer equality 1956 bytes, predicted [7,2,9]. Baseline outputs `99_build/baseline_golden_515a0fa671`, `baseline_golden_51dab8755a`, `baseline_golden_c526978256`.
- Source reviewed for independent reference and expected-value isolation. No model/data changes. Next M2; repairs 0.
