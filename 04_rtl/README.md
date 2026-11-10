# RTL hierarchy

mac_array now contains a signed INT8 input/weight register stage before its
existing product and partial-sum stages. MAC data and valid both use three stages.
Control metadata is aligned to result capture at R+5 and output write at R+6.
Verification sources and five generated headers/data sets have been updated.
Generation checks passed; unit tests, new RTL simulation and implementation have
not been run. See [the revision contract](../00_docs/mac_input_pipeline.md).

## Directories

- mac_array/: MAC, dot product, multiplier and adder tree.
- accumulator_postprocess/: accumulator, bias alignment, ReLU, shift, saturation.
- memory/: RAM, memory access routing and TB access.
- controller/: Control unit, ARGMAX and mlp_top.
- common/: shared register_en, delay_line and signed_adder32.

Module-specific helpers live with their owning major module. Only helpers shared
across major modules remain in common/.

## RTL hierarchy after the revision (not yet verified)

```text
mlp_top
  memory_wrapper
    tb_address_decoder, buffer_router, memory_port_mux x7, tb_read_mux
    single_port_bram x7 (A, B, weight banks 0..3, bias)
  mac_array
    register_en: INT8 input registers x4 and weight registers x16
    dot_product4 x4
      signed_multiplier8 x4
      register_en x4 (product)
      adder_tree4 -> signed_adder32 x3
      register_en (partial sum)
    delay_line (common valid, depth 3)
  accumulator_postprocess
    accumulator_lane x4
      bias_align -> sign_extend8_to32, signed_shifter32
      accumulator32 -> signed_adder32, accumulator_update, register_en
      register_en (result)
      postprocess_lane -> relu32, arithmetic_rshift32, saturate32_to8
    pack_int8x4
  control_unit
    layer_config_lut, control_fsm, mlp_counters, address_generator
    pipeline_control -> read_issue_control, delay_line, pipeline_event_control
    argmax_control -> counter_en, argmax_schedule
    argmax_unit -> byte_select4, signed_compare8, argmax_tracker
    control_read_mux
```

The MAC input registers belong inside mac_array; Top's unpack_int8x4 instances
remain combinational wiring. Each adder tree retains two combinational addition
levels with registers before and after the tree and none between the levels.
MAC data and valid advance every clock, including invalid bubbles. The new input
and weight registers follow the existing asynchronous active-low zero reset.

Memory read latency remains one clock. mac_input_valid remains read-enable delayed
by one clock. For the last read at R, accumulation is R+4, result capture R+5,
output write R+6. The next group's bias load coincides with result capture; the
first bias load of each layer remains one clock after its first bias read.
Read cadence and the one-cycle inter-group gap remain unchanged. Control metadata,
output address, layer completion and DRAIN completion must be updated together.

## Existing implementation and evidence

All major RTL modules were implemented and passed functional verification with
the previous two-stage MAC, including full real-RTL Top samples 0..9. Those results
remain evidence for the old structure. The OOC synthesis passed; post-route timing
at 100 MHz failed setup (WNS -0.058 ns, four failing endpoints). See
[the implementation record](../07_runs/mlp_top_ooc_impl_20261109_185811_178681Z/README.md).
New-stage RTL has been edited and data generation checks passed. No unit tests,
new-stage RTL simulation, synthesis or timing run have been performed. Existing
run summaries and source snapshots are preserved.

Compile controller/control_state_pkg.sv before the other SystemVerilog files.
The current simulation source lists are in ../90_scripts/sim_targets.json. They
have been updated for the new data lengths and delays. New headers are available;
RTL edits still require separately authorized tests and simulation. The runner
rejects old headers instead of reusing previous data silently.
