// Independent signed INT8 ARGMAX; CSR snapshots are owned by Instruction Controller.
module argmax_engine(
    input logic clk,rst_n,start,
    input logic [31:0] config_words [0:1],
    output logic [7:0] config_error,
    output logic active,done,fault,
    output logic [7:0] error_code,
    output wire [3:0] result_index,
    output logic sram_en,
    output logic [31:0] sram_address,
    input logic [31:0] sram_rdata,
    input logic [7:0] sram_error
);
    import npu_isa_pkg::*;
    import npu_memory_pkg::*;
    typedef enum logic [2:0] {IDLE,READ,PROCESS,COMPLETE,FAILED} state_t;
    state_t state;
    logic [3:0] index;
    logic initialize,compare_en,bad_region;
    logic [63:0] words_full,bytes_full,end_full,buffer_limit,read_full;
    logic [7:0] runtime_error;
    // P6-D-02: extend BEFORE rounding/multiplication. Invalid lengths still check bounds.
    assign words_full=({32'd0,config_words[1]}+64'd3)>>2;
    assign bytes_full=words_full<<2;
    assign end_full={32'd0,config_words[0]}+bytes_full;
    assign buffer_limit={32'd0,bank_base(config_words[0][19:17])}+
                        bank_depth(config_words[0][19:17])*64'd4;
    assign bad_region=!(sram_region(config_words[0]) && config_words[0][19:17]<=1);
    always_comb begin
        config_error=ERR_OK;
        if(config_words[0][1:0]!=0) config_error=ERR_MISALIGNED;
        else if(bad_region) config_error=ERR_INVALID_REGION;
        else if({32'd0,config_words[0]}>=buffer_limit || end_full>buffer_limit)
            config_error=ERR_MEMORY_BOUNDS;
        else if(config_words[1]==0 || config_words[1]>10) config_error=ERR_INVALID_CONFIG;
    end
    assign active=(state==READ)||(state==PROCESS);
    assign done=(state==COMPLETE);
    assign fault=(state==FAILED);
    assign read_full={32'd0,config_words[0]}+({62'd0,index[3:2]}<<2);
    always_comb begin
        runtime_error=ERR_OK;
        if(active) begin
            if(config_error!=ERR_OK) runtime_error=config_error;
            else if({28'd0,index}>=config_words[1] || read_full+64'd4>buffer_limit)
                runtime_error=ERR_MEMORY_BOUNDS;
        end
    end
    assign sram_en=rst_n && state==READ && runtime_error==ERR_OK;
    assign sram_address=read_full[31:0];
    assign initialize=rst_n && state==PROCESS && runtime_error==ERR_OK && index==0;
    assign compare_en=rst_n && state==PROCESS && runtime_error==ERR_OK && index!=0;
    // RAM updates after request R; PROCESS consumes it at R+1 and then holds the word.
    argmax_unit u_compare(.clk(clk),.rst_n(rst_n),.word_data(sram_rdata),.class_index(index),
        .initialize(initialize),.compare_en(compare_en),.prediction(result_index));
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin state<=IDLE;index<=0;error_code<=ERR_OK;end
        else case(state)
            IDLE: if(start) begin
                index<=0;error_code<=config_error;
                if(config_error!=ERR_OK) state<=FAILED;
                else state<=READ;
            end
            READ: begin
                if(runtime_error!=ERR_OK || sram_error!=ERR_OK) begin
                    state<=FAILED;error_code<=(runtime_error!=ERR_OK)?runtime_error:sram_error;
                end else state<=PROCESS;
            end
            PROCESS: begin
                if(runtime_error!=ERR_OK) begin state<=FAILED;error_code<=runtime_error;end
                else if({28'd0,index}==config_words[1]-32'd1) state<=COMPLETE;
                else begin
                    index<=index+1'b1;
                    if(index[1:0]==3) state<=READ;
                end
            end
            // result_index includes the LAST comparison before done is consumed at the next edge.
            COMPLETE: state<=IDLE;
            FAILED: begin end
            default: begin state<=FAILED;error_code<=ERR_ILLEGAL_ENCODING;end
        endcase
    end
endmodule
