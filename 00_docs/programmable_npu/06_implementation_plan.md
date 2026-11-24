# Implementation plan — autonomous milestone gates
Proceed sequentially in a local branch, no per-step user approval. Each gate requires actual evidence. Commit passing milestone with progress/decisions before moving on. See 07 for bounded retries. Actual code paths/commands may differ from proposed names; document them. Do not claim this plan is implementation.

| Milestone | Work | Gate / evidence |
|---|---|---|
| M0 preflight | verify repo/commit, local ignored checkpoint & MNIST, Vivado/XSim/versions/license, Python packages, disk, branch; inventory main and read old docs/RTL; freeze new spec; check conflicts | actual commands/results, base SHA, environment, hashes, known blockers; initial docs commit |
| M1 software foundations | quantized model loader/reference, scenario, packing/layout, manifest, assembler all 24 and pseudos/labels; simple emitters | independent encoder vectors, pack/unpack, sample0 old golden equality, generated program/data valid; commit |
| M2 scalar IC | ISA package, decoder/GPR/CSR/ALU/perf, exact 9 FSM and 4 stage regs, fixed external IMEM/DMEM, scalar LW/SW | scalar test program through external memory; observed results via SW and CSR/SW, branch/JAL, done; commit |
| M3 SRAM/DMA | adapt wrapper/owner/ports, pipeline DMA and DMEM mux; SRAM seven bank sizes, registered selector | valid roundtrip LOAD/STORE single/multi, final word, known timing, owner; commit |
| M4 GEMM | extract legacy per-GEMM scheduler, capture params local, cursor/bases, preserve pipeline, direct MAC/accumulator top wiring | small signed GEMM with correct padding and base; actual result through STORE, legacy regression if feasible; commit |
| M5 ARGMAX and integrated smoke | independent engine and local params; connect complete top; timer incl STORE, no ARGMAX | signed/tie/lens, integrated small chain, timer observed via CSR/SW, all smoke; commit |
| M6 full toolchain | actual MLP emitters/assembly loops, generated hex, real external TB dump, comparator, runner, manifest | full scenario V1, 512+128+12 bytes+argmax; commit |
| M7 functional scale | V5, V20, V100, V200, V200F sequential; diagnostic only on mismatch | all required pass reports; commit each meaningful gate or group with exact logs |
| M8 synthesis | OOC npu_top sources/XDC and run scripts, actual synth, inspect hierarchy/BRAM mapping, utilization, timing | synth success and resource fit, report paths; commit |
| M9 implementation | opt/place/route, analyze paths and fix within spec if needed; rerun functional regression after RTL edits; iterate bounded | routed WNS>=0, no constrained setup/hold violations, resource fit, reports & DCP; commit |
| M10 final | routed power report last, complete usage commands and final report, check git state/no push | all gates and final branch/commit evidence, power estimates/assumptions; final commit |

## Integration details
M2/M3/M4 may use a temporary minimal top or test harness with inactive unused interfaces, as long as it never enters final synth file list and observable outputs use ISA. Keep top interface stable. Every new engine start/done integrated into exact MEM_START/MEM_WAIT, no fake done. On M7+ RTL changes rerun smoke and all mandatory scenarios for final chosen commit before reporting final PASS. Pure documentation or report changes need not rerun unchanged RTL. Avoid unnecessary giant waveforms or generated headers; use HEX. No new feature or sweeping refactor after passing gates. If timing optimization needs alternate architecture violating 02, stop/report instead of silently changing it. Existing phase8 is for reference only. See 05 for requirements and 07 for failure policy.

## Final user handoff
Provide one documented Windows command for each scenario and optional 1000/10000 with count and save selection; command for synth/place/route/power; location of comparison outputs, actual design reports and final commit. Preserve failed branches and logs. Explicitly list missing gates and next action if incomplete. Do not launch 1000/10000 test by default.
