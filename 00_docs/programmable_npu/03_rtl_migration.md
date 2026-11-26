# Baseline RTL analysis and migration
Read-only review of main commit `2e89b8e994982094a36172a3fd2f65d4a9edaff7`; detailed per-file audit to be completed at milestone 0. Source links relative to [baseline tree](https://github.com/darwin5991/AISSD_project/tree/2e89b8e994982094a36172a3fd2f65d4a9edaff7). Phase8 reference is not current target.

## Current structure
`04_rtl/controller/mlp_top.sv` instantiates memory_wrapper, unpackers, mac_array, accumulator_postprocess, control_unit; exposes tb_en/we/addr/wdata/rdata, prediction and start/busy/done. `control_unit` contains layer_config_lut, control_fsm, mlp_counters, address_generator, pipeline_control, argmax_control, argmax_unit, control_read_mux. Old control_fsm IDLE/PREP/RUN/DRAIN→PREP(next layer)→ARGMAX→IDLE. Old LUT hardcodes FC1/2/3 dimensions, offsets, shifts and ping-pong, ARGMAX length 10. New NPU delegates layer sequence to software. Existing memory_wrapper has seven single_port_bram instances, per-bank 2:1 TB/core mux, buffer_router, tb_address_decoder and tb_read_mux. `busy` selects core path, unsuitable for LOAD/STORE while program busy. `tb_read_mux` latches read bank ID; preserve this latency. Existing main weight banks have area decomposition hint. Existing `pipeline_control` uses delays 1/5/6, read_issue_control inserts single bubble, and fault_hold/state_is_valid masks old invalid state handling. `address_generator` uses combinational `output_group * input_words`; cursor preferable for new dynamic GEMM. Existing `argmax_schedule` uses word_loaded and reads each word before byte compares. Existing legacy top golden uses hierarchical write probes and direct TB SRAM load; new integration must not.

## Reuse / modify / remove (from new design)
| Path under 04_rtl | Action | Required change |
|---|---|---|
| mac_array/* | reuse unchanged | 3-stage operands/products/sums and valid |
| accumulator_postprocess/* | reuse unchanged | bias align, accumulator, result reg, ReLU/shift/sat/pack |
| common/* | reuse | register_en, delay_line, signed_adder32, as needed |
| controller/unpack_int8x4.sv | reuse | top instantiates input, 4 weights, bias |
| memory/single_port_bram.sv | reuse unchanged | preserve seven depths, W area option and latency |
| memory/memory_wrapper.sv | modify or create new variant | owner vs busy, DMA/ARGMAX ports, writable W/Bias, independent bank muxes |
| memory/memory_port_mux.sv | adapt or replace in new wrapper | NONE/DMA/GEMM/ARGMAX paths, no arbitration |
| memory/buffer_router.sv | adapt | A/B ping-pong; full A output width 8 bits; offsets |
| memory/tb_address_decoder.sv, tb_read_mux.sv | reuse logic | rename/generic DMA path if needed; registered response selection |
| controller/mlp_top.sv | superseded in new top | not synthesized in new target; keep old file if legacy tests need it |
| controller/control_unit.sv | superseded | extract one GEMM and independent ARGMAX; IC owns dispatch |
| controller/control_fsm.sv, control_state_pkg.sv | adapt/new variant | GEMM four states only; no next layer or ARGMAX |
| controller/layer_config_lut.sv | remove from new hierarchy | CSR + local start-latched parameters |
| controller/mlp_counters.sv | adapt | remove layer counter, retain input/group counters |
| controller/address_generator.sv | adapt | input/output/bias base; common incremental weight cursor to avoid dynamic multiply critical path |
| controller/pipeline_control.sv | adapt | R+1/5/6 delays retained, remove layer advance/fault_hold/state validation path; delayed output group address with base |
| controller/read_issue_control.sv | adapt | per-GEMM schedule, Q/G and one bubble, remove layer/invalid recovery/zero-size checks; retain end comparisons |
| controller/pipeline_event_control.sv, counter_en.sv | reuse | existing events/counter primitives |
| controller/control_read_mux.sv | remove from new hierarchy | separate GEMM/ARGMAX SRAM owner paths |
| controller/argmax_control.sv, argmax_schedule.sv | adapt/new variant | local base/LEN and standalone start/done |
| controller/argmax_unit.sv, byte_select4.sv, signed_compare8.sv, argmax_tracker.sv, argmax_update.sv | reuse | signed first-max arithmetic unchanged |

Legacy modules may remain for regression/history, or be renamed/adapted with documented impact; do not gratuitously delete original source or break legacy tests by shared changes. Prefer new variants where shared interface incompatible. No unnecessary `gemm_engine` wrapper. Final new top can instantiate new variant module name with documented mapping. Existing main RTL file names are verified; proposed new paths below are recommendations, not already existing code.

## New files/modules (proposed organization)
```
04_rtl/
  npu_top.sv
  isa/  npu_isa_pkg.sv instruction_controller.sv instruction_decoder.sv
        register_file.sv csr_file.sv scalar_alu.sv perf_timer.sv
  controller/ dma_controller.sv gemm_controller.sv argmax_engine.sv
  memory/ dmem_port_mux.sv [adapted memory_wrapper or npu_memory_wrapper]
05_tb/npu/ tb_npu_top.sv external_imem.sv external_dmem.sv [unit smoke tests]
90_scripts/npu/ [Python toolchain, see 04]
06_fpga/constraints/npu_top_ooc.xdc
06_fpga/tcl/ [npu OOC build scripts]
```
Phase8 ISA files/assembler may be consulted for encoding, branch/pseudo implementation, cursor and tests, but must remove conflicting fault checking, old CSR map, old snapshots/monolithic IC and old timer LOAD-only count. Do not merge Phase8 or reintroduce timing path. Explicit new top file list, update sim targets and Tcl; avoid duplicate modules and exclude TB/model code from synthesis. `04_rtl/README.md`, `06_fpga/README.md`, `90_scripts` usage docs update with actual paths/commands. Main old synthesis reports are historical, not new PASS evidence.

## Model/tool audit
`03_model/generate_golden.py` uses LayerViewer/IntegerMLP, CPU trace, int8/32, known model formats and packing, outputs `golden.npz`, memory/expected HEX, manifest. Reuse arithmetic/quantization/model loading; split reusable pure functions, avoid reliance on legacy generated header timing/probes and sample IDs 0..9 restriction in `mlp_top_golden.py`. Existing `90_scripts/run.py`, `sim_targets.json` and `06_fpga/tcl/create_mlp_top_ooc_project.tcl` useful for XSim/Vivado environment; existing Tcl only creates OOC project, new scripts must actually execute synth/opt/place/route/report. Preflight inspect local checkpoint/dataset ignored files and run small existing reference check. Keep original checkpoint unchanged.
