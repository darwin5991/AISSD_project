# Approved OOC implementation from the reviewed synthesis checkpoint, no RTL edits.
if {[llength $argv]!=2} {error "Usage: synthesized.dcp report_dir"}
lassign $argv checkpoint report_dir
file mkdir $report_dir
set_param general.maxThreads 2
open_checkpoint $checkpoint
set stage_log [open [file join $report_dir stages.txt] w]
foreach stage {opt_design place_design phys_opt_design route_design} {
    puts $stage_log "$stage START"
    flush $stage_log
    $stage
    puts $stage_log "$stage COMPLETED"
    flush $stage_log
}
close $stage_log
write_checkpoint -force [file join $report_dir routed.dcp]
report_route_status -file [file join $report_dir route_status.rpt]
report_utilization -file [file join $report_dir utilization.rpt]
report_utilization -hierarchical -file [file join $report_dir utilization_hierarchical.rpt]
report_ram_utilization -file [file join $report_dir ram_utilization.rpt]
report_clocks -file [file join $report_dir clocks.rpt]
report_clock_utilization -file [file join $report_dir clock_utilization.rpt]
check_timing -verbose -file [file join $report_dir check_timing.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $report_dir timing_summary.rpt]
report_exceptions -file [file join $report_dir exceptions.rpt]
report_methodology -file [file join $report_dir methodology.rpt]
report_drc -file [file join $report_dir drc.rpt]
set regs [all_registers -clock [get_clocks npu_clk]]
report_timing -from $regs -to $regs -delay_type max -max_paths 10 -input_pins -file [file join $report_dir internal_setup_paths.rpt]
report_timing -from $regs -to $regs -delay_type min -max_paths 10 -input_pins -file [file join $report_dir internal_hold_paths.rpt]
set summary [open [file join $report_dir implementation_status.txt] w]
puts $summary "status=ROUTED"
puts $summary "clock_period_ns=[get_property PERIOD [get_clocks npu_clk]]"
foreach {kind delay} {setup max hold min} {
    set p [get_timing_paths -from $regs -to $regs -delay_type $delay -max_paths 1]
    if {[llength $p]!=1} {error "No internal $kind timing path"}
    puts $summary [format "%s_slack_ns=%s" $kind [get_property SLACK $p]]
    puts $summary [format "%s_startpoint=%s" $kind [get_property STARTPOINT_PIN $p]]
    puts $summary [format "%s_endpoint=%s" $kind [get_property ENDPOINT_PIN $p]]
    set pf [open [file join $report_dir [format "%s_path_properties.txt" $kind]] w]
    foreach key [list_property $p] {puts $pf "$key=[get_property $key $p]"}
    close $pf
}
puts $summary "boundary_timing_verified=false"
puts $summary "bitstream_generated=false"
puts $summary "timing_exceptions_added=false"
close $summary
puts "PHASE8_IMPLEMENTATION_COMPLETE $report_dir"
close_project
