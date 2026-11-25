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

## D004 / 2026-11-25 / tooling repair and provenance
- Anchor 87a8b86; original tool failures and resolved commands logged under M2 in 09. Native XSim 2025.2 has no `-O` option; use default optimization and explicit `--timescale 1ns/1ps`. Quote entire `key=value` argument through Windows batch wrappers. This avoids changing installed software or global settings; alternative direct unwrapped binaries unnecessary.
- Four tooling repairs total: two for invalid -O option (first argument-only attempt was ineffective), one timescale default, one batch '=' tokenization. No RTL functional mismatches, recovery branches or reference corrections. Subsequent M2–M7 actual runs validate the resulting launcher.
- Tool timeouts own a Windows process group and kill only its child tree; source hashes prevent stale snapshot reuse. Run evidence retains failing folders instead of cleanup.

## D005 / 2026-11-25 / M8 preparation
- Anchor 72f48a1; use explicit new-top source list, OOC xc7a100tcsg324-1, sole 10ns clock, no path exceptions or IO timing claims. Unchanged single_port_bram area decomposition preserved; inspect actual utilization/hierarchy and routed reports.
- Use nonproject synth (rebuilt hierarchy), opt/place/phys_opt/route default directives with maxThreads6; no seed sweep or architectural alternative. Source/constraint hashes, commands, logs, reports and DCP retained in unique ignored build folder. Power runs separately only after six matching functional gates and routed setup/hold pass.
- Alternative GUI project or blanket legacy source glob rejected as unnecessary and potentially ambiguous. No semantic/timing-contract changes are authorized by this implementation choice.

## D006 / 2026-11-25 / M10 source identity
- Anchor5cf0429; power precheck rejected a string-key mismatch, not a content mismatch. Existing sim artifact paths contain Windows backslashes; FPGA manifest normalizes forward slashes. Independent audit found39/39 RTL SHA256 values identical after path normalization.
- Normalize only dictionary path separators at lookup, then require exact SHA equality for every RTL source in each of six mandatory gates. Alternative rerun simulations or edit old evidence rejected because neither addresses the string-key cause. Preserve failed launcher log npu_m0/m10_power.log. Retry actual power and final integrity audit PASS; no hardware, constraints or expected arrays changed.

## D007 / 2026-11-26 / user-requested local artifact commit
- Anchor 4384cc2f6923aebd52dcfdafae5e7e7bb6e0460b, branch npu-v2/20261125. User explicitly requested committing the previously recommended 14 passing NPU run packages:108 files, about10.04MiB, including assembly, IMEM/DMEM, metadata, reference/quantized NPZ and external results/comparisons. This request overrides the earlier default of keeping these generated artifacts local/ignored.
- Keep original bytes and existing run directories; allowlist these14 runs and known artifact filenames in .gitignore. Future runs, scalar_8e0ac731d5 without a completed comparison, logs, build caches, cleanup archives, original checkpoint/MNIST remain ignored. Assembler/generators already tracked and unchanged.
- Add scoped -text attributes for NPU snapshots because manifest hashes cover ASM/JSON as well as HEX/NPZ. core.autocrlf=true must not change immutable snapshot bytes at staging/checkout. No reference, comparison, RTL, ISA or timing modification.
- Validate package membership, exact file hashes, reassembly, existing external results and a Git index/checkout roundtrip before local commit; no simulation or FPGA rerun required for unchanged source/data. No push.
