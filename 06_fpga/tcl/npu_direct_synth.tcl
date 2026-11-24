# Phase 8: unchanged RTL, in-memory OOC synthesis. Never opens the Legacy project.
if {[llength $argv] != 4} { error "Usage: sources.txt constraints.xdc report_dir top" }
lassign $argv source_file xdc report_dir top
file mkdir $report_dir
set_param general.maxThreads 2
create_project -in_memory -part xc7a100tcsg324-1
set fh [open $source_file r]
set sources [split [string trim [read $fh]] "\n"]
close $fh
foreach source $sources {
    if {![file isfile $source] || [file extension $source] ne ".sv"} { error "Invalid synthesis source: $source" }
    if {[string match "*/05_tb/*" $source]} { error "Testbench excluded from synthesis" }
}
read_verilog -sv $sources
read_xdc $xdc
synth_design -top $top -part xc7a100tcsg324-1 -mode out_of_context
write_checkpoint -force [file join $report_dir synthesized.dcp]
write_verilog -force -mode funcsim [file join $report_dir synthesized_funcsim.v]
report_utilization -file [file join $report_dir utilization.rpt]
report_utilization -hierarchical -file [file join $report_dir utilization_hierarchical.rpt]
report_ram_utilization -file [file join $report_dir ram_utilization.rpt]
report_clocks -file [file join $report_dir clocks.rpt]
check_timing -verbose -file [file join $report_dir check_timing.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -max_paths 10 -file [file join $report_dir timing_summary.rpt]
report_drc -file [file join $report_dir drc.rpt]
set regs [all_registers -clock [get_clocks npu_clk]]
report_timing -from $regs -to $regs -delay_type max -max_paths 10 -input_pins -file [file join $report_dir internal_setup_paths.rpt]
report_timing -from $regs -to $regs -delay_type min -max_paths 10 -input_pins -file [file join $report_dir internal_hold_paths.rpt]
set cells [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]
for {set b 0} {$b<7} {incr b} {
    set r36($b) 0
    set r18($b) 0
    set ff($b) 0
    set lr($b) 0
}
set total36 0
set total18 0
set totalff 0
set totallr 0
set totaldsp 0
set detail [open [file join $report_dir bram_cells.tsv] w]
puts $detail "cell\tprimitive\tproperties"
foreach c $cells {
    set ref [get_property REF_NAME $c]
    set name [get_property NAME $c]
    set is36 [expr {$ref eq "RAMB36E1"}]
    set is18 [expr {$ref eq "RAMB18E1"}]
    set isff [string match FD* $ref]
    set islr [expr {[string match RAM* $ref] && !$is36 && !$is18}]
    incr total36 $is36
    incr total18 $is18
    incr totalff $isff
    incr totallr $islr
    if {[string match DSP* $ref]} { incr totaldsp }
    if {[regexp {g_banks\[([0-6])\]} $name unused bank]} {
        incr r36($bank) $is36
        incr r18($bank) $is18
        incr ff($bank) $isff
        incr lr($bank) $islr
    }
    if {$is36 || $is18} {
        set properties {}
        set available [list_property $c]
        foreach key {READ_WIDTH_A READ_WIDTH_B WRITE_WIDTH_A WRITE_WIDTH_B DOA_REG DOB_REG WRITE_MODE_A WRITE_MODE_B SRVAL_A SRVAL_B} {
            if {[lsearch -exact $available $key]>=0} { lappend properties "$key=[get_property $key $c]" }
        }
        puts $detail "$name\t$ref\t[join $properties ,]"
    }
}
close $detail
set table [open [file join $report_dir banks.tsv] w]
puts $table "bank\tdepth\twidth\tramb36\tramb18\tff\tlutram"
set depths {196 128 29280 29280 29280 29280 163}
for {set b 0} {$b<7} {incr b} {
    puts $table "$b\t[lindex $depths $b]\t32\t$r36($b)\t$r18($b)\t$ff($b)\t$lr($b)"
}
close $table
set summary [open [file join $report_dir synthesis_status.txt] w]
puts $summary "status=COMPLETED"
puts $summary "top=$top"
puts $summary "part=xc7a100tcsg324-1"
puts $summary "clock_period_ns=[get_property PERIOD [get_clocks npu_clk]]"
puts $summary "ramb36=$total36"
puts $summary "ramb18=$total18"
puts $summary "ff=$totalff"
puts $summary "lutram=$totallr"
puts $summary "dsp=$totaldsp"
puts $summary "boundary_timing_verified=false"
puts $summary "implementation_executed=false"
close $summary
puts "PHASE8_SYNTHESIS_COMPLETE $report_dir"
close_project
