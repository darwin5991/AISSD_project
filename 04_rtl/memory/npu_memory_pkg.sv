package npu_memory_pkg;
    import npu_isa_pkg::*;
    localparam logic [1:0] OWNER_NONE=0, OWNER_XFER=1, OWNER_GEMM=2, OWNER_ARGMAX=3;
    function automatic integer bank_depth(input logic [2:0] bank);
        case(bank)
            0: bank_depth=196;
            1: bank_depth=128;
            2,3,4,5: bank_depth=29280;
            6: bank_depth=163;
            default: bank_depth=0;
        endcase
    endfunction
    function automatic logic [31:0] bank_base(input logic [2:0] bank);
        bank_base=32'h8000_0000+({29'd0,bank}<<17);
    endfunction
    function automatic logic sram_region(input logic [31:0] addr);
        sram_region=(addr[31:20]==12'h800)&&(addr[19:17]<7);
    endfunction
    function automatic logic [7:0] sram_range_error(
        input logic [31:0] addr, input logic [31:0] length_bytes);
        logic [32:0] last_exclusive,limit;
        begin
            last_exclusive={1'b0,addr}+{1'b0,length_bytes};
            limit={1'b0,bank_base(addr[19:17])}+bank_depth(addr[19:17])*4;
            if(addr[1:0]!=0 || length_bytes[1:0]!=0)
                sram_range_error=ERR_MISALIGNED;
            else if(!sram_region(addr))
                sram_range_error=ERR_INVALID_REGION;
            else if(last_exclusive[32] ||
                    {1'b0,addr}>=limit || last_exclusive>limit)
                sram_range_error=ERR_MEMORY_BOUNDS;
            else if(length_bytes==0)
                sram_range_error=ERR_INVALID_CONFIG;
            else sram_range_error=ERR_OK;
        end
    endfunction
    // Approved DMEM logical region: top nibble 1; capacity is elaboration-defined.
    function automatic logic [7:0] transfer_error(
        input logic [31:0] src,dst,length_bytes,input logic store_mode,
        input logic [32:0] dmem_bytes);
        logic [31:0] ext_addr,int_addr;
        logic [32:0] ext_end,int_end,ext_limit,int_limit;
        begin
            ext_addr=store_mode?dst:src;int_addr=store_mode?src:dst;
            ext_end={1'b0,ext_addr}+{1'b0,length_bytes};
            int_end={1'b0,int_addr}+{1'b0,length_bytes};
            ext_limit={1'b0,DMEM_BASE}+dmem_bytes;
            int_limit={1'b0,bank_base(int_addr[19:17])}+bank_depth(int_addr[19:17])*4;
            if(src[1:0]!=0 || dst[1:0]!=0 || length_bytes[1:0]!=0)
                transfer_error=ERR_MISALIGNED;
            else if(ext_addr[31:28]!=4'h1 || !sram_region(int_addr))
                transfer_error=ERR_INVALID_REGION;
            else if(ext_end[32] || int_end[32] ||
                    {1'b0,ext_addr}>=ext_limit || ext_end>ext_limit ||
                    ext_end>33'h02000_0000 ||
                    {1'b0,int_addr}>=int_limit || int_end>int_limit)
                transfer_error=ERR_MEMORY_BOUNDS;
            else if(length_bytes==0) transfer_error=ERR_INVALID_CONFIG;
            else transfer_error=ERR_OK;
        end
    endfunction
endpackage
