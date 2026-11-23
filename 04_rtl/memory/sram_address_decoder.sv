module sram_address_decoder (
    input logic [31:0] address,
    output logic [2:0] bank,
    output logic [14:0] word_address,
    output logic [7:0] error_code
);
    assign bank=address[19:17];
    assign word_address=address[16:2];
    assign error_code=npu_memory_pkg::sram_range_error(address,32'd4);
endmodule
