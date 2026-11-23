// Seven unchanged single_port_bram leaves. Owner muxes never register read data.
module npu_memory_wrapper (
    input logic clk,rst_n,
    input logic [1:0] owner,
    input logic xfer_en,xfer_we,
    input logic [31:0] xfer_address,xfer_wdata,
    output logic [31:0] xfer_rdata,
    output logic [7:0] xfer_error,
    // Trusted, prevalidated physical word ports for a future GEMM controller.
    input logic [6:0] gemm_en,gemm_we,
    input logic [14:0] gemm_address [0:6],
    input logic [31:0] gemm_wdata [0:6],
    output wire [31:0] gemm_rdata [0:6],
    input logic argmax_en,
    input logic [31:0] argmax_address,
    output logic [31:0] argmax_rdata,
    output logic [7:0] argmax_error
);
    import npu_memory_pkg::*;
    import npu_isa_pkg::*;
    logic [2:0] xfer_bank,arg_bank,xfer_read_bank,arg_read_bank;
    logic [14:0] xfer_word,arg_word;
    logic [7:0] xfer_decode_error,arg_decode_error;
    wire [31:0] ram_rdata [0:6];
    wire [6:0] ram_en,ram_we;
    wire [14:0] ram_addr [0:6];
    wire [31:0] ram_wdata [0:6];
    sram_address_decoder u_xfer_decode(
        .address(xfer_address),.bank(xfer_bank),.word_address(xfer_word),.error_code(xfer_decode_error));
    sram_address_decoder u_arg_decode(
        .address(argmax_address),.bank(arg_bank),.word_address(arg_word),.error_code(arg_decode_error));
    assign xfer_error=(owner==OWNER_XFER && xfer_en)?xfer_decode_error:ERR_OK;
    assign argmax_error=(owner==OWNER_ARGMAX && argmax_en)?arg_decode_error:ERR_OK;
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin xfer_read_bank<=0;arg_read_bank<=0;end
        else begin
            if(owner==OWNER_XFER && xfer_en && !xfer_we && xfer_decode_error==ERR_OK)
                xfer_read_bank<=xfer_bank;
            if(owner==OWNER_ARGMAX && argmax_en && arg_decode_error==ERR_OK)
                arg_read_bank<=arg_bank;
        end
    end
    assign xfer_rdata=ram_rdata[xfer_read_bank];
    assign argmax_rdata=ram_rdata[arg_read_bank];
    for(genvar b=0;b<7;b++) begin:g_banks
        sram_port_mux u_mux(
            .owner(owner),.xfer_en(xfer_en && xfer_bank==b && xfer_decode_error==ERR_OK),
            .xfer_we(xfer_we),.xfer_addr(xfer_word),.xfer_wdata(xfer_wdata),
            .gemm_en(gemm_en[b]),.gemm_we(gemm_we[b]),.gemm_addr(gemm_address[b]),.gemm_wdata(gemm_wdata[b]),
            .argmax_en(argmax_en && arg_bank==b && arg_decode_error==ERR_OK),.argmax_addr(arg_word),
            .ram_en(ram_en[b]),.ram_we(ram_we[b]),.ram_addr(ram_addr[b]),.ram_wdata(ram_wdata[b]));
        localparam integer AW=(b==0 || b==6)?8:(b==1?7:15);
        single_port_bram #(.DEPTH(bank_depth(b)),.ADDR_WIDTH(AW),.RAM_DECOMP((b>=2 && b<=5)?"area":"auto")) u_ram(
            .clk(clk),.rst_n(rst_n),.en(ram_en[b]),.we(ram_we[b]),
            .addr(ram_addr[b][AW-1:0]),.wdata(ram_wdata[b]),.rdata(ram_rdata[b]));
        assign gemm_rdata[b]=ram_rdata[b];
    end
endmodule
