# mlp_top OOC timing target: 100 MHz (10 ns).
# Ports remain logical block interfaces; no package pins or I/O standards.
create_clock -name core_clk -period 10.000 [get_ports clk]

# Boundary timing is deliberately not specified in this first evaluation.
# Do not assume zero input/output delay or hide boundary paths with false paths.
# Input/output timing and asynchronous reset release require separate conditions.
# A timing summary is not evidence of complete interface timing closure.
