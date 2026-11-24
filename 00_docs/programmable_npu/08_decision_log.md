# Decision log (append only)
## D003 / 2026-11-25 / M0 / npu-v2/20261125
- Anchor: 2e89b8e994982094a36172a3fd2f65d4a9edaff7. Read 00–07 and baseline datapath/scheduler/model/tool sources before code edits.
- Keep all legacy RTL intact; add `npu_memory_wrapper` and new controller variants. This avoids breaking archival TB interfaces; top directly instantiates unchanged MAC/accumulator/unpackers. Alternative shared-interface replacement adds avoidable regression risk.
- Use existing successful Vivado process-local environment and local tools. Reuse preflight license/place/route evidence; do not repeat synthetic preflight. Current Python/checkpoint/dataset verified in `99_build/npu_m0/environment.txt`.
- Toolchain will use JSON scenarios, baseline `LayerViewer`/quantization adapter, independent NumPy integer reference, dense external result records and store-count monitoring. No network, no subagents, no Phase8 merge.
- Gate commits stage explicit source/docs only; preserve user ZIP untracked. All build/generated evidence remains ignored.
## User decisions fixed in normative files
- Base main 2e89b8e, Phase8 reference only. Valid programs; no runtime validation/fault. Preserve datapath/BRAM. Single in-order instruction, 9 IC states, 4 stage regs; two fetch states; internal engine parameter capture at start. Per-bank mux. DMA pipelined word transfers. Timer includes LOAD/STORE/GEMM, excludes ARGMAX and scalar. Reset retains SRAM; END→HALTED until reset.
- 24 instructions, packed CSRs, 8 GPR. External IMEM/DMEM; Python scenario-driven generation, independent reference/comparator. ISA-only DMEM result writes. 1/5 deep, 20/100/200 argmax, then 200 FC3+argmax. Later 1000/10000 user-run. Same checkpoint, settings, weight reused within each scenario. OOC 100MHz routed WNS≥0, resources fit, power last, no overall runtime benchmark.
- Local commits new branch, never push; record decisions and choose one compliant route; bounded retry/alternate branch from earlier commit if necessary.

## Document-author implementation defaults (not separate user mandates)
- D001: register aliases r0..r7, example x1..x7 convention, little-endian dense dump files with manifest; software validation. Wrap32 semantics consistent with legacy arithmetic, compare zero padding. Unknown CSR read can be zero, not fault. Timer wrap/sticky, clear at TSTART. 3 repair attempts per blocker, 2 recovery branches total, 12 attempts overall. Alternative options/limits documented in 07. OOC hold/no unconstrained required internal paths and independent encodings as robust acceptance evidence. These clarify implementation, do not add new hardware features.
- D002: baseline old control scheduler uses weight group multiply; prefer incremental weight cursor (old Phase8 approach) for timing without changing address schedule. Keep legacy file variants if needed instead of deleting historical code. Actual exact module filenames delegated.

## New decision entry template
```
ID/date:
Milestone / current branch / anchor commit:
Question / evidence (source paths/lines or run logs):
Options considered:
Chosen compliant option and reason:
Rejected options and why:
Affected files / spec sections:
Validation and results:
Recovery branch if applicable:
```
