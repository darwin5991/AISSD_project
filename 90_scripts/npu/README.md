# Programmable NPU v2 local verification

Run from repository root in Windows PowerShell. All Python uses existing Conda
`aissd`; no downloads, installs or checkpoint/dataset writes. Vivado/XSim 2025.2
is at `D:/AMDDesignTools/2025.2/Vivado/bin` (change `simulator.BIN` if installed
elsewhere). `model_loader` adapts baseline `LayerViewer` and its local IDX search.
Original checkpoint SHA is checked on every generation.

```powershell
conda run -n aissd python -m unittest discover -s 90_scripts/npu/tests -v
conda run -n aissd python 90_scripts/npu/smoke.py all
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v1.json
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v5.json
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v20.json
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v100.json
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200.json
conda run -n aissd python 90_scripts/npu/run_verification.py verify --scenario 90_scripts/npu/scenarios/v200f.json
```

Each invocation generates a unique `07_runs/npu/<name>_<timestamp>_<id>` with
scenario, immutable reference/quantized NPZ, layout/hash manifest, readable
assembly, dense input HEX, external output HEX, logs and strict comparison.
Result slots begin with A5A5A5A5 and TB checks exactly one external write per
requested result word. Every scenario has one reset/start/END, loads each
weight bank and bias once, and uses a scalar image loop. No internal hierarchy
is read/forced. Only external memory model tasks dump external results.

`--build 99_build/npu_model_<id>` reuses an elaborated full top after checking
every RTL/TB source hash. `--timeout 1200` bounds the XSim process. A cycle
watchdog also fails runaway programs. Bulk waves and timer are disabled.
Timeout cleanup targets only the owned process tree.

User-run large cases (supported; intentionally not part of default execution):

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 1000 --save argmax --timeout 3600
conda run -n aissd python 90_scripts/npu/run_verification.py verify --count 10000 --save argmax --timeout 21600
```

Explicit diagnostic IDs retain their supplied order; choose saved outputs:

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py verify --ids 7,0,19 --save fc1,fc2,fc3,argmax
```

Automatic diagnostics use full-layer stores for all failed original sample IDs,
preserving the failed run/reference; a fix must rerun the original gate. Labels
are informational accuracy, while reference array equality is the RTL gate.
Comparator checks every requested byte, both FC3 pad bytes and full uint32
ARGMAX, rejecting X/Z, missing/extra words and changed immutable inputs.

Stages can be separated (replace placeholders with actual generated paths):

```powershell
conda run -n aissd python 90_scripts/npu/run_verification.py generate --count 5 --save fc3,argmax
conda run -n aissd python 90_scripts/npu/assembler.py <run>/input/program.asm <new_imem.hex>
conda run -n aissd python 90_scripts/npu/run_verification.py simulate --run <run> --build <build>
conda run -n aissd python 90_scripts/npu/run_verification.py compare --run <run>
```

Assembler supports all 24 instructions, case-insensitive mnemonics, x0..x7 and
r0..r7, `.equ NAME,integer`, labels, `LI` and `SETADDR` (clobbers x4); `#` and
`//` comments. Branch/JAL offsets are from current PC after pseudo expansion.
Generator preserves x5 image pointer, x6 output record pointer and x7 count;
x1..x4 are scratch. Software enforces supported ranges, capacities and bank
roles. Unsupported hardware input behavior is unspecified.

`scenario.py` defines operations/ordered samples/save policy; `model_loader.py`
only loads/quantizes; `reference.py` implements address-independent NumPy ops;
`memory_builder.py` packs/allocates; `assembly_generator.py` dispatches emitters;
`assembler.py` encodes; `simulator.py` owns tools; `comparator.py` compares;
`run_verification.py` orchestrates. Reference and assembly operation registries
are separate. To extend supported models, adapt the loader and scenario while
retaining ISA/bank/shape validation; new operators require an explicit ISA/RTL
spec change and are outside this implementation.

FPGA reproduction is documented in `06_fpga/README.md`; actual final evidence,
source SHAs and exact paths are in `00_docs/programmable_npu/10_final_report.md`.
