# AGENTS.md — AISSD Programmable NPU (2026-11-25)

## Mission / authority
Implement, verify, synthesize and place/route the programmable NPU end-to-end in a new local branch from `2e89b8e994982094a36172a3fd2f65d4a9edaff7` (`main` baseline). User authorizes all milestones in this run, local file edits, local tool execution and local commits; **never push**. Do not stop after merely planning. No RTL implementation has been done by this document package.

Read `00_docs/programmable_npu/00_overview.md`, then 01–07 before modifying code. 01 ISA, 02 architecture, 04 Python, 05 verification are normative target contracts; 03 describes baseline/migration, 06 plan and 07 execution policy govern work. 08–10 are writable records. The original main legacy docs remain evidence for datapath behavior. Phase8 branch `20f88bc008ad78e654ffd4eeba4ed1e4c504d5a8` is reference only, never merge wholesale. New spec supersedes old fault handling, CSR map, controller, timer and TB assumptions. If contradictory, record conflict; do not quietly change requirements.

## Non-negotiable
- Valid programs only: no hardware opcode/region/bounds/alignment/CSR privilege/config/runtime fault checking or error code; software assembler/builder validates supported inputs. Keep ordinary loop/end comparisons and deterministic safe idle controls.
- Keep 24 instructions, 8x32 GPR, 10 CSRs, nine-state IC, single instruction in flight, 7 SRAM banks, fixed sync memory contracts. No prefetch, new protocol, CPU features, new arithmetic operators, wrappers obscuring the datapath, or arbitrary extra stages.
- Preserve existing MAC and accumulator/postprocess arithmetic, R→R+6, group bubble, BRAM sizes/decomposition, signed packing. Modify only necessary control/ports; optimization only if semantics and verified timing contracts preserved.
- No direct TB initialization of internal SRAM, internal result probes, hierarchical SRAM/GPR/CSR extraction, or forcing DUT signals for new end-to-end tests. IMEM/DMEM external TB only; ISA LOAD/STORE, CSRR/SW write results to DMEM. Legacy unit TB can remain archival. Do not tailor Reference or comparison masks to DUT results.
- No invalid-input exhaustive tests; focus valid-program correctness. Mandatory scenario gates per 05; power after post-route. Never label unrun tests PASS, weaken clock, ignore mismatches, or add false/multicycle constraints to hide failures.
- Keep original checkpoint/dataset unchanged; no uploading, credential access, network transfers or destructive cleanup. Do not edit main, push, force-push, merge recovery branches into main, reset hard, clean -fdx, or overwrite user changes. Preserve local ignored model/data.

## Execution
Follow 06 and 07: preflight, small changes, test, review, commit each gate, update 08/09. Continue automatically through gates without requesting routine approvals. On unresolved choice, select a spec-compatible option, record alternatives/reason/anchor commit and proceed; bounded recovery branches only. On blocker after retry budget, preserve work/logs and report exact failure; don't pretend success. Final report 10 includes real paths, commands, git SHAs, all test counts and routed metrics. Read it and ensure clean tracked worktree (ignored build artifacts allowed). Restore no user files. Do not push.

## Python Execution Environment

- Always use the existing Conda environment named `aissd` for all Python-related tasks.
- Prefer `conda run -n aissd python ...` to ensure the correct environment is used across independent shell executions.
- Use this environment for reference generation, quantization, assembly generation, verification, comparison, and automation scripts.
- Do not create a new virtual environment or install dependencies into the base environment.
- Verify the Python executable and required dependencies during preflight.
- Preserve the existing environment and avoid unnecessary package upgrades or removals.

## Verified Local Development Environment

- OS: Windows 11.
- Python: existing Conda environment `aissd` (Python 3.11.16).
- Always use `conda run -n aissd python ...`.
- Vivado 2025.2 and XSim are installed and verified.
- FPGA part: `xc7a100tcsg324-1`.
- Model checkpoint and MNIST datasets are already available locally and verified.
- Do not download, replace, or modify the original model or dataset.

### Vivado Execution Notes

The preflight test successfully executed xvlog, xelab, xsim, synthesis, optimization, placement and routing.

If environment or temporary-directory access errors occur:

- Set `XILINX_LOCAL_USER_DATA=no`.
- Use process-local APPDATA, TEMP and TMP directories under the repository's ignored `99_build/` directory.
- Normalize Tcl paths using forward slashes.
- Start shell commands from the repository root and use PowerShell `Set-Location` if necessary.
- Reuse the successful preflight configuration rather than repeatedly investigating known environment issues.

Preflight evidence:
`99_build/preflight_5dd1565c7eba/evidence/report.txt`

### Filesystem and Git Safety

Even when Full Access is enabled, restrict all project modifications to the AISSD repository. Do not modify unrelated files, global settings, installed software, or external repositories.

Local branch creation and commits are authorized. Git push is prohibited. Preserve existing untracked user files.