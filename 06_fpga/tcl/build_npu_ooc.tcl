# argv: repository, unique run directory, synth|implement|power
set root [lindex $argv 0]
set out [lindex $argv 1]
set stage [lindex $argv 2]
set part xc7a100tcsg324-1
set_param general.maxThreads 6
proc reports {out prefix} {
    report_utilization -hierarchical -file $out/${prefix}_utilization_hier.rpt
    report_utilization -file $out/${prefix}_utilization.rpt
    report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file $out/${prefix}_timing_summary.rpt
    report_timing -delay_type max -max_paths 20 -sort_by group -file $out/${prefix}_critical_setup.rpt
    report_timing -delay_type min -max_paths 20 -sort_by group -file $out/${prefix}_critical_hold.rpt
    report_drc -file $out/${prefix}_drc.rpt
    check_timing -verbose -file $out/${prefix}_check_timing.rpt
    report_clocks -file $out/${prefix}_clocks.rpt
}
if {$stage eq "synth"} {
    set f [open $out/sources.txt r]
    foreach src [split [read $f] "\n"] {
        if {[string trim $src] ne ""} {read_verilog -sv [string trim $src]}
    }
    close $f
    read_xdc $root/06_fpga/constraints/npu_top_ooc.xdc
    synth_design -top npu_top -part $part -mode out_of_context -flatten_hierarchy rebuilt
    write_checkpoint $out/synth.dcp
    reports $out synth
    puts "NPU_SYNTH_COMPLETE"
} elseif {$stage eq "implement"} {
    open_checkpoint $out/synth.dcp
    opt_design
    place_design
    phys_opt_design
    route_design
    write_checkpoint $out/routed.dcp
    reports $out routed
    report_route_status -file $out/routed_route_status.rpt
    set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
    set whs [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
    set setup_bad [llength [get_timing_paths -delay_type max -slack_lesser_than 0 -max_paths 100000]]
    set hold_bad [llength [get_timing_paths -delay_type min -slack_lesser_than 0 -max_paths 100000]]
    set f [open $out/routed_gate.json w]
    puts $f "{\"wns_ns\":$wns,\"whs_ns\":$whs,\"setup_bad_paths\":$setup_bad,\"hold_bad_paths\":$hold_bad}"
    close $f
    if {$wns < 0 || $whs < 0 || $setup_bad != 0 || $hold_bad != 0} {error "NPU post-route timing gate failed"}
    puts "NPU_ROUTE_TIMING_COMPLETE"
} elseif {$stage eq "power"} {
    if {![file exists $out/functional_and_route_pass.json]} {error "functional/routed gate evidence required before power"}
    open_checkpoint $out/routed.dcp
    report_power -file $out/routed_power.rpt
    puts "NPU_POWER_COMPLETE"
} else {error "unknown stage"}
exit
