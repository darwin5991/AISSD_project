# Scenario-driven Python verification toolchain
Normative functional interfaces, proposed filenames; implement modularly. Python is not part of synthesized NPU. No general compiler or graph importer. A configurable operation list + emitters is a small code generator, not a hardcoded assembly file per image count.

## Data flow and responsibility
```
checkpoint + MNIST ── model/image loader + quantization ── immutable quantized arrays
                                  scenario ─┬─ Reference (independent math) → reference.npz
                                            ├─ Memory Builder → dmem.hex + manifest/layout
                                            └─ Assembly Generator (uses layout + op specs)
                                               → program.asm → Assembler → imem.hex
imem.hex + dmem.hex + manifest → external-memory RTL TB → result HEX ranges
reference.npz + manifest + actual result HEX → Python Comparator → report / diagnostic rerun
```
All stages use same quantized input/weights and operation parameters but reference must not depend on packed memory addresses, RTL implementation, DUT results, or generated assembly. No duplication of numerical algorithms in packer/generator. Manifest is source of truth for addresses, logical lengths and output layout, never read expected arrays to generate result words for DUT. Scenario is source of truth for model/ops/sample selection/save policy.

## Proposed file organization
```
90_scripts/npu/
  scenario.py             # dataclasses or JSON parsing, operation specs
  model_loader.py         # adapter to existing 03_model/src (no new quantization policy)
  reference.py            # mathematical ops + reference generator
  memory_builder.py       # allocator, pack/unpack helpers, DMEM and manifest
  assembly_generator.py   # operation emitter dispatch, register convention, loops
  assembler.py            # full 24 instruction encoder + symbols/pseudos
  comparator.py           # decode actual results and compare arrays
  run_verification.py     # one command runs requested scenario(s)
  scenarios/              # committed scenario configs and valid unit cases
  tests/                  # packing/assembler/reference/codegen smoke tests
```
Equivalent module paths allowed if documented. Reuse existing `generate_golden.py`, `IntegerMLP`, `LayerViewer`, existing model/dataset paths; ensure imports work from repo root under Windows. Keep pure ops reusable; independent reference ops and emitters registered by operation type, e.g. `reference_ops={"gemm": reference_gemm, "argmax": reference_argmax}`, `assembly_ops={"gemm": emit_gemm, "argmax": emit_argmax}`. Model data, shape, per-op fixed-point config and execution order specified in scenario, not hidden hardcoded per-layer emitter. Future supported models/layers/scenarios can change within memory and ISA limits; new operators require corresponding reference, emitter, and if necessary RTL/ISA/assembler. No requirement to support arbitrary PyTorch graph.

## Scenario contract
Example declarative scenario (field names may vary, preserve behavior):
```json
{"name":"mnist_200_fc3","checkpoint":"03_model/checkpoints/MLP_MNIST_GPU_FINAL_BEST.pth",
 "dataset":"MNIST test","sample_ids":{"start":0,"count":200},
 "ops":[{"id":"fc1","op":"gemm","k":784,"n":512,"src":"A","dst":"B","bias_shift":3,"out_shift":10,"relu":true},
        {"id":"fc2","op":"gemm","k":512,"n":128,"src":"B","dst":"A","bias_shift":1,"out_shift":7,"relu":true},
        {"id":"fc3","op":"gemm","k":128,"n":10,"src":"A","dst":"B","bias_shift":2,"out_shift":7,"relu":false},
        {"id":"argmax","op":"argmax","src":"B","length":10}],
 "save_outputs":["fc3","argmax"],"reuse_weights":true,"timer":false,"waveform":false}
```
Support explicit arbitrary ordered sample ID list for debug reruns, not just count. Run each scenario with single reset/start/END, weights/bias LOAD once, sequential images and assembly loop; no host-driven per-image restart. Allow per-image or designated debug outputs via a generated diagnostic program. Timer default off in bulk; separate small timer verification, optional measurement mode. 1,000/10,000 later supported by same code, not required overnight; validate capacity or explicitly chunk as needed (10k×784B≈7.84 MB plus weights/output fits default DMEM; loops avoid IMEM blowup).

## Model and reference
Baseline checkpoint SHA-256 per 00; normalized image `(pixel/255-0.1307)/0.3081`, existing trained preprocessing unknown but use selected baseline setting. Model 784→512→128→10, all FC bias. Signed INT8 throughout; input frac 5, weight frac (7,7,7), bias frac (9,8,7), output frac (2,2,2); offline round nearest ties-to-even and clip signed INT8, existing code authoritative. Output rounding arithmetic shift (floor). Reuse exact baseline quantization, verify sample0 and additional known examples against existing independent `generate_golden.py` (not DUT). Preserve checkpoint and dataset; load weights once, batch reference allowed. FC3 zero-pad rows/bias/outputs to 12 for physical store, compare all 12 bytes when FC3 requested; ARGMAX only first 10, strict first maximum.

Illustrative pure functions (adapt NumPy implementation, explicit INT32 wrap before postprocessing; validate overflow semantics against legacy):
```python
import numpy as np

def wrap32(x):
    return (np.asarray(x, dtype=np.int64) & 0xffffffff).astype(np.uint32).view(np.int32)

def reference_gemm(x, w, b, bias_shift, out_shift, relu):
    x, w, b = (np.asarray(v, dtype=np.int64) for v in (x, w, b))
    aligned = wrap32(b << bias_shift if bias_shift >= 0 else b >> -bias_shift)
    acc = wrap32(w @ x + aligned.astype(np.int64))
    activated = np.maximum(acc, 0) if relu else acc
    return np.clip(activated >> out_shift, -128, 127).astype(np.int8)

def reference_argmax(logits, length):
    return int(np.argmax(np.asarray(logits, dtype=np.int8)[:length]))
```
Modulo accumulation equivalent to legacy for valid INT32 arithmetic; if existing baseline rejects overflow in golden, retain checks for MNIST and separate precise wrap behavior for unit tests. Use int64 intermediate to avoid NumPy type-dependent overflow. Output padding must come from valid zero weights/bias, not hide nonzero RTL bytes. Reference can compute all layer values for all images even if only ARGMAX compared; no extra RTL stores required for reference. Save `reference.npz` with `sample_ids` int32/int64, `labels`, `fc1` shape (B,512) int8, `fc2` (B,128) int8, `fc3` (B,10) int8 (or separate `fc3_padded` (B,12) int8), `argmax` (B,) uint32/int, optional immutable quantized input/weights or separate `quantized.npz`. `allow_pickle=False`. Do not regenerate expected results to match DUT; store hashes and reuse unchanged across repair reruns. A legitimate independent reference bug correction requires documented proof against baseline/hand values and rerun all gates.

## Memory Builder and HEX format
DMEM base 0x10000000, 16 MiB. Allocate aligned, nonoverlapping contiguous regions: W0..W3 each 117120 B, Bias 652 B, N×784B input images, explicit output regions only for requested outputs, optional timer words. No internal memory prefill. Weights layout per bank j, layer → output group g → input word i; pack w[4g+j,4i:4i+4], little-endian. Bias group of 4 outputs; zero pad final group. For existing model:
| Layer | K,N | Q,G | W word base | Bias word base | Input/Output | shifts bias/out/ReLU |
|---|---|---|---:|---:|---|---|
| fc1 | 784,512 | 196,128 | 0 | 0 | A→B | 3/10/1 |
| fc2 | 512,128 | 128,32 | 25088 | 128 | B→A | 1/7/1 |
| fc3 | 128,10 | 32,3 | 29184 | 160 | A→B | 2/7/0 |
W0 byte base FC1 80040000, FC2 80058800, FC3 8005C800; Bias 800C0000,800C0200,800C0280. Full W per bank 29280 words, Bias 163 words. Validate dimensions, bank ranges/roles, alignment, input/output stride, program capacity, DMA no boundary crossing, exact manifest layout. Pack signed bytes by masking 0xff and placing byte0 bits[7:0]. One 32-bit word = 8 hex digits per line; `dmem.hex` dense from base to highest initialized address (avoid full 16MiB text if not necessary), imem dense from PC0. Initialize unused TB DMEM and IMEM deterministic zeros before readmemh; **output slots prefill sentinel** (e.g. 0xA5A5A5A5, not Reference values), validate actual writes to requested result slots or test expected store counts using external DMEM bus only. No expected arrays loaded into RTL. Manifest records initial file length, region base/byte length, sample stride, dtype, shape, logical count, padded count, output dump range base/word count/file, checkpoint/sample/quantization hashes, reference hash, scenario and seed, program hash. No machine-specific absolute paths needed for reproducibility.

## Assembly generation
Generate weight/bias LOAD once for each separate bank (5 instructions plus GPR constants); image loop updates source pointer by 784, executes layer CSR writes and EXEC GEMM; before next layer overwrites output, STORE required FC1 (512B)/FC2 (128B)/FC3 (12B) to corresponding per-image DMEM location. `EXEC ARGMAX,rd` then SW index as 32-bit result. Increment output pointers/loop counter and BNE back; END once. Output layout can use a single per-image record pointer plus constant offsets loaded as needed; do not allocate more than x1..x7. Example register convention chosen by generator: x1/x2/x3 scratch DMA src/dst/len, x4 CSR scratch (SETADDR clobber), x5 input pointer, x6 record pointer, x7 loop count (decrement via ADDI, BNE x7,x0,label). Reuse scratch for ARGMAX rd and SW. Keep all long-lived regs intact across emitter calls; add checks/test. LI/CSRW for full DIM (SETI only signed 13-bit); CFG may use SETI if representable. Handle record stride with ADDI or LI+ADD when needed. Assembler full ISA per 01, no pseudo-direct machine words to bypass it; test independent encodings, signed immediates, labels after pseudo expansion. Generate source readable for inspection. Data hex and assembly generated separately from shared layout; do not reverse-engineer hex to infer addresses.

## External TB and Comparator
TB initializes only IMEM/DMEM, pulses reset/start, waits top done and dumps requested **external DMEM address ranges** only. Map base byte→word index; one file per dump range, exactly 8 hex digits/word, no address tags (TB may use explicit file I/O or normalize $writememh tags deterministically). Dump includes only output addresses written via program STORE/SW, not all DMEM. No DUT hierarchy reading/forcing or internal SRAM/GPR/CSR dumps. Timeout fails nonzero, no hangs; allow scenario-dependent generous deterministic cycles. Waveforms off in bulk; diagnostic optional external trace, not validation shortcut. Testbench must not calculate golden arithmetic. Monitor top done pulse and external bus as appropriate. No overall execution time reporting requirement.
```python
from pathlib import Path
import re
import numpy as np

def read_words(path, expected_count):
    lines = Path(path).read_text().splitlines()
    if len(lines) != expected_count or not all(re.fullmatch(r'[0-9a-fA-F]{8}', s) for s in lines):
        raise ValueError('invalid dump length or word (including X/Z)')
    return np.array([int(s,16) for s in lines], dtype='<u4')

def unpack_i8(words):
    return np.asarray(words, dtype='<u4').view(np.int8)

def compare(actual, expected):
    if actual.shape != expected.shape:
        raise ValueError('shape mismatch')
    return np.argwhere(actual != expected)
```
Comparator uses manifest offsets/strides to extract all requested records, restore signed INT8, keep ARGMAX uint32 (do not truncate), compare against NPZ arrays, verify padding zero. Report scenario, sample IDs, layer, mismatch counts, first mismatches index/address/expected/actual signed values and raw hex, match totals and pass/fail. Missing/extra/invalid dumps, unknown bits, timeout or unwritten required slots are failure. Comparison returns nonzero on failure. No tolerance or masks to hide mismatches. Reference labels vs predictions accuracy is informational, not correctness gate. For argmax-only mismatch run new diagnostic scenario containing failing original image(s) with full FC stores, using same model/quantization/inputs; report exact failure. Also rerun original full scenario after any fix.

## Outputs and reproducible CLI
```
07_runs/npu/<run_id>/
  manifest.json  scenario.json  reference.npz  [quantized.npz]
  input/program.asm  input/imem.hex  input/dmem.hex
  output/<range>.hex
  logs/  comparison.json  summary.md
```
Use unique run dirs; never overwrite evidence; keep large artifacts ignored/local, commit source configs, compact reports and actual command references/hashes. Expose CLI for `generate`, `assemble`, `simulate`, `compare`, `verify` or equivalent and documented example for changing count/save policy, explicit sample IDs, no-wave, timeout. One command should run each complete scenario, fail nonzero on mismatch. Later user can run count 1000/10000 and compare accuracy without editing RTL/assembler. No actual file paths/commands falsely marked executed; document actual commands after implementation.
