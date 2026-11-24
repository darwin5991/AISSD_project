# Final report — fill after actual execution
**Status: NOT RUN** (template; replace only with observed results).

## 1. Repository and environment
Baseline / final branch / final commit (or last code commit plus report commit), clean tracked status, no push, recovery branch ancestry. OS/Python/NumPy/PyTorch/Vivado/XSim versions, checkpoint path/SHA, dataset/test IDs. Summarize RTL and Python changes and actual module hierarchy. Link decisions and progress records.

## 2. Test results
| Test | Expected | Actual | Status | Source version / artifact path |
|---|---|---|---|---|
| Python encoder/pack/reference | PASS | — | NOT RUN | |
| ISA smoke | PASS | — | NOT RUN | |
| DMA/GEMM/ARGMAX/timer smoke | PASS | — | NOT RUN | |
| 1 deep | 1 argmax + 652 bytes | — | NOT RUN | |
| 5 deep | 5 argmax + 3260 bytes | — | NOT RUN | |
| 20 argmax | 20/20 | — | NOT RUN | |
| 100 argmax | 100/100 | — | NOT RUN | |
| 200 argmax | 200/200 | — | NOT RUN | |
| 200 FC3+argmax | 2400 bytes + 200/200 | — | NOT RUN | |
Provide actual comparison counts, reference/RTL vs labels informational accuracy, mismatch examples/diagnostic reruns, commands, output manifests and hashes. No internal probes as result sources. State any legacy regressions run/not run. User 1000/10000 default NOT RUN.

## 3. Synthesis and routed implementation (OOC)
Target `xc7a100tcsg324-1`, top `npu_top`, 10ns. Report actual run status, DCP, Tcl command, log, XDC, tool strategy/seed. Table actual utilization counts, capacity and % for LUT/FF/RAMB36/RAMB18/BRAM tiles/DSP, inference vs expected. Post-synth WNS/TNS (informational), post-route setup WNS/TNS/endpoints, hold WHS/THS/endpoints, DRC, worst path description, internal clock coverage, unconstrained external I/O/reset caveats. Do not state whole board timing PASS. Power (last, static/dynamic/total, temperature/activity assumptions, report path). No fabricated numbers. Note why any step not run.

## 4. Reproduction instructions
Exact Windows commands from repo root to generate/assemble/simulate/compare, V1/5/20/100/200/200F and user-run 1000/10000; change save policy and sample IDs, diagnose one image, rerun synth/route/power. Required packages and local model/dataset paths. Final output file layout and logs.

## 5. Decisions, limitations and next steps
List unresolved issues, retry/recovery history, known assumptions, remaining gates and recommendation. PASS only if all mandatory gates satisfied; otherwise PARTIAL/FAIL/BLOCKED with next reproducible action. Explicit statement no push. Final report commit SHA may be obtained after commit; avoid circular self-hash by recording final code commit and giving report commit in final message.
