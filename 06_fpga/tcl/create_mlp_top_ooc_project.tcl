# Create a standalone Vivado project; do not launch synthesis or implementation.
# Source this file from a Vivado Tcl console with no project open.
# Original RTL/XDC files are referenced, not copied.

set mlp_ooc_script_dir [file dirname [file normalize [info script]]]
set mlp_ooc_root [file normalize [file join $mlp_ooc_script_dir ../..]]
set mlp_ooc_project_dir [file join $mlp_ooc_root 99_build vivado_mlp_top_ooc]
set mlp_ooc_xdc [file join $mlp_ooc_root 06_fpga constraints mlp_top_ooc.xdc]

# Keep the package first and restrict this project to the actual RTL hierarchy.
# TBs, behavioral models and mlp_top_tb_data.vh are not synthesis inputs.
set mlp_ooc_relative_sources {
    04_rtl/controller/control_state_pkg.sv
    04_rtl/controller/control_unit.sv
    04_rtl/controller/layer_config_lut.sv
    04_rtl/controller/control_fsm.sv
    04_rtl/controller/mlp_counters.sv
    04_rtl/controller/counter_en.sv
    04_rtl/controller/address_generator.sv
    04_rtl/controller/pipeline_control.sv
    04_rtl/controller/read_issue_control.sv
    04_rtl/controller/pipeline_event_control.sv
    04_rtl/controller/argmax_control.sv
    04_rtl/controller/argmax_schedule.sv
    04_rtl/controller/argmax_unit.sv
    04_rtl/controller/byte_select4.sv
    04_rtl/controller/signed_compare8.sv
    04_rtl/controller/argmax_tracker.sv
    04_rtl/controller/argmax_update.sv
    04_rtl/controller/control_read_mux.sv
    04_rtl/common/delay_line.sv
    04_rtl/common/register_en.sv
    04_rtl/controller/mlp_top.sv
    04_rtl/controller/unpack_int8x4.sv
    04_rtl/memory/memory_wrapper.sv
    04_rtl/memory/tb_address_decoder.sv
    04_rtl/memory/buffer_router.sv
    04_rtl/memory/memory_port_mux.sv
    04_rtl/memory/single_port_bram.sv
    04_rtl/memory/tb_read_mux.sv
    04_rtl/mac_array/mac_array.sv
    04_rtl/mac_array/dot_product4.sv
    04_rtl/mac_array/signed_multiplier8.sv
    04_rtl/mac_array/adder_tree4.sv
    04_rtl/common/signed_adder32.sv
    04_rtl/accumulator_postprocess/accumulator_postprocess.sv
    04_rtl/accumulator_postprocess/accumulator_lane.sv
    04_rtl/accumulator_postprocess/bias_align.sv
    04_rtl/accumulator_postprocess/sign_extend8_to32.sv
    04_rtl/accumulator_postprocess/signed_shifter32.sv
    04_rtl/accumulator_postprocess/accumulator32.sv
    04_rtl/accumulator_postprocess/accumulator_update.sv
    04_rtl/accumulator_postprocess/postprocess_lane.sv
    04_rtl/accumulator_postprocess/relu32.sv
    04_rtl/accumulator_postprocess/arithmetic_rshift32.sv
    04_rtl/accumulator_postprocess/saturate32_to8.sv
    04_rtl/accumulator_postprocess/pack_int8x4.sv
}

# Refuse to overwrite a previous project or change an already open project.
if {[llength [get_projects -quiet]] != 0} {
    error "Close the current project before creating the mlp_top OOC project."
}
if {[file exists $mlp_ooc_project_dir]} {
    error "Project directory already exists: $mlp_ooc_project_dir. Open the existing .xpr instead."
}
set mlp_ooc_sources [list]
foreach mlp_ooc_relative_file $mlp_ooc_relative_sources {
    set mlp_ooc_source [file join $mlp_ooc_root $mlp_ooc_relative_file]
    if {![file isfile $mlp_ooc_source]} {
        error "Missing RTL source: $mlp_ooc_source"
    }
    lappend mlp_ooc_sources $mlp_ooc_source
}
if {![file isfile $mlp_ooc_xdc]} {
    error "Missing clock constraints: $mlp_ooc_xdc"
}

create_project mlp_top_ooc $mlp_ooc_project_dir -part xc7a100tcsg324-1
set_property target_language Verilog [current_project]
add_files -norecurse $mlp_ooc_sources
set_property top mlp_top [get_filesets sources_1]
add_files -fileset constrs_1 -norecurse $mlp_ooc_xdc
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} \
    -value {-mode out_of_context} -objects [get_runs synth_1]
update_compile_order -fileset sources_1

puts "Created project: [file join $mlp_ooc_project_dir mlp_top_ooc.xpr]"
puts "Top: mlp_top; part: xc7a100tcsg324-1; synthesis: out_of_context."
puts "Clock: core_clk, 100 MHz / 10 ns. Boundary timing remains unspecified."
puts "Setup only: synthesis, implementation, simulation and bitstream generation have not started."
