# NPU internal OOC target, explicitly approved: 100 MHz.
create_clock -name npu_clk -period 10.000 [get_ports clk]
# Board locations, I/O delays and clock source placement are unspecified.
# No invented package pins, virtual-I/O delays, false paths or multicycle paths.
# Missing boundary constraints remain visible in check_timing and timing reports.
