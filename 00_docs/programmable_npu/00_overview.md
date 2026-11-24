# Programmable NPU — design package
**Version:** 2026-11-25 / implementation target, not a report of completed RTL.

## Goal
Turn existing fixed 784→512→128→10 signed INT8 MLP accelerator into an ISA-controlled NPU; retain MAC/accumulator/7 SRAM banks, add scalar control, DMA and reusable independent GEMM/ARGMAX engines. Execute externally supplied program/data, verify against independent Python integer reference, meet internal 100 MHz OOC post-route on Artix-7 `xc7a100tcsg324-1`. No actual board integration, external physical memory controller, general RV32 CPU, AXI, compiler graph importer or new operators.

## Read order and ownership
| File | Role |
|---|---|
| 01_isa_spec.md | Normative programmer-visible interface, encoding, addressing |
| 02_architecture.md | Normative hardware contract, cycle/handshake |
| 03_rtl_migration.md | Existing source analysis and proposed reuse/removal/addition |
| 04_python_toolchain.md | Normative scenario-driven software contract |
| 05_verification_spec.md | Required tests and acceptance criteria |
| 06_implementation_plan.md | Milestones with concrete gates |
| 07_execution_policy.md | Local Git, decision/recovery and completion rules |
| 08_decision_log.md | Append-only decisions during work |
| 09_progress.md | Persistent progress and evidence |
| 10_final_report.md | Final report to fill with observed results |

Root `AGENTS.md` is the agent's operational entry. New contracts override earlier Phase8 documents where inconsistent. Treat 03/06 implementation details as proposed where not constrained; preserve normative requirements. Never silently rewrite target to fit implementation.

## Baseline sources
- [main baseline, bram 사용률 개선](https://github.com/darwin5991/AISSD_project/commit/2e89b8e994982094a36172a3fd2f65d4a9edaff7), use exact SHA to start new branch.
- [Phase8 reference](https://github.com/darwin5991/AISSD_project/tree/20f88bc008ad78e654ffd4eeba4ed1e4c504d5a8): old ISA/architecture/assembler/RTL; not base, no blind copy. Old full-width CSRs, error/fault paths, timer policy and monolithic controller are superseded.
- main `00_docs/architecture.md`, `00_docs/mac_input_pipeline.md`, `00_docs/modules/`, `03_model/generate_golden.py`, `03_model/src`, `04_rtl`, `05_tb`, `06_fpga`, `90_scripts`.
- Checkpoint `03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth` is gitignored, 1,879,001 bytes, SHA-256 `aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd` per baseline README; verify local file and MNIST dataset before simulation. Do not substitute another model.

## Scope boundaries
The following are deferred to user: 1,000/10,000 image accuracy runs (support them, do not run overnight by default), board-level timing and I/O, additional operation ISA, generalized compiler. No overall Start→Done timing benchmark required; simulation may maintain a watchdog counter for timeout only. Measure performance through PERF_COUNT, not internal probing. Power report last; report estimation assumptions.

## Package conventions selected for implementation
`x0..x7` canonical, accept legacy `r0..r7` aliases in assembler; packed CSR fields below; fixed word-aligned SRAM offsets. Explicitly selected implementation defaults (not separate user approvals): bounded 3 repair attempts per blocker and at most 2 recovery branches overall, stable ordered sample IDs, output manifest and dense per-range HEX dumps, modular source paths proposed in 03/04. Record these in decision log and adapt implementation-only details with rationale, not requirements.
