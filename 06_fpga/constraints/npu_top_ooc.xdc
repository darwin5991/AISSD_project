# OOC internal 100 MHz only. No board pins or external memory/IO timing claim.
create_clock -name npu_clk -period 10.000 [get_ports clk]
