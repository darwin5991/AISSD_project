# RTL hierarchy

## Directories

```text
04_rtl/
  mac_array/                 # MAC, dot product, multiplier and adder tree
  accumulator_postprocess/   # accumulator, bias alignment, ReLU, shift, saturation
  memory/                    # RAM, memory access routing and TB access
  controller/                # Control unit, ARGMAX and mlp_top
  common/                    # shared register_en, delay_line and signed_adder32
```

Module-specific helpers live with their owning major module. Only helpers used
across multiple major modules remain in common/.

Status: Control unit scheduling, counters, address generation and signed ARGMAX
are implemented, together with shared register_en and delay_line. The existing
MNIST sample-0 Control golden test passes in xsim. Memory internals are implemented
and pass standalone xsim (265,015 vectors, 1,708,021 comparisons, zero errors).
MAC arithmetic and shared signed_adder32 are implemented; standalone MAC xsim
passes 265,017 vectors and 1,325,085 comparisons with zero masked checks or errors.
Accumulator/postprocess internals remain pending. Real Top + Control + Memory
with behavioral MAC/accumulator models passes sample-0 xsim (913,467 comparisons,
prediction 7). The subsequent Top run with real MAC also passes with the same
comparison count and prediction; only accumulator/postprocess remains modeled.
Whole-Top functionality using only real RTL is pending.
Top-level ports and the architecture's data/control pipeline stages are unchanged.

```text
mlp_top
  memory_wrapper
    tb_address_decoder
    buffer_router
    memory_port_mux x7
    single_port_bram x7 (A, B, weight banks 0..3, bias)
    tb_read_mux
  mac_array
    dot_product4 x4
      signed_multiplier8 x4
      register_en x4 (product)
      adder_tree4 -> signed_adder32 x3
      register_en (partial sum)
    delay_line (common valid, depth 2)
  accumulator_postprocess
    accumulator_lane x4
      bias_align -> sign_extend8_to32, signed_shifter32
      accumulator32 -> signed_adder32, accumulator_update, register_en
      register_en (result)
      postprocess_lane -> relu32, arithmetic_rshift32, saturate32_to8
    pack_int8x4
  control_unit
    layer_config_lut
    control_fsm
    mlp_counters -> counter_en x3
    address_generator
    pipeline_control
      read_issue_control
      delay_line (read/event/address alignment)
      pipeline_event_control
    argmax_control -> counter_en, argmax_schedule
    argmax_unit
      byte_select4
      signed_compare8
      argmax_tracker -> argmax_update, register_en
    control_read_mux
```

Top also instantiates unpack_int8x4 for input, bias and the four weight words.
Only Control unit and its scheduling children choose when operations happen.
Arithmetic leaves receive data/settings; storage leaves receive explicit enables.
No additional data pipeline stages are introduced by splitting modules.

The original architecture is specified in ../00_docs/architecture.md.
Control uses the 3-bit state definitions in controller/control_state_pkg.sv.
Unused states block memory/control events and recover to IDLE. Memory access
routing, storage and read selection pass the standalone golden test.
Accumulator/postprocess arithmetic leaves, full real-RTL integration and
synthesis/timing verification are pending. Actual BRAM inference and mapping
have not been checked.

All source files: mac_array/*.sv, accumulator_postprocess/*.sv, memory/*.sv,
controller/*.sv, common/*.sv.
Compile controller/control_state_pkg.sv before other SystemVerilog files.
The common runner's Control and Top source lists enforce this order. Control
verification: python project/90_scripts/run.py control_unit. No RAM IP or vendor
simulation library is required by the current source hierarchy.

Top with models: `python project/90_scripts/run.py mlp_top`.
Generate its data separately with `03_model/golden/mlp_top_golden.py --source-run <run>`.
The Top source list now selects real Top/Control, Memory and MAC, including their
helpers and shared signed_adder32. Only accumulator/postprocess uses a model from
`05_tb/*/models/`; Memory and MAC models are excluded. Top RTL needs no simulation
branches. This configuration passes compilation, elaboration and xsim in
`07_runs/mlp_top_xsim_20261109_144425_513778Z/`: 265,015 vectors, 913,467 comparisons,
1,206,653 masked checks, zero errors and prediction 7 at 2,650,180 ns. The runner's
12 tests also pass. modeled_modules lists only accumulator_postprocess and
rtl_verified stays false.
See ../00_docs/verification/mlp_top.md for scope, masks and initialization/readback.

Standalone Memory uses `python project/90_scripts/run.py memory_wrapper` with the
existing generated data. The earlier skeleton run compiled/elaborated and then
failed at vector 0 (40 ns, in_data=X). That result remains FAIL. After implementing
the Memory leaves, run `07_runs/memory_wrapper_xsim_20261109_103936_500210Z/` passes
265,015/265,015 vectors and 1,708,021 comparisons with zero errors at 2,650,180 ns.
No golden expectations were changed. Top integration using real Memory and Control
passes in `07_runs/mlp_top_xsim_20261109_104742_239167Z/`: 265,015/265,015 vectors,
913,467 comparisons, zero errors, prediction 7 at 2,650,180 ns. MAC/accumulator
were modeled in that run, so that result keeps rtl_verified=false. Full real-RTL integration
and synthesis/timing verification are pending.
