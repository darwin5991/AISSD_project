// Eight physical registers. The decoder validates five-bit ISA register numbers.
module register_file (
    input logic clk, rst_n,
    input logic [2:0] rs1_addr, rs2_addr,
    output logic [31:0] rs1_data, rs2_data,
    input logic write_en,
    input logic [2:0] write_addr,
    input logic [31:0] write_data
);
    logic [31:0] registers [0:7];
    assign rs1_data = (rs1_addr == 0) ? 32'd0 : registers[rs1_addr];
    assign rs2_data = (rs2_addr == 0) ? 32'd0 : registers[rs2_addr];
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (integer i = 0; i < 8; i = i + 1)
                registers[i] <= 32'd0;
        end else if (write_en && (write_addr != 0))
            registers[write_addr] <= write_data;
    end
endmodule
