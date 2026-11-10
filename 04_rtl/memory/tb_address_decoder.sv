////////////////////////////////////////////////////////////////////////////////
// Design Name : MLP end-to-end accelerator
// Module Name : tb_address_decoder
// Description : Decode aligned TB byte address into memory selection and word address.
// Status      : combinational address decode implemented; RTL verification pending
// Reference   : project/00_docs/architecture.md
////////////////////////////////////////////////////////////////////////////////
// Memory selectors 0..6: A, B, weight0..3, bias. Selector 7 is unused.
// Only legal, aligned addresses are supported by the current contract.
// Unsupported regions, alignment and depth violations have no defined policy.

module tb_address_decoder (
    input  logic                tb_en,
    input  logic        [19:0]  tb_addr,

    output logic        [2:0]   memory_select,
    output logic        [14:0]  word_addr,
    output logic        [6:0]   memory_en
);

assign memory_select = tb_addr[19:17];
assign word_addr = tb_addr[16:2];
assign memory_en = tb_en ? (7'b0000001 << memory_select) : 7'd0;

endmodule
