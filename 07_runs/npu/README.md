# Committed NPU simulation snapshots

These are the 14 passing local simulation runs from 2026-11-25. The packages
contain the original assembly, external IMEM/DMEM initialization, external
result dumps and comparison data. Files were retained byte-for-byte; no model,
reference, program or DUT result was regenerated for this commit.

| Run directory | Scope |
|---|---|
| `scalar_377ea75f5d` | M2 scalar harness, 19 output words |
| `dma_e2a1db6f61` | M3 DMA harness, 24 output words |
| `gemm_913b7c97c7` | M4 small GEMM, 8 output words |
| `scalar_52cc5fe152` | Final full-top scalar smoke, 19 output words |
| `dma_9c0e67b2e2` | Final full-top DMA smoke, 24 output words |
| `gemm_9f3f342382` | Final full-top GEMM smoke, 8 output words |
| `argmax_4105a01fb9` | Signed/tie/length/timer smoke, 12 output words |
| `chain_3de93df10a` | Integrated small chain, 14 output words |
| `mnist_1_fc1_fc2_fc3_argmax_20261125_024139_b33a42` | V1: all layers + ARGMAX |
| `v5_20261125_024215_8631ca` | V5: all layers + ARGMAX |
| `v20_20261125_024243_a4c11b` | V20: ARGMAX |
| `v100_20261125_024314_8859ab` | V100: ARGMAX |
| `v200_20261125_024439_4aec3b` | V200: ARGMAX |
| `v200f_20261125_024812_6bde90` | V200F: FC3 + ARGMAX |

`input/program.asm` is readable assembly; `input/imem.hex` contains encoded
instructions. `input/dmem.hex` contains packed weights, bias, images and
sentinel result slots. ISA LOAD transfers data into the internal SRAM banks;
the external TB does not initialize those banks directly.

The six MNIST packages also contain scenario/layout manifests and immutable
reference/quantized NPZ arrays. Both NPZ files are included because the
comparator checks their manifest hashes. `output/results.hex` is the recorded
external DMEM dump. The eight smoke packages use `expected.json` and
`comparison.json` for their word-level expected/actual values.

Source tools, including the assembler and assembly/data generators, are already
tracked in `90_scripts/npu/`. See that directory's README for the full CLI and
`00_docs/programmable_npu/10_final_report.md` for original verification evidence
and OOC timing/resource/power scope. All six MNIST runs used the unchanged final
RTL introduced by `af165948b5ca65fc52ec4f36ccf2a2f32a354052`.

From the repository root, compare a recorded model snapshot without simulating:

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py compare --run 07_runs/npu/v200f_20261125_024812_6bde90
```

To simulate that saved program/data again with native XSim, then compare:

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py simulate --run 07_runs/npu/v200f_20261125_024812_6bde90
conda run -n aissd python 90_scripts/npu/run_verification.py compare --run 07_runs/npu/v200f_20261125_024812_6bde90
```

This creates an ignored build and local logs and rewrites that snapshot's output
and comparison files. Inspect any resulting Git diff. The saved IMEM/DMEM and
reference data suffice for replay; generating a new model scenario requires
the original local checkpoint and MNIST files.

For fresh integrated smoke runs:

```powershell
conda run -n aissd python 90_scripts/npu/smoke.py all
```

Only these existing passing run IDs and known package filenames are allowed by
`.gitignore`. Future runs, the incomplete `scalar_8e0ac731d5` run, all `logs/`,
`99_build/`, cleanup archives and original checkpoint/dataset remain local.
Snapshot attributes disable newline conversion so manifest SHA-256 checks
survive checkout on different platforms. No files in the snapshots are edited
to accommodate checkout or DUT results.
